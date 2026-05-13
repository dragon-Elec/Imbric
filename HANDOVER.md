# ImbricFS Handover Document

## Project Identity
- **Name:** ImbricFS ("Imbric")
- **Root Package:** `com.imbric`
- **Core VFS abstraction:** `ifs`
- **Language:** Kotlin 2.3.20+ (K2 compiler) on **Kotlin/JVM** (not Kotlin/Native)
- **JVM target:** JDK 25
- **Build system:** Gradle 9.5.0
- **UI Strategy:** Compose Multiplatform (Kotlin) — **not GTK**

## Repository
- Path: `/home/ray/Desktop/files/wrk/Imbric/imbric-kt`
- Standalone Git repo (no shared history with Python original at `/home/ray/Desktop/files/wrk/Imbric/Imbric`)
- 5 commits on `master` as of handover:
  1. `fb58be3` — Initial commit: Kotlin ImbricFS core layout
  2. `d5e9a19` — feat(core): complete Kotlin 2.3+ core rewrite
  3. `39b465e` — refine read pipeline & unify ifs backends
  4. `7adb470` — test: add tier 1 unit tests and test infrastructure
  5. `624556d` — fix(native): automate binding generation and gpid pointer patching

---

## Project File Structure

```
imbric-kt/
├── AGENTS.md                         # Agent instructions (architecture, build, conventions)
├── HANDOVER.md                       # THIS FILE
├── build.gradle.kts                  # Gradle build config (JDK 25, sourceSets for bindings)
├── build.properties                  # Gradle properties (JDK home)
├── .gitignore                        # Ignores .gradle/, build/, .kotlin/
├── scripts/
│   └── generate_bindings.sh          # Auto-generate + patch GIO bindings (5-step pipeline)
├── src/
│   ├── main/kotlin/com/imbric/core/
│   │   ├── ifs/                      # VFS foundation (agnostic layer)
│   │   │   ├── IOBackend.kt          # Interface: list/copy/move/trash/rename/getMetadata
│   │   │   ├── BackendCapabilities.kt # Capabilities & locality flags
│   │   │   ├── BackendRegistry.kt    # URI scheme → backend router (singleton)
│   │   │   ├── PathCapabilities.kt   # Per-path capability inspection
│   │   │   ├── FileEvent.kt          # File system event types
│   │   │   └── backends/
│   │   │       └── GioBackend.kt     # java-gi GIO implementation (GNOME 46)
│   │   ├── transactions/             # Mutating operations hub
│   │   │   ├── TransactionManager.kt # Orchestrator: batch lifecycle, conflict hooks
│   │   │   ├── UndoManager.kt        # Stack-based undo/redo
│   │   │   └── TrashManager.kt       # Trash lifecycle, cache, restore
│   │   ├── logic/
│   │   │   └── XferArbiter.kt        # ConflictAction + SyncPolicy + resolve()
│   │   └── models/
│   │       ├── FileInfo.kt           # Immutable file metadata snapshot (16 fields)
│   │       ├── FileJob.kt            # Atomic work unit + InversePayload + TransferProgress
│   │       └── TrashItem.kt          # Trash bin item metadata
│   └── test/kotlin/com/imbric/core/
│       ├── ifs/
│       │   ├── IOBackendTest.kt
│       │   ├── BackendRegistryTest.kt
│       │   ├── PathCapabilitiesTest.kt
│       │   ├── monitoring/
│       │   │   └── DirectoryMonitorTest.kt
│       │   └── backends/
│       │       ├── GioBackendTest.kt
│       │       └── GioTypeMappersIntegrationTest.kt
│       ├── logic/
│       │   └── XferArbiterTest.kt
│       ├── models/
│       │   ├── FileInfoTest.kt
│       │   └── FileJobTest.kt
│       ├── transactions/
│       │   ├── TransactionManagerTest.kt
│       │   ├── TransferOrchestratorTest.kt
│       │   ├── TrashManagerTest.kt
│       │   ├── UndoManagerTest.kt
│       │   └── UndoFactoryTest.kt
│       ├── desktop/
│       │   └── DeviceManagerTest.kt
│       └── testing/
│           └── InMemoryBackend.kt    # HashMap-based test double for IOBackend
└── ref/                              # Reference documentation (java-gi docs, examples)
```

---

## Current Status (What Works)

### ✅ Completed (Stable, Verified)
| Component | Status | Notes |
|:---|---:|:---|
| **ifs abstraction** | ✅ Standardized | V2 upgraded: smart routing, dynamic capabilities, action checks. Added **"Does it require a URI?"** boundary. |
| **InMemoryBackend** | ✅ Fully Recursive | Test double now supports recursive copy/move, metadata failures, and StateFlow trash tracking. |
| **FileInfo model** | ✅ Hardened | 18+ fields, `PathType`, `nativeId`, and verified "Secret Bag" (`attributes`) for native GIO metadata. |
| **XferArbiter** | ✅ Polymorphic | Added **Merge** action; refactored `SyncPolicy` to interface for app-layer extensibility. |
| **TransferOrchestrator** | ✅ Nautilus-grade | Implements recursive pre-flight planning, **Sticky Conflict Resolution** (Apply to All), and robust cancellation. |
| **GioBackend** | ✅ Native | Full native attribute mapping, recursive `WOULD_RECURSE` fallback (code 25), and `TRASH_ITEM_COUNT` optimization. |
| **Transaction Hub** | ✅ Polished | `TransactionManager`, `UndoManager` (with rename support), and `TrashManager` (StateFlow-based) fully verified. |
| **Desktop Integration** | ✅ Native | `DesktopEnvironment` and `GioDesktopEnvironment` for hardware drives and mounts via `GVolumeMonitor`. |
| **Live Monitoring** | ✅ Debounced | `DirectoryMonitor` provides stable, flicker-free `Flow<FileEvent>` from native `GFileMonitor`. |

---

## The java-gi Binding Pipeline (5-Step Automated Process)

All steps are automated in `scripts/generate_bindings.sh`:

```
Step 1: Download java-gi CLI
         → Codeberg release v0.15.0 → build/native-gen/tools/
Step 2: Extract Foundation + Hand-written types
         → org.javagi.*, glib/List.java, SList.java, HashTable.java, ByteArray.java
         → from Maven Central glib-0.15.0-sources.jar
Step 3: Generate GNOME 46 bindings from local GIR files
         → /usr/share/gir-1.0/{GLib,GObject,Gio}-2.0.gir
         → using -d org.gnome package flag
Step 4: Flatten directory structure (glib/org/... + gobject/org/... + gio/org/... → org/)
         → Prevents "duplicate class" errors from conflicting directory roots
Step 5: Surgical patching (GPid pointer bug in MountOperation.java)
         → sed: Pid.get*Values → Alias.getAddressValues
         → sed: pointer size 4 → 8 (64-bit)
         → sed: remove module-info.java
```

### The Three Bugs We Tamed

| Bug | Root Cause | Symptom | Fix |
|:---|---:|:---|---:|
| **GPid Pointer Mismatch** | GNOME 46 defines GPid as `void*`; generator templates hardcode `int` | `cannot find symbol Pid.getJava.lang.foreign...` | `sed` patch: 8-byte pointer, `Alias.getAddressValues` |
| **Initialization Paradox** | Java interface static methods **don't** trigger library static init | `UnsupportedOperationException: Cannot find function 'g_file_new_for_uri'` | Manual `` Gio.`javagi$ensureInitialized`() `` in `GioBackend.init` |
| **Generator Flattening** | Generator nests per-library dirs (`glib/org/`, `gio/org/`) vs flat `org/gnome/` in official JAR | `duplicate class: org.gnome.glib.X` | Flatten via `find ... -path "*/org/gnome/*"` → single root |
| **G_IO_ERROR code** | GIOErrorEnum mapping mismatch | `WOULD_RECURSE` was assumed 32, is actually 25 | Verified 25 in GNOME 46 headers; hardcoded in `GioBackend` |

---

## Test Infrastructure

| Test Class | Type | Backend | Purpose |
|:---|---:|:---|---:|
| `IOBackendTest.kt` | Unit | `InMemoryBackend` | Verify IOBackend contract (list, exists, getMetadata, copy, move) |
| `TransactionManagerTest.kt`| Unit | `InMemoryBackend` | Verify batch lifecycle, progress, and cleanup |
| `TransferOrchestratorTest.kt`| Unit | `InMemoryBackend` | Verify recursive merge, sticky decisions, and planning failures |
| `DirectoryMonitorTest.kt` | Unit | `InMemoryBackend` | Verify event debouncing and buffering |
| `DeviceManagerTest.kt` | Unit | `InMemoryBackend` | Verify drive tracking and StateFlow updates |
| `UndoFactoryTest.kt` | Unit | None | Verify "Undo DNA" generation for all ops |
| `GioTypeMappersIntegrationTest.kt`| Integration | Real GIO | Verify GIO-to-Imbric attribute mapping accuracy |
| `XferArbiterTest.kt` | Unit | None | Sync policy evaluation, conflict actions |
| `GioBackendTest.kt` | Integration | Real GIO | Physical filesystem: listing, metadata, symlinks, recursive copy/move |

**Total Tests:** 46+ passing (including deep recursive merge and metadata hardening suites).

---

## Architecture Decisions (The "Why")

### 1. Polymorphic Sync Policies (The "Rsync Engine")
**Decision:** Refactored `SyncPolicy` from a `sealed class` to a public **`interface`**.

**Why:**
- **App-Layer Control:** Allows the application layer to define "Smart" policies that access external state (databases, cloud metadata) without modifying the Core.
- **Rsync-lite:** Standard policies like `ModifiedOnly` are now standardized implementations that any UI can toggle.
- **Metadata-Intelligence:** Policies now receive the full `FileInfo` including the `attributes` bag, enabling checksum-based or permission-based synchronization.
- **Ergonomics:** `SyncPolicy.custom { ... }` factory provides a lightweight path for ad-hoc logic while maintaining a structured API for complex rules.

### 2. Sync over Async (Phase 1)
**Decision:** Use synchronous GIO calls (`enumerateChildren`, `queryInfo`) wrapped in `Dispatchers.IO` instead of native `...Async` methods.

**Why:**
- GIO's async is Main-Loop-dependent. Without a running `g_main_loop_run()`, callbacks never fire → coroutines hang forever
- Spawning a dedicated GLib Main Loop thread adds the same deadlock/complexity we fled from in Python
- `Dispatchers.IO` is an elastic thread pool (default 64 threads) — no starvation risk
- For Compose UI, this is indistinguishable from async: the Flow emits results on IO, UI observes on Main

**Critical Synchronization Pattern:**
When relaying events from synchronous `commitTransaction()` calls through a `channelFlow` (e.g. in `TransferOrchestrator`), use `launch(start = CoroutineStart.UNDISPATCHED)` for the collector. This ensures the collector is subscribed *before* the synchronous emits occur, preventing missed events and hangs in virtual-time test dispatchers.

**Future Async Path:**
Three bridge patterns available (see `ref/GIO-COROUTINE-BRIDGE.md`):
1. **Idle-Async Bridge** — `GLib.idleAdd` + `suspendCancellableCoroutine` to wrap native async methods without a dedicated loop thread
2. **MainContext Pump** — `MainContext.default().iteration(mayBlock)` integrated into Compose frame callbacks (`withFrameMillis`)
3. **Custom `GlibDispatcher`** — `CoroutineDispatcher` scheduling work via `GLib.idleAdd`

### 3. Local Generation over Pre-built JARs
**Decision:** Generate bindings from local GIR files rather than using Maven Central's pre-built JARs.

**Why:**
- Maven Central's JARs are compiled for GNOME 50 — **incompatible with GNOME 46** at binary level
- Local GIR files guarantee perfect ABI match with the host OS libraries
- The `generate_bindings.sh` script is a project artifact — any machine can reproduce

### 4. Compose over GTK
**Decision:** UI will use Compose Multiplatform (Kotlin/JVM), not GTK.

**Why:**
- Compose is Kotlin-native with first-class coroutine/Flow integration
- GTK signal system would add unnecessary bridging between GObject and Kotlin StateFlow
- Internal communication uses `StateFlow`/`SharedFlow` — no GObject signals needed

### 5. Application Lifecycle (GApplication + Compose)
**Decision:** Use `GApplication.register()` (not `app.run()`), integrate via idle callbacks.

**Why:**
- `Application.run(args)` starts a GTK event loop, blocking the thread — incompatible with Compose
- `register()` activates the GMainContext without blocking, enabling `GLib.idleAdd`/`timeoutAdd` to process
- **Critical:** `register()` expects `argv[0]` to be program name. Prepend `"imbric"` to args array.

---

## GioBackend Initialization Pattern (Mandatory)

Every class that uses GIO types must call `Gio.javagi$ensureInitialized()` before using GIO static methods:

```kotlin
class GioBackend : IOBackend {
    init {
        org.gnome.gio.Gio.`javagi$ensureInitialized`()
    }
    // ...
}
```

Without this, calling `File.newForUri(...)` throws:
```
UnsupportedOperationException: Cannot find function 'g_file_new_for_uri'
```

---

## Next Steps (New Session)

### Phase 2 — Compose UI & App Layer
1. **Sidebar Aggregator**: Combine GTK bookmarks, `recent:///` locations, and `DeviceManager` drives into a unified sidebar model.
2. **Thumbnail Loader**: Implement an async image loader (like Coil/Kamel) to load the `thumbnailPath` exposed in `FileInfo`.
3. **Main Application Bridge**: Initialize Compose Desktop and integrate `GApplication.register()` with the `MainContext.iteration()` pump for native callbacks.
4. **Visual Prototype**: Build the first interactive Compose Multiplatform frontend consuming the transaction engine and ambient providers.


---

*Generated after binding-generation battle (Sessions 1-2), Core Rewrite (Sessions 3-4), and Policy Hardening (Session 5). Updated at session close.*

sincerely yours, crimson heart ❤️
