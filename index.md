<!-- INDEX MAINTENANCE RULES
1. New file created → add to this index with 1-line summary
2. File deleted → remove from this index
3. File renamed → update entry
4. Context file created → register in this index
-->

# Imbric VFS Engine - Project Index

/home/ray/Desktop/files/wrk/Imbric/imbric-kt/
├── src/main/kotlin/com/imbric/
│   ├── core/                           — Core headless virtual file system library
│   │   ├── desktop/                    — OS hardware mount listeners, bookmark list, starred files, and trash monitor
│   │   │   └── desktopcontext.md       — Context Router: com.imbric.core.desktop package logic map
│   │   ├── ifs/                        — Virtual File System (VFS) abstraction engine
│   │   │   ├── backends/               — Concrete FFM GIO unified, virtual recent, and search backends
│   │   │   │   └── backendscontext.md  — Context Router: com.imbric.core.ifs.backends package logic map
│   │   │   ├── provider/               — Folder live state coordinators and WeakReference caches
│   │   │   │   └── providercontext.md  — Context Router: com.imbric.core.ifs.provider package logic map
│   │   │   ├── services/               — Thumbnail tracker coordinating generation state flows
│   │   │   └── ifscontext.md           — Context Router: com.imbric.core.ifs package logic map
│   │   ├── logic/                      — Stateless validation rules and Rsync-lite collision decision arbiter
│   │   ├── models/                     — Shared immutable type models (FileInfo, FileJob, VfsError, TrashItem)
│   │   │   └── modelscontext.md        — Context Router: com.imbric.core.models package logic map
│   │   ├── transactions/               — Concurrency-controlled transactional writes and stack undo history
│   │   │   └── transactionscontext.md  — Context Router: com.imbric.core.transactions package logic map
│   │   └── corecontext.md              — Context Router: com.imbric.core package logic map
│   └── app/                            — Desktop Compose M3 file manager product
│       ├── bootstrap/                  — Entry point, GApplication registration, and main GLib context loop pump
│       ├── ui/                         — View components (DirectoryView, AddressBar, dynamic themes)
│       ├── viewmodel/                  — MVVM navigation, selection, and view history state controllers
│       └── appcontext.md               — Context Router: com.imbric.app package logic map
├── scripts/                            — Command line development helper tooling
│   ├── generate_bindings.sh            — Generates java-gi FFI bindings from system GLib/GIO GIR XML files
│   ├── dev.sh                          — Starts continuous compiler watch
│   ├── ib.py                           — Process manager for clean, clean --deep, doctor, dev, run, and kill commands
│   ├── compile_kotlin_grammar.sh       — Tree-sitter AST parser compiler script
│   └── audit_validator.sh              — Checks Logic-DNA context validation format
├── ref/
│   ├── java-gi_patched/                — Local patched generator fixing async safety and callback lifetimes
│   └── leaktrace.md                    — Reference guide for profiling and solving JVM/FFM/C memory leaks
├── gradle/                             — Gradle wrapper resources
├── build.gradle.kts                    — Gradle project build configuration
├── gradle.properties                   — Build environment VM configuration presets
├── dircontextworflow.md                — Package context design and Logic-DNA grammar guide
├── projectcontext.md                   — Context Router: Root high-level architecture routing page
└── index.md                            — This file (Self-maintaining structural layout index)
