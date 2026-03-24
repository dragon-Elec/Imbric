"""
Custom assertions for file operations testing.

These assertions provide better error messages and handle common
file operation edge cases.
"""

import os
import time
from pathlib import Path
from typing import Union, Optional


class FileAssertionError(AssertionError):
    """Base error for file assertion failures."""

    pass


def assert_file_exists(path: Union[str, Path], message: Optional[str] = None):
    """Assert that a file exists and is a regular file (not directory)."""
    path = Path(path)
    if not path.exists():
        raise FileAssertionError(message or f"File does not exist: {path}")
    if path.is_dir():
        raise FileAssertionError(message or f"Expected file, got directory: {path}")


def assert_file_not_exists(path: Union[str, Path], message: Optional[str] = None):
    """Assert that a file does not exist."""
    path = Path(path)
    if path.exists():
        raise FileAssertionError(message or f"File should not exist: {path}")


def assert_dir_exists(path: Union[str, Path], message: Optional[str] = None):
    """Assert that a directory exists."""
    path = Path(path)
    if not path.exists():
        raise FileAssertionError(message or f"Directory does not exist: {path}")
    if not path.is_dir():
        raise FileAssertionError(message or f"Expected directory, got file: {path}")


def assert_file_empty(path: Union[str, Path], message: Optional[str] = None):
    """Assert that a file exists and is empty."""
    path = Path(path)
    assert_file_exists(path)
    if path.stat().st_size != 0:
        raise FileAssertionError(
            message or f"File is not empty: {path} ({path.stat().st_size} bytes)"
        )


def assert_file_not_empty(path: Union[str, Path], message: Optional[str] = None):
    """Assert that a file exists and is not empty."""
    path = Path(path)
    assert_file_exists(path)
    if path.stat().st_size == 0:
        raise FileAssertionError(message or f"File is empty: {path}")


def assert_file_size(
    path: Union[str, Path], expected_size: int, message: Optional[str] = None
):
    """Assert that a file has the expected size."""
    path = Path(path)
    assert_file_exists(path)
    actual = path.stat().st_size
    if actual != expected_size:
        raise FileAssertionError(
            message
            or f"File size mismatch: {path} (expected {expected_size}, got {actual})"
        )


def assert_file_content(
    path: Union[str, Path],
    expected_content: Union[str, bytes],
    message: Optional[str] = None,
    binary: bool = False,
):
    """Assert that a file contains the expected content."""
    path = Path(path)
    assert_file_exists(path)

    if binary:
        actual = path.read_bytes()
        expected = (
            expected_content
            if isinstance(expected_content, bytes)
            else expected_content.encode()
        )
    else:
        actual = path.read_text()
        expected = (
            expected_content
            if isinstance(expected_content, str)
            else expected_content.decode()
        )

    if actual != expected:
        raise FileAssertionError(message or f"File content mismatch for {path}")


def assert_files_identical(
    path1: Union[str, Path], path2: Union[str, Path], message: Optional[str] = None
):
    """Assert that two files have identical content."""
    path1, path2 = Path(path1), Path(path2)
    assert_file_exists(path1, f"First file does not exist: {path1}")
    assert_file_exists(path2, f"Second file does not exist: {path2}")

    # Compare sizes first (fast)
    size1 = path1.stat().st_size
    size2 = path2.stat().st_size

    if size1 != size2:
        raise FileAssertionError(
            message
            or f"Files have different sizes: {path1} ({size1}) vs {path2} ({size2})"
        )

    # Compare content
    if size1 > 0:
        with open(path1, "rb") as f1, open(path2, "rb") as f2:
            if f1.read() != f2.read():
                raise FileAssertionError(
                    message or f"Files have different content: {path1} vs {path2}"
                )


def assert_dir_empty(path: Union[str, Path], message: Optional[str] = None):
    """Assert that a directory is empty."""
    path = Path(path)
    assert_dir_exists(path)
    items = list(path.iterdir())
    if items:
        item_names = [i.name for i in items[:5]]
        raise FileAssertionError(
            message
            or f"Directory is not empty: {path} ({len(items)} items, first: {item_names})"
        )


def assert_dir_not_empty(path: Union[str, Path], message: Optional[str] = None):
    """Assert that a directory contains at least one item."""
    path = Path(path)
    assert_dir_exists(path)
    items = list(path.iterdir())
    if not items:
        raise FileAssertionError(message or f"Directory is empty: {path}")


def assert_dir_count(
    path: Union[str, Path],
    expected_count: int,
    include_dirs: bool = True,
    include_files: bool = True,
    message: Optional[str] = None,
):
    """Assert that a directory contains exactly the expected number of items."""
    path = Path(path)
    assert_dir_exists(path)

    items = list(path.iterdir())
    if include_dirs and include_files:
        actual = len(items)
    else:
        actual = sum(
            1
            for i in items
            if (i.is_dir() and include_dirs) or (i.is_file() and include_files)
        )

    if actual != expected_count:
        raise FileAssertionError(
            message
            or f"Directory count mismatch: {path} (expected {expected_count}, got {actual})"
        )


def assert_path_contains(
    path: Union[str, Path], filename: str, message: Optional[str] = None
):
    """Assert that a directory contains a file or subdirectory with given name."""
    path = Path(path)
    assert_dir_exists(path)

    contained = [i.name for i in path.iterdir()]
    if filename not in contained:
        raise FileAssertionError(
            message
            or f"Directory {path} does not contain '{filename}'. Contents: {contained}"
        )


def assert_symlink_exists(path: Union[str, Path], message: Optional[str] = None):
    """Assert that a symlink exists (pointing anywhere)."""
    path = Path(path)
    if not path.is_symlink():
        raise FileAssertionError(message or f"Path is not a symlink: {path}")


def assert_symlink_targets(
    path: Union[str, Path], target: Union[str, Path], message: Optional[str] = None
):
    """Assert that a symlink points to the expected target."""
    path = Path(path)
    assert_symlink_exists(path)

    actual_target = os.readlink(str(path))
    expected_target = str(target)

    if actual_target != expected_target:
        raise FileAssertionError(
            message
            or f"Symlink target mismatch: {path} (expected '{expected_target}', got '{actual_target}')"
        )


def wait_for_file(
    path: Union[str, Path], timeout_ms: int = 5000, poll_interval_ms: int = 50
) -> bool:
    """Wait for a file to exist. Returns True if exists, False if timeout."""
    path = Path(path)
    start = time.time()
    timeout_sec = timeout_ms / 1000
    poll_sec = poll_interval_ms / 1000

    while not path.exists():
        if (time.time() - start) > timeout_sec:
            return False
        time.sleep(poll_sec)

    return True


def wait_for_file_gone(
    path: Union[str, Path], timeout_ms: int = 5000, poll_interval_ms: int = 50
) -> bool:
    """Wait for a file to be deleted. Returns True if gone, False if timeout."""
    path = Path(path)
    start = time.time()
    timeout_sec = timeout_ms / 1000
    poll_sec = poll_interval_ms / 1000

    while path.exists():
        if (time.time() - start) > timeout_sec:
            return False
        time.sleep(poll_sec)

    return True


def wait_for_dir_contents(
    path: Union[str, Path], expected_count: int, timeout_ms: int = 5000
) -> bool:
    """Wait for directory to contain expected number of items."""
    path = Path(path)
    start = time.time()
    timeout_sec = timeout_ms / 1000

    while True:
        if (time.time() - start) > timeout_sec:
            return False
        if len(list(path.iterdir())) >= expected_count:
            return True
        time.sleep(0.05)
