---
description: Context Router for com.imbric.app package. Contains the desktop application layer, UI components, view models, and bootstrap logic.
---

# App Package Context

## Identity
- Package: `com.imbric.app`
- Purpose: Desktop Compose Multiplatform application layer. Orchestrates core VFS primitives into a user-facing file manager product with Material 3 design, Monet dynamic colors, and GLib event loop integration.

## Rules
- UI components MUST be stateless composables where possible, delegating state to ViewModels.
- All native callbacks (GIO async, signals) MUST be processed on the GLib MainContext, which is pumped in sync with the Compose frame loop.
- Use `DynamicMaterialTheme` with `MaterialKolor` for Monet dynamic colors seeded by GNOME GSettings.

## Atomic Notes
- `!Decision: [GLib MainContext Pump] - Reason: Compose Desktop and GIO async callbacks run on different threads; pumping GLib events on the UI thread prevents thread-safety issues and ensures reactive UI updates.`
- `!Pattern: [Atomic View State] - Reason: Combining URI, items, and loading state into a single FileBrowserState prevents race conditions and UI flashing during navigation.`
- `!Pattern: [DirState Lifecycle Management] - Reason: ViewModel must call destroy() on the previous DirState when navigating away to stop directory monitoring and release native resources.`

## Index
- bootstrap/Main.kt — Application entry point, initializes GIO and boots Compose UI.
- bootstrap/ImbricApp.kt — Root UI layout coordinating AddressBar, navigation, and DirectoryView.
- bootstrap/MainContextPump.kt — Composable synchronizing GLib event loop with Compose frame loop.
- ui/AddressBar.kt — Path segment breadcrumb navigation and layout toggle.
- ui/DirectoryView.kt — List and Grid file views with hover states and thumbnail rendering.
- ui/theme/ImbricTheme.kt — Material 3 theme wrapper with Monet dynamic color generation.
- ui/theme/ThemeDetector.kt — GSettings observer for system dark mode and GTK accent colors.
- viewmodel/FileBrowserViewModel.kt — State coordinator managing navigation history and DirState lifecycles.

---

## Audits

### [FILE: Main.kt] [USABLE]
Role: Application entry point, initializes GIO and boots Compose UI.

/DNA/: [main(args) -> Gio.ensureInitialized() -> ImbricDesktop.initialize() -> application { Window { MainContextPump() + ImbricTheme { ImbricApp(registry) } } }]

- SrcDeps: .bootstrap.MainContextPump, .bootstrap.ImbricApp, .ui.theme.ImbricTheme, .core.desktop.ImbricDesktop, .core.ifs.BackendRegistry, .core.ifs.provider.DirStateRegistry
- SysDeps: org.gnome.gio.Gio, androidx.compose.ui.window{Window, application}

API:
  - fun main(args: Array<String>): Unit
!Caveat: `Gio.javagi$ensureInitialized()` must be called before any other GIO classes are loaded to prevent JVM crashes.

### [FILE: ImbricApp.kt] [USABLE]
Role: Root UI layout coordinating AddressBar, navigation, and DirectoryView.

/DNA/: [ImbricApp(registry) -> FileBrowserViewModel(registry) -> Scaffold { TopAppBar(AddressBar + GoUp button) + FileBrowserContent(AnimatedContent { DirectoryView | LoadingView | EmptyFolderView }) }]

- SrcDeps: .ui.AddressBar, .ui.DirectoryView, .ui.LayoutMode, .viewmodel.FileBrowserViewModel, .core.ifs.provider.DirStateRegistry
- SysDeps: androidx.compose.material3.*, androidx.compose.runtime.*

API:
  - fun ImbricApp(registry: DirStateRegistry): Unit
!Caveat: Uses custom M3 Emphasized easing curves for slide/fade transitions during folder navigation.

### [FILE: MainContextPump.kt] [USABLE]
Role: Composable synchronizing GLib event loop with Compose frame loop.

/DNA/: [MainContextPump() -> LaunchedEffect(Unit) -> while(isActive) { withFrameMillis { while(context.iteration(mayBlock = false)) { /* process events */ } } }]

- SrcDeps: 
- SysDeps: org.gnome.glib.MainContext, androidx.compose.runtime.LaunchedEffect, kotlinx.coroutines.isActive

API:
  - fun MainContextPump(): Unit
!Caveat: `mayBlock = false` is critical in `context.iteration` to prevent blocking the Compose UI thread.

### [FILE: AddressBar.kt] [USABLE]
Role: Path segment breadcrumb navigation and layout toggle.

/DNA/: [AddressBar(uri, layoutMode, onToggleLayoutMode, onSegmentClick) -> IfsUri(uri) -> segments list -> Surface { Row { FolderIcon + segments.forEach { clickable Text + Chevron } + LayoutModeIconButton } }]

- SrcDeps: .ui.LayoutMode, .core.ifs.IfsUri
- SysDeps: androidx.compose.material3.*, androidx.compose.runtime.*

API:
  - fun AddressBar(uri: String, layoutMode: LayoutMode, onToggleLayoutMode: () -> Unit, modifier: Modifier, onSegmentClick: (String) -> Unit): Unit
!Caveat: Limits visible path segments to the last 4 to prevent UI overflow on deep directory structures.

### [FILE: DirectoryView.kt] [USABLE]
Role: List and Grid file views with hover states and dynamic Material 3 MIME type icons.

/DNA/: [DirectoryView(items, layoutMode, onItemClick) -> if(LIST) FileList else FileGrid] + [FileList/FileGrid -> LazyColumn/LazyVerticalGrid + VerticalScrollbar] + [FileRow/FileGridCell -> Surface(hoverable) -> ListItem/Column + getIconForFile(mimeType)]

- SrcDeps: .core.models.FileInfo
- SysDeps: androidx.compose.foundation.*, androidx.compose.material3.*

API:
  - enum class LayoutMode: LIST, GRID
  - fun DirectoryView(items: List<FileInfo>, layoutMode: LayoutMode, onItemClick: (FileInfo) -> Unit, modifier: Modifier): Unit
  - fun getIconForFile(item: FileInfo): ImageVector
  - fun FileList(items: List<FileInfo>, onItemClick: (FileInfo) -> Unit, modifier: Modifier): Unit
  - fun FileGrid(items: List<FileInfo>, onItemClick: (FileInfo) -> Unit, modifier: Modifier): Unit
  - fun FileRow(item: FileInfo, onClick: () -> Unit, modifier: Modifier): Unit
  - fun FileGridCell(item: FileInfo, onClick: () -> Unit, modifier: Modifier): Unit
!Caveat: Uses symbolic Material 3 icons based on MIME types to represent files without requiring slow blocking disk reads for image thumbnails.

### [FILE: ImbricTheme.kt] [USABLE]
Role: Material 3 theme wrapper with Monet dynamic color generation.

/DNA/: [ImbricTheme(content) -> observeDarkMode() + observeAccentColor() -> seedColor = accentSeed ?: purple -> DynamicMaterialTheme(seedColor, useDarkTheme, animate = true) { content() }]

- SrcDeps: .ui.theme.ThemeDetector
- SysDeps: com.materialkolor.DynamicMaterialTheme, androidx.compose.material3.*

API:
  - fun ImbricTheme(content: @Composable () -> Unit): Unit
!Caveat: Uses `MaterialKolor` to generate a full 30+ color tonal palette from a single seed color.

### [FILE: ThemeDetector.kt] [USABLE]
Role: GSettings observer for system dark mode and GTK accent colors.

/DNA/: [ThemeDetector -> GioSettingsProvider("org.gnome.desktop.interface")] + [observeDarkMode() -> provider.observeString("color-scheme") -> map { it == "prefer-dark" }] + [observeAccentColor() -> provider.observeString("gtk-theme") -> map { extractAccentFromThemeName(it) }]

- SrcDeps: .core.desktop.GioSettingsProvider
- SysDeps: kotlinx.coroutines.flow.Flow

API:
  - object ThemeDetector:
    - fun observeDarkMode(): Flow<Boolean>
    - fun isDarkMode(): Boolean
    - fun observeAccentColor(): Flow<Long?>
!Caveat: Falls back to light theme and default purple seed if GSettings schema is unavailable (e.g., non-GNOME desktop).

### [FILE: FileBrowserViewModel.kt] [USABLE]
Role: State coordinator managing navigation history and DirState lifecycles.

/DNA/: [FileBrowserViewModel(registry, initialUri, scope) -> dirStateFlow = _currentUri.map { registry.getOrCreate(it) }] + [state = dirStateFlow.flatMapLatest { combine(it.items, it.isLoading) { items, loading -> FileBrowserState(it.uri, items, loading) } }] + [navigateTo(uri) -> registry.getOrCreate(oldUri).destroy() -> _currentUri.value = uri] + [goUp() -> navigateTo(parent)]

- SrcDeps: .ui.LayoutMode, .core.ifs.IfsUri, .core.ifs.provider.DirState, .core.ifs.provider.DirStateRegistry, .core.models.FileInfo
- SysDeps: kotlinx.coroutines.flow.*, kotlinx.coroutines.CoroutineScope

API:
  - data class FileBrowserState(val uri: String, val items: List<FileInfo>, val isLoading: Boolean, val canGoUp: Boolean)
  - class FileBrowserViewModel:
    - val currentUri: StateFlow<String>
    - val layoutMode: StateFlow<LayoutMode>
    - val state: StateFlow<FileBrowserState>
    - fun navigateTo(uri: String): Unit
    - fun goUp(): Unit
    - fun toggleLayoutMode(): Unit
!Caveat: `navigateTo` explicitly calls `destroy()` on the previous `DirState` to prevent leaking directory monitors and coroutine collectors.
