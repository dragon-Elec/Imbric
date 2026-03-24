Identity: core/interfaces — ABC layer defining every backend contract. Any new backend must implement these protocols.

!Decision: [ABCs > duck-typing] - Reason: Enforces contract completion at instantiation time; prevents silent partial implementations.
!Pattern: [IO via FileJob] - Reason: All IOBackend methods accept a FileJob and return job_id (str); result is surfaced via signals, never return value.

---

### [FILE: __init__.py] [DONE]
Role: Re-exports all ABCs for single-import convenience.

/DNA/: `from core.interfaces import IOBackend, ScannerBackend, ...` -> all 5 ABCs available.

- SysDeps: (none — pure re-export)

---

### [FILE: io_backend.py] [DONE]
Role: ABC for all file I/O (copy, move, trash, restore, delete, create, rename, symlink).

/DNA/: All methods accept `FileJob` -> return `job_id: str`; contract mandates callers receive outcome via `FileOperationSignals`, not return value.

- SysDeps: abc, core.models.file_job

API:
  - IOBackend(ABC):
    - copy(job) -> str
    - move(job) -> str
    - batch_transfer(job) -> str
    - trash(job) -> str
    - restore(job) -> str
    - delete(job) -> str
    - create_folder(job) -> str
    - create_file(job) -> str
    - rename(job) -> str
    - create_symlink(job) -> str
    - list_trash(job) -> str
    - empty_trash(job) -> str
    - query_exists(path) -> bool
    - is_same_file(path_a, path_b) -> bool

---

### [FILE: scanner_backend.py] [DONE]
Role: ABC for directory scanning; results delivered via signals, not returns.

/DNA/: `scan_directory(path)` -> emits file-discovery signals; `cancel()` -> halts scan in progress.

- SysDeps: abc

API:
  - ScannerBackend(ABC):
    - scan_directory(path) -> None
    - scan_single_file(path) -> None
    - cancel() -> None

---

### [FILE: metadata_provider.py] [DONE]
Role: ABC for synchronous (blocking) metadata retrieval.

/DNA/: `get_file_info(path_or_uri)` => `FileInfo | None`; `get_dimensions` and `get_item_count` may return sentinel (`None`/`-1`) for async-only impls.

- SysDeps: abc, typing, core.models.file_info

API:
  - MetadataProvider(ABC):
    - get_file_info(path_or_uri, attributes=None) -> FileInfo | None
    - get_dimensions(path_or_uri) -> tuple[int, int] | None
    - get_item_count(path) -> int: -1 on error

---

### [FILE: thumbnail_provider.py] [DONE]
Role: ABC for thumbnail generation; providers stacked in registry, first-match wins.

/DNA/: `supports(mime_type)` => bool; `if True` -> `generate(uri, mime, mtime)` => thumb_path | None; `lookup` checks cache before generate.

- SysDeps: abc

API:
  - ThumbnailProviderBackend(ABC):
    - supports(mime_type) -> bool
    - generate(uri, mime_type, mtime) -> str | None
    - lookup(uri, mtime) -> str | None

---

### [FILE: cache_provider.py] [DONE]
Role: ABC for mount-scoped cache layer (get/set/invalidate/warm/clear).

/DNA/: `get(key)` => cached value or None; `warm(path)` pre-fills cache aggressively; `clear()` nukes all entries.

- SysDeps: abc, typing

API:
  - CacheProvider(ABC):
    - get(key) -> object | None
    - set(key, value) -> None
    - invalidate(key) -> None
    - warm(path) -> None
    - clear() -> None
