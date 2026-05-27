# Package Context: core

com.imbric.core
Bootstraps GNOME desktop integrations, coordinates VFS backends, registers system file monitors, and holds stateless conflict transfer logic.

## Rules
- Inject interfaces (e.g. StarredStateProvider, TrashStateProvider) as defaults in constructors to allow unit tests to bypass native systems.
- Logic engines (XferArbiter, Validation) must remain side-effect-free, executing solely on immutable metadata structures.

## Atomic Notes
- !Pattern: [DI Pattern for Singletons] - Reason: Production default parameters invoke native singleton providers (e.g. TrashMonitor.getInstance()) while test suites pass fakes.
- !Decision: [Bidirectional GTK JSON Sync] - Reason: Persists bookmarks in standard JSON formatting under ~/.config/imbric/ while syncing ~/.config/gtk-3.0/ to interoperate with Nautilus.
- !Decision: [Pure stateless logic DNA] - Reason: Keeping filesystem checks (FAT rules, Rsync-lite decisions) stateless ensures unit test stability and zero performance overhead.

## Index
- desktop/ImbricDesktop.kt — Setup bootloader registering standard, trash, recent, and tracker3 search backends.
- logic/XferArbiter.kt — Rsync-lite engine classifying conflicts and deciding merge, overwrite, rename, or skip outcomes.
- logic/Validation.kt — Filename component validator enforcing FAT/NTFS filename character rules.
- desktop/ — OS hardware volume mount managers, theme detectors, starred file managers, and system bookmarks sync logic. See desktopcontext.md.
- models/ — Package enclosing shared immutable data contracts (FileInfo, FileJob, TrashItem, UndoAction, VfsError).
- ifs/ — Virtual filesystem routing and directory registry. See ifscontext.md.
- transactions/ — Concurrency-controlled transactional operations. See transactionscontext.md.

---

## Audits

### [FILE: ImbricDesktop.kt] [USABLE]
Role: Bootstrap entry point registering core VFS GIO backend schemes.

/DNA/: [initialize() -> register file/trash/smb/sftp GIO backends -> register recent/search specialized backends -> setDefaultIo => BackendRegistry]

- SrcDeps: .ifs.BackendRegistry, .ifs.backends.GioBackend, .ifs.backends.GioRecentBackend, .ifs.backends.GioSearchBackend
- SysDeps: (none)

API:
  - ImbricDesktop (object):
    - fun initialize()


### [FILE: XferArbiter.kt] [USABLE]
Role: Stateless decision arbiter resolving copy/move filesystem collisions.

/DNA/: [decide(src, dest, policy) -> if(src.isDirectory && dest.isDirectory) => ConflictAction.Merge | else policy.decide(src, dest)] + [isModified(src, dest) -> if(size != size) => true | if(mtime > dest.mtime || diff > 2000ms) => true | else false]

- SrcDeps: .ifs.uriParent, .models.FileInfo
- SysDeps: kotlin.math.abs

API:
  - ConflictAction (sealed class):
    - Overwrite:
    - Merge:
    - Skip:
    - Rename(newName: String):
    - AutoRename:
    - Prompt:
    - Cancel:
  - SyncPolicy (interface):
    - var applyToAllIdentical: Boolean
    - var applyToAllDifferent: Boolean
    - var applyToAllFolders: Boolean
    - fun decide(src: FileInfo, dest: FileInfo): ConflictAction
    - companion object AlwaysOverwrite: SyncPolicy
    - companion object AlwaysSkip: SyncPolicy
    - companion object ModifiedOnly: SyncPolicy
    - companion object AutoRename: SyncPolicy
    - companion object Standard: SyncPolicy
    - companion object custom(resolver: (FileInfo, FileInfo) -> ConflictAction): SyncPolicy
  - BaseSyncPolicy (abstract class):
    - var applyToAllIdentical: Boolean
    - var applyToAllDifferent: Boolean
    - var applyToAllFolders: Boolean
  - AlwaysOverwritePolicy (class):
    - fun decide(src: FileInfo, dest: FileInfo): ConflictAction
  - AlwaysSkipPolicy (class):
    - fun decide(src: FileInfo, dest: FileInfo): ConflictAction
  - ModifiedOnlyPolicy (class):
    - fun decide(src: FileInfo, dest: FileInfo): ConflictAction
  - AutoRenamePolicy (class):
    - fun decide(src: FileInfo, dest: FileInfo): ConflictAction
  - StandardPolicy (class):
    - fun decide(src: FileInfo, dest: FileInfo): ConflictAction
  - XferArbiter (object):
    - fun decide(src: FileInfo, dest: FileInfo, policy: SyncPolicy): ConflictAction
    - fun generateNewName(original: String): String
    - fun classifyConflict(src: FileInfo, dest: FileInfo): ConflictType
    - fun canOverwrite(src: FileInfo, dest: FileInfo): Boolean
    - fun isSameContent(src: FileInfo, dest: FileInfo): Boolean
  - ConflictResponse (data class):
    - val action: ConflictAction
    - val applyToAll: Boolean
  - enum class ConflictType: IDENTICAL_FILE, DIFFERENT_FILE, DIRECTORY_MERGE, FOLDER_REPLACE_FILE, FILE_REPLACE_FOLDER
  - ConflictContext (data class):
    - val src: String
    - val dest: String
    - val srcMeta: FileInfo
    - val destMeta: FileInfo
    - val type: ConflictType


### [FILE: Validation.kt] [USABLE]
Role: Component-level validator checking character constraints on FAT filesystem components.

/DNA/: [isValidComponentName(name) -> if(isBlank || name == . || name == ..) => false | else none { it in FAT_FORBIDDEN_CHARACTERS }]

- SrcDeps: (none)
- SysDeps: (none)

API:
  - val FAT_FORBIDDEN_CHARACTERS: String
  - fun isValidComponentName(name: String): Boolean
  - fun findForbiddenChars(name: String): Set<Char>
