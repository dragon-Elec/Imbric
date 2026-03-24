"""
Pre-generated test data fixtures for Imbric tests.

This module provides paths to pre-created test data for reproducible testing.
Data is created on first access and cached for subsequent tests.

Types of fixtures:
- Directory structures (nested folders, various depths)
- Files with special names (unicode, spaces, special chars)
- Edge case files (symlinks, empty files, huge files)
- Real-world scenarios (photo dumps, document folders)
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
import hashlib


# =============================================================================
# Base Fixture Directory
# =============================================================================


def get_fixture_base() -> Path:
    """Get or create the base fixtures directory."""
    base = Path(tempfile.gettempdir()) / "imbric_fixtures"
    base.mkdir(parents=True, exist_ok=True)
    return base


# =============================================================================
# Edge Case Fixtures
# =============================================================================


def get_symlink_loop_fixture() -> Path:
    """
    Creates a directory with a circular symlink for testing.
    Use with care - recursive operations may hang.
    """
    base = get_fixture_base() / "symlink_loop"
    if not base.exists():
        base.mkdir(parents=True)
        link = base / "recursive_link"
        link.symlink_to(base)  # Points to itself
    return base


def get_deep_symlink_fixture() -> Path:
    """
    Creates nested directories with symlinks pointing to parent.
    """
    base = get_fixture_base() / "deep_symlink"
    if not base.exists():
        base.mkdir(parents=True)
        for i in range(3):
            subdir = base / f"level_{i}"
            subdir.mkdir(exist_ok=True)
            if i > 0:
                # Symlink in each subdir pointing to level above
                (subdir / "parent_link").symlink_to(base / f"level_{i - 1}")
    return base


def get_unicode_names_fixture() -> Path:
    """
    Creates files with unicode characters in names.
    Tests handling of non-ASCII paths.
    """
    base = get_fixture_base() / "unicode_names"
    if not base.exists():
        base.mkdir(parents=True)
        unicode_names = [
            "café.txt",
            "日本語.txt",
            "Документ.txt",
            "파일.txt",
            "🎉 celebration.txt",
            "file with spaces.txt",
            "file-with-dashes.txt",
            "file_with_underscores.txt",
            "CamelCase.txt",
            "UPPERCASE.TXT",
        ]
        for name in unicode_names:
            (base / name).write_text(f"Content of {name}")
    return base


def get_long_names_fixture() -> Path:
    """
    Creates files with very long names.
    Tests handling of path length limits.
    """
    base = get_fixture_base() / "long_names"
    if not base.exists():
        base.mkdir(parents=True)
        # Create names of various lengths
        for length in [100, 200, 255]:
            name = "a" * length + ".txt"
            try:
                (base / name).write_text(f"Length: {length}")
            except OSError:
                # OS may not support this length
                pass
    return base


def get_special_chars_fixture() -> Path:
    """
    Creates files with special characters in names.
    """
    base = get_fixture_base() / "special_chars"
    if not base.exists():
        base.mkdir(parents=True)
        special_names = [
            "file with 'quotes'.txt",
            'file with "double quotes".txt',
            "file$with&special.txt",
            "file#with#hashes.txt",
            "file@with@at.txt",
            "file[with]brackets.txt",
            "file;with;semicolons.txt",
        ]
        for name in special_names:
            try:
                (base / name).write_text(f"Content of {name}")
            except OSError:
                # Some filesystems don't allow these
                pass
    return base


# =============================================================================
# Size Fixtures
# =============================================================================


def get_large_file_fixture(size_mb: int = 10) -> Path:
    """
    Creates a large file of specified size.

    Args:
        size_mb: Size in megabytes

    Returns:
        Path to the large file
    """
    base = get_fixture_base() / "large_files"
    base.mkdir(parents=True, exist_ok=True)

    file_path = base / f"large_{size_mb}mb.bin"

    if not file_path.exists():
        # Create sparse-ish file with random chunks
        chunk_size = 1024 * 1024  # 1MB chunks
        with open(file_path, "wb") as f:
            for _ in range(size_mb):
                f.write(os.urandom(chunk_size))

    return file_path


def get_empty_files_fixture() -> Path:
    """
    Creates multiple empty files.
    """
    base = get_fixture_base() / "empty_files"
    if not base.exists():
        base.mkdir(parents=True)
        for i in range(5):
            (base / f"empty_{i}.txt").write_text("")
    return base


# =============================================================================
# Structure Fixtures
# =============================================================================


def get_nested_structure_fixture(depth: int = 5, breadth: int = 3) -> Path:
    """
    Creates a nested directory structure.

    Args:
        depth: How deep to nest directories
        breadth: How many items per directory

    Structure:
        root/
            file_0.txt
            dir_0/
                file_0.txt
                dir_0/
                    ...
    """
    base = get_fixture_base() / f"nested_d{depth}_b{breadth}"
    if not base.exists():
        base.mkdir(parents=True)
        _create_nested_recursive(base, depth, breadth)
    return base


def _create_nested_recursive(parent: Path, remaining_depth: int, breadth: int):
    """Recursively create nested structure."""
    if remaining_depth <= 0:
        return

    # Create files
    for i in range(breadth):
        (parent / f"file_{i}.txt").write_text(f"Content at depth {5 - remaining_depth}")

    # Create subdirectories
    for i in range(breadth):
        subdir = parent / f"dir_{i}"
        subdir.mkdir(exist_ok=True)
        _create_nested_recursive(subdir, remaining_depth - 1, breadth)


def get_camera_dump_fixture(num_photos: int = 100) -> Path:
    """
    Simulates a camera dump with photos in nested folder structure.

    Structure:
        DCIM/
            100CANON/
                IMG_0001.jpg
                ...
            101CANON/
                IMG_0001.jpg
                ...
    """
    base = get_fixture_base() / "camera_dump"
    if not base.exists():
        base.mkdir(parents=True)
        dcim = base / "DCIM"
        dcim.mkdir()

        photos_per_folder = 100
        num_folders = (num_photos + photos_per_folder - 1) // photos_per_folder

        photo_num = 1
        for folder_num in range(num_folders):
            folder = dcim / f"{folder_num:03d}CANON"
            folder.mkdir()

            for i in range(min(photos_per_folder, num_photos - photo_num + 1)):
                # Fake EXIF-like filename
                filename = f"IMG_{photo_num:04d}.jpg"
                (folder / filename).write_bytes(b"FAKE_JPEG_HEADER" + os.urandom(1024))
                photo_num += 1

    return base


def get_mixed_content_fixture() -> Path:
    """
    Creates a realistic mixed content folder.
    """
    base = get_fixture_base() / "mixed_content"
    if not base.exists():
        base.mkdir(parents=True)

        # Documents
        docs = base / "documents"
        docs.mkdir()
        (docs / "report.pdf").write_bytes(b"PDF_HEADER" + b"x" * 5000)
        (docs / "notes.txt").write_text("Meeting notes")
        (docs / "budget.xlsx").write_bytes(b"XLSX_HEADER" + b"y" * 3000)

        # Images
        images = base / "images"
        images.mkdir()
        for i in range(5):
            (images / f"photo_{i}.jpg").write_bytes(b"JPEG" + os.urandom(10000))

        # Archives
        archives = base / "archives"
        archives.mkdir()
        (archives / "backup.zip").write_bytes(b"PK" + b"z" * 10000)

        # Mixed names
        (base / "README.md").write_text("# Project")
        (base / ".hidden").write_text("Hidden file")

    return base


# =============================================================================
# Cleanup
# =============================================================================


def cleanup_fixtures():
    """Remove all cached fixture data."""
    base = get_fixture_base()
    if base.exists():
        shutil.rmtree(base)


# =============================================================================
# Fixture Registry (for conftest integration)
# =============================================================================

FIXTURES: Dict[str, callable] = {
    "symlink_loop": get_symlink_loop_fixture,
    "deep_symlink": get_deep_symlink_fixture,
    "unicode_names": get_unicode_names_fixture,
    "long_names": get_long_names_fixture,
    "special_chars": get_special_chars_fixture,
    "empty_files": get_empty_files_fixture,
    "nested_structure": get_nested_structure_fixture,
    "camera_dump": get_camera_dump_fixture,
    "mixed_content": get_mixed_content_fixture,
}


def get_all_fixtures() -> Dict[str, Path]:
    """Get all fixture paths (creates if needed)."""
    return {name: factory() for name, factory in FIXTURES.items()}
