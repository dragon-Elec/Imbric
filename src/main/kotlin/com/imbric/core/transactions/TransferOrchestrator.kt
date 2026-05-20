@file:OptIn(ExperimentalUuidApi::class)
package com.imbric.core.transactions

import com.imbric.core.ifs.*
import com.imbric.core.logic.*
import com.imbric.core.models.FileInfo
import com.imbric.core.transactions.models.TransactionEvent
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.util.Collections
import kotlin.uuid.Uuid
import kotlin.uuid.ExperimentalUuidApi

class TransferOrchestrator(
    private val backendRegistry: BackendRegistry,
    private val transactionManager: TransactionManager
) {
    fun planAndExecute(
        sources: List<String>,
        destDir: String,
        mode: String = "copy",
        policy: SyncPolicy = SyncPolicy.Standard,
        onManualConflict: suspend (ConflictContext) -> ConflictResponse = { ConflictResponse(ConflictAction.Prompt) }
    ): Flow<TransactionEvent> = channelFlow {
        val tid = transactionManager.startTransaction("Batch $mode to $destDir")
        val stickyDecisions = mutableMapOf<ConflictType, ConflictAction>()
        val mutex = Mutex()
        val validatedOps = Collections.synchronizedList(mutableListOf<ValidatedOp>())

        // 1. Parallel Pre-flight Planning
        withContext(Dispatchers.IO) {
            sources.map { src ->
                async {
                    planOperation(src, destDir, mode, policy, onManualConflict, stickyDecisions, mutex, validatedOps)
                }
            }.awaitAll()
        }
        
        // 2. Dispatch to TransactionManager
        validatedOps.forEach { op ->
            transactionManager.addOperation(
                tid, 
                mode, 
                op.src, 
                op.dest, 
                overwrite = op.overwrite, 
                autoRename = op.autoRename
            )
        }
        
        val collector = launch(start = CoroutineStart.UNDISPATCHED) {
            transactionManager.events
                .filter { it.tid == tid }
                .collect {
                    send(it)
                    if (it is TransactionEvent.Finished) {
                        throw CancellationException("Transaction $tid finished")
                    }
                }
        }
        
        val jitResolver: suspend (ConflictContext) -> ConflictResponse = { context ->
            val existing = mutex.withLock { stickyDecisions[context.type] }
            if (existing != null) {
                ConflictResponse(existing)
            } else {
                val response = onManualConflict(context)
                if (response.applyToAll) {
                    mutex.withLock {
                        val doubleCheck = stickyDecisions[context.type]
                        if (doubleCheck == null) {
                            stickyDecisions[context.type] = response.action
                            response
                        } else {
                            ConflictResponse(doubleCheck)
                        }
                    }
                } else {
                    response
                }
            }
        }

        transactionManager.commitTransaction(tid, jitResolver, policy)
        
        try {
            collector.join()
        } catch (_: CancellationException) {
            // Collector terminated normally when transaction finished
        }
    }

    private suspend fun planOperation(
        src: String,
        destParent: String,
        mode: String,
        policy: SyncPolicy,
        onManualConflict: suspend (ConflictContext) -> ConflictResponse,
        stickyDecisions: MutableMap<ConflictType, ConflictAction>,
        mutex: Mutex,
        validatedOps: MutableList<ValidatedOp>
    ) {
        val fileName = src.uriName
        val dest = destParent.uriJoin(fileName)
        
        val srcBackend = backendRegistry.getIo(src) ?: return
        val destBackend = backendRegistry.getIo(dest) ?: return
        
        val srcMeta = srcBackend.getMetadata(src).getOrNull() ?: return
        val destExists = destBackend.exists(dest)
        
        if (!destExists) {
            validatedOps.add(ValidatedOp(src, dest, false))
            return
        }

        val destMeta = destBackend.getMetadata(dest).getOrNull() ?: return
        val conflictType = XferArbiter.classifyConflict(srcMeta, destMeta)
        
        // Check sticky decisions first under lock
        var action: ConflictAction = mutex.withLock {
            stickyDecisions[conflictType] ?: XferArbiter.decide(srcMeta, destMeta, policy)
        }
        
        if (action is ConflictAction.Prompt) {
            val existing = mutex.withLock { stickyDecisions[conflictType] }
            val response = if (existing != null) {
                ConflictResponse(existing)
            } else {
                val res = onManualConflict(ConflictContext(src, dest, srcMeta, destMeta, conflictType))
                if (res.applyToAll) {
                    mutex.withLock {
                        val doubleCheck = stickyDecisions[conflictType]
                        if (doubleCheck == null) {
                            stickyDecisions[conflictType] = res.action
                            res
                        } else {
                            ConflictResponse(doubleCheck)
                        }
                    }
                } else {
                    res
                }
            }
            action = response.action
        }
        
        when (action) {
            is ConflictAction.Overwrite -> validatedOps.add(ValidatedOp(src, dest, true))
            is ConflictAction.AutoRename -> validatedOps.add(ValidatedOp(src, dest, false, true))
            is ConflictAction.Rename -> {
                val newName = action.newName
                val newDest = destParent.uriJoin(newName)
                validatedOps.add(ValidatedOp(src, newDest, false))
            }
            is ConflictAction.Merge -> {
                // Recursive Merge: plan all children of source into destination
                srcBackend.list(src).collect { child ->

                    planOperation(child.path, dest, mode, policy, onManualConflict, stickyDecisions, mutex, validatedOps)
                }
            }
            is ConflictAction.Skip -> { /* Do nothing */ }
            is ConflictAction.Cancel -> throw CancellationException("Operation cancelled by user")
            else -> { /* Prompt already handled or unexpected action */ }
        }
    }
    
    private data class ValidatedOp(val src: String, val dest: String, val overwrite: Boolean, val autoRename: Boolean = false)
}
