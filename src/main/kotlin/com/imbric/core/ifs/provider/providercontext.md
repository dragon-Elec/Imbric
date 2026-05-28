# Package Context: provider

com.imbric.core.ifs.provider
Tracks live directory state lists, manages flyweight caching of folders, and handles composition-based list strategies.

## Rules
- Viewing layers/ViewModels MUST call destroy() on DirState when navigating away to release coroutine supervisor scopes.
- Cache lookups MUST go through DirStateRegistry to maintain single-instance-per-URI properties across the core.

## Atomic Notes
- !Pattern: [Debounced Event Storms] - Reason: Avoid UI blocking when hundreds of GIO signals fire during large batch copies. Delays 200ms before batch fetching.
- !Decision: [Flyweight weak caches] - Reason: Avoids duplicate GIO watch and FFM memory allocation overheads by retaining active directories via WeakReference.
- !Pattern: [Composition-based directory strategy] - Reason: Decouples view strategies (Standard, Starred, Search, Virtual) from DirState using ListingStrategy sealed interfaces instead of class inheritance.

## Index
- DirState.kt — State coordinator managing folder listings, live monitor subscriptions, and background metadata enrichment.
- DirStateRegistry.kt — Cache repository managing flyweight directory instances using ConcurrentHashMap and WeakReferences.
- ListingStrategy.kt — Polymorphic strategies defining how data list providers query files (GIO walk, star bookmarks, CLI query).
- DirectoryType.kt — Sealed enum classifying virtual/physical directories by their scheme without backend dependencies.

---

## Audits

### [FILE: DirState.kt] [USABLE]
Role: Coordinates initial batch loading, active signal monitoring, and async deep metadata enrichment for a directory.

/DNA/: [refreshJob.cancelAndJoin() -> strategy.list(backend) -> chunked(50) -> updateAndGet(_items) -> em:_itemsList -> launch(ioDispatcher) { backend.enrichMetadata(info) => updateItem() }]

- SrcDeps: .ifs.IOBackend, .ifs.FileEvent, .ifs.provider.ListingStrategy, .ifs.provider.DirectoryType, .models.FileInfo, .models.DeepCount
- SysDeps: kotlinx.coroutines{CoroutineScope, SupervisorJob, Job, launch, delay, cancelAndJoin, isActive, yield}, kotlinx.coroutines.flow{MutableStateFlow, StateFlow, filter, take, mapNotNull}, java.util.Collections, java.util.concurrent.atomic.AtomicBoolean

API:
  - DirState:
    - val uri: String
    - val items: StateFlow<List<FileInfo>>
    - val isLoading: StateFlow<Boolean>
    - val loadError: StateFlow<Exception?>
    - val directoryType: DirectoryType
    - val isDestroyedState: Boolean
    - val isNotEmpty: Boolean
    - var pipelineTimer: PipelineTimer?
    - fun refresh()
    - fun onActive()
    - fun stop()
    - fun destroy()
    - fun containsFile(uri: String): Boolean
    - fun getFileByName(name: String): FileInfo?
    - fun matchPattern(pattern: String): List<FileInfo>
    - fun whenReady(predicate: (List<FileInfo>) -> Boolean): Flow<List<FileInfo>>
    - fun whenEnriched(uri: String): Flow<FileInfo>

!Caveat: Suspend lambdas capture a strong reference to DirState, meaning weak-cached instances will leak unless destroy() is explicitly called to cancel the supervisor job.


### [FILE: DirStateRegistry.kt] [USABLE]
Role: Cache manager storing and resolving unique DirState singletons using WeakReference caches.

/DNA/: [getOrCreate(uri) -> ConcurrentHashMap.computeIfAbsent(uri, {WeakReference(DirState)}) -> if(state == null || state.isDestroyedState) remove(uri) -> retry up to 3 times]

- SrcDeps: .ifs.IOBackend, .ifs.provider.DirState
- SysDeps: java.lang.ref.WeakReference, java.util.concurrent.ConcurrentHashMap, java.util.concurrent.atomic.AtomicInteger, kotlinx.coroutines.CoroutineScope

API:
  - DirStateRegistry:
    - val size: Int
    - var pipelineTimer: PipelineTimer?
    - fun getOrCreate(uri: String): DirState
    - fun contains(uri: String): Boolean
    - fun remove(uri: String)
    - fun clear()

!Caveat: Sweeps and removes dead garbage-collected WeakReference caches opportunistically every 100 directory accesses.


### [FILE: ListingStrategy.kt] [USABLE]
Role: Encapsulates VFS, starred, search, and static virtual listing providers.

/DNA/: [sealed ListingStrategy -> list(backend, uri) => Flow<FileInfo> | watchable() => Boolean]

- SrcDeps: .desktop.StarredManager, .models.FileInfo, .models.VfsQuery, .ifs.IOBackend
- SysDeps: kotlinx.coroutines.flow{Flow, flow}

API:
  - ListingStrategy:
    - data object Standard:
    - data class Search(val query: VfsQuery):
    - data class Starred(val starredManager: StarredManager):
    - data class Virtual(val items: List<FileInfo>):


### [FILE: DirectoryType.kt] [USABLE]
Role: Enum classification indicating if a directory is physical, trash, recent, starred, or network-bound.

/DNA/: [DirectoryType.fromUri(uri) -> parse scheme (trash/recent/starred/search/smb/sftp/file) => DirectoryType]

- SrcDeps: (none)
- SysDeps: (none)

API:
  - DirectoryType (enum):
    - REGULAR, TRASH, RECENT, STARRED, SEARCH, NETWORK, OTHER
