# Kotlin vs. Python: Transition Notes

## Strengths of the Kotlin Foundation (Over Python)
1. **True Concurrency (No GIL):** Python's Global Interpreter Lock made async I/O and QML thread maintenance a constant struggle. Kotlin Coroutines provide structured, safe concurrency. No more deadlocking QThreads.
2. **Strict Architecture:** The Kotlin version enforces a hard boundary between `core` (the VFS engine) and `app` (the UI). The Python version struggled with logic bleeding into the UI layer.
3. **Type Safety & Performance:** Kotlin's static typing, combined with the K2 compiler and JVM performance, prevents an entire class of runtime errors that were common in the Python/PySide codebase.
4. **Native GIO via FFM:** Using `java-gi` and the JDK 22+ FFM API allows direct, efficient bridging to GNOME's GIO without the heavy overhead of Python's PyGObject introspection.
5. **Robust Transaction Engine:** The `ifs` core and `TransactionManager` in Kotlin handle batch processing, hybrid JIT fallback for conflicts, and Undo operations natively and predictively, compared to the more fragile signal-based routing in the Python version.

## What is NOT Done Yet (Pending Port from Python)
1. **Compose UI Layer:** The Python version had a polished QML UI (Material Symbols Rounded, justified grid, reflow animations, dark/light system palette adaptation). The Kotlin `app/` package is currently just a bootstrap skeleton.
2. **Justified Grid View:** The custom math and layout logic that packed photos smartly without cropping needs to be ported to Compose Desktop.
3. **Advanced Transfer Dialog:** The UI for handling file collisions (size and mtime comparisons) needs to be rebuilt.
4. **Sidebar & Multi-tab Isolation:** The Python version had independent per-tab state and sidebar reflow animations that need to be re-implemented.
5. **Standalone React Gallery Prototype:** The experimental web gallery script is currently left behind in the legacy Python branch.
