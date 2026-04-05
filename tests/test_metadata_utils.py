"""
Tests for core/metadata_utils.py
"""

import pytest
import os
import time
from core.utils.formatting import format_size, unix_mode_to_str
from core.backends.gio.helpers import to_unix_timestamp
from core.backends.gio.metadata import get_file_info, resolve_mime_icon
from gi.repository import GLib, Gio

def test_format_size():
    assert format_size(0) == "0.0 B"
    assert format_size(500) == "500.0 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1536) == "1.5 KB"
    assert format_size(1024**2) == "1.0 MB"
    assert format_size(1024**3) == "1.0 GB"

def test_unix_mode_to_str():
    # 0o755 = rwxr-xr-x
    assert unix_mode_to_str(0o100755) == "-rwxr-xr-x"
    # 0o644 = rw-r--r--
    assert unix_mode_to_str(0o100644) == "-rw-r--r--"
    # 0o777 = rwxrwxrwx
    assert unix_mode_to_str(0o100777) == "-rwxrwxrwx"

def test_to_unix_timestamp():
    # Helper to create GLib.DateTime
    now = GLib.DateTime.new_now_local()
    ts = to_unix_timestamp(now)
    assert isinstance(ts, int)
    assert ts > 0
    assert to_unix_timestamp(None) == 0

def test_resolve_mime_icon(tmp_path):
    # Create a real file
    f = tmp_path / "test.txt"
    f.write_text("Hello")
    
    gfile = Gio.File.new_for_path(str(f))
    icon_name = resolve_mime_icon(gfile)
    
    # Should get something text-related or generic
    assert icon_name in ["text-plain", "text-x-generic", "application-text", "text-plain-symbolic", "text-x-generic-symbolic"]

def test_get_file_info(tmp_path):
    f = tmp_path / "info_test.txt"
    f.write_text("Data")
    
    # Verify basic info
    info = get_file_info(str(f))
    assert info is not None
    assert info.name == "info_test.txt"
    assert info.size == 4
    assert info.size_human == "4.0 B"
    assert not info.is_dir
    assert not info.is_symlink
    assert info.mime_type in ["text/plain", "application/x-zerosize"] # depends on content/system
    
    # Timestamps should be recent
    assert info.modified_ts > 0
    
    # Permissions should be sensible
    assert "r" in info.permissions_str
