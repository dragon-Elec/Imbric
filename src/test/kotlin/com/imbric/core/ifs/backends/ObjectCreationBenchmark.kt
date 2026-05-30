@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)
package com.imbric.core.ifs.backends

import com.imbric.core.models.FileEntry
import com.imbric.core.models.SortKey
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.gnome.gio.Gio
import org.junit.jupiter.api.BeforeAll
import org.junit.jupiter.api.Test
import kotlin.system.measureTimeMillis
import kotlin.test.assertTrue

/**
 * Benchmark that uses the EXACT production pipeline:
 * - Same query attributes (FileEntry.listingAttributesFor)
 * - Same async dispatch (GioCoroutineBridge.awaitGioAsync)
 * - Same worker pool (ListingDispatchers.Listing)
 * - Same object construction (GioTypeMappers.toListingFile)
 *
 * Then isolates each phase to measure overhead.
 */
class ObjectCreationBenchmark {
    companion object {
        @JvmStatic
        @BeforeAll
        fun setup() {
            Gio.`javagi$ensureInitialized`()
        }
    }

    @Test
    fun benchmarkProductionPipeline() = runBlocking {
        val target = "file:///home/ray/Pictures/Screenshots"
        val backend = GioBackend()

        TestUtils.withGlibPump {
            println("\n=== PRODUCTION PIPELINE BENCHMARK ===")
            println("Target: $target\n")

            // --- Phase 1: Full production pipeline (backend.list) ---
            val times = mutableListOf<Long>()
            var count = 0
            for (i in 1..5) {
                System.gc()
                kotlinx.coroutines.delay(100)
                val time = measureTimeMillis {
                    count = backend.list(target, SortKey.NAME).size
                }
                times.add(time)
            }
            val avg = times.average()
            println("[PRODUCTION] backend.list(NAME): ${avg.toLong()}ms avg ($count items)")
            println("  Runs: ${times.map { "${it}ms" }}")

            // --- Phase 2: Same pipeline but with MODIFIED sort (more attributes) ---
            val modTimes = mutableListOf<Long>()
            for (i in 1..5) {
                System.gc()
                kotlinx.coroutines.delay(100)
                val time = measureTimeMillis {
                    backend.list(target, SortKey.MODIFIED).size
                }
                modTimes.add(time)
            }
            val modAvg = modTimes.average()
            println("[PRODUCTION] backend.list(MODIFIED): ${modAvg.toLong()}ms avg")
            println("  Runs: ${modTimes.map { "${it}ms" }}")

            // --- Phase 3: Raw GIO fetch only (no construction, no sort) ---
            val queryAttributes = FileEntry.listingAttributesFor(SortKey.NAME)
            println("\n[QUERY ATTRIBUTES] $queryAttributes")

            val rawGioTimes = mutableListOf<Long>()
            var rawCount = 0
            for (i in 1..5) {
                System.gc()
                kotlinx.coroutines.delay(100)
                val time = measureTimeMillis {
                    val gfile = org.gnome.gio.File.newForUri(target)
                    val enumerator = GioCoroutineBridge.awaitGioAsync<org.gnome.gio.FileEnumerator>(
                        block = { cancellable, callback ->
                            gfile.enumerateChildrenAsync(queryAttributes, org.gnome.gio.FileQueryInfoFlags.NONE, org.gnome.glib.GLib.PRIORITY_DEFAULT, cancellable, callback)
                        },
                        finish = { result -> gfile.enumerateChildrenFinish(result) }
                    )
                    rawCount = 0
                    try {
                        while (true) {
                            val batch = GioCoroutineBridge.awaitGioAsync<org.gnome.glib.List<org.gnome.gio.FileInfo>>(
                                block = { cancellable, callback ->
                                    enumerator.nextFilesAsync(5000, org.gnome.glib.GLib.PRIORITY_DEFAULT, cancellable, callback)
                                },
                                finish = { result -> enumerator.nextFilesFinish(result) }
                            )
                            if (batch == null || batch.isEmpty()) break
                            rawCount += batch.size
                        }
                    } finally {
                        enumerator.close(null)
                    }
                }
                rawGioTimes.add(time)
            }
            val rawAvg = rawGioTimes.average()
            println("[RAW GIO] enumerate + nextFiles(5000): ${rawAvg.toLong()}ms avg ($rawCount items)")
            println("  Runs: ${rawGioTimes.map { "${it}ms" }}")

            // --- Phase 4: Object construction only (pre-fetched GFileInfo) ---
            // Fetch once, then time just the construction
            val gfile = org.gnome.gio.File.newForUri(target)
            val enumerator = GioCoroutineBridge.awaitGioAsync<org.gnome.gio.FileEnumerator>(
                block = { cancellable, callback ->
                    gfile.enumerateChildrenAsync(queryAttributes, org.gnome.gio.FileQueryInfoFlags.NONE, org.gnome.glib.GLib.PRIORITY_DEFAULT, cancellable, callback)
                },
                finish = { result -> gfile.enumerateChildrenFinish(result) }
            )
            val allInfos = mutableListOf<org.gnome.gio.FileInfo>()
            try {
                while (true) {
                    val batch = GioCoroutineBridge.awaitGioAsync<org.gnome.glib.List<org.gnome.gio.FileInfo>>(
                        block = { cancellable, callback ->
                            enumerator.nextFilesAsync(5000, org.gnome.glib.GLib.PRIORITY_DEFAULT, cancellable, callback)
                        },
                        finish = { result -> enumerator.nextFilesFinish(result) }
                    )
                    if (batch == null || batch.isEmpty()) break
                    for (info in batch) {
                        if (info != null) allInfos.add(info)
                    }
                }
            } finally {
                enumerator.close(null)
            }

            val parentUri = target.trimEnd('/')
            val parentPath = gfile.path?.toString()?.trimEnd('/') ?: GioTypeMappers.localPathFromFileUri(parentUri)
            val parentPathType = GioTypeMappers.determinePathType(parentUri)
            val parentIsRemote = GioTypeMappers.isRemoteUri(parentUri)

            val constructTimes = mutableListOf<Long>()
            for (i in 1..5) {
                val time = measureTimeMillis {
                    for (info in allInfos) {
                        val name = info.name?.toString() ?: continue
                        GioTypeMappers.toListingFile(
                            name = name,
                            parentUri = parentUri,
                            parentPath = parentPath ?: "",
                            gioInfo = info,
                            parentPathType = parentPathType,
                            parentIsRemote = parentIsRemote
                        )
                    }
                }
                constructTimes.add(time)
            }
            val constructAvg = constructTimes.average()
            println("[CONSTRUCT] toListingFile × ${allInfos.size}: ${constructAvg.toLong()}ms avg")
            println("  Runs: ${constructTimes.map { "${it}ms" }}")

            // --- Phase 5: Sorting only ---
            val items = mutableListOf<FileEntry>()
            for (info in allInfos) {
                val name = info.name?.toString() ?: continue
                items.add(GioTypeMappers.toListingFile(
                    name = name,
                    parentUri = parentUri,
                    parentPath = parentPath ?: "",
                    gioInfo = info,
                    parentPathType = parentPathType,
                    parentIsRemote = parentIsRemote
                ))
            }

            val sortTimes = mutableListOf<Long>()
            for (i in 1..5) {
                val time = measureTimeMillis {
                    items.sortedWith(FileEntry.comparatorFor(SortKey.NAME))
                }
                sortTimes.add(time)
            }
            val sortAvg = sortTimes.average()
            println("[SORT] sortedWith(NAME) × ${items.size}: ${sortAvg.toLong()}ms avg")

            // --- Phase 6: HashMap construction ---
            val mapTimes = mutableListOf<Long>()
            for (i in 1..5) {
                val time = measureTimeMillis {
                    items.associateBy { it.uri }
                }
                mapTimes.add(time)
            }
            val mapAvg = mapTimes.average()
            println("[MAP] associateBy(uri) × ${items.size}: ${mapAvg.toLong()}ms avg")

            // --- Summary ---
            println("\n--- BREAKDOWN ---")
            println("Raw GIO fetch:         ${rawAvg.toLong()}ms")
            println("Object construction:   ${constructAvg.toLong()}ms")
            println("Sorting:               ${sortAvg.toLong()}ms")
            println("HashMap:               ${mapAvg.toLong()}ms")
            println("Sum of parts:          ${(rawAvg + constructAvg + sortAvg + mapAvg).toLong()}ms")
            println("Production pipeline:   ${avg.toLong()}ms")
            println("=====================================\n")
        }
        assertTrue(true)
    }
}
