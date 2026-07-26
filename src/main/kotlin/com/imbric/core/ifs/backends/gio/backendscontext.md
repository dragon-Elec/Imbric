# Package Context: backends

com.imbric.core.ifs.backends
Provides concrete Virtual File System (VFS) backends wrapping GNOME GIO via java-gi Foreign Function & Memory (FFM) bindings.

## Rules
- GIO FFM invocations must have a running GMainContext pump on some thread to fire async callbacks.
- Mutating operations must use GioCoroutineBridge.awaitGioAsync for cooperative cancellation and memory-safe callback arenas.

## Atomic Notes
- !Decision: [GLib BookmarkFile > GTK RecentManager] - Reason: Avoid display manager connection (GLFW vs GDK) conflict inside shared JVM process.
- !Pattern: [universal bridge via awaitGioAsync] - Reason: Standardizes async-to-suspend calls with Cancellable and idle-task garbage collection protection.
- !Pattern: [isolated type mappers] - Reason: Isolates GIO FFM models and Imbric platform models to avoid namespace collision and keep backend code clean.
- !Decision: [Tracker3 CLI via ProcessBuilder] - Reason: Native tracker-sparql bindings are complex and unstable; CLI is robust and easy to parse.

## Index
- GioBackend.kt — Direct GIO-native implementations of all VFS read/write operations and thumbnail generation.
- GioRecentBackend.kt — Read-only bookmark-driven representation of virtual recent:/// filesystem space.
- GioSearchBackend.kt — Hybrid desktop search backend utilizing tracker3 CLI with manual DFS walk fallback.
- GioCoroutineBridge.kt — FFM-to-Coroutine adapter with lifecycle pinning and GLib event pump daemon.
- GioTypeMappers.kt — Conversions mapping GIO FileInfo objects to immutable Imbric FileInfo data models.

---

## Audits

### [FILE: GioBackend.kt] [USABLE]
Role: Direct GIO-native implementation of standard, trash, recent, and virtual VFS interactions.

/DNA/: [call:File.newForUri(uri) -> awaitGioAsync(cancellable, callback) -> src.copyAsync/moveAsync => src.copyFinish/moveFinish -> emit TransferProgress | if(WouldRecurse) call:copyRecursive/deleteRecursive]

- SrcDeps: .ifs.IOBackend, .ifs.LatencyProfiler, .ifs.backends.GioTypeMappers, .ifs.backends.GioCoroutineBridge, .models.FileInfo, .models.FileJob, .models.TransferProgress, .models.VfsError, .logic.XferArbiter
- SysDeps: kotlinx.coroutines{Dispatchers, flow, flowOn, withContext, channelFlow}, org.gnome.gio{File, FileQueryInfoFlags, FileType, FileCopyFlags, FileProgressCallback}, org.gnome.gdkpixbuf.PixbufLoader, org.gnome.glib{KeyFile, KeyFileFlags, GLib}

API:
  - GioBackend:
    - fun getCapabilities(uri: String): BackendCapabilities
    - suspend fun canPerform(action: FileAction, uri: String): Boolean
    - fun canHandle(uri: String): Boolean
    - fun list(uri: String): Flow<FileInfo>
    - suspend fun getMetadata(uri: String): Result<FileInfo>
    - suspend fun copy(job: FileJob): Flow<TransferProgress>
    - suspend fun move(job: FileJob): Flow<TransferProgress>
    - suspend fun restoreFromTrash(trashPath: String, originalPath: String): Result<String>
    - suspend fun listTrash(): Result<List<TrashItem>>
    - suspend fun emptyTrash(): Result<Int>
    - suspend fun isTrashEmpty(uri: String): Boolean
    - suspend fun createFolder(parentUri: String, name: String): Result<String>
    - suspend fun createFile(parentUri: String, name: String): Result<String>
    - suspend fun rename(uri: String, newName: String): Result<String>
    - suspend fun createLink(targetUri: String, linkUri: String): Result<String>
    - suspend fun extractArchive(archiveUri: String, destDirUri: String): Result<String>
    - suspend fun compressArchive(sourceUris: List<String>, destArchiveUri: String): Result<String>
    - suspend fun mountEnclosingVolume(uri: String): Result<Unit>
    - suspend fun unmount(uri: String): Result<Unit>
    - suspend fun trash(job: FileJob, recoverTrashUri: Boolean): Result<String>
    - suspend fun delete(job: FileJob): Result<Unit>
    - suspend fun executeInverse(payload: UndoAction): Result<Unit>
    - fun watch(uri: String): Flow<FileEvent>
    - fun exists(uri: String): Boolean
    - fun search(query: VfsQuery): Flow<FileInfo>
    - suspend fun readHeader(uri: String, size: Long): Result<ByteArray>
    - suspend fun enrichMetadata(info: FileInfo): FileInfo
    - suspend fun getThumbnailPath(uri: String): String?
    - suspend fun generateThumbnail(uri: String): Result<String?>
    - suspend fun getUsage(uri: String): Result<DiskUsage?>

!Caveat: Must call org.gnome.gio.Gio.javagi$ensureInitialized() and GdkPixbuf.javagi$ensureInitialized() in init block.
!Caveat: Large transfers and complex operations check and trigger recursive fallback if WouldRecurse is caught.


### [FILE: GioRecentBackend.kt] [USABLE]
Role: Virtual directory list provider based on the shared system recently-used.xbel file.

/DNA/: [bookmarkFile.loadFromFile(getRecentFilePath) -> uris.forEach { File.newForUri(item) -> gfile.queryInfo => emit mapped FileInfo }]

- SrcDeps: .ifs.IOBackend, .ifs.backends.GioTypeMappers, .models.FileInfo, .models.FileJob, .models.TransferProgress
- SysDeps: org.gnome.gio{File, FileQueryInfoFlags}, org.gnome.glib{BookmarkFile, GLib}, kotlinx.coroutines{Dispatchers, flowOn}

API:
  - GioRecentBackend:
    - fun list(uri: String): Flow<FileInfo>
    - fun exists(uri: String): Boolean
    - suspend fun addToRecent(uri: String, mimeType: String?): Result<Unit>
    - suspend fun removeFromRecent(uri: String): Result<Unit>
    - suspend fun purgeRecent(olderThanMs: Long): Result<Int>

!Caveat: Avoids all display manager connection issues by parsing Bookmarks XML instead of invoking GTK RecentManager.


### [FILE: GioSearchBackend.kt] [USABLE]
Role: Search provider prioritizing GNOME Tracker3 indexing daemon with VFS walking fallback.

/DNA/: [ProcessBuilder(tracker3, search, query.text) -> readLine() -> if(startsWith(file://)) emit uri -> if(trackerSuccess) getMetadata(uri) => emit | else manual fallback.search(query)]

- SrcDeps: .ifs.IOBackend, .ifs.backends.GioBackend, .models.FileInfo, .models.VfsQuery
- SysDeps: kotlinx.coroutines{Dispatchers, flow, flowOn, yield}, java.io{BufferedReader, InputStreamReader}

API:
  - GioSearchBackend:
    - fun list(uri: String): Flow<FileInfo>
    - fun search(query: VfsQuery): Flow<FileInfo>

!Caveat: Command-line tracker3 search queries are sensitive to user-level indexing status and permissions.


### [FILE: GioCoroutineBridge.kt] [USABLE]
Role: Low-level GLib main context runner and safe async callback-to-suspension bridge.

/DNA/: [suspendCancellableCoroutine -> Cancellable() -> AsyncReadyCallback { if(cont.isActive) cont.resume(finish) } -> GLib.idleAdd { block(cancellable, callback) } -> cont.invokeOnCancellation { cancellable.cancel() + Source.remove(idleSourceId) }]

- SrcDeps: (none)
- SysDeps: org.gnome.gio{AsyncReadyCallback, AsyncResult, Cancellable}, org.gnome.glib{GLib, MainContext, Source}, kotlinx.coroutines{suspendCancellableCoroutine, CoroutineScope, withTimeout}

API:
  - GioCoroutineBridge:
    - fun startMainContextPump(scope: CoroutineScope)
    - suspend fun <T> awaitGioAsync(block: (Cancellable, AsyncReadyCallback) -> Unit, finish: (AsyncResult) -> T, timeoutMs: Long? = null): T

!Caveat: Pinnned keepAliveCallback keeps native function upcall pointers from getting garbage collected while suspended, avoiding fatal SIGSEGV.


### [FILE: GioTypeMappers.kt] [USABLE]
Role: Map compiler for translating between GIO and Imbric internal type models.

/DNA/: [toImbricFileInfo(gfile, gioInfo) -> resolve standard, unix, access, owner attributes -> determine location flags (trash, recent, remote) -> extract attributes map => FileInfo]

- SrcDeps: .models.FileInfo, .models.PathType
- SysDeps: org.gnome.gio{File, FileInfo, FileType, FileAttributeType, ThemedIcon}, kotlinx.datetime.Instant

API:
  - GioTypeMappers:
    - fun toImbricFileInfo(gfile: File, gioInfo: org.gnome.gio.FileInfo, backendId: String = "gio"): FileInfo
