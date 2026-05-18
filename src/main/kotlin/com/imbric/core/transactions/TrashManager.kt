@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.desktop.TrashMonitor
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
 */
class TrashManager(
    private val backendRegistry: BackendRegistry,
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.Default)
) {
    private val trashMonitor = TrashMonitor.getInstance()

    // --- Trash Items Cache ---
    private var trashItemsCache: List<TrashItem>? = null
    private var lastScanTime: Long = 0
    private val cacheValidityMs: Long = 5000 // 5 seconds

    // --- State for UI ---
    val isTrashEmpty: StateFlow<Boolean> = trashMonitor.isEmpty

    // --- Trash Operations ---
    suspend fun trashFiles(paths: List<String>): Result<List<String>> {
        val results = mutableListOf<String>()
        var hasError = false
        
        for (path in paths) {
            val backend = backendRegistry.getIo(path) ?: continue
            val job = FileJob(id = Uuid.random(), opType = "trash", source = path)
            val result = backend.trash(job)
            if (result.isSuccess) {
                results.add(path)
                invalidateCache()
            } else {
                hasError = true
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
            invalidateCache()
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
        
        invalidateCache()
        return if (hasError) Result.failure(Exception("Some items could not be deleted")) else Result.success(Unit)
    }

    // --- Listing & Status ---
    suspend fun listTrashItems(forceRefresh: Boolean = false): List<TrashItem> {
        val now = System.currentTimeMillis()
        if (!forceRefresh && trashItemsCache != null && (now - lastScanTime) < cacheValidityMs) {
            return trashItemsCache!!
        }
        
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
        
        trashItemsCache = items
        lastScanTime = now
        trashMonitor.refresh()
        return items
    }

    fun getTrashSize(): Long = trashItemsCache?.sumOf { it.size } ?: 0L
    
    suspend fun isTrashEmpty(): Boolean = trashMonitor.isEmpty.value

    // --- Utility ---
    private fun invalidateCache() {
        trashItemsCache = null
        trashMonitor.refresh()
    }

    fun canTrash(path: String): Boolean {
        val backend = backendRegistry.getIo(path) ?: return false
        return backend.exists(path) && backend.getCapabilities(path).supportsTrash
    }
}
