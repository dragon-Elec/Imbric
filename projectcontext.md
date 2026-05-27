# Project Context: Root Overview

/home/ray/Desktop/files/wrk/Imbric/imbric-kt
Unified virtual file system (VFS) and desktop file manager utilizing safe FFM-bridged GIO bindings and Compose M3.

## Rules
- Keep the local java-gi_patched clone clean; maintain patches strictly on the imbric-patches branch.
- Compile-check all bot PRs using JDK 25 and running tests before merging to prevent compilation regressions.

## Atomic Notes
- !Decision: [Two-Layer Architecture] - Reason: com.imbric.core is a headless, unopinionated library that does not know about views or sidebars, whereas com.imbric.app manages MVVM state and Compose UI views.
- !Pattern: [JvmInline value classes] - Reason: Keeps filesystem path representation zero-allocation while enabling rich scheme and parents parsing via IfsUri.
- !Decision: [GLib BookmarkFile > GTK RecentManager] - Reason: Prevents GdkDisplayManager display server conflicts inside the shared JVM process during Compose rendering.

## Index
- com/imbric/core/ — Headless VFS framework, conflict logic, and OS sensors. Refer to corecontext.md.
- com/imbric/core/ifs/ — VFS interface base and registry. Refer to ifscontext.md.
- com/imbric/core/ifs/provider/ — Live directory state providers and flyweight caches. Refer to providercontext.md.
- com/imbric/core/ifs/backends/ — Native FFM GIO implementations. Refer to backendscontext.md.
- com/imbric/core/transactions/ — Safe transactional writes and stack undo history. Refer to transactionscontext.md.
- com/imbric/app/ — Desktop Compose UI manager and ViewModels.
- index.md — Self-maintaining structural layout index.

---

## Audits

### [FILE: System Flow] [USABLE]
Role: End-to-end VFS listing and rendering lifecycle from bootstrap to UI.

/DNA/: [ImbricDesktop.initialize() -> register VFS Backends -> DirStateRegistry caches -> FileBrowserViewModel navigation -> Compose DirectoryView renders]

- SrcDeps: .desktop.ImbricDesktop, .ifs.BackendRegistry, .ifs.provider.DirStateRegistry, .app.viewmodel.FileBrowserViewModel, .app.ui.DirectoryView
- SysDeps: kotlinx.coroutines, org.gnome.gio

API:
  - System Flow:
    - fun ImbricDesktop.initialize(): registers all backend handlers
    - fun DirStateRegistry.getOrCreate(uri): returns live cache monitor
    - fun FileBrowserViewModel.navigateTo(uri): updates back/forward and current folder
    - fun DirectoryView: observes ViewModel items and updates Compose LazyColumn

!Caveat: Compose UI context pump (MainContextPump) must be active for FFM callbacks to safely fire and render.
