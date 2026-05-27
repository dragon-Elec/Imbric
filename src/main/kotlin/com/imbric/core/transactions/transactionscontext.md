# Package Context: transactions

com.imbric.core.transactions
Manages transaction units, pre-flight orchestration, undo/redo state stacks, and debounced/throttled mutation dispatching.

## Rules
- Mutating operations MUST register within transaction units by calling TransactionManager.startTransaction.
- Mutating dispatch loops MUST utilize BulkDispatcher thread limits to avoid OS file descriptor crashes.

## Atomic Notes
- !Pattern: [Pre-flight parallel planning] - Reason: TransferOrchestrator uses async pre-flight checking to pre-plan overwrite and merge actions before launching transaction operations.
- !Decision: [Inverse-based undo cleaning] - Reason: Decouples reversal logic from specific buttons; UndoManager delegates inverse operations back to the backend that executed them.
- !Pattern: [Fuzzy operation re-linking] - Reason: Re-links progress events to pending operations by matching the source URI if a jobId changes during JIT conflict resolution.
- !Decision: [Backend-aware semaphores] - Reason: Throttles local operations to 32 concurrent runs and network operations to 8 concurrent runs to protect bandwidth/system stability.

## Index
- TransactionManager.kt — Core state repository tracking job statuses, progress rates, and triggering commits.
- TransferOrchestrator.kt — Mutator checking pre-flight drive conflicts and resolving sticky decisions.
- TrashManager.kt — Manager coordinating physical file trashing and trashing state triggers.
- UndoManager.kt — Stack manager processing reverse operations via dynamic back-propagation payload mapping.
- TransactionDispatcher.kt — Executor implementing queue semaphores, JIT policy deciders, and 100ms progress limits.
- BulkDispatcher.kt — Trivial. Object storing thread-pool boundaries (32 local, 8 network) to avoid resource exhaustion.
- models/Transaction.kt — Trivial. Data structures detailing transaction operations, statuses, and events.

---

## Audits

### [FILE: TransactionManager.kt] [USABLE]
Role: Core transaction registry keeping operational mappings, progress rates, and triggering batch commits.

/DNA/: [startTransaction -> Transaction(tid) -> addOperation -> commitTransaction -> dispatcher.dispatchJob -> onProgress update OperationStatus pct calculations => em:events]

- SrcDeps: .ifs.BackendRegistry, .ifs.uriName, .ifs.uriJoin, .logic.XferArbiter, .logic.SyncPolicy, .models.UndoAction, .models.TransferProgress, .transactions.TransactionDispatcher, .transactions.models.Transaction, .transactions.models.TransactionOperation, .transactions.models.TransactionStatus, .transactions.models.TransactionEvent
- SysDeps: kotlinx.coroutines{CoroutineScope, Dispatchers}, kotlinx.coroutines.flow{MutableSharedFlow, SharedFlow, asSharedFlow}, java.util.concurrent.ConcurrentHashMap, kotlin.uuid.Uuid

API:
  - TransactionManager:
    - val events: SharedFlow<TransactionEvent>
    - var onTransactionStarted: ((Uuid, String) -> Unit)?
    - var onTransactionFinished: ((Uuid, TransactionStatus) -> Unit)?
    - var onTransactionProgress: ((Uuid, Float) -> Unit)?
    - var onHistoryCommitted: ((Transaction) -> Unit)?
    - fun startTransaction(description: String, isReversible: Boolean = true): Uuid
    - fun addOperation(tid: Uuid, opType: String, src: String, dest: String = "", jobId: Uuid = Uuid.random(), overwrite: Boolean = false, autoRename: Boolean = false, undoAction: UndoAction? = null)
    - fun batchTransfer(sources: List<String>, destDir: String, mode: String = "auto"): Uuid
    - fun commitTransaction(tid: Uuid, conflictResolver: (suspend (ConflictContext) -> ConflictResponse)? = null, policy: SyncPolicy = SyncPolicy.Standard)
    - fun findOperation(tid: Uuid, jobId: Uuid): TransactionOperation?
    - fun getTransferCapabilities(sources: List<String>, dest: String): Map<String, Int>
    - fun cancelTransaction(tid: Uuid)


### [FILE: TransferOrchestrator.kt] [USABLE]
Role: Orchestrator managing parallel pre-flight checking, sticky conflict logic, and action translation.

/DNA/: [planAndExecute -> PlanningSession -> async:planOperation(src) -> classifyConflict -> applyAction(Merge/Overwrite/Rename/Skip/Cancel) -> addOperation(validatedOps) -> commitTransaction]

- SrcDeps: .ifs.BackendRegistry, .ifs.uriName, .ifs.uriJoin, .logic.SyncPolicy, .logic.ConflictContext, .logic.ConflictResponse, .logic.ConflictAction, .logic.XferArbiter, .transactions.TransactionManager, .transactions.models.TransactionEvent
- SysDeps: kotlinx.coroutines{Dispatchers, withContext, async, awaitAll, channelFlow, launch, CancellationException, CoroutineStart}, kotlinx.coroutines.flow{Flow, filter, collect}, kotlinx.coroutines.sync.Mutex, java.util.Collections

API:
  - TransferOrchestrator:
    - fun planAndExecute(sources: List<String>, destDir: String, mode: String = "copy", policy: SyncPolicy = SyncPolicy.Standard, onManualConflict: suspend (ConflictContext) -> ConflictResponse = ...): Flow<TransactionEvent>


### [FILE: TrashManager.kt] [USABLE]
Role: Manager handling multi-threaded trashing, restores, and emptying operations via backend capabilities.

/DNA/: [trashFiles(paths) -> async(BulkDispatcher.Local) { backend.trash(recoverTrashUri=false) } -> awaitAll -> trashState.refresh => TrashResult]

- SrcDeps: .desktop.TrashMonitor, .desktop.TrashStateProvider, .ifs.BackendRegistry, .models.FileJob, .models.TrashItem
- SysDeps: kotlinx.coroutines{CoroutineScope, Dispatchers, coroutineScope, async, awaitAll}, kotlinx.coroutines.flow{StateFlow}

API:
  - TrashManager:
    - val isTrashEmpty: StateFlow<Boolean>
    - suspend fun trashFiles(paths: List<String>): TrashResult
    - suspend fun restoreFromTrash(trashItem: TrashItem): Result<String>
    - suspend fun emptyTrash(): Result<Unit>
    - suspend fun listTrashItems(): List<TrashItem>
    - suspend fun getTrashSize(): Long
    - suspend fun isTrashEmpty(): Boolean
    - fun canTrash(path: String): Boolean
  - TrashResult (data class):
    - val successful: List<String>
    - val failed: List<String>

!Caveat: Sets recoverTrashUri = false in batch requests to avoid N^2 performance bottlenecks in GIO lookups.


### [FILE: UndoManager.kt] [USABLE]
Role: Stack history manager triggering typed inverse mutations back to handling backends.

/DNA/: [undo() -> pop from stack -> map reversed completed op undoAction -> startTransaction(Undo, reversible=false) -> addOperation -> commitTransaction => push to redoStack]

- SrcDeps: .ifs.BackendRegistry, .models.FileJob, .models.UndoAction, .transactions.TransactionManager, .transactions.models.Transaction, .transactions.models.TransactionOperation, .transactions.models.TransactionStatus, .transactions.models.TransactionEvent
- SysDeps: kotlinx.coroutines{CoroutineScope, Dispatchers, launch}, kotlinx.coroutines.flow{filter, filterIsInstance, first}, java.util.Deque, java.util.ArrayDeque

API:
  - UndoManager:
    - var onStackChanged: ((Boolean, Boolean) -> Unit)?
    - var onBusyChanged: ((Boolean) -> Unit)?
    - fun attach()
    - fun canUndo(): Boolean
    - fun canRedo(): Boolean
    - fun getUndoLabel(): String?
    - fun getRedoLabel(): String?
    - fun commitTransaction(tx: Transaction)
    - fun undo(): Boolean
    - fun redo(): Boolean


### [FILE: TransactionDispatcher.kt] [USABLE]
Role: Concurrency dispatcher implementing queues, progress throttling, and JIT policy resolution.

/DNA/: [dispatchJob -> withPermit(semaphore) -> executeSingleJob -> collect copy/move/trash/delete/rename events -> emitThrottledProgress(100ms limit) -> catch VfsError.AlreadyExists -> decide(policy) | conflictResolver => retry | onStatusUpdate]

- SrcDeps: .ifs.BackendRegistry, .ifs.uriParent, .ifs.uriJoin, .logic.XferArbiter, .logic.SyncPolicy, .logic.ConflictContext, .logic.ConflictResponse, .logic.ConflictAction, .models.FileJob, .models.UndoAction, .models.TransferProgress, .models.VfsError, .transactions.models.TransactionOperation, .transactions.models.TransactionStatus
- SysDeps: kotlinx.coroutines{CoroutineScope, Dispatchers, launch, isActive, CancellationException}, kotlinx.coroutines.sync.Semaphore, java.util.concurrent.ConcurrentHashMap

API:
  - TransactionDispatcher:
    - fun dispatchJob(tid: Uuid, op: TransactionOperation, conflictResolver: (suspend (ConflictContext) -> ConflictResponse)?, onProgress: (TransferProgress) -> Unit, onStatusUpdate: (Uuid, TransactionStatus, String, String?, UndoAction?) -> Unit, policy: SyncPolicy = SyncPolicy.Standard)
    - fun cancelJobs(jobIds: List<Uuid>)

!Caveat: Limits progress updates to a 100ms interval to prevent Compose UI lockups on fast transfers.
