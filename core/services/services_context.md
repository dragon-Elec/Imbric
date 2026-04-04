Identity: core/services — Stateless utility services: sorting, pre/post operation validation, and file search.

Index:
- search/ — SearchEngine implementations + QThread worker for background search.

---

### [FILE: sorter.py] [DONE]
Role: QML-exposed file list sorter with natural sort, folders-first, and sort-direction state.

/DNA/: `sort(files, key?, asc?)` -> [if folders_first: split dirs/files -> each.sort(key) -> rejoin | else: list.sort(key)] => sorted list; `setKey()/setAscending()/setFoldersFirst()` -> if changed: em:sortChanged

- SysDeps: PySide6{QtCore}, enum

API:
  - SortKey(IntEnum): NAME=0, DATE_MODIFIED=1, SIZE=2, TYPE=3

  - Sorter(QObject):
    Signals: sortChanged()
    Properties: key (int), ascending (bool), foldersFirst (bool)
    - sort(files: list[dict], key=None, ascending=None) -> list[dict]
    - setKey(key: int) -> None
    - setAscending(ascending: bool) -> None
    - setFoldersFirst(enabled: bool) -> None
    - currentKey() -> int: returns current SortKey value.
    - isAscending() -> bool: returns current sort direction.
    - isFoldersFirst() -> bool: returns current folders-first preference.

!Caveat: `sort()` operates on list[dict] (QML JSON model dicts), not `FileInfo` objects. Keys accessed: `isDir`, `name`, `dateModified`, `size`.

---

### [FILE: validator.py] [DONE]
Role: Post-operation filesystem verifier. Runs async spot-checks after I/O completes to detect ghost successes.

/DNA/: `validate(job_id, op_type, src, result, success)` -> if enabled and success: `ValidationRunnable(op_type).run()` -> `_VALIDATORS[op_type](src, result)` -> if passed: em:validationPassed | else: print + em:validationFailed

- SrcDeps: core.backends.gio.helpers
- SysDeps: PySide6{QtCore}, gi.repository{Gio}

API:
  - OperationValidator(QObject):
    Signals: validationPassed(job_id, op_type), validationFailed(job_id, op_type, source, expected, actual)
    - validate(job_id, op_type, source, result_path, success) -> None
    - setEnabled(enabled: bool) -> None

!Caveat: `delete` op_type has no validator entry in `_VALIDATORS`; validation is silently skipped for deletes.
!Caveat: Validator uses `_make_gfile` directly — GIO-coupled, not backend-agnostic. Only works for local/GVfs paths.
