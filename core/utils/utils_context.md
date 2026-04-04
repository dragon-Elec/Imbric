1. Identity: /Imbric/core/utils - Stateless formatting, path manipulation, and batch payload helpers.
2. Rules:
3. - Pure Functions: Utilities should remain stateless and side-effect free.
4. - Thread Safety: Must remain thread-safe (no global state) as they are called from multiple GIO and UI threads.
5. 
6. !Decision: [Pure Python > Gio.File] - Reason: Path string manipulation (splitting extensions, auto-rename suffixes) is faster and more predictable in pure Python than VFS roundtrips.
7. 
8. Index:
9. - None

## Module Audits

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

/DNA/: [generate_candidate_path(base, count) -> _split_name_ext() -> suffix_style => str] + [build_conflict_payload(src_path, dest_path, ...) -> dict_mapping => JSON-serializable collision data]

- SrcDeps: None
- SysDeps: re, os

API:
  - generate_candidate_path(base_path, counter, style="copy") => str
  - build_dest_path(src, dest_dir) => str
  - build_renamed_dest(dest, new_name) => str
  - build_conflict_payload(src_path, dest_path, src_info, dest_info, extra_src_data) => dict
38: 
39: ### [FILE: vfs_path.py] [USABLE]
40: Role: URI-safe path manipulation utilities.
41: 
42: /DNA/: [vfs_basename(path) => unquote(name)] + [vfs_dirname(path) => scheme://dir] + [vfs_join(base, *parts) => combined_path]
43: 
44: - SrcDeps: None
45: - SysDeps: urllib.parse, os
46: 
47: API:
48:   - vfs_basename(path_or_uri: str) -> str: returns decoded basename handling schemes.
49:   - vfs_dirname(path_or_uri: str) -> str: returns parent path preserving scheme.
50:   - vfs_join(base: str, *parts) -> str: joins URI parts without breaking schemes.
