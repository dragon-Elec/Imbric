@file:OptIn(ExperimentalUuidApi::class)

package com.imbric.core.transactions

import com.imbric.core.ifs.*
import com.imbric.core.ifs.contracts.BackendContract
import com.imbric.core.logic.*
import com.imbric.core.transactions.models.TransactionEvent
import com.imbric.core.transactions.models.TransactionStatus
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.util.Collections
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
        val session = PlanningSession(mode, policy, onManualConflict)
        val initialDesc = "Batch $mode to $destDir"



        // Surface warning if trash mode skipped files due to unsupported filesystem
        val desc = if (mode == "trash" && session.skippedUnsupported > 0) {
            "$initialDesc (${"${session.skippedUnsupported} skipped: filesystem doesn't support trash"})"
        } else initialDesc

        val tid = transactionManager.startTransaction(desc)

        // 1. Parallel Pre-flight Planning
        coroutineScope {
            sources.map { src ->
                async {
                    session.planOperation(src, destDir)
                }
            }.awaitAll()
        }

        // 1.5 Disk-space pre-flight: halt if total source exceeds free space
        val destBackend = backendRegistry.get(destDir)
        if (destBackend != null && session.totalSourceSize > 0L) {
            val usage = destBackend.getUsage(destDir).getOrNull()
            if (usage != null && session.totalSourceSize > usage.availableBytes) {
                send(TransactionEvent.Finished(tid, TransactionStatus.PARTIAL))
                return@channelFlow
            }
        }
        
        // 2. Dispatch to TransactionManager
        session.validatedOps.forEach { op ->
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
            session.getOrPromptDecision(context)
        }

        transactionManager.commitTransaction(tid, jitResolver, policy)
        
        try {
            collector.join()
        } catch (_: CancellationException) {
            // Collector terminated normally when transaction finished
        }
    }

    private inner class PlanningSession(
        private val mode: String,
        private val policy: SyncPolicy,
        private val onManualConflict: suspend (ConflictContext) -> ConflictResponse
    ) {
        val stickyDecisions = mutableMapOf<ConflictType, ConflictAction>()
        val stateMutex = Mutex()
        val promptMutex = Mutex()
        val validatedOps = Collections.synchronizedList(mutableListOf<ValidatedOp>())
        val totalSourceSize: Long get() = _totalSourceSize.get()
        private val _totalSourceSize = java.util.concurrent.atomic.AtomicLong(0L)
        var skippedUnsupported: Int = 0
            private set

        suspend fun planOperation(src: String, destParent: String) {
            val fileName = src.uriName
            val dest = destParent.uriJoin(fileName)

            val srcBackend = backendRegistry.get(src) ?: return
            val destBackend = backendRegistry.get(dest) ?: return

            val srcMeta = srcBackend.getMetadata(src).getOrNull() ?: return

            // Trash pre-flight: skip files on filesystems that don't support trash
            if (mode == "trash" && !srcBackend.getCapabilities(src).supportsTrash) {
                skippedUnsupported++
                return
            }

            val destMeta = destBackend.getMetadata(dest).getOrNull()

            if (destMeta == null) {
                _totalSourceSize.addAndGet(srcMeta.size)
                validatedOps.add(ValidatedOp(src, dest, false))
                return
            }

            val conflictType = XferArbiter.classifyConflict(srcMeta, destMeta)
            val conflictContext = ConflictContext(src, dest, srcMeta, destMeta, conflictType)

            val action = determineAction(conflictContext)
            applyAction(action, conflictContext, destParent, srcBackend)
        }

        private suspend fun determineAction(context: ConflictContext): ConflictAction {
            var action: ConflictAction = stateMutex.withLock {
                stickyDecisions[context.type] ?: XferArbiter.decide(context.srcMeta, context.destMeta, policy)
            }

            if (action is ConflictAction.Prompt) {
                val response = getOrPromptDecision(context)
                action = response.action
            }
            return action
        }

        private suspend fun applyAction(
            action: ConflictAction,
            context: ConflictContext,
            destParent: String,
            srcBackend: BackendContract
        ) {
            val src = context.src
            val dest = context.dest

            when (action) {
                is ConflictAction.Overwrite -> validatedOps.add(ValidatedOp(src, dest, true))
                is ConflictAction.AutoRename -> validatedOps.add(ValidatedOp(src, dest, false, true))
                is ConflictAction.Rename -> {
                    val newDest = destParent.uriJoin(action.newName)
                    validatedOps.add(ValidatedOp(src, newDest, false))
                }
                is ConflictAction.Merge -> {
                    // Recursive Merge: plan all children of source into destination
                srcBackend.list(src).forEach { child ->
                    planOperation(child.path, dest)
                }
                }
                is ConflictAction.Skip -> { /* Do nothing */ }
                is ConflictAction.Cancel -> throw CancellationException("Operation cancelled by user")
                else -> { /* Prompt already handled or unexpected action */ }
            }
        }

        suspend fun getOrPromptDecision(context: ConflictContext): ConflictResponse {
            val existing = stateMutex.withLock { stickyDecisions[context.type] }
            if (existing != null) {
                return ConflictResponse(existing)
            }

            return promptMutex.withLock {
                val doubleCheck = stateMutex.withLock { stickyDecisions[context.type] }
                if (doubleCheck != null) {
                    return@withLock ConflictResponse(doubleCheck)
                }

                val response = onManualConflict(context)
                if (response.applyToAll) {
                    stateMutex.withLock {
                        stickyDecisions[context.type] = response.action
                    }
                }
                response
            }
        }
    }

    private data class ValidatedOp(val src: String, val dest: String, val overwrite: Boolean, val autoRename: Boolean = false)
}
