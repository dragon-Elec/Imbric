---
description: Context Router for com.imbric.core.models package. Contains shared immutable data contracts and VFS models.
---

# Models Package Context

## Identity
- Package: `com.imbric.core.models`
- Purpose: Headless, unopinionated, immutable data contracts and domain models for the Virtual File System (VFS).

## Rules
- All models MUST be immutable (`val` only, no `var`).
- No platform-specific dependencies (e.g., GIO, GLFW, Compose) allowed in this package.
- Use `kotlin.uuid.Uuid` for unique identifiers.

## Atomic Notes
- `!Decision: [Immutable Data Contracts] - Reason: Ensures thread safety across concurrent VFS operations and transaction pipelines.`
- `!Pattern: [Sealed Class Hierarchies] - Reason: Used for algebraic types like VfsError and UndoAction to enforce exhaustive compile-time checks.`

## Index
- FileInfo.kt — Comprehensive metadata model for files and directories with computed properties.
- FileJob.kt — Atomic unit of work describing copy/move/trash/rename operations and cancellation tokens.
- UndoAction.kt — Sealed interface defining how to reverse completed file operations.
- VfsError.kt — Sealed class hierarchy representing typed VFS errors mapped from GIO/IOErrorEnum.
- Bookmark.kt — Trivial. User-saved location data contract.
- DeepCount.kt — Trivial. Intermediate and final results of recursive directory counting.
- DiskUsage.kt — Trivial. Storage capacity and usage metrics.
- PathType.kt — Trivial. Enum categorizing physical, virtual, or synthetic paths.
- TrashItem.kt — Trivial. Metadata for items in the trash bin.

---

## Audits

### [FILE: FileInfo.kt] [USABLE]
Role: Comprehensive metadata model for files and directories with computed properties.

/DNA/: [FileInfo(id, nativeId, name, path, uri, ...) -> isVisiblyHidden(showHiddenFiles) => Boolean] + [matches(pattern) -> compileGlob(pattern) => Regex] + [isArchive => Boolean derived from mimeType] + [isLaunchable => Boolean derived from mimeType/isExecutable/activationUri] + [permissionsString => Unix-style rwxrwxrwx string] + [humanReadableSize => formatted size string]

- SrcDeps: .models.PathType
- SysDeps: kotlinx.datetime.Instant, kotlin.uuid.Uuid

API:
  - FileInfo:
    - val id: Uuid
    - val nativeId: String?
    - val name: String
    - val path: String
    - val uri: String
    - val pathType: PathType
    - val displayName: String
    - val isDirectory: Boolean
    - val isSymlink: Boolean
    - val symlinkTarget: String?
    - val size: Long
    - val mimeType: String
    - val modifiedTime: Instant?
    - val accessedTime: Instant?
    - val createdTime: Instant?
    - val isHidden: Boolean
    - val isReadable: Boolean
    - val isWritable: Boolean
    - val isExecutable: Boolean
    - val permissions: String
    - val owner: String
    - val group: String
    - val childCount: Int
    - val iconName: String?
    - val thumbnailPath: String?
    - val backendId: String?
    - val trashTime: Instant?
    - val recency: Instant?
    - val isStarred: Boolean
    - val activationUri: String?
    - val isInTrash: Boolean
    - val isInRecent: Boolean
    - val isRemote: Boolean
    - val canMount: Boolean
    - val canUnmount: Boolean
    - val canEject: Boolean
    - val selinuxContext: String?
    - val attributes: Map<String, Any?>
    - isVisiblyHidden(showHiddenFiles: Boolean): Boolean
    - shouldShow(showHiddenFiles: Boolean): Boolean
    - matches(pattern: String): Boolean
    - val extension: String
    - val isEmptyDirectory: Boolean
    - val isArchive: Boolean
    - val isLaunchable: Boolean
    - val permissionsString: String
    - val humanReadableSize: String
    - getMetadata(key: String): String?
    - getMetadataInt(key: String): Int?
    - getMetadataBool(key: String): Boolean?
    - getMetadataKeys(prefix: String): List<String>
    - companion object SortByName: Comparator<FileInfo>
    - companion object SortBySize: Comparator<FileInfo>
    - companion object SortByDate: Comparator<FileInfo>
    - companion object SortByTrashTime: Comparator<FileInfo>
    - companion object SortByRecency: Comparator<FileInfo>
    - companion object compileGlob(pattern: String): Regex
!Caveat: Uses experimental `kotlin.uuid.Uuid` requiring `@file:OptIn(ExperimentalUuidApi::class)`.

### [FILE: FileJob.kt] [USABLE]
Role: Atomic unit of work describing copy/move/trash/rename operations and cancellation tokens.

/DNA/: [FileJob(id, opType, source, dest, ...) -> inversePayload => UndoAction] + [CancellationToken -> cancel() -> _isCancelled = true] + [VfsQuery -> structured search parameters] + [TransferProgress -> progress update for ongoing operations]

- SrcDeps: .models.UndoAction
- SysDeps: kotlin.uuid.Uuid

API:
  - FileJob:
    - val id: Uuid
    - val opType: String
    - val source: String
    - val dest: String
    - val overwrite: Boolean
    - val autoRename: Boolean
    - val uiRefreshRateMs: Int
    - val haltOnError: Boolean
    - val inversePayload: UndoAction?
  - CancellationToken:
    - val isCancelled: Boolean
    - fun cancel(): Unit
  - VfsQuery:
    - val text: String
    - val rootUri: String
    - val mimeFilter: String?
    - val recursive: Boolean
    - val includeHidden: Boolean
    - val maxDepth: Int
    - val contentSearch: Boolean
    - val onScanned: ((Int) -> Unit)?
    - val modifiedAfter: Long?
    - val modifiedBefore: Long?
    - val minSize: Long?
    - val maxSize: Long?
    - val starredOnly: Boolean
  - TransferProgress:
    - val jobId: Uuid
    - val currentFile: String
    - val actualDest: String?
    - val inversePayload: UndoAction?
    - val completedCount: Int
    - val totalCount: Int
    - val completedSize: Long
    - val totalSize: Long
!Caveat: CancellationToken is an open class with a private backing field and custom getter.

### [FILE: UndoAction.kt] [USABLE]
Role: Sealed interface defining how to reverse completed file operations.

/DNA/: [UndoAction -> sealed interface] + [TransferUndo -> delete dest or move back to source] + [TrashUndo -> restore from trash to original location] + [CreateUndo -> delete created file/folder] + [RenameUndo -> rename back to original name]

- SrcDeps: 
- SysDeps: kotlin.uuid.Uuid

API:
  - UndoAction:
    - val undoLabel: String
    - val itemDescription: String
  - TransferUndo:
    - val destinations: List<String>
    - val sources: List<String>?
    - val srcDir: String?
    - val backendId: String?
  - TrashUndo:
    - val trashedUris: List<String>
    - val originalUris: List<String>
    - val backendId: String?
  - CreateUndo:
    - val createdUri: String
    - val backendId: String?
  - RenameUndo:
    - val currentUri: String
    - val originalUri: String
    - val currentName: String
    - val originalName: String
    - val backendId: String?
!Caveat: Variants are based on HOW the action is reversed (delete, move back, restore, rename), not WHAT button the user clicked.

### [FILE: VfsError.kt] [USABLE]
Role: Sealed class hierarchy representing typed VFS errors mapped from GIO/IOErrorEnum.

/DNA/: [VfsError(message, cause) -> sealed class] + [AlreadyExists | NotFound | WouldRecurse | PermissionDenied | InvalidName | NoSpace | ReadOnly | Cancelled | NotSupported | IsDirectory | NotDirectory | Busy | IoError => typed exceptions with URI context]

- SrcDeps: 
- SysDeps: 

API:
  - VfsError:
    - val message: String
    - val cause: Throwable?
  - AlreadyExists: val uri: String
  - NotFound: val uri: String
  - WouldRecurse: val uri: String
  - PermissionDenied: val uri: String
  - InvalidName: val name: String, val forbiddenChars: Set<Char>
  - NoSpace: val uri: String
  - ReadOnly: val uri: String
  - Cancelled: val uri: String
  - NotSupported: val uri: String
  - IsDirectory: val uri: String
  - NotDirectory: val uri: String
  - Busy: val uri: String
  - IoError: val uri: String
!Caveat: All variants carry the URI context to allow the app layer to produce localized, user-friendly error messages.
