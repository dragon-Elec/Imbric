# Package Context: desktop

com.imbric.core.desktop
Integrates virtual desktop environment managers, hardware volume sensors, GSettings accent/theme trackers, and persistent bookmark lists.

## Rules
- Avoid referencing production singletons inside unit tests; inject interface stubs (e.g. StarredStateProvider, TrashStateProvider) instead.
- Native GIO volume callbacks require active MainContext pumps to function correctly.

## Atomic Notes
- !Decision: [GSettings interface theme detection] - Reason: Querying GNOME org.gnome.desktop.interface scheme color-scheme provides true system theme states.
- !Pattern: [Callback-to-flow mapping] - Reason: Converts native GNOME VolumeMonitor drive connection callbacks into asynchronous coroutine Flow streams via callbackFlow.
- !Pattern: [Debounced GIO monitors] - Reason: Debounces rapid filesystem monitors by 500ms-2000ms before reading database tags to optimize CPU cycles.

## Index
- DesktopEnvironment.kt — Interface detailing OS volume mounting, default application launching, and interface observations.
- DeviceManager.kt — High-level volume coordinator exposing drives StateFlow for application sidebars.
- TrashMonitor.kt — Singleton watching GIO trash:/// empty/filled statuses.
- StarredManager.kt — Singleton tracking GNOME metadata tag changes for Nautilus-starred entries.
- BookmarkList.kt — Bi-directional synchronizer syncing bookmarks.json with local ~/.config/gtk-3.0/bookmarks.
- DesktopLinkMonitor.kt — Singleton monitoring the desktop directory for link changes and providing a live list of desktop links.
- GioSettingsProvider.kt — Reactive wrapper for GSettings allowing observation of system preference changes.
- backends/GioDesktopEnvironment.kt — Concrete FFM implementation for GNOME drive detection and interface GSettings.
- DesktopDirectory.kt — Trivial. Helper resolving OS default paths (Downloads, Documents, Pictures).
- SandboxDetector.kt — Trivial. Helper checking container runtime structures (.dockerenv, flatpak-info).
- DesktopLink.kt — Trivial. Data class representing a desktop link (computer, home, trash, network, shortcut).
- DesktopProviders.kt — Dependency Injection interfaces (`SettingsProvider`, `TrashStateProvider`, `StarredStateProvider`, `DesktopLinkProvider`) for decoupling application logic from host OS hardware state.

---

## Audits

### [FILE: DesktopEnvironment.kt] [USABLE]
Role: Interface definition defining drive observations, default application launching, and dark/light themes.

/DNA/: [observeDrives() => Flow<List<DesktopDrive>>] + [mount(driveId) => Result<String>] + [getDefaultApp(mime) => DesktopAppInfo?]

- SrcDeps: (none)
- SysDeps: kotlinx.coroutines.flow.Flow

API:
  - DesktopEnvironment (interface):
    - fun observeDrives(): Flow<List<DesktopDrive>>
    - suspend fun mount(driveId: String): Result<String>
    - suspend fun unmount(driveId: String): Result<Unit>
    - fun getDefaultApp(mimeType: String): DesktopAppInfo?
    - fun getAllApps(mimeType: String): List<DesktopAppInfo>
    - suspend fun openFile(uri: String): Result<Unit>
    - fun observeTheme(): Flow<ThemeMode>
  - DesktopDrive:
    - val id: String
    - val name: String
    - val icon: String?
    - val isMounted: Boolean
    - val mountUri: String?
    - val totalBytes: Long
    - val availableBytes: Long
  - DesktopAppInfo:
    - val id: String
    - val name: String
    - val executable: String
    - val icon: String?
  - enum class ThemeMode: LIGHT, DARK, SYSTEM


### [FILE: DeviceManager.kt] [USABLE]
Role: Sidebar-facing coordinator tracking eager StateFlow volumes and mount requests.

/DNA/: [drives = environment.observeDrives().stateIn(scope, SharingStarted.Eagerly) -> mount/unmount delegates => Result]

- SrcDeps: .desktop.DesktopEnvironment, .desktop.DesktopDrive
- SysDeps: kotlinx.coroutines{CoroutineScope, Dispatchers, SupervisorJob}, kotlinx.coroutines.flow{StateFlow, SharingStarted, stateIn}

API:
  - DeviceManager:
    - val drives: StateFlow<List<DesktopDrive>>
    - suspend fun mount(drive: DesktopDrive): Result<String>
    - suspend fun unmount(drive: DesktopDrive): Result<Unit>


### [FILE: TrashMonitor.kt] [USABLE]
Role: GFileMonitor-backed directory status observer mapping native trash:/// counts to StateFlows.

/DNA/: [setupMonitor -> homeDir.monitorDirectory -> onChanged -> debounce refreshJob -> queryInfo(trash::item-count) => isEmpty.value = count == 0]

- SrcDeps: .desktop.TrashStateProvider
- SysDeps: kotlinx.coroutines{CoroutineScope, Dispatchers, SupervisorJob, launch, delay}, kotlinx.coroutines.flow{StateFlow}, org.gnome.gio{Gio, File, FileMonitor, FileMonitorFlags, FileQueryInfoFlags}, org.gnome.glib.GLib

API:
  - TrashMonitor:
    - val isEmpty: StateFlow<Boolean>
    - fun refresh()
    - companion object getInstance(): TrashMonitor
    - companion object clear(): Unit


### [FILE: StarredManager.kt] [USABLE]
Role: GFileMonitor-backed tag observer mapping metadata::nautilus-tags-starred fields to lists.

/DNA/: [setupMonitor -> homeDir.monitorDirectory -> onChanged -> debounce refreshJob -> recentRoot.enumerateChildren(metadata::nautilus-tags-starred) => starredUris.value = starred]

- SrcDeps: .desktop.StarredStateProvider
- SysDeps: kotlinx.coroutines{CoroutineScope, Dispatchers, SupervisorJob, launch, delay, yield}, kotlinx.coroutines.flow{StateFlow, update}, org.gnome.gio{Gio, File, FileMonitor, FileMonitorFlags, FileQueryInfoFlags}, org.gnome.glib.GLib

API:
  - StarredManager:
    - val starredUris: StateFlow<Set<String>>
    - fun refresh()
    - fun isStarred(uri: String): Boolean
    - suspend fun toggleStarred(uri: String): Result<Boolean>
    - companion object getInstance(): StarredManager


### [FILE: BookmarkList.kt] [USABLE]
Role: Debounced persistence sync manager matching bookmark.json with system GTK bookmarks.

/DNA/: [load() -> parse bookmarks.json | import parseGtkBookmarks -> setupReactiveSave -> debounce(500) -> saveJson() + writeGtkBookmarks] + [setupGtkMonitor -> onChanged -> debounce -> importFromGtk()]

- SrcDeps: .models.Bookmark
- SysDeps: kotlinx.coroutines{CoroutineScope, Dispatchers, SupervisorJob, launch, delay, cancel}, kotlinx.coroutines.flow{StateFlow, MutableStateFlow, debounce, drop, collect, update}, kotlinx.serialization.json.Json, org.gnome.gio{Gio, File, FileMonitor, FileMonitorFlags, FileMonitorEvent}, org.gnome.glib.GLib, java.nio.file.Path

API:
  - BookmarkList:
    - val bookmarks: StateFlow<List<Bookmark>>
    - fun contains(uri: String): Boolean
    - fun canBookmark(uri: String): Boolean
    - fun getBookmark(uri: String): Bookmark?
    - fun getAll(): List<Bookmark>
    - fun add(bookmark: Bookmark, index: Int = -1): Boolean
    - fun remove(uri: String)
    - fun moveItem(fromIndex: Int, toIndex: Int)
    - companion object getInstance(): BookmarkList


### [FILE: DesktopLinkMonitor.kt] [USABLE]
Role: Singleton monitoring the desktop directory for link changes and providing a live list of desktop links.

/DNA/: [setupMonitor -> desktopDir.monitorDirectory -> onChanged -> debounce refreshJob -> refresh()] + [refresh() -> add system links (computer, home, trash, network) + scan desktopDir for .desktop shortcuts => _links.value = links]

- SrcDeps: .desktop.DesktopLinkProvider, .desktop.DesktopLink, .desktop.DesktopDirectory
- SysDeps: kotlinx.coroutines{CoroutineScope, Dispatchers, SupervisorJob, launch, delay, yield}, kotlinx.coroutines.flow{StateFlow, MutableStateFlow, asStateFlow}, org.gnome.gio{Gio, File, FileMonitor, FileMonitorFlags, FileQueryInfoFlags}, org.gnome.glib.GLib

API:
  - DesktopLinkMonitor:
    - val links: StateFlow<List<DesktopLink>>
    - fun refresh(): Unit
    - companion object getInstance(): DesktopLinkMonitor
    - companion object clear(): Unit
!Caveat: DesktopLinkMonitor is a singleton with a private constructor and thread-safe double-checked locking companion object.


### [FILE: GioSettingsProvider.kt] [USABLE]
Role: Reactive wrapper for GSettings allowing observation of system preference changes.

/DNA/: [GioSettingsProvider(schemaId) -> Settings(schemaId)] + [observeBoolean/String/Int(key) -> callbackFlow { settings.onChanged(key) { trySend(get) } -> awaitClose { disconnect() } } -> onStart { emit(get) }] + [setBoolean/String/Int(key, value) -> settings.set(key, value)]

- SrcDeps: .desktop.SettingsProvider
- SysDeps: kotlinx.coroutines.flow{Flow, callbackFlow, onStart}, kotlinx.coroutines.channels.awaitClose, org.gnome.gio{Gio, Settings}

API:
  - GioSettingsProvider:
    - val schemaId: String
    - fun observeBoolean(key: String): Flow<Boolean>
    - fun observeString(key: String): Flow<String>
    - fun observeInt(key: String): Flow<Int>
    - fun setBoolean(key: String, value: Boolean): Unit
    - fun setString(key: String, value: String): Unit
    - fun setInt(key: String, value: Int): Unit
!Caveat: Calls `Gio.javagi$ensureInitialized()` in init block to ensure native bindings are ready.


### [FILE: GioDesktopEnvironment.kt] [USABLE]
Role: Concrete FFM GNOME implementation tracking volume monitor connectors and Settings keys.

/DNA/: [observeDrives() -> callbackFlow { connectedDrives.map { async { mapDrive(it) } } -> awaitAll() -> send -> onDriveConnected/Disconnected update }] + [observeTheme() -> callbackFlow { settings(interface).getString(color-scheme) => emit ThemeMode }]

- SrcDeps: .desktop.DesktopEnvironment, .desktop.DesktopDrive, .desktop.ThemeMode, .desktop.DesktopAppInfo, .ifs.backends.GioCoroutineBridge
- SysDeps: kotlinx.coroutines{Dispatchers, launch, async, awaitAll, withContext}, kotlinx.coroutines.flow{Flow, callbackFlow, flowOn}, org.gnome.gio{Gio, VolumeMonitor, File, Settings}, org.gnome.glib.GLib

API:
  - GioDesktopEnvironment:
    - fun observeDrives(): Flow<List<DesktopDrive>>
    - suspend fun mount(driveId: String): Result<String>
    - suspend fun unmount(driveId: String): Result<Unit>
    - fun getDefaultApp(mimeType: String): DesktopAppInfo?
    - fun getAllApps(mimeType: String): List<DesktopAppInfo>
    - suspend fun openFile(uri: String): Result<Unit>
    - fun observeTheme(): Flow<ThemeMode>
