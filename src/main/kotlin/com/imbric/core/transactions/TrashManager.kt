@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.desktop.TrashMonitor
import com.imbric.core.desktop.TrashStateProvider
import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.models.FileJob
import com.imbric.core.models.TrashItem
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

/**
 * Specialized transaction logic for trash operations.
 * Ported from Python trash_manager.py.
 *
 * TrashManager is the transactional layer — it performs trash operations
 * via IOBackend and observes trash state via TrashMonitor.
 * Each platform provides its own TrashMonitor implementation:
 * - Linux/GIO: GFileMonitor on trash:/// with TRASH_ITEM_COUNT
 * - Windows: future SHChangeNotifyRegister implementation
 * - macOS: future FSEvents implementation
 */
class TrashManager(
    private val backendRegistry: BackendRegistry,
    private val trashState: TrashStateProvider = TrashMonitor.getInstance(),
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.Default)
) {
    // --- State for UI (delegates to TrashMonitor's real-time StateFlow) ---
    val isTrashEmpty: StateFlow<Boolean> = trashState.isEmpty

    // --- Trash Operations ---
    suspend fun trashFiles(paths: List<String>): Result<List<String>> {
        val results = mutableListOf<String>()
        var hasError = false
        
        val dispatcher = Dispatchers.IO.limitedParallelism(32)
        coroutineScope {
            val ops = paths.map { path ->
                async(dispatcher) {
                    val backend = backendRegistry.getIo(path)
                    if (backend == null) {
                        null
                    } else {
                        val job = FileJob(id = Uuid.random(), opType = "trash", source = path)
                        val result = backend.trash(job)
                        path to result
                    }
                }
            }.awaitAll()

            var anySuccess = false
            for (op in ops) {
                if (op == null) continue
                val (path, result) = op
                if (result.isSuccess) {
                    results.add(path)
                    anySuccess = true
                } else {
                    hasError = true
                }
            }

            if (anySuccess) {
                trashState.refresh()
            }
        }
        
        if (hasError) {
            return Result.failure(Exception("Some files could not be trashed"))
        }
        return Result.success(results)
    }

    suspend fun restoreFromTrash(trashItem: TrashItem): Result<String> {
        val backend = backendRegistry.getIo(trashItem.originalPath) ?: return Result.failure(Exception("No backend for ${trashItem.originalPath}"))
        val result = backend.restoreFromTrash(trashItem.trashPath, trashItem.originalPath)
        if (result.isSuccess) {
            trashState.refresh()
        }
        return result
    }

    suspend fun emptyTrash(): Result<Unit> {
        var hasError = false
        
        for (scheme in backendRegistry.getRegisteredSchemes()) {
            val backend = backendRegistry.getIo("$scheme:///") ?: continue
            backend.getTrashBackend(backendRegistry)?.let { trashBackend ->
                val result = trashBackend.emptyTrash()
                if (!result.isSuccess) {
                    hasError = true
                }
            }
        }
        
        trashState.refresh()
        return if (hasError) Result.failure(Exception("Some items could not be deleted")) else Result.success(Unit)
    }

    // --- Listing & Status ---
    /**
     * Lists all trash items across all registered backends.
     * Always queries backends fresh — real-time state is TrashMonitor's job.
     */
    suspend fun listTrashItems(): List<TrashItem> {
        val items = mutableListOf<TrashItem>()
        for (scheme in backendRegistry.getRegisteredSchemes()) {
            val backend = backendRegistry.getIo("$scheme:///") ?: continue
            backend.getTrashBackend(backendRegistry)?.let { trashBackend ->
                val result = trashBackend.listTrash()
                if (result.isSuccess) {
                    items.addAll(result.getOrThrow())
                }
            }
        }
        return items
    }

    /**
     * Computes total size of all items in trash across all backends.
     */
    suspend fun getTrashSize(): Long = listTrashItems().sumOf { it.size }

    suspend fun isTrashEmpty(): Boolean = trashState.isEmpty.value

    fun canTrash(path: String): Boolean {
        val backend = backendRegistry.getIo(path) ?: return false
        return backend.exists(path) && backend.getCapabilities(path).supportsTrash
    }
}
