Identity: core/services/search — File search subsystem: pluggable engine selection and QThread-based background worker.

!Decision: [fd > scandir] - Reason: Factory prefers `fd`/`fdfind` if installed for ~10x speed; falls back to pure-Python `ScandirSearchEngine` automatically.
!Pattern: [batched emit] - Reason: SearchWorker collects paths in batches of 50 before emitting `resultsFound` to reduce QML model thrash.

---

### [FILE: engines.py] [DONE]
Role: Search engine ABC and two concrete implementations (fd subprocess, os.scandir).

/DNA/: `get_search_engine()` => FdSearchEngine if `fd`/`fdfind` on PATH else ScandirSearchEngine; `engine.search(dir, pattern, recursive)` => Iterator[path_str]; `stop()` terminates subprocess or sets _cancelled flag.

- SysDeps: abc, typing, os, shutil, subprocess, fnmatch

API:
  - SearchEngine(ABC):
    - search(directory, pattern, recursive=True) -> Iterator[str]
    - stop() -> None
    - name (property) -> str

  - FdSearchEngine(SearchEngine):
    - is_available() -> bool (static)
    - search(...): spawns `fd --absolute-path --hidden --no-ignore [pattern] [dir]`
    - stop(): terminates subprocess

  - ScandirSearchEngine(SearchEngine):
    - search(...): recursive `os.scandir` + `fnmatch`; pattern auto-wrapped to `*pattern*` if no glob chars

  - get_search_engine() -> SearchEngine: factory

!Caveat: FdSearchEngine wraps `pattern` as positional arg to `fd`; empty pattern passes `"."` to match all files.

---

### [FILE: worker.py] [DONE]
Role: QThread wrapper that drives a SearchEngine, emits batched results, and validates location before searching.

/DNA/: `start_search(dir, pattern, recursive)` -> [if running: cancel(); wait(1000)] -> self.start() -> `run()` [validates via Gio.File.query_exists + get_path() for local check] -> em:searchStarted -> loop engine.search: batch.append -> if len>=50: em:resultsFound(batch) -> em:searchFinished(total)

- SrcDeps: core.services.search.engines
- SysDeps: PySide6{QtCore}, gi.repository{Gio}, os

API:
  - SearchWorker(QThread):
    Signals: resultsFound(list[str]), searchFinished(int), searchError(str), searchStarted(str)
    - start_search(directory, pattern, recursive=True) -> None (slot)
    - cancel() -> None (slot)
    - engine_name (property) -> str

!Caveat: Search is limited to local POSIX paths (`gfile.get_path()`); non-local GVfs paths (MTP, SFTP) emit `searchError` rather than attempting search.
