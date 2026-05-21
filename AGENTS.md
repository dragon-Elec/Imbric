# ImbricFS — AGENTS.md

## Project Identity

- **Name:** Imbric
- **Root package:** `com.imbric`
- **Core VFS abstraction:** `ifs`
- **Language:** Kotlin 2.3.20+ (K2 compiler active)
- **JVM target:** JDK 25
- **Build system:** Gradle 9.5.0 (wrapper committed)

## Repository

- **Path:** `/home/ray/Desktop/files/wrk/Imbric/imbric-kt`
- **Standalone Git repo** (no shared history with Python original at `/home/ray/Desktop/files/wrk/Imbric/Imbric`)
- **Git user:** `ray`

## Build & Run

```bash
cd /home/ray/Desktop/files/wrk/Imbric/imbric-kt
./scripts/generate_bindings.sh  # generate GIO bindings from local GIR files
./gradlew build                 # full build
./gradlew compileKotlin         # fast compiler check
```

- **Gradle properties:** `org.gradle.java.home=/usr/lib/jvm/java-25-openjdk-amd64`
- **LSP:** JetBrains `intellij-server` with `--stdio` flag (configured in OpenCode settings)
- **Workspace root must be the project dir** for LSP indexing to work

## Architecture (Two-Layer System)

```
com.imbric
├── core/                     # ☙ Reusable headless engine (VFS library)
│   ├── ifs/                  #    VFS abstraction layer
│   ├── transactions/         #    Mutating ops hub
│   ├── logic/                #    Pure math and logic.
│   ├── models/               #    Shared data contracts
│   └── desktop/              #    OS hardware sensors (drives, mounts)
└── app/                      # ☙ The actual desktop file manager product
    ├── aggregators/          #    SidebarModel, BookmarkService (core data → UI models)
    ├── viewmodel/            #    Navigation state, selection, preferences
    ├── ui/                   #    Compose Desktop UI components
    └── bootstrap/            #    Main entry point, GApplication, MainContextPump
```

### Key Design Decisions

- **No Auto-Commits:** Do NOT commit, amend, or push changes unless explicitly requested by the user.
- **core = The Engine, app = The Product:** The `core` package (`com.imbric.core`) is a headless, unopinionated library. It could be published as a standalone JAR for CLI tools, servers, or automated scripts. It knows about files, backends, transactions, and hardware sensors, but it does **not** know what a "sidebar" or a "view model" is. The `app` package (`com.imbric.app`) is the actual desktop file manager product. It owns UI state, cross-data aggregation (e.g., merging drives + bookmarks → sidebar), user preferences, and the Compose Desktop entry point. The app depends on the core; the core never depends on the app.
- **Aggregation lives in app, not core:** If the product needs to combine data from multiple core sources (e.g., `DeviceManager.drives` + bookmark files → `SidebarItem`), that mapping code lives in `app/aggregators/`. The core simply provides the raw signals; it does not model what a sidebar is.
- **UI state is app-only:** Which folder is the user looking at? What's selected? Grid or list view? These are application-layer concerns. The core provides `DirState` (a live folder watcher), but the `FileBrowserViewModel` that wraps it with back/forward history and selection state lives in `app/viewmodel/`.
- **"Composed features" belong in app, not core:** If a user-facing feature is just a composition of existing core primitives, it belongs in the app layer. Core provides `copy()`, `createFile()`, `rename()`, `delete()`. The app layer builds "Duplicate" (copy + auto-rename), "New Document → .md" (createFile + open editor), "Create from Template" (copy from ~/Templates), and "Create Link" (createFile with symlink). The core does NOT need dedicated methods for these — they are app-layer orchestration. The undo system handles them automatically because they decompose into standard core operations (copy → undo deletes copy, createFile → undo deletes file).
- **Reads vs Writes:** Scans/reads go through `ifs` directly. Only mutating ops (copy/move/trash) create transactions.
- **Undo is type-driven, not operation-driven:** The core undo system uses a `sealed interface UndoAction` with variants based on *how the action is reversed* (delete, move back, rename back, restore metadata), not *what button the user clicked* (duplicate, template, starred). This keeps the undo engine small and generic. UI labels are derived from the action type + item description, not from 19 separate undo info classes.
- **Initialization:** Always call `org.gnome.gio.Gio.javagi$ensureInitialized()` before using GIO interfaces (especially static methods on interfaces like `File.newForUri`).
- **Sync over Async (Reads):** Prefer synchronous GIO methods wrapped in `Dispatchers.IO` (e.g., `enumerateChildren`, `queryInfo`) for fast metadata reads to avoid GLib Main Context synchronization issues in Coroutines. For recursive operations (like search), use `kotlinx.coroutines.yield()` inside loops to ensure cooperative cancellation.
- **Async over Sync (Writes):** All mutating operations (copy, move, trash, delete, rename) MUST use the `GioCoroutineBridge.awaitGioAsync` bridge. This ensures proper cancellation propagation via `GCancellable`, prevents JVM thread blocking during long transfers, and avoids FFM memory crashes via the patched generator.
- **GLib Main Context Pump:** All `awaitGioAsync` calls require a running `GMainContext` pump (see `GioCoroutineBridge.startMainContextPump`). In the `app` layer, this is typically handled by the Compose frame loop or a dedicated daemon thread.
- **GPid Bug:** The `java-gi` generator has a template bug on older GNOME versions where `GPid` is a pointer. This is patched in `generate_bindings.sh` by replacing `Pid.get...Values` with `Alias.getAddressValues` and forcing a pointer-size of 8 bytes.
- **Undo/Trash:** Integrated into `transactions/` hub, not separate modules.
- **Policies are application-layer:** Core provides `XferArbiter` engine + `SyncPolicy` interface; user policies (e.g. "Modified Only") live in app layer.
- **FFI backends:** Concrete backends (GIO via java-gi, SMB via gRPC, Python via IPC) encapsulate all FFI mess behind `IOBackend`.
- **"Does it require a URI?" Rule:** This is the core boundary between the Virtual File System (`ifs`) and the Desktop Environment.
  - **VFS (IOBackend):** Anything tied to a specific file, path, or URI MUST be implemented here. This includes Thumbnails, Search, Directory Monitoring, Trash, and Recents. This allows multiple backends (e.g., GIO and OneDrive) to each provide their own native optimizations for these features.
  - **Desktop Environment:** Global system states WITHOUT a URI MUST be handled by a separate `DesktopEnvironment` interface. This includes Hardware Mounts/Volumes (event of plugging in a USB), Default Application launching, and System Theme preferences.
- **What Is a "Service"?** A service is a **state coordinator** that wraps IOBackend calls and adds observable state for the UI. Services live in `core/ifs/services/`. They are NOT backend capabilities — they are higher-level wrappers that track cross-cutting concerns like loading state, failure state, or progress. The distinction:
  - **IOBackend method:** A per-URI VFS operation. Each backend can implement it differently (GIO native, SMB RPC, etc.). Examples: `deepCount()`, `getThumbnailPath()`, `generateThumbnail()`.
  - **Service:** A state coordinator that wraps IOBackend methods and exposes `StateFlow` for UI observation. Examples: `ThumbnailStateTracker` wraps `IOBackend.getThumbnailPath()` and tracks `thumbnailingInProgress`/`thumbnailingFailed` sets.
  - **Desktop singleton:** System-wide state without a URI. Examples: `TrashMonitor`, `StarredManager`, `SettingsProvider`.
  - **Rule of thumb:** If it's a per-URI file operation → IOBackend. If it has state the UI observes → Service wrapping IOBackend. If it's global system state → Desktop singleton.

## Kotlin 2.3.x Features (Relevant)

### 2.3.0 (Dec 2025) — base used

- **Explicit backing fields** (stable): `val isCancelled: Boolean = false\n    private field\n    get() = field` — the `field` keyword in the body declares the backing field explicitly. Also supported: traditional `_prop` + custom getter pattern.
- **`kotlin.uuid.Uuid`** (experimental): `@file:OptIn(ExperimentalUuidApi::class)` required. Stable random, name-based UUID v3/v5, parsing.
- **Java 25 bytecode support** — toolchain must be set.
- **Unused return value checker** — warns when non-`Unit` return values are discarded.
- **`kotlin.time.Clock`** — stable time API alongside `kotlinx.datetime`.

### 2.3.20 (Mar 2026) — current

- **Name-based destructuring** (experimental): `-Xname-based-destructuring=only-syntax`. Enables `(val mail = email, val name = username) = user`. Modes: `only-syntax` (opt-in), `name-mismatch` (warn on position/data class mismatch), `complete` (full mode with bracket syntax for positional). Not enabled in project yet.
- **Explicit backing fields bugfixes** — intersection overrides, subclass access, `final` enforcement all fixed.
- **Gradle 9.3+ compatibility** (Build Tools API by default for JVM compilation).
- **`Map.Entry` immutable copy** API in stdlib.

### 2.3.21 (Apr 2026) — latest patch, no new features

- Wasm IC mode fix, SPM ObjC linking fix, `@JvmRecord` in commonMain fixed.
- False positive `SUBCLASS_CANT_CALL_COMPANION_PROTECTED_NON_STATIC` fixed.

## Kotlin 2.3+ Conventions

- **Explicit backing fields**: prefer `_prop` + custom getter (`val isCancelled: Boolean get() = _isCancelled`) for clarity. The `field` keyword syntax (`private field`) is also stable but less explicit.
- `@file:OptIn(ExperimentalUuidApi::class)` required for `kotlin.uuid.Uuid`
- Enum shorthand `.PENDING` does NOT work — always use full `TransactionStatus.PENDING`
- `throw`/`error()` preferred over `Result.failure` for unrecoverable errors
- `when` guards: use nested `if` in branch body, not inline `when (x) if y ->`
- Prefer `object`/`data class`/`sealed class` over loose enums for algebraic types

## LSP Diagnostic Patterns

- `Initializer type mismatch` / `Unresolved reference` — usually stale test files left in tree. Delete them.
- `This declaration needs opt-in` — missing `@file:OptIn(ExperimentalUuidApi::class)`
- `Modifier 'override' not applicable to top level function` — dangling code outside class body
- `Redeclaration` — duplicate class definitions (often from botched file writes)

## Commit Style

- Lowercase prose, emoji markers (🍂 🍁 ✨ ❤️)
  
  ## GIO Binding Generation

```bash
./scripts/generate_bindings.sh  # auto-generate from local GIR files
```

Pipeline: download java-gi CLI from Codeberg → generate Java sources from `/usr/share/gir-1.0/{GLib,GObject,Gio}-2.0.gir` → fetch foundation classes (`org.javagi.*`) from Maven Central → delete `module-info.java` → strip `org.gnome.` prefix via sed → compile via Gradle source set.

**Local Patched Generator (`ref/java-gi`):**
We maintain a local clone of the `java-gi` repository in `ref/java-gi`. We have applied critical AST-level patches to the generator source code to fix upstream GNOME metadata bugs:
1. **Async Safety Patch:** Automatically detects `_async` functions and forces their callbacks to use `Scope.ASYNC` (Global Arena), preventing fatal `SIGSEGV` crashes (like the one in `moveAsync`) caused by incorrect `scope="call"` annotations in GNOME's GIR files.
2. **Override Priority Patch:** Allows CLI-provided `.gir` files to correctly override the generator's internal bundled `gir-files.zip`.

The `generate_bindings.sh` script builds and uses this local, patched generator instead of the official release to ensure our async file operations are memory-safe.

**Known generator bugs (java-gi 0.15.0):**

- Internal templates hardcode `org.gnome.*` cross-references. The `-d` flag changes output package names but not internal refs. FIX: `sed -i 's/org\\.gnome\\.//g'` on all generated files.
- No `org.java-gi:base` artifact. Foundation classes live inside `glib-0.15.0-sources.jar`.
- Generated `module-info.java` files cause K2 "Too many source modules" error — must be deleted.
- Only Maven dep needed: `compileOnly("org.jspecify:jspecify:1.0.0")` for `@Nullable`.
- CI dependency: `libglib2.0-dev` package (for GIR files).

## Environment

- **OS:** Linux (Ubuntu 24.04+)
- **JDK:** `/usr/lib/jvm/java-25-openjdk-amd64`
- **Gradle:** 9.5.0 (downloaded to `/tmp/gradle-9.5.0/gradle-9.5.0/`)
- **Python original:** `/home/ray/Desktop/files/wrk/Imbric/Imbric`

## Agent Reference Files (Machine-Optimized)

These files contain dense, structured patterns for LLM/agent consumption.
Read them when working on the corresponding topic.

- **`ref/GIO-COROUTINE-BRIDGE.md`** — GLib Main Loop integration patterns,
  `GLib.idleAdd`/`timeoutAdd` usage, `MainContext.iteration()` pump,
  coroutine dispatcher proposal, Arena lifecycle for async callbacks,
  signal patterns, GApplication lifecycle quirks, and known workarounds.

## Magic Context & Agent Workflow

- **Automatic Truncation:** Magic Context automatically truncates old tool outputs (replacing them with `[truncated]` stubs) when they age out and the context window hits its threshold. This safely manages token limits.
- **Immediate Memorization:** Because truncated tool outputs disappear from the active context window, **immediately** save important architectural rules or findings to `ctx_memory` while the full file is still visible.
- **Recovery:** Truncated content is not lost forever; it is stored in SQLite and can be queried via `ctx_search` or recovered via `ctx_expand`, but `ctx_memory` is the most reliable way to persist knowledge.

## Hard-Won Learnings

### PR Review Discipline
- **Never merge "unused import" PRs without compile-checking.** PR #24 removed `@OptIn(ExperimentalUuidApi::class)` from `TransferOrchestrator.kt`, but `startTransaction()` returns `Uuid`. Broke compilation.
- **PR #19 was worse** — tried to remove `withContext` from `GioRecentBackend` which IS used on 3 lines. Would have broken build.
- **Bot PRs (Jules, etc.) need human review.** "Simple" cleanup PRs aren't always safe. Always verify at compile level.

### URI String Manipulation
- **`trimEnd('/')` on `file:///` gives `file:`** which breaks scheme detection. Always check for root URIs (`isRootUri()`) before trimming slashes.
- **Plain paths (`/path`) have no scheme.** Code that assumes `scheme://` exists will break on plain paths. Handle `schemeEnd == -1` separately.
- **Test root URIs explicitly:** `file:///`, `file://`, `smb://`, `smb:///`, `/`, `/path` are all valid and must be tested.

### Testability & Bash Workflow
- **Singleton dependencies kill testability.** `TrashManager` hardcoding `TrashMonitor.getInstance()` meant tests hit real GIO. Always inject external dependencies via interfaces (`TrashStateProvider`).
- **Bash is a helpful assistant for tests.** Use bash scripts to orchestrate complex real-filesystem states (deep trees, symlinks, permissions) before running tests, rather than writing 50 lines of Kotlin setup.
- **Configure Gradle for better output.** Add `testLogging { events("failed"); exceptionFormat = FULL }` to `build.gradle.kts` to print exact failures and stack traces to the console.
- **Stop over-filtering Gradle output.** Do NOT pipe `./gradlew test` to `| tail` or `| grep`. It throws away the exact stack traces we configured Gradle to print.
- **The Balanced Testing Workflow:**
  - For quick checks: `./gradlew test --tests "SpecificTest"` (Targeted, 7s vs 48s).
  - For full suite: `./gradlew test` (Without `--continue`). It stops at the *first* error and prints the exact stack trace, preventing 50-error spam.
  - If output is massive: Redirect to a file (`> /tmp/test.log 2>&1`), then use native `grep` and `read` tools to inspect it. Avoid dumping 2000 lines of stack traces into the context window, as it causes token bloat and pushes out useful memory.

## Session Handover

Before ending a session, update `HANDOVER.md` with the current status, bugs found, and next steps. This ensures the next session can start without re-exploring the entire codebase.

## Notes

- Always use `rg` (ripgrep) instead of `grep` for codebase searches. OpenCode has its own internal `grep` tool — use that for quick searches; fall back to `rg` via bash for advanced patterns.
- Prototyping approach = interpreted iteration (like Python dev). Production path = GraalVM AOT bytecode for first stable release.
- Avoid platform-specific libs (`java.util.UUID`) in core logic.
- `java-gi` library uses JEP 454 FFM API (JDK 22+ required).
