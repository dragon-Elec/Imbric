@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import org.gnome.gio.Gio
import org.junit.jupiter.api.BeforeAll
import org.junit.jupiter.api.Test
import kotlin.system.measureTimeMillis
import kotlin.test.assertTrue
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class GioListingBenchmark {
    companion object {
        @JvmStatic
        @BeforeAll
        fun setup() {
            Gio.`javagi$ensureInitialized`()
        }
    }

    private suspend fun <T> awaitGioAsyncDirect(
        block: (cancellable: org.gnome.gio.Cancellable, callback: org.gnome.gio.AsyncReadyCallback) -> Unit,
        finish: (result: org.gnome.gio.AsyncResult) -> T
    ): T = kotlinx.coroutines.suspendCancellableCoroutine { cont ->
        val cancellable = org.gnome.gio.Cancellable()
        val callback = org.gnome.gio.AsyncReadyCallback { _, res, _ ->
            if (cont.isActive) {
                try {
                    cont.resume(finish(res))
                } catch (e: Exception) {
                    cont.resumeWithException(e)
                }
            }
        }
        
        try {
            block(cancellable, callback)
        } catch (e: Exception) {
            cont.resumeWithException(e)
        }
        
        cont.invokeOnCancellation {
            cancellable.cancel()
        }
    }

    @Test
    fun benchmarkListDirectories() = runBlocking {
        val backend = GioBackend()
        val targets = listOf(
            "file:///home/ray/Downloads",
            "file:///home/ray/Pictures/Screenshots",
            "file:///home/ray/Downloads/Sidebery"
        )

        println("\n=== KOTLIN ASYNC BENCHMARK REPORT ===")
        TestUtils.withGlibPump {
            for (target in targets) {
                // Warmup run (Ignored)
                var count = 0
                val warmupTime = measureTimeMillis {
                    count = backend.list(target).toList().size
                }
                println("[$target] Warmup Run: $warmupTime ms")

                val times = mutableListOf<Long>()
                for (i in 1..5) {
                    // Garbage collect to ensure clean state
                    System.gc()
                    kotlinx.coroutines.delay(100)

                    val time = measureTimeMillis {
                        val items = backend.list(target).toList()
                        count = items.size
                    }
                    times.add(time)
                    println("[$target] Run $i: $time ms")
                }

                val avg = times.average()
                println("$target:")
                println("  Runs: ${times.map { "${it}ms" }}")
                println("  Average: ${String.format("%.2f", avg)} ms (Item count: $count)")
            }
        }
        println("=====================================\n")
        assertTrue(true)
    }

    @Test
    fun benchmarkAsyncDirectListDirectories() = runBlocking {
        val targets = listOf(
            "file:///home/ray/Downloads",
            "file:///home/ray/Pictures/Screenshots",
            "file:///home/ray/Downloads/Sidebery"
        )

        println("\n=== KOTLIN ASYNC DIRECT BENCHMARK REPORT ===")
        val queryAttributes = "standard::name,standard::type,standard::is-hidden,standard::size,standard::content-type,standard::is-symlink,access::can-execute"
        val LISTING_SENTINEL_UUID = kotlin.uuid.Uuid.fromLongs(0, 0)
        val batchSizes = intArrayOf(75, 100, 300, 500)

        TestUtils.withGlibPump {
            for (target in targets) {
                val gfile = org.gnome.gio.File.newForUri(target)
                val parentUri = target.trimEnd('/')
                val parentPath = gfile.path?.toString()?.trimEnd('/')
                    ?: GioTypeMappers.localPathFromFileUri(parentUri)

                // Warmup
                var count = 0
                val warmupTime = measureTimeMillis {
                    val enumerator = awaitGioAsyncDirect<org.gnome.gio.FileEnumerator>(
                        block = { cancellable, callback ->
                            gfile.enumerateChildrenAsync(queryAttributes, org.gnome.gio.FileQueryInfoFlags.NONE, org.gnome.glib.GLib.PRIORITY_DEFAULT, cancellable, callback)
                        },
                        finish = { result ->
                            gfile.enumerateChildrenFinish(result)
                        }
                    )
                    try {
                        while (true) {
                            val batch = awaitGioAsyncDirect<org.gnome.glib.List<org.gnome.gio.FileInfo>>(
                                block = { cancellable, callback ->
                                    enumerator.nextFilesAsync(100, org.gnome.glib.GLib.PRIORITY_DEFAULT, cancellable, callback)
                                },
                                finish = { result ->
                                    enumerator.nextFilesFinish(result)
                                }
                            )
                            if (batch == null || batch.isEmpty()) break
                            count += batch.size
                        }
                    } finally {
                        enumerator.close(null)
                    }
                }
                println("[$target] Warmup Run: $warmupTime ms")

                val times = mutableListOf<Long>()
                for (i in 1..5) {
                    System.gc()
                    kotlinx.coroutines.delay(100)

                    val time = measureTimeMillis {
                        count = 0
                        val enumerator = awaitGioAsyncDirect<org.gnome.gio.FileEnumerator>(
                            block = { cancellable, callback ->
                                gfile.enumerateChildrenAsync(queryAttributes, org.gnome.gio.FileQueryInfoFlags.NONE, org.gnome.glib.GLib.PRIORITY_DEFAULT, cancellable, callback)
                            },
                            finish = { result ->
                                gfile.enumerateChildrenFinish(result)
                            }
                        )
                        
                        var batchIndex = 0
                        try {
                            while (true) {
                                val batchSize = if (batchIndex < batchSizes.size) batchSizes[batchIndex] else 500
                                batchIndex++

                                val batch = awaitGioAsyncDirect<org.gnome.glib.List<org.gnome.gio.FileInfo>>(
                                    block = { cancellable, callback ->
                                        enumerator.nextFilesAsync(batchSize, org.gnome.glib.GLib.PRIORITY_DEFAULT, cancellable, callback)
                                    },
                                    finish = { result ->
                                        enumerator.nextFilesFinish(result)
                                    }
                                )
                                if (batch == null || batch.isEmpty()) break

                                for (info in batch) {
                                    val name = info?.name?.toString() ?: continue
                                    val fastUri = GioTypeMappers.fastChildUri(parentUri, name)
                                    
                                    val fileInfo = if (fastUri != null) {
                                        com.imbric.core.models.FileInfo(
                                            id = LISTING_SENTINEL_UUID,
                                            name = name,
                                            path = "$parentPath/$name",
                                            uri = fastUri,
                                            pathType = com.imbric.core.models.PathType.PHYSICAL,
                                            isDirectory = info.fileType == org.gnome.gio.FileType.DIRECTORY,
                                            size = info.size,
                                            mimeType = info.contentType?.toString() ?: "application/octet-stream",
                                            modifiedTime = info.modificationDateTime?.let { kotlinx.datetime.Instant.fromEpochSeconds(it.toUnix()) },
                                            isHidden = info.isHidden,
                                            backendId = "gio",
                                            isInTrash = parentUri.startsWith("trash:///"),
                                            isInRecent = parentUri.startsWith("recent:///"),
                                            symlinkTarget = "",
                                            isExecutable = false,
                                            thumbnailPath = null
                                        )
                                    } else {
                                        val childFile = gfile.getChild(name)
                                        GioTypeMappers.toImbricFileInfo(childFile, info, listingMode = true, parentUri = parentUri, parentPath = parentPath)
                                    }
                                    count++
                                }
                            }
                        } finally {
                            enumerator.close(null)
                        }
                    }
                    times.add(time)
                    println("[$target] Run $i: $time ms")
                }

                val avg = times.average()
                println("$target:")
                println("  Runs: ${times.map { "${it}ms" }}")
                println("  Average: ${String.format("%.2f", avg)} ms (Item count: $count)")
            }
        }
        println("============================================\n")
        assertTrue(true)
    }

    @Test
    fun benchmarkSyncListDirectories() = runBlocking {
        val targets = listOf(
            "file:///home/ray/Downloads",
            "file:///home/ray/Pictures/Screenshots",
            "file:///home/ray/Downloads/Sidebery"
        )

        println("\n=== KOTLIN SYNC BENCHMARK REPORT ===")
        val queryAttributes = "standard::name,standard::type,standard::is-hidden,standard::size,standard::content-type,standard::is-symlink,access::can-execute"
        val LISTING_SENTINEL_UUID = kotlin.uuid.Uuid.fromLongs(0, 0)

        for (target in targets) {
            val gfile = org.gnome.gio.File.newForUri(target)
            val parentUri = target.trimEnd('/')
            val parentPath = gfile.path?.toString()?.trimEnd('/')
                ?: GioTypeMappers.localPathFromFileUri(parentUri)

            // Warmup
            var count = 0
            val warmupTime = measureTimeMillis {
                val enumerator = gfile.enumerateChildren(queryAttributes, org.gnome.gio.FileQueryInfoFlags.NONE, null)
                try {
                    while (true) {
                        val info = enumerator.nextFile(null) ?: break
                        count++
                    }
                } finally {
                    enumerator.close(null)
                }
            }
            println("[$target] Warmup Run: $warmupTime ms")

            val times = mutableListOf<Long>()
            for (i in 1..5) {
                System.gc()
                kotlinx.coroutines.delay(100)

                val time = measureTimeMillis {
                    count = 0
                    val enumerator = gfile.enumerateChildren(queryAttributes, org.gnome.gio.FileQueryInfoFlags.NONE, null)
                    try {
                        while (true) {
                            val info = enumerator.nextFile(null) ?: break
                            val name = info.name?.toString() ?: ""
                            val fastUri = GioTypeMappers.fastChildUri(parentUri, name)
                            
                            val fileInfo = if (fastUri != null) {
                                com.imbric.core.models.FileInfo(
                                    id = LISTING_SENTINEL_UUID,
                                    name = name,
                                    path = "$parentPath/$name",
                                    uri = fastUri,
                                    pathType = com.imbric.core.models.PathType.PHYSICAL,
                                    isDirectory = info.fileType == org.gnome.gio.FileType.DIRECTORY,
                                    size = info.size,
                                    mimeType = info.contentType?.toString() ?: "application/octet-stream",
                                    modifiedTime = info.modificationDateTime?.let { kotlinx.datetime.Instant.fromEpochSeconds(it.toUnix()) },
                                    isHidden = info.isHidden,
                                    backendId = "gio",
                                    isInTrash = parentUri.startsWith("trash:///"),
                                    isInRecent = parentUri.startsWith("recent:///"),
                                    symlinkTarget = "",
                                    isExecutable = false,
                                    thumbnailPath = null
                                )
                            } else {
                                val childFile = gfile.getChild(name)
                                GioTypeMappers.toImbricFileInfo(childFile, info, listingMode = true, parentUri = parentUri, parentPath = parentPath)
                            }
                            count++
                        }
                    } finally {
                        enumerator.close(null)
                    }
                }
                times.add(time)
                println("[$target] Run $i: $time ms")
            }

            val avg = times.average()
            println("$target:")
            println("  Runs: ${times.map { "${it}ms" }}")
            println("  Average: ${String.format("%.2f", avg)} ms (Item count: $count)")
        }
        println("====================================\n")
        assertTrue(true)
    }
}

