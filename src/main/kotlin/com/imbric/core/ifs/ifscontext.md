# Package Context: ifs

com.imbric.core.ifs
Defines virtual file system abstractions, backend registries, performance profiling, and state tracking services.

## Rules
- Avoid manual URI extraction; use IfsUri value class to parse parents, schemes, names, and extensions to prevent errors.
- Always retrieve backend handlers from BackendRegistry instead of allocating concrete backend instances directly.

## Atomic Notes
- !Decision: [Passive latency profiling > static presets] - Reason: Dynamic scaling allows downstream tools (such as thread pools) to adapt to network/physical drive speeds.
- !Pattern: [Flyweight schema routing] - Reason: BackendRegistry delegates VFS operations dynamically to the registered backend best suited to handle the URI scheme.
- !Pattern: [Value class for URIs] - Reason: JvmInline value class IfsUri offers zero-allocation parent/name string calculations to keep listing tight.

## Index
- IOBackend.kt — Virtual file system interface for metadata lookup, streaming reads, watches, and filesystem writes.
- IfsUri.kt — Lightweight inline value class wrapping URI string parsing safely.
- BackendRegistry.kt — Singleton repository mapping URI schemas to registered filesystem IOBackend handlers.
- LatencyProfiler.kt — Timing observe monitor scaling drive latency profiles using halving decay filters.
- services/ThumbnailStateTracker.kt — Spinner status and load path tracker wrapping backend thumbnail methods.
- backends/ — Concrete GIO binding backend implementations. See backendscontext.md.
- provider/ — Live listing registries and folder listing strategies. See providercontext.md.
- BackendCapabilities.kt — Trivial. Model class encapsulating backend locality and capability support flags.
- PathCapabilities.kt — Trivial. Utility helper classifying scheme native/writable/virtual traits.
- FileAction.kt — Trivial. Enum declaring operations checked against permissions before execution.
- FileEvent.kt — Trivial. Sealed classes alerting UI of filesystem modifications.

---

## Audits

### [FILE: IOBackend.kt] [USABLE]
Role: Virtual file system interface defining metadata, reads, deep counts, searches, writes, and undo execution hooks.

/DNA/: [deepCount(uri) -> stack.add(uri) -> list(dirUri).collect { if(info.isDirectory) stack.add(info.uri) else totalSize += info.size } => emit DeepCount] + [search(query) -> manual walk matching name/mime/date/size filters => emit FileInfo]

- SrcDeps: .models.FileInfo, .models.FileJob, .models.TransferProgress, .models.TrashItem, .models.DiskUsage, .models.DeepCount, .models.UndoAction, .models.VfsQuery, .ifs.BackendCapabilities, .ifs.FileAction, .ifs.FileEvent, .ifs.BackendRegistry
- SysDeps: kotlinx.coroutines{Dispatchers, async, awaitAll, withContext, yield}, kotlinx.coroutines.flow{Flow, flow, emptyFlow}

API:
  - IOBackend (interface):
    - val scheme: String
    - val displayName: String
    - fun getCapabilities(uri: String): BackendCapabilities
    - suspend fun canPerform(action: FileAction, uri: String): Boolean
    - fun list(uri: String): Flow<FileInfo>
    - suspend fun getMetadata(uri: String): Result<FileInfo>
    - suspend fun getMetadata(uris: List<String>): List<Result<FileInfo>>
    - fun exists(uri: String): Boolean
    - suspend fun readHeader(uri: String, size: Long): Result<ByteArray>
    - suspend fun enrichMetadata(info: FileInfo): FileInfo
    - suspend fun getUsage(uri: String): Result<DiskUsage?>
    - fun deepCount(uri: String, maxDepth: Int = Int.MAX_VALUE): Flow<DeepCount>
    - suspend fun getThumbnailPath(uri: String): String?
    - suspend fun generateThumbnail(uri: String): Result<String?>
    - suspend fun copy(job: FileJob): Flow<TransferProgress>
    - suspend fun move(job: FileJob): Flow<TransferProgress>
    - suspend fun trash(job: FileJob, recoverTrashUri: Boolean = true): Result<String>
    - suspend fun restoreFromTrash(trashPath: String, originalPath: String): Result<String>
    - suspend fun delete(job: FileJob): Result<Unit>
    - suspend fun createFolder(parentUri: String, name: String): Result<String>
    - suspend fun createFile(parentUri: String, name: String): Result<String>
    - suspend fun rename(uri: String, newName: String): Result<String>
    - suspend fun createLink(targetUri: String, linkUri: String): Result<String>
    - suspend fun addToRecent(uri: String, mimeType: String? = null): Result<Unit>
    - suspend fun removeFromRecent(uri: String): Result<Unit>
    - suspend fun purgeRecent(olderThanMs: Long = 0): Result<Int>
    - suspend fun extractArchive(archiveUri: String, destDirUri: String): Result<String>
    - suspend fun compressArchive(sourceUris: List<String>, destArchiveUri: String): Result<String>
    - suspend fun mountEnclosingVolume(uri: String): Result<Unit>
    - suspend fun unmount(uri: String): Result<Unit>
    - suspend fun executeInverse(payload: UndoAction): Result<Unit>
    - suspend fun listTrash(): Result<List<TrashItem>>
    - suspend fun emptyTrash(): Result<Int>
    - suspend fun isTrashEmpty(uri: String): Boolean
    - fun search(query: VfsQuery): Flow<FileInfo>
    - fun watch(uri: String): Flow<FileEvent>
    - fun canHandle(uri: String): Boolean
    - suspend fun getTrashBackend(registry: BackendRegistry): IOBackend?
  - VfsConflictException (class):
    - val code: Int
    - companion object EXISTS: Int
    - companion object NOT_FOUND: Int
    - companion object WOULD_RECURSE: Int

!Caveat: default list-based getMetadata utilizes capped parallel execution at 10 to avoid system overload.


### [FILE: IfsUri.kt] [USABLE]
Role: Zero-allocation inline value class calculating URI scheme, names, parents, and file extensions.

/DNA/: [IfsUri(uriString) -> trimEnd('/') -> parse indexOf(://) => scheme/parent/name/extension without allocations]

- SrcDeps: (none)
- SysDeps: (none)

API:
  - IfsUri (value class):
    - val scheme: String
    - val isNative: Boolean
    - fun isRootUri(): Boolean
    - val name: String
    - val parent: IfsUri
    - val extension: String
    - val nameWithoutExtension: String
    - fun join(child: String): IfsUri
    - fun renameTarget(newName: String): IfsUri
  - val String.uriName: String
  - val String.uriParent: String
  - fun String.uriJoin(child: String): String


### [FILE: BackendRegistry.kt] [USABLE]
Role: Routing registry mapping URI string structures to corresponding VFS concrete IOBackends.

/DNA/: [getIo(uri) -> if(noScheme) => defaultIo | else try exactMatch or canHandle(uri) => IOBackend]

- SrcDeps: .ifs.IOBackend, .models.FileInfo
- SysDeps: kotlinx.coroutines.flow.Flow

API:
  - BackendRegistry (object):
    - fun registerIo(scheme: String, backend: IOBackend)
    - fun setDefaultIo(backend: IOBackend)
    - fun getDefaultIo(): IOBackend?
    - fun getIo(pathOrUri: String): IOBackend?
    - fun getRegisteredSchemes(): List<String>
    - fun clear()
    - fun list(uri: String): Flow<FileInfo>?
    - suspend fun getMetadata(uri: String): Result<FileInfo>?


### [FILE: LatencyProfiler.kt] [USABLE]
Role: Timing profiler monitoring filesystem latency and applying rolling averaging decay.

/DNA/: [recordSample(scheme, timeMs) -> MountProfile.recordSample -> sampleCount++ -> totalTimeMs += timeMs -> if(count > 20) halving decay]

- SrcDeps: .ifs.LatencyProfile
- SysDeps: java.util.concurrent.ConcurrentHashMap, kotlin.math.max

API:
  - LatencyProfiler (interface):
    - fun recordSample(scheme: String, timeMs: Long)
    - fun getLatency(scheme: String): LatencyProfile
  - PassiveLatencyProfiler:
    - fun setFixed(scheme: String, profile: LatencyProfile)
  - NoopLatencyProfiler:
  - MountProfile:
    - fun recordSample(timeMs: Long)
    - fun getCurrentLatency(): LatencyProfile


### [FILE: services/ThumbnailStateTracker.kt] [USABLE]
Role: Service coordinating thumbnail generation states, error maps, and readiness.

/DNA/: [ensureThumbnail(info) -> if(getThumbnailPath != null) => path | else markInProgress -> backend.generateThumbnail => path | markFailed]

- SrcDeps: .models.FileInfo, .ifs.IOBackend
- SysDeps: kotlinx.coroutines{CoroutineScope, Dispatchers, SupervisorJob}, kotlinx.coroutines.flow{MutableStateFlow, StateFlow, update}

API:
  - ThumbnailStateTracker:
    - val thumbnailingInProgress: StateFlow<Set<String>>
    - val thumbnailingFailed: StateFlow<Set<String>>
    - fun canThumbnail(info: FileInfo): Boolean
    - fun isCurrentlyThumbnailing(uri: String): Boolean
    - fun hasFailed(uri: String): Boolean
    - suspend fun ensureThumbnail(info: FileInfo): String?
    - fun clearFailedState(uri: String)
    - fun clearAllState()
