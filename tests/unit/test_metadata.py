"""
Unit tests for metadata utilities.
Tests formatting, MIME detection, and file info extraction.
"""

import pytest
from pathlib import Path

from core.utils.formatting import format_size, unix_mode_to_str
from core.backends.gio.helpers import to_unix_timestamp
from core.backends.gio.metadata import get_file_info, resolve_mime_icon


class TestFormatSize:
    """Test size formatting utility."""

    def test_zero_bytes(self):
        assert format_size(0) == "0.0 B"

    def test_small_bytes(self):
        assert format_size(500) == "500.0 B"

    def test_one_kilobyte(self):
        assert format_size(1024) == "1.0 KB"

    def test_kilobyte_and_half(self):
        assert format_size(1536) == "1.5 KB"

    def test_one_megabyte(self):
        assert format_size(1024**2) == "1.0 MB"

    def test_one_gigabyte(self):
        assert format_size(1024**3) == "1.0 GB"

    def test_terabyte(self):
        assert format_size(1024**4) == "1.0 TB"


class TestUnixModeToStr:
    """Test Unix permission string formatting."""

    def test_executable_file(self):
        """0o100755 = -rwxr-xr-x"""
        assert unix_mode_to_str(0o100755) == "-rwxr-xr-x"

    def test_regular_file(self):
        """0o644 = rw-r--r--"""
        assert unix_mode_to_str(0o100644) == "-rw-r--r--"

    def test_full_permissions(self):
        """0o777 = rwxrwxrwx"""
        assert unix_mode_to_str(0o100777) == "-rwxrwxrwx"

    def test_read_only(self):
        """0o100444 = -r--r--r-- (file prefix + read-only)"""
        assert unix_mode_to_str(0o100444) == "-r--r--r--"


class TestToUnixTimestamp:
    """Test GLib.DateTime to Unix timestamp conversion."""

    def test_valid_datetime(self):
        from gi.repository import GLib

        now = GLib.DateTime.new_now_local()
        ts = to_unix_timestamp(now)
        assert isinstance(ts, int)
        assert ts > 0

    def test_none_returns_zero(self):
        assert to_unix_timestamp(None) == 0


class TestResolveMimeIcon:
    """Test MIME icon resolution."""

    def test_text_file(self, tmp_path):
        """Text file should resolve to text-related icon."""
        f = tmp_path / "test.txt"
        f.write_text("Hello")

        from gi.repository import Gio

        gfile = Gio.File.new_for_path(str(f))
        icon_name = resolve_mime_icon(gfile)

        assert icon_name in [
            "text-plain",
            "text-x-generic",
            "application-text",
            "text-plain-symbolic",
            "text-x-generic-symbolic",
        ]

    def test_none_file_returns_generic(self, tmp_path):
        """Nonexistent file should return generic icon."""
        from gi.repository import Gio

        gfile = Gio.File.new_for_path(str(tmp_path / "nonexistent.txt"))
        icon_name = resolve_mime_icon(gfile)
        # Accept any generic icon
        assert "generic" in icon_name or icon_name == "text-x-generic"


class TestGetFileInfo:
    """Test file info extraction."""

    def test_basic_file_info(self, tmp_path):
        """Verify basic file info extraction."""
        f = tmp_path / "info_test.txt"
        f.write_text("Data")

        info = get_file_info(str(f))

        assert info is not None
        assert info.name == "info_test.txt"
        assert info.size == 4
        assert info.size_human == "4.0 B"
        assert not info.is_dir
        assert not info.is_symlink
        assert info.mime_type in ["text/plain", "application/x-zerosize"]
        assert info.modified_ts > 0
        assert "r" in info.permissions_str

    def test_directory_info(self, tmp_path):
        """Directory should have is_dir=True."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        info = get_file_info(str(subdir))

        assert info is not None
        assert info.is_dir
        assert info.name == "subdir"

    def test_nonexistent_file_returns_none(self, tmp_path):
        """Nonexistent file should return None."""
        result = get_file_info(str(tmp_path / "nonexistent.txt"))
        assert result is None
