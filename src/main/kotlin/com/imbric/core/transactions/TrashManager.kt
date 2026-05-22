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

data class TrashResult(val successful: List<String>, val failed: List<String>)

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
    suspend fun trashFiles(paths: List<String>): TrashResult {
        val successful = mutableListOf<String>()
        val failed = mutableListOf<String>()
        
        val dispatcher = BulkDispatcher.Local
        coroutineScope {
            val ops = paths.map { path ->
                async(dispatcher) {
                    val backend = backendRegistry.getIo(path)
                    if (backend == null) {
                        path to Result.failure(Exception("No backend found"))
                    } else {
                        val job = FileJob(id = Uuid.random(), opType = "trash", source = path)
                        // Pass recoverTrashUri = false to avoid O(N^2) bottleneck in GioBackend
                        val result = backend.trash(job, recoverTrashUri = false)
                        path to result
                    }
                }
            }.awaitAll()

            var anySuccess = false
            for (op in ops) {
                val (path, result) = op
                if (result.isSuccess) {
                    successful.add(path)
                    anySuccess = true
                } else {
                    failed.add(path)
                }
            }

            if (anySuccess) {
                trashState.refresh()
            }
        }
        
        return TrashResult(successful, failed)
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
        
        coroutineScope {
            val ops = backendRegistry.getRegisteredSchemes().map { scheme ->
                async {
                    val backend = backendRegistry.getIo("$scheme:///") ?: return@async null
                    val trashBackend = backend.getTrashBackend(backendRegistry) ?: return@async null
                    trashBackend.emptyTrash()
                }
            }.awaitAll()
            
            for (result in ops) {
                if (result != null && !result.isSuccess) {
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
        coroutineScope {
            val ops = backendRegistry.getRegisteredSchemes().map { scheme ->
                async {
                    val backend = backendRegistry.getIo("$scheme:///") ?: return@async null
                    val trashBackend = backend.getTrashBackend(backendRegistry) ?: return@async null
                    trashBackend.listTrash()
                }
            }.awaitAll()
            
            for (result in ops) {
                if (result != null && result.isSuccess) {
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
        if (!backend.getCapabilities(path).supportsTrash) return false
        return backend.exists(path)
    }
}
