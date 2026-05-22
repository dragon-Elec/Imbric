# ImbricFS Handover Document

## Project Identity
- **Name:** ImbricFS ("Imbric")
- **Root Package:** `com.imbric`
- **Core VFS abstraction:** `ifs`
- **Language:** Kotlin 2.3.20+ (K2 compiler) on **Kotlin/JVM** (not Kotlin/Native)
- **JVM target:** JDK 25
- **Build system:** Gradle 9.5.1
- **UI Strategy:** Compose Multiplatform (Kotlin) — **not GTK**

## Repository
- Path: `/home/ray/Desktop/files/wrk/Imbric/imbric-kt`
- Standalone Git repo (no shared history with Python original)
- 71 commits on `main`
- **Test count:** 188 passing

---

## Project File Structure

```
imbric-kt/
├── AGENTS.md                           # Agent instructions (architecture, build, conventions)
├── HANDOVER.md                         # THIS FILE
├── build.gradle.kts                    # Gradle build config (JDK 25, sourceSets for bindings)
├── gradle.properties                   # Clean — no hardcoded JDK path (Gradle Toolchains handles it)
├── scripts/
│   ├── generate_bindings.sh            # 5-step binding pipeline (dynamic paths, no hardcoded /home/ray)
│   └── filter_gradle.py               # Test output filter: . for PASSED, full block for FAILED
├── src/main/kotlin/com/imbric/
│   ├── core/
│   │   ├── ifs/                        # VFS abstraction layer
│   │   │   ├── IOBackend.kt            # Interface: list/copy/move/trash/rename/getMetadata/deepCount/thumbnail
│   │   │   ├── BackendCapabilities.kt  # Capabilities & locality flags
│   │   │   ├── BackendRegistry.kt      # URI scheme → backend router
│   │   │   ├── IfsUri.kt              # URI parsing with scheme/root detection
│   │   │   ├── VfsError.kt            # Sealed class hierarchy (AlreadyExists, NotFound, PermissionDenied, etc.)
│   │   │   ├── FileAction.kt          # File action types
│   │   │   ├── FileEvent.kt           # File system event types
│   │   │   ├── PathCapabilities.kt    # Per-path capability inspection
│   │   │   ├── LatencyProfiler.kt     # Performance monitoring
│   │   │   ├── backends/
│   │   │   │   ├── GioBackend.kt      # GIO implementation — all ops use awaitGioAsync
│   │   │   │   ├── GioCoroutineBridge.kt  # GLib MainContext pump + suspendCancellableCoroutine
│   │   │   │   ├── GioSearchBackend.kt    # Tracker3 + manual fallback search
│   │   │   │   ├── GioRecentBackend.kt    # recent:/// backend
│   │   │   │   └── GioTypeMappers.kt     # GIO ↔ Imbric attribute mapping
│   │   │   ├── provider/
│   │   │   │   ├── DirState.kt        # Live directory state (StateFlow, enrichment, readiness)
│   │   │   │   ├── DirStateRegistry.kt # WeakReference shared DirState cache
│   │   │   │   ├── DirectoryType.kt   # Enum: STANDARD, SEARCH, STARRED, VIRTUAL
│   │   │   │   └── ListingStrategy.kt # Sealed interface: Standard, Search, Starred, Virtual
│   │   │   └── services/
│   │   │       └── ThumbnailStateTracker.kt  # StateFlow thumbnail tracking
│   │   ├── transactions/               # Mutating operations hub
│   │   │   ├── TransactionManager.kt   # Batch lifecycle, conflict hooks
│   │   │   ├── TransactionDispatcher.kt # Backend-aware concurrency (Local: 32, Network: 8)
│   │   │   ├── TransferOrchestrator.kt # Recursive pre-flight, sticky conflict resolution
│   │   │   ├── BulkDispatcher.kt       # Concurrent I/O with limitedParallelism
│   │   │   ├── UndoManager.kt          # Stack-based undo/redo
│   │   │   ├── TrashManager.kt         # Trash lifecycle, StateFlow tracking
│   │   │   └── models/
│   │   │       └── Transaction.kt      # Transaction data model
│   │   ├── logic/
│   │   │   ├── XferArbiter.kt          # ConflictAction + SyncPolicy interface + resolve()
│   │   │   └── Validation.kt          # FAT_FORBIDDEN_CHARACTERS, isValidComponentName
│   │   ├── models/
│   │   │   ├── FileInfo.kt            # 20+ fields: timestamps, flags, visibility, sort, permissions
│   │   │   ├── FileJob.kt             # Atomic work unit + TransferProgress
│   │   │   ├── TrashItem.kt           # Trash bin item metadata
│   │   │   ├── Bookmark.kt            # Bookmark data class (name, uri, label, icon)
│   │   │   ├── DeepCount.kt           # Recursive directory count
│   │   │   ├── DiskUsage.kt           # Disk usage model
│   │   │   ├── PathType.kt            # PHYSICAL, VIRTUAL
│   │   │   ├── UndoAction.kt          # Sealed interface: TransferUndo, TrashUndo, RenameUndo, CreateUndo, MetadataUndo
│   │   │   └── VfsError.kt           # (see ifs/)
│   │   └── desktop/                    # Global system state (no URI required)
│   │       ├── DeviceManager.kt       # Hardware drives/volumes via GVolumeMonitor
│   │       ├── DesktopEnvironment.kt  # Interface for hardware mounts
│   │       ├── GioDesktopEnvironment.kt # GIO implementation
│   │       ├── TrashMonitor.kt        # Real-time GFileMonitor on trash:///
│   │       ├── TrashStateProvider.kt  # Injectable interface (testability)
│   │       ├── StarredManager.kt      # System-wide starred file tracking
│   │       ├── StarredStateProvider.kt # Injectable interface
│   │       ├── BookmarkList.kt        # JSON + GTK bidirectional sync
│   │       ├── SettingsProvider.kt    # GSettings interface
│   │       ├── GioSettingsProvider.kt # GIO implementation
│   │       ├── DesktopLink.kt         # .desktop file handling
│   │       ├── DesktopLinkProvider.kt # Desktop link provider
│   │       ├── DesktopLinkMonitor.kt  # Desktop link monitoring
│   │       ├── DesktopDirectory.kt    # XDG desktop directory
│   │       ├── SandboxDetector.kt     # Flatpak/sandbox detection
│   │       └── ImbricDesktop.kt       # Desktop integration coordinator
│   └── app/                            # Application layer (not started)
│       └── bootstrap/
│           ├── Main.kt                # Entry point
│           └── MainContextPump.kt     # GLib MainContext iteration pump
├── src/test/kotlin/com/imbric/core/   # 188 tests
│   ├── ifs/
│   │   ├── IOBackendTest.kt
│   │   ├── backends/
│   │   │   ├── GioBackendAsyncTest.kt
│   │   │   ├── GioSearchBackendTest.kt
│   │   │   └── VfsQueryFilterTest.kt
│   │   ├── provider/
│   │   │   ├── DirStateTest.kt
│   │   │   └── DirectoryTypeTest.kt
│   │   └── services/
│   │       └── ThumbnailStateTrackerTest.kt
│   ├── models/
│   │   ├── FileInfoTest.kt
│   │   ├── FileJobTest.kt
│   │   └── VfsQueryTest.kt
│   ├── transactions/
│   │   ├── TransferOrchestratorTest.kt
│   │   ├── UndoManagerTest.kt
│   │   └── HardeningIntegrationTest.kt
│   ├── desktop/
│   │   ├── DeviceManagerTest.kt
│   │   ├── DesktopDirectoryTest.kt
│   │   ├── ImbricDesktopTest.kt
│   │   └── backends/
│   │       ├── GioRecentBackendTest.kt
│   │       └── GioRecentBackendBenchmark.kt
│   └── testing/
│       ├── InMemoryBackend.kt         # HashMap-based test double
│       ├── InMemoryBackendContractTest.kt
│       ├── GioBackendContractTest.kt   # Ensures both backends behave identically
│       └── BashHelper.kt             # Bash script helper for complex filesystem state setup
└── ref/                                # Reference documentation (untracked)
    ├── java-gi_patched/                # Patched java-gi generator (tracked in git)
    │   ├── generator/src/main/java/org/javagi/
    │   │   ├── gir/Callable.java       # Simplified isAsync() using finishFunc
    │   │   ├── gir/Parameter.java      # sharesAsyncCallbackArena() + findPrimaryAsyncCallback()
    │   │   ├── generators/TypedValueGenerator.java  # Shared arena + IllegalStateException for malformed GIR
    │   │   ├── generators/PreprocessingGenerator.java  # Skip arena allocation for progress callbacks
    │   │   └── generators/PostprocessingGenerator.java # Skip arena close for progress callbacks
    │   └── ext/gir-files/              # Official upstream GIR files (restored)
    ├── java-gi-remote/                 # Clean upstream clone (for diffing)
    ├── codeberg-reply.md               # Draft reply for Codeberg maintainer
    ├── CODEBERG_PROPOSAL_ASYNC_ARENA.md # RcArena + Isolated Teardown architecture proposal
    └── JAVA-GI-REFERENCE.md            # java-gi repo structure documentation
```

---

## Current Status (What Works)

### ✅ Completed (Stable, Verified)
| Component | Status | Notes |
|:---|---:|:---|
| **ifs abstraction** | ✅ Hardened | V2 with smart routing, dynamic capabilities, VfsError hierarchy, URI parsing |
| **IOBackend** | ✅ Full Surface | list, copy, move, trash, delete, rename, getMetadata, deepCount, thumbnail, search, mount/unmount |
| **InMemoryBackend** | ✅ Contract-Tested | IOBackendContractTest ensures behavioral parity with GioBackend |
| **FileInfo** | ✅ Nautilus-Grade | 20+ fields: timestamps (birth/access/modify), capability flags (canMount/canEject/canTrash), visibility (isHidden/shouldShow), sort functions, permissions, owner/group, child count, isArchive, isLaunchable, isStarred, trashTime, recency, activationUri |
| **DirState** | ✅ Strategy-Based | ListingStrategy sealed interface (Standard/Search/Starred/Virtual), DirStateRegistry with WeakReference caching, whenReady/whenEnriched StateFlows, deep count enrichment |
| **GioBackend** | ✅ Fully Async | All mutating ops use `awaitGioAsync` bridge. Recursive ops (copyRecursive/deleteRecursive) use sequential async with `yield()` for cancellation. Backend-aware semaphores (Local: 32, Network: 8). |
| **GioCoroutineBridge** | ✅ Battle-Tested | `startMainContextPump(scope)` + `awaitGioAsync(block, finish)`. GLib.idleAdd dispatch, Source.remove() cleanup, cont.isActive check for double-resume safety. |
| **VfsError** | ✅ Typed Hierarchy | Sealed class (not interface) extending Exception. 12 variants: AlreadyExists, NotFound, WouldRecurse, PermissionDenied, NoSpace, ReadOnly, Cancelled, NotSupported, IsDirectory, NotDirectory, Busy, IoError |
| **UndoAction** | ✅ Type-Driven | Sealed interface: TransferUndo, TrashUndo, RenameUndo, CreateUndo, MetadataUndo. Full URI recovery for trash restore. |
| **Bookmarks** | ✅ GTK-Synced | JSON primary store + bidirectional sync with `~/.config/gtk-3.0/bookmarks`. GFileMonitor for external edits. 500ms debounce. |
| **Search** | ✅ Tracker3 + Fallback | VfsQuery with depth/MIME/hidden/date/size/content filters. Progress reporting. Flow-based result streaming. |
| **TrashMonitor** | ✅ Real-Time | GFileMonitor on `trash:///` with TRASH_ITEM_COUNT optimization. Debounced StateFlow. |
| **ThumbnailStateTracker** | ✅ Observable | StateFlow-based thumbnail tracking. Per-URI VFS ops on IOBackend. |
| **Desktop Integration** ✅ | DeviceManager, DesktopLink, DesktopDirectory, SandboxDetector, StarredManager, SettingsProvider — all injectable via interfaces for testability. |
| **BulkDispatcher** | ✅ Safe Parallelism | `limitedParallelism()` for concurrent I/O. Local: 32 threads, Network: 8. |

---

## The java-gi Binding Pipeline

All steps automated in `scripts/generate_bindings.sh` (dynamic path resolution, no hardcoded paths):

```
Step 1: Infrastructure Setup
         → Create build/native-gen/{tools,bindings,temp_raw}
Step 2: Extract Foundation Classes
         → org.javagi.* from Maven Central glib-0.15.0-sources.jar
         → org/gnome/* + org/javagi/* from local ref/java-gi_patched/modules/
Step 3: Generate GNOME 46 Bindings
         → PATCHED generator from ref/java-gi_patched/generator/build/install/
         → /usr/share/gir-1.0/{GLib,GObject,Gio}-2.0.gir
Step 4: Flatten & Merge
         → Prevents "duplicate class" errors
Step 5: Post-Processing
         → GPid pointer fix (detect type, call correct helper)
         → Remove module-info.java
```

### The Patches We Maintain (in ref/java-gi_patched)

| Patch | File | What | Why |
|:---|:---|:---|:---|
| **Shared Arena** | `Parameter.java` | `sharesAsyncCallbackArena()` detects progress callbacks in async functions | GNOME GIR marks progress callbacks as `scope="call"` instead of `scope="notified"` |
| **Arena Sharing** | `TypedValueGenerator.java` | Progress callbacks reuse primary callback's `_asyncScope` arena | Prevents SIGSEGV from premature arena close |
| **Fail-Fast** | `TypedValueGenerator.java` | Throws `IllegalStateException` if no primary callback found | Prevents silent memory leaks from malformed GIR data |
| **Arena Skip** | `PreprocessingGenerator.java` | Skips arena allocation for progress callbacks | They share the primary's arena |
| **Close Skip** | `PostprocessingGenerator.java` | Skips arena close for progress callbacks | Primary callback's arena handles cleanup |
| **isAsync()** | `Callable.java` | Simplified to `finishFunc != null` | More reliable than string heuristic |
| **Override Priority** | `Library.java` | CLI-provided GIR files override internal bundle | Generator ignores user GIR files without this |

### java-gi Fork Strategy

- **`ref/java-gi_patched/`** — Patched local clone (tracked in git). Edge development. Pushes to Codeberg fork.
- **`ref/java-gi-remote/`** — Clean upstream clone (untracked). For diffing against official and submitting PRs.
- **Codeberg fork:** `codeberg.org/dragon-Elec/java-gi` (origin) — for PRs to maintainer
- **GitHub fork:** `github.com/dragon-Elec/java-gi` (github remote) — for ahead/behind UI visibility
- **Official:** `codeberg.org/java-gi/java-gi` (upstream) — for pulling updates

---

## Nautilus Parity Scorecard

| Audit Section | Status | Core/App | Notes |
|:---|---:|:---|:---|
| 1. FileInfo model | ✅ 90% | Core | All Nautilus fields present except emblem icons and GIcon pipeline |
| 2. Directory model | ✅ 85% | Core | DirState + ListingStrategy + Registry. Missing: async deep count for UI |
| 3. File Operations | ✅ 95% | Core | Full async with progress + cancellation. Missing: attribute preservation edge cases |
| 4. Trash Monitor | ✅ 90% | Core | Real-time GFileMonitor. Missing: cross-volume trash detection |
| 5. Undo/Redo | ✅ 95% | Core | Typed UndoAction. Missing: batch undo UI |
| 6. Search | ✅ 80% | Core | VfsQuery + Tracker3. Missing: result ranking, composite search |
| 7. Thumbnails | ✅ 70% | Core | ThumbnailStateTracker skeleton. Missing: actual thumbnail generation pipeline |
| 8. Bookmarks | ✅ 95% | Core | JSON + GTK sync. Complete for v1 |
| 9. Sidebar | ❌ 0% | App | Purely app-layer. No core work needed |
| 10. Monitoring | ✅ 90% | Core | DirectoryMonitor + TrashMonitor + DesktopLinkMonitor |
| 11. Error Reporting | ✅ 95% | Core | VfsError hierarchy with human-readable messages |
| 12. Preferences | ✅ 60% | Core | SettingsProvider interface. Missing: app-layer preference UI |
| 13. DBus | ❌ 0% | App | org.freedesktop.FileManager1 is pure app-layer |
| 14. Icon Names | ❌ 0% | App | GIO already returns icon strings. App maps to Compose icons |
| 15-22. Remaining | ⏳ Planned | Mixed | Symlink creation, recent CRUD, SELinux, compression primitives |

**Overall:** ~65% Nautilus parity. ~75% of remaining work is core, ~25% app-layer.

---

## Architecture Decisions (Key "Why"s)

### 1. Async for Writes, Sync for Reads
- **Reads** (list, metadata, enumerate): Synchronous GIO wrapped in `Dispatchers.IO`. Fast, simple, no GLib Main Context dependency.
- **Writes** (copy, move, trash, delete, rename): `awaitGioAsync` bridge. Non-blocking, cancellation-aware, progress-reporting.

### 2. Injectable Singletons (Testability)
All `core/desktop/` singletons are accessed via interfaces (`TrashStateProvider`, `StarredStateProvider`, `SettingsProvider`). Production uses real implementations; tests inject fakes. No test ever mutates the host OS.

### 3. Services vs IOBackend
- **IOBackend method:** Per-URI VFS operation. Each backend can override. Examples: `deepCount()`, `getThumbnailPath()`.
- **Service:** State coordinator wrapping IOBackend calls, exposing StateFlow for UI. Example: `ThumbnailStateTracker`.
- **Desktop singleton:** System-wide state without a URI. Example: `TrashMonitor`, `StarredManager`.

### 4. Typed Undo (Not Operation-Driven)
`UndoAction` sealed interface defines actions by *how* they are reversed (delete, move back, rename back, restore), not *what button the user clicked* (duplicate, template, starred). Keeps undo engine small and generic.

### 5. Compose over GTK
- Compose is Kotlin-native with first-class coroutine/Flow integration
- GTK signal system would add unnecessary bridging
- Internal communication uses `StateFlow`/`SharedFlow` — no GObject signals needed

---

## GioBackend Initialization Pattern (Mandatory)

Every class that uses GIO types must call `Gio.javagi$ensureInitialized()` before using GIO static methods:

```kotlin
class GioBackend : IOBackend {
    init {
        org.gnome.gio.Gio.`javagi$ensureInitialized`()
    }
}
```

Without this: `UnsupportedOperationException: Cannot find function 'g_file_new_for_uri'`

---

## Testing Workflow

```bash
# Quick check — specific test class (~7s)
./gradlew test --tests "ClassName" --console=plain 2>&1 | python3 scripts/filter_gradle.py

# Full suite (~50s)
./gradlew test --console=plain 2>&1 | python3 scripts/filter_gradle.py

# Regenerate bindings + compile + test
./scripts/generate_bindings.sh && ./gradlew test --console=plain 2>&1 | python3 scripts/filter_gradle.py
```

- `filter_gradle.py` prints `.` for PASSED, full error blocks for FAILED, always shows `error:`/`Exception`/`BUILD`
- Use `2>&1` to merge stderr into stdout when piping
- `BashHelper.kt` for setting up complex filesystem states (symlinks, permissions) via bash scripts
- `IOBackendContractTest` enforces identical behavior across `GioBackend` and `InMemoryBackend`

---

## Known Issues & Gotchas

1. **URI String Manipulation:** `trimEnd('/')` on `file:///` gives `file:` — breaks scheme detection. Always check `isRootUri()` first.
2. **Plain paths have no scheme:** Handle `schemeEnd == -1` separately from `scheme://` URIs.
3. **Enum shorthand doesn't work:** `.PENDING` doesn't compile — use full `TransactionStatus.PENDING`.
4. **CancellationException must be re-thrown:** Any catch block in coroutine code must `if (e is CancellationException) throw e` or coroutines hang on cancel.
5. **Never hardcode dispatchers in suspend functions:** `.flowOn(Dispatchers.IO)` inside suspend/Flow bypasses test dispatchers.
6. **Bot PRs must be compile-checked:** Static analysis often flags required imports as unused. Always verify before merging.

---

## Next Steps

### Phase 2 — App Layer (Not Started)
1. **Sidebar Aggregator:** Combine bookmarks, recent, DeviceManager into unified sidebar model
2. **Thumbnail Pipeline:** Coil 3 + custom GNOME fetcher (symlink resolution, local fast-path, theme icon fallback)
3. **Main Application Bridge:** Compose Desktop + GApplication.register() + MainContext pump
4. **Visual Prototype:** First interactive frontend consuming transaction engine

### Phase 2 — Core Polish
1. **Symlink creation** via `IOBackend.createSymlink()`
2. **Recent file CRUD** (add/remove from recent:/// list)
3. **Attribute preservation** on copy/move edge cases
4. **Compression primitives** for archive integration

---

*Updated after Sessions 1-20+. 71 commits, 188 tests passing. Core engine complete. App layer not started.*
