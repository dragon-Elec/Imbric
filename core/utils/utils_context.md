Identity: /Imbric/core/utils - Stateless formatting, path orchestration, and URI-safe manipulation.

Rules:
- [Pure Functions] Utilities MUST remain stateless and side-effect free.
- [Thread Safety] MUST remain thread-safe (no global state) for GIO and UI thread calls.

Atomic Notes:
- !Decision: [Pure Python > Gio.File] - Reason: Path string split/suffix operations are faster/predictable in pure Python than VFS roundtrips.

Index:
- formatting.py — Human-readable string conversion.
- path_ops.py — Path string orchestration and conflict metadata.
- path_classifier.py — Pure utility for VFS path capability detection.
- vfs_path.py — URI-safe path manipulation.
- vfs_enforce.py — VFS enforcement helpers for UI migration.

Audits:

### [FILE: formatting.py] [USABLE]
Role: Human-readable string conversion for file metadata.

/DNA/: [format_size(bytes) -> loop 1024 -> float_precision => str] + [unix_mode_to_str(mode) -> stat.filemode => str]

- SrcDeps: None
- SysDeps: stat

API:
  - format_size(size_bytes: int) => str
  - unix_mode_to_str(mode: int) => str

### [FILE: path_ops.py] [USABLE]
Role: Path string orchestration and conflict metadata formatting.

/DNA/: [path_manipulation (generate/dest/rename) -> vfs_path orchestration => str] + [build_conflict_payload(...) => metadata_dict]

- SrcDeps: .vfs_path
- SysDeps: None

API:
  - generate_candidate_path(base_path, counter, style="copy") => str
  - build_dest_path(src, dest_dir) => str
  - build_renamed_dest(dest, new_name) => str
  - build_conflict_payload(src_path, dest_path, src_info, dest_info, extra_src_data) => dict

### [FILE: vfs_path.py] [USABLE]
Role: URI-safe path manipulation utilities.

/DNA/: [vfs_basename(path) => unquote(name)] + [vfs_dirname(path) => scheme://dir] + [vfs_join(base, *parts) => combined_path]

- SrcDeps: None
- SysDeps: urllib.parse, os

API:
  - vfs_basename(path_or_uri: str) -> str: decoded basename handling schemes.
  - vfs_dirname(path_or_uri: str) -> str: parent path preserving scheme.
  - vfs_join(base: str, *parts) -> str: joins URI parts preserving schemes.

### [FILE: path_classifier.py] [USABLE]
Role: Pure utility that categorizes paths by their VFS capabilities. Zero I/O, thread-safe.

/DNA/: `classify(path)` -> [split scheme from "://" or default "file"] -> [lookup frozensets] => PathCapabilities(scheme, is_native, is_monitorable, is_writable, is_virtual)

- SrcDeps: None
- SysDeps: dataclasses

API:
  - PathCapabilities(dataclass, frozen):
    - scheme: str
    - is_native: bool
    - is_monitorable: bool
    - is_writable: bool
    - is_virtual: bool
    - is_local_file: bool (property)
    - is_recent: bool (property)
    - is_trash: bool (property)
  - classify(path: str) -> PathCapabilities

!Caveat: `is_monitorable` is False for `recent://` and `trash://` — GIO cannot monitor synthetic paths.
!Caveat: `is_writable` is False for `recent://` — it's a read-only aggregation.

---

### [FILE: vfs_enforce.py] [USABLE]
Role: VFS enforcement utilities that force the UI layer to go through BackendRegistry instead of direct os/pathlib access.

/DNA/: [normalize_to_uri(path) -> if no "://" prepend file://] + [require_vfs_path(path, registry) -> get_io(uri) is None => raise RuntimeError] + [is_vfs_routable(path, registry) -> bool]

- SrcDeps: None
- SysDeps: (none)

API:
  - normalize_to_uri(path: str) -> str
  - require_vfs_path(path: str, registry, operation: str = "file operation") -> None
  - is_vfs_routable(path: str, registry) -> bool
