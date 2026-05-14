@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.ifs.*
import com.imbric.core.logic.*
import com.imbric.core.models.*
import com.imbric.core.transactions.models.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import java.util.concurrent.ConcurrentHashMap
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

class TransactionManager(
    private val backendRegistry: BackendRegistry,
    private val xferArbiter: XferArbiter,
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.Default)
) {
    private val transactions = ConcurrentHashMap<Uuid, Transaction>()
    private val activeJobs = ConcurrentHashMap<Uuid, kotlinx.coroutines.Job>()
    
    private val _events = MutableSharedFlow<TransactionEvent>(extraBufferCapacity = 128)
    val events: SharedFlow<TransactionEvent> = _events.asSharedFlow()
    
    // --- Legacy Callback hooks for UI (transitional) ---
    var onTransactionStarted: ((Uuid, String) -> Unit)? = null
    var onTransactionFinished: ((Uuid, TransactionStatus) -> Unit)? = null
    var onTransactionProgress: ((Uuid, Float) -> Unit)? = null
    var onHistoryCommitted: ((Transaction) -> Unit)? = null

    // --- Transaction Lifecycle ---
    fun startTransaction(description: String, isReversible: Boolean = true): Uuid {
        val tid = Uuid.random()
        transactions[tid] = Transaction(
            id = tid,
            description = description,
            isReversible = isReversible
        )
        return tid
    }

    fun addOperation(
        tid: Uuid, 
        opType: String, 
        src: String, 
        dest: String = "", 
        jobId: Uuid = Uuid.random(), 
        overwrite: Boolean = false,
        autoRename: Boolean = false
    ) {
        val tx = transactions[tid] ?: return
        tx.addOperation(TransactionOperation(
            jobId = jobId,
            opType = opType,
            src = src,
            dest = dest,
            overwrite = overwrite,
            autoRename = autoRename
        ))
    }

    // --- High-level Entry Point ---
    fun batchTransfer(
        sources: List<String>,
        destDir: String,
        mode: String = "auto"
    ): Uuid {
        val tid = startTransaction("Batch transfer to $destDir")
        sources.forEach { src ->
            val fileName = src.uriName
            val fullDest = destDir.uriJoin(fileName)
            addOperation(tid, if (mode == "move") "move" else "copy", src, fullDest)
        }
        
        commitTransaction(tid) { op, _ ->
            executeBatchJob(tid, op)
        }
        return tid
    }

    // --- Commit & Execute ---
    fun commitTransaction(
        tid: Uuid, 
        conflictResolver: (suspend (ConflictContext) -> ConflictResponse)? = null,
        executor: (TransactionOperation, (suspend (ConflictContext) -> ConflictResponse)?) -> kotlinx.coroutines.Job
    ) {
        val tx = transactions[tid] ?: return
        tx.status = TransactionStatus.RUNNING
        
        onTransactionStarted?.invoke(tid, tx.description)
        _events.tryEmit(TransactionEvent.Started(tid, tx.description))
        
        tx.ops.forEach { op ->
            val job = executor(op, conflictResolver)
            activeJobs[op.jobId] = job
        }
        
        if (tx.ops.isEmpty()) {
            tx.status = TransactionStatus.COMPLETED
            _events.tryEmit(TransactionEvent.Finished(tid, tx.status))
            onTransactionFinished?.invoke(tid, tx.status)
        }
    }

    internal fun executeBatchJob(
        tid: Uuid,
        op: TransactionOperation,
        conflictResolver: (suspend (ConflictContext) -> ConflictResponse)? = null
    ): kotlinx.coroutines.Job {
        return scope.launch {
            var currentOp = op
            var retry = true
            
            while (retry) {
                retry = false
                try {
                    val backend = backendRegistry.getIo(currentOp.src) ?: return@launch
                    val job = FileJob(
                        id = currentOp.jobId,
                        opType = currentOp.opType,
                        source = currentOp.src,
                        dest = currentOp.dest,
                        overwrite = currentOp.overwrite,
                        autoRename = currentOp.autoRename,
                        transactionId = tid
                    )
                    
                    var actualDest: String? = null
                    when (currentOp.opType) {
                        "copy" -> backend.copy(job).collect { 
                            actualDest = it.actualDest
                            updateProgress(tid, it) 
                        }
                        "move" -> backend.move(job).collect { 
                            actualDest = it.actualDest
                            updateProgress(tid, it) 
                        }
                        "trash" -> backend.trash(job).getOrThrow().also { updateProgress(tid, TransferProgress(job.id, job.source, null, 1, 1, 0, 0)) }
                        "delete" -> backend.delete(job).getOrThrow().also { updateProgress(tid, TransferProgress(job.id, job.source, null, 1, 1, 0, 0)) }
                        "rename" -> backend.rename(job.source, job.dest).getOrThrow().also { 
                            actualDest = job.dest
                            updateProgress(tid, TransferProgress(job.id, job.source, actualDest, 1, 1, 0, 0)) 
                        }
                    }
                    updateOperationStatus(tid, currentOp.jobId, TransactionStatus.COMPLETED, resultPath = actualDest)
                } catch (e: Exception) {
                    val errorCode = (e as? VfsConflictException)?.code ?: -1
                    
                    if (errorCode == VfsConflictException.EXISTS && conflictResolver != null && (currentOp.opType == "copy" || currentOp.opType == "move")) {
                        val srcBackend = backendRegistry.getIo(currentOp.src)!!
                        val destBackend = backendRegistry.getIo(currentOp.dest)!!
                        val srcMeta = srcBackend.getMetadata(currentOp.src).getOrNull()
                        val destMeta = destBackend.getMetadata(currentOp.dest).getOrNull()
                        
                        if (srcMeta != null && destMeta != null) {
                            val conflictType = XferArbiter.classifyConflict(srcMeta, destMeta)
                            val context = ConflictContext(currentOp.src, currentOp.dest, srcMeta, destMeta, conflictType)
                            
                            _events.tryEmit(TransactionEvent.Conflict(tid, currentOp.jobId, context.src, context.dest, context.srcMeta, context.destMeta))
                            
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
                                is ConflictAction.Skip -> {
                                    updateOperationStatus(tid, currentOp.jobId, TransactionStatus.COMPLETED)
                                }
                                is ConflictAction.Cancel -> {
                                    updateOperationStatus(tid, currentOp.jobId, TransactionStatus.CANCELLED)
                                }
                                else -> {
                                    updateOperationStatus(tid, currentOp.jobId, TransactionStatus.FAILED, "Unresolved conflict")
                                }
                            }
                        } else {
                            updateOperationStatus(tid, currentOp.jobId, TransactionStatus.FAILED, e.message ?: "Conflict metadata error")
                        }
                    } else {
                        updateOperationStatus(tid, currentOp.jobId, TransactionStatus.FAILED, e.message ?: "Transfer failed")
                    }
                }
            }
        }
    }

    private fun updateOperationStatus(tid: Uuid, jobId: Uuid, status: TransactionStatus, error: String = "", resultPath: String? = null) {
        val tx = transactions[tid] ?: return
        val opIndex = tx.ops.indexOfFirst { it.jobId == jobId }
        if (opIndex != -1) {
            val op = tx.ops[opIndex]
            val updatedOp = op.copy(
                status = status, 
                error = error, 
                resultPath = resultPath ?: op.resultPath,
                inversePayload = if (status == TransactionStatus.COMPLETED && tx.isReversible) UndoFactory.createInverse(op.copy(resultPath = resultPath ?: op.resultPath)) else null
            )
            tx.ops[opIndex] = updatedOp
            updateProgress(tid, TransferProgress(jobId, op.src, resultPath ?: op.resultPath))
        }
    }

    // --- Progress & Status ---
    private fun updateProgress(tid: Uuid, progress: TransferProgress) {
        val tx = transactions[tid] ?: return
        
        // Update per-job progress for byte-level aggregation
        val op = tx.ops.find { it.jobId == progress.jobId }
        val pct = if (tx.totalOps > 0) {
            val completedBase = tx.completedOps.toFloat()
            
            // Calculate fractional progress of currently running jobs
            // (Simple version: factor in the current job's bytes if available)
            val currentJobFraction = if (progress.totalSize > 0) {
                progress.completedSize.toFloat() / progress.totalSize
            } else if (progress.totalCount > 0) {
                progress.completedCount.toFloat() / progress.totalCount
            } else 0f
            
            (completedBase + currentJobFraction.coerceIn(0f, 0.99f)) / tx.totalOps
        } else 0f
        
        onTransactionProgress?.invoke(tid, pct)
        _events.tryEmit(TransactionEvent.Progress(tid, pct))
        _events.tryEmit(TransactionEvent.FileProgress(tid, progress))
        
        if (tx.finishedOps == tx.totalOps) {
            val hasFailures = tx.ops.any { it.status == TransactionStatus.FAILED }
            tx.status = if (hasFailures) TransactionStatus.PARTIAL else TransactionStatus.COMPLETED
            
            onTransactionFinished?.invoke(tid, tx.status)
            _events.tryEmit(TransactionEvent.Finished(tid, tx.status))
            
            if (tx.isReversible && !hasFailures) {
                onHistoryCommitted?.invoke(tx)
            }
        }
    }

    // --- Capabilities ---
    fun getTransferCapabilities(sources: List<String>, dest: String): Map<String, Int> {
        val capabilities = mutableMapOf<String, Int>()
        sources.forEach { src ->
            backendRegistry.getIo(src)?.let { backend ->
                capabilities[backend.scheme] = (capabilities[backend.scheme] ?: 0) + 1
            }
        }
        return capabilities
    }

    // --- Cleanup ---
    fun cancelTransaction(tid: Uuid) {
        val tx = transactions[tid] ?: return
        tx.ops.forEach { op ->
            activeJobs[op.jobId]?.cancel()
            activeJobs.remove(op.jobId)
        }
        tx.status = TransactionStatus.CANCELLED
        _events.tryEmit(TransactionEvent.Finished(tid, TransactionStatus.CANCELLED))
        onTransactionFinished?.invoke(tid, TransactionStatus.CANCELLED)
    }
}
