@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.ifs.BackendRegistry
import com.imbric.core.ifs.VfsConflictException
import com.imbric.core.ifs.uriParent
import com.imbric.core.ifs.uriJoin
import com.imbric.core.logic.*
import com.imbric.core.models.FileJob
import com.imbric.core.models.InversePayload
import com.imbric.core.models.TransferProgress
import com.imbric.core.transactions.models.TransactionOperation
import com.imbric.core.transactions.models.TransactionStatus
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import java.util.concurrent.ConcurrentHashMap
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

/**
 * TransactionDispatcher handles the actual execution of VFS operations.
 * It provides concurrency control (Semaphore) and UI progress throttling.
 */
class TransactionDispatcher(
    private val backendRegistry: BackendRegistry,
    // Dedicated IO scope for heavy disk work
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.IO) 
) {
    // 🔥 THE FIX: Limits disk I/O to 4 files at a time. Prevents OS crash!
    private val ioSemaphore = Semaphore(4) 
    
    // Tracks active jobs so we can cancel them instantly if requested
    private val activeJobs = ConcurrentHashMap<Uuid, Job>()

    /**
     * Dispatches a single job to the backend. 
     * Handles the execution, throttling, and JIT conflicts.
     *
     * @param policy  SyncPolicy evaluated JIT in the catch block before prompting the user.
     *                On HIGH-latency backends (MTP, SMB) this prevents unnecessary network
     *                round-trips during pre-flight — conflicts are resolved here instead.
     */
    fun dispatchJob(
        tid: Uuid,
        op: TransactionOperation,
        conflictResolver: (suspend (ConflictContext) -> ConflictResponse)?,
        onProgress: (TransferProgress) -> Unit,
        onStatusUpdate: (Uuid, TransactionStatus, String, String?, InversePayload?) -> Unit,
        policy: SyncPolicy = SyncPolicy.Standard
    ) {
        val jobCoro = scope.launch {
            // 🔥 WAIT IN LINE: Coroutine pauses here until one of the 4 slots opens up
            ioSemaphore.withPermit {
                // Ensure we haven't been cancelled while waiting in line
                if (!isActive) return@withPermit 
                
                executeSingleJob(tid, op, conflictResolver, onProgress, onStatusUpdate, policy)
            }
        }
        
        activeJobs[op.jobId] = jobCoro
        jobCoro.invokeOnCompletion { activeJobs.remove(op.jobId) }
    }

    /**
     * Cancels all currently running and queued jobs for a transaction.
     */
    fun cancelJobs(jobIds: List<Uuid>) {
        jobIds.forEach { jobId ->
            activeJobs[jobId]?.cancel()
            activeJobs.remove(jobId)
        }
    }

    private suspend fun executeSingleJob(
        tid: Uuid,
        initialOp: TransactionOperation,
        conflictResolver: (suspend (ConflictContext) -> ConflictResponse)?,
        onProgress: (TransferProgress) -> Unit,
        onStatusUpdate: (Uuid, TransactionStatus, String, String?, InversePayload?) -> Unit,
        policy: SyncPolicy = SyncPolicy.Standard
    ) {
        var currentOp = initialOp
        var retry = true
        
        while (retry) {
            retry = false
            try {
                val backend = backendRegistry.getIo(currentOp.src) ?: return
                
                val job = FileJob(
                    id = currentOp.jobId,
                    opType = currentOp.opType,
                    source = currentOp.src,
                    dest = currentOp.dest,
                    overwrite = currentOp.overwrite,
                    autoRename = currentOp.autoRename,
                    inversePayload = currentOp.inversePayload?.let { InversePayload(
                        action = it["action"] as? String ?: "",
                        target = it["target"] as? String ?: "",
                        dest = it["dest"] as? String,
                        newName = it["newName"] as? String,
                        renameTo = it["renameTo"] as? String,
                        tid = (it["tid"] as? String)?.let { Uuid.parse(it) } ?: it["tid"] as? Uuid,
                        backendId = it["backendId"] as? String
                    )}
                )
                
                var actualDest: String? = null
                var inverse: InversePayload? = null
                var lastEmitTime = 0L // For throttling UI

                // Helper to emit progress safely at 100ms intervals
                val emitThrottledProgress = { progress: TransferProgress ->
                    val now = System.currentTimeMillis()
                    // 🔥 THE FIX: Only emit every 100ms OR if the file is 100% finished
                    if (now - lastEmitTime > 100 || progress.completedSize == progress.totalSize) {
                        onProgress(progress)
                        lastEmitTime = now
                    }
                }

                when (currentOp.opType) {
                    "copy" -> backend.copy(job).collect { 
                        actualDest = it.actualDest
                        inverse = it.inversePayload
                        emitThrottledProgress(it) 
                    }
                    "move" -> backend.move(job).collect { 
                        actualDest = it.actualDest
                        inverse = it.inversePayload
                        emitThrottledProgress(it) 
                    }
                    "trash" -> backend.trash(job).getOrThrow().also { 
                        inverse = InversePayload(action = "undo_trash", target = job.source, dest = job.source, backendId = "gio")
                        onProgress(TransferProgress(job.id, job.source, null, inverse, 1, 1, 0, 0)) 
                    }
                    "delete" -> backend.delete(job).getOrThrow().also { 
                        onProgress(TransferProgress(job.id, job.source, null, null, 1, 1, 0, 0)) 
                    }
                    "rename" -> backend.rename(job.source, job.dest).getOrThrow().also { 
                        actualDest = job.dest
                        inverse = InversePayload(action = "undo_rename", target = actualDest!!, dest = job.source, backendId = "gio")
                        onProgress(TransferProgress(job.id, job.source, actualDest, inverse, 1, 1, 0, 0)) 
                    }
                    "undo" -> {
                        val payload = job.inversePayload ?: throw Exception("Undo payload missing")
                        backend.executeInverse(payload).getOrThrow()
                        onProgress(TransferProgress(job.id, job.source, null, null, 1, 1, 0, 0))
                    }
                }
                
                // Job completely finished successfully
                onStatusUpdate(currentOp.jobId, TransactionStatus.COMPLETED, "", actualDest, inverse)

            } catch (e: Exception) {
                // JIT CONFLICT RESOLUTION (also handles blind pre-flight from HIGH-latency backends)
                val errorCode = (e as? VfsConflictException)?.code ?: -1
                
                if (errorCode == VfsConflictException.EXISTS && (currentOp.opType == "copy" || currentOp.opType == "move")) {
                    val srcBackend = backendRegistry.getIo(currentOp.src)
                    val destBackend = backendRegistry.getIo(currentOp.dest)
                    
                    if (srcBackend != null && destBackend != null) {
                        val srcMeta = srcBackend.getMetadata(currentOp.src).getOrNull()
                        val destMeta = destBackend.getMetadata(currentOp.dest).getOrNull()
                        
                        if (srcMeta != null && destMeta != null) {
                            val conflictType = XferArbiter.classifyConflict(srcMeta, destMeta)
                            
                            // 🔥 JIT POLICY: Apply SyncPolicy before bothering the user.
                            // This is critical for HIGH-latency backends where pre-flight was
                            // skipped — we only pay the metadata cost for files that ACTUALLY conflict.
                            val policyAction = XferArbiter.decide(srcMeta, destMeta, policy)
                            
                            when (policyAction) {
                                is ConflictAction.Overwrite -> {
                                    currentOp = currentOp.copy(overwrite = true)
                                    retry = true
                                }
                                is ConflictAction.AutoRename -> {
                                    currentOp = currentOp.copy(autoRename = true)
                                    retry = true
                                }
                                is ConflictAction.Skip -> {
                                    onStatusUpdate(currentOp.jobId, TransactionStatus.COMPLETED, "", null, null)
                                }
                                is ConflictAction.Cancel -> {
                                    onStatusUpdate(currentOp.jobId, TransactionStatus.CANCELLED, "", null, null)
                                }
                                // Merge, Rename(newName), Prompt — need user input
                                else -> {
                                    if (conflictResolver != null) {
                                        val context = ConflictContext(currentOp.src, currentOp.dest, srcMeta, destMeta, conflictType)
                                        val response = conflictResolver(context)
                                        
                                        when (val action = response.action) {
                                            is ConflictAction.Overwrite -> {
                                                currentOp = currentOp.copy(overwrite = true)
                                                retry = true
                                            }
                                            is ConflictAction.Rename -> {
                                                val destParent = currentOp.dest.uriParent
                                                val newDest = if (destParent.isEmpty()) action.newName else destParent.uriJoin(action.newName)
                                                currentOp = currentOp.copy(dest = newDest, overwrite = false)
                                                retry = true
                                            }
                                            is ConflictAction.AutoRename -> {
                                                currentOp = currentOp.copy(autoRename = true)
                                                retry = true
                                            }
                                            is ConflictAction.Skip -> {
                                                onStatusUpdate(currentOp.jobId, TransactionStatus.COMPLETED, "", null, null)
                                            }
                                            is ConflictAction.Cancel -> {
                                                onStatusUpdate(currentOp.jobId, TransactionStatus.CANCELLED, "", null, null)
                                            }
                                            else -> {
                                                onStatusUpdate(currentOp.jobId, TransactionStatus.FAILED, "Unresolved conflict after user prompt", null, null)
                                            }
                                        }
                                    } else {
                                        onStatusUpdate(currentOp.jobId, TransactionStatus.FAILED, "Unresolved conflict", null, null)
                                    }
                                }
                            }
                        } else {
                            onStatusUpdate(currentOp.jobId, TransactionStatus.FAILED, e.message ?: "Conflict metadata error", null, null)
                        }
                    } else {
                        onStatusUpdate(currentOp.jobId, TransactionStatus.FAILED, e.message ?: "Backend not found for conflict resolution", null, null)
                    }
                } else {
                    onStatusUpdate(currentOp.jobId, TransactionStatus.FAILED, e.message ?: "Transfer failed", null, null)
                }
            }
        }
    }
}
