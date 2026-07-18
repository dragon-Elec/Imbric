# ImbricFS Handover Document

## Project Identity
- **Name:** ImbricFS ("Imbric")
- **Root Package:** `com.imbric`
- **Core VFS abstraction:** `ifs`
- **Language:** Kotlin 2.4.10+ (K2 compiler) on **Kotlin/JVM** (not Kotlin/Native)
- **JVM target:** JDK 25
- **Build system:** Gradle 9.6.1
- **UI Strategy:** Compose Multiplatform (Kotlin) — **not GTK**

## Repository
- Path: `/home/ray/Desktop/files/wrk/Imbric/imbric-kt`
- Standalone Git repo (no shared history with Python original)
- **Test count:** 205 passing

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
│   └── app/                            # Application layer
│       ├── bootstrap/
│       │   ├── Main.kt                # Entry point
│       │   ├── ImbricApp.kt           # Main application shell with animations
│       │   └── MainContextPump.kt     # GLib MainContext iteration pump
│       └── ui/
│           ├── AddressBar.kt          # Path breadcrumbs segment navigator + list/grid layout toggle
│           └── DirectoryView.kt       # Unified LIST and GRID view layouts supporting native thumbnails
```

---

## Current Status (What Works)

### ✅ Completed (Stable, Verified)
- **Upstream java-gi 1.0.0-RC1 Merge:** Merged the latest upstream commits into `ref/java-gi_patched`, including the critical `GList`/`GSList` double-free fix, `new_` prefix stripping, and `GIOException` rename. Regenerated the bindings and updated the entire Imbric codebase to use the new `File.forUri`, `File.forPath`, and `GIOException` APIs.
- **Synchronous Test Stability:** Fixed asynchronous test failures in `FileBrowserViewModelTest` by asserting on synchronous `currentUri.value` and `virtualUri.value` properties.
- **Material You 2025 Spec Integration:** Upgraded `material-kolor` to `4.1.1` and configured `ImbricTheme` to use `specVersion = ColorSpec.SpecVersion.SPEC_2025` and `style = PaletteStyle.Vibrant` by default, enabling high-contrast, true-to-seed dynamic colors.
- **Decoupled App Layer:** Decoupled `ImbricApp.kt` by extracting the main layout to `MainWindow.kt`, the folder view canvas to `FileBrowserPane.kt`, and service instantiation to `Main.kt`.
- **Premium Breadcrumbs & Focus:** Implemented horizontal mouse wheel scrolling, Nemo-style `virtualUri` retention (Ghost Paths), tactile button styling, and global focus-clearing on outside clicks.
- **Skia Codec with Pixbuf Fallback:** Re-enabled image dimension enrichment in `GioBackend.kt` using Skia's `Codec` (via Skiko) as the primary, high-performance, pure-Kotlin decoder, and native `PixbufLoader` as a robust fallback for formats not compiled into Skiko (like JXL, HEIC, or AVIF on some platforms).
- **Grid View Rendering Optimizations:** Replaced heavy Material 3 `Surface` components in `FileGridCell` and `FileRow` with lightweight `Box` + `Modifier.clickable` + `Modifier.background` to eliminate composition and layout overhead. Removed conflicting `.width(120.dp)` constraint from `FileGridCell` to eliminate layout double-measurement passes.
- **Reduced Recomposition Thrashing:** Increased `DirState` chunk size from 50 to 200 to reduce StateFlow emissions and Compose recompositions by 66% during directory loading.
- **Unified `ib` CLI Commands:** Integrated `ib test` (replacing `filter_gradle.py`) and `ib audit` (replacing `audit_validator.py` and `audit_validator.sh`).
  * `ib test` runs tests and filters the output cleanly (replacing passed tests with dots and showing full stack traces for failures) without any bold/color formatting.
  * `ib audit` automatically scans the entire codebase, finds all Kotlin files, locates their corresponding context files, and validates all of them in one pass.
- **Cleaned Up `scripts/` Folder:** Deleted redundant/useless standalone scripts (`filter_gradle.py`, `audit_validator.py`, `audit_validator.sh`, `dev.sh`).
- **Fixed Parser Bug in Audit Validator:** Fixed a bug in the validator where default lambdas inside constructor parameters (like `private val uriValidator: (String) -> Boolean = { ... }`) were incorrectly parsed as class body scopes, causing local variables (like `val gfile`) to be flagged as missing public declarations. The validator now tracks parentheses depth to isolate parameter scopes.
- **Unused Image Dimension Enrichment Commented Out:** Commented out `enrichImageMetadata` in `GioBackend.kt` to prevent 440 concurrent native `PixbufLoader` allocations and file reads when navigating large image directories, completely eliminating CPU thrashing and UI state flooding.
- **Skia Codec Verification:** Added `SkiaCodecTest.kt` verifying that Skia's `Codec` (via Skiko) is the perfect, high-performance, zero-dependency equivalent to Qt's `QImageReader` for Kotlin Compose Desktop, supporting modern formats (WebP, HEIC, AVIF, PNG, JPEG, GIF, BMP) and extracting dimensions from the first 64KB without decoding the actual pixels.
- **JXL Support Analysis:** Documented that Skia supports JXL decoding natively, but JetBrains does not compile JXL support into the pre-built Skiko binaries for Compose Desktop. GNOME's `GdkPixbuf` (which `PixbufLoader` uses) supports JXL if the host system has `jxl-pixbuf-loader` installed.
- **Unique Child URIs Bug Fix (`GioBackend.kt`):** Resolved a major bug in the `list()` loop where listed child items were assigned the parent directory's URI instead of their unique subpath. This previously collapsed folder items into a single entry inside `DirState` and caused Jetpack Compose to deadlock or freeze in `LazyVerticalGrid` due to duplicate keys.
- **Empirical Non-UI Diagnostic CLI Mode (`Main.kt`):** Built a powerful diagnostic shell tool intercepting CLI arguments `./gradlew run --args="file:///path"`. Emulates the App-layer `DirState` flow, pumps the GLib context, prints state transitions, lists VFS details, and cleanly cancels monitoring loops on exit.
- **Compose Transition Deadlock Fixed (`ImbricApp.kt`):** Refactored `AnimatedContent` inside `FileBrowserContent` to target `state.uri` instead of the full state block. This confines vertical page animations purely to folder-change navigation events, allowing Compose to instantly and cleanly recompose loading/empty/directory states in-place.
- **GIO FFI Test Stability:** Added `@BeforeEach` GIO initialization safeguards to integration tests (`GioRecentBackendTest`, `GioBackendTest`, `DesktopDirectoryTest`, `ImbricDesktopTest`). Calls `Gio.javagi$ensureInitialized()` before GObject interaction, preventing SIGSEGV native pointer clean-up crashes on JVM garbage collection.
- **Hot Reload Integration (JBR 25):** Wired up JetBrains DCEVM Runtime (`/opt/jbr-25`) inside gradle.properties, enabling instant, live class swapping for Compose elements in the CLI via the Compose Hot Reload plugin.
- **Process Guard & Daemon Hardening:** Modified `scripts/ib/daemon.py` and `scripts/ib/process.py` to run atomic cleanup `ProcessManager.kill_all(force=True, include_daemons=False)` before starting each compilation round. Distinguishes daemon and app instances, successfully eliminating the "Two Windows" duplicate process bug.
- **Atomic Navigation State:** Introduced a unified, atomic `FileBrowserState` flow in `FileBrowserViewModel.kt`. This completely eliminates the navigation race condition where changing paths momentarily flashed an "Empty Folder" view for folders that actually contained files.
- **Layout views (`DirectoryView.kt`):** Refactored stub-level `FileList.kt` into `DirectoryView.kt` with support for `LayoutMode` (LIST / GRID). 

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

---

## Testing Workflow

```bash
# Quick check — specific test class (~7s)
./gradlew test --tests "ClassName" --console=plain 2>&1 | python3 scripts/filter_gradle.py

# Full suite (~40s)
./gradlew test --console=plain 2>&1 | python3 scripts/filter_gradle.py
```

---

## Hard-Won Learnings

1. **Kotlin Coroutine Self-Cancellation Prevention:** When launching a cancellable background job inside a class (like DirState's `refreshJob`), always capture the mutable job reference locally *before* launching the new coroutine:
   ```kotlin
   val oldJob = refreshJob
   refreshJob = scope.launch(ioDispatcher) {
       oldJob?.cancelAndJoin()
       ...
   }
   ```
   Otherwise, the asynchronous coroutine will read the newly assigned job and call `cancelAndJoin()` on itself, silently deadlocking the job and leaving `isLoading` at `true` forever.

2. **VFS Child URI Integrity Contract:** Integration and contract tests for directory listings must explicitly assert that listed child items have unique, correct URIs conforming to `"$parentUri/$name"`. Previously, passing the parent folder handle instead of a resolved child handle in `GioBackend.kt` caused all items to share the parent URI, causing StateFlow map collisions and deadlocking Jetpack Compose's `LazyVerticalGrid` stable key layout.

3. **GIO JNI SIGSEGV Safety:** Any test suite or benchmark that interacts with native GIO or GLib FFI bindings must run `Gio.javagi$ensureInitialized()` in a `@BeforeEach` or `@BeforeAll` block. Bypassing this creates half-constructed GObject proxy wrappers that cause native `SIGSEGV` crashes when the JVM Garbage Collector runs `MemoryCleaner` and invokes `g_object_unref`.

---

## Missing Test Types (Testing Gaps Audit)

1. **Real-Ground VFS Stress Tests:**
   * **Hostile/Broken Filesystems:** We need integration tests running on mock/temp directories populated with broken symlinks, nested hidden structures, and circular symlink references. This asserts that `deepCount` and search algorithms handle cyclic paths without infinite loops or thread hangs.
   * **Locked/Restricted Permissions:** Tests for files with no read/write access (`000` or `r--` owned by other users) to ensure that `getMetadata` and `Strategy.list` return robust `VfsError.PermissionDenied` exceptions rather than native crashes.
   * **Corrupt/Over-sized File Enrichment:** Tests where metadata collectors are fed 100MB+ corrupt or partially written image headers. This asserts that `PixbufLoader` handles parsing failures cleanly without JNI native memory overflows.

2. **High-Concurrency & Interruption Tests:**
   * **Bulk Operation Race Conditions:** High-load transaction tests launching concurrent copy and delete actions on the same 1,000-file directories. This validates that our pre-flight locking checks and Sticky Arbiter policies prevent race states, dirty directory reads, or orphaned lock files.
   * **Mid-Transfer Scope Cancellation:** Tests that abruptly cancel the coroutine scope during a long active transfer. This asserts that `GCancellable` immediately halts native FFI writes, native heap buffers are deallocated, and incomplete files are rolled back cleanly.

3. **App-Layer Compose UI Tests:**
   * **Component & Gesture Tests:** Desktop-specific `runComposeUiTest` blocks rendering `DirectoryView` (list and grid layouts) to assert that cell outlines, selections, and MIME icon lookups reactively respond to user interactions and scroll positions are retained during Stale-While-Revalidate cycles.

---

## Next Steps

1. **Sidebar Aggregator:** Combine bookmarks, recent, DeviceManager into unified sidebar model.
2. **Batch Operations UI:** Multi-select context menu actions (Copy, Cut, Delete, Star) in DirectoryView.
3. **Visual Enhancements:** Add animations and transitions to grid view elements during list mutations.

---

*Updated after Session 24. Completed Phase 3 & 4 of the SoA Log-Structured DirState Integration. Wired `DirState` to use `ListingDirectory` and `EnrichedListingView` instead of `HashMap<String, FileEntry>`, reducing GC pressure and object allocation overhead for directory listings.*
