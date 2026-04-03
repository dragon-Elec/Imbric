"""
Pytest configuration and shared fixtures for Imbric tests.

This module provides:
- Session-scoped fixtures for expensive objects (QApplication, registry, etc.)
- Function-scoped fixtures for test isolation
- Proper cleanup and teardown
- Test categorization markers

Usage:
    import pytest
    def test_something(file_ops_system):
        ...

Markers:
    @pytest.mark.unit - Fast, mocked tests
    @pytest.mark.integration - Real GIO, may use private APIs
    @pytest.mark.stress - Performance/load tests
    @pytest.mark.stress_mock - Fast mocked stress tests
    @pytest.mark.stress_real - Real filesystem stress tests
    @pytest.mark.slow - Tests that take > 5 seconds
"""

import os
import sys
import shutil
import tempfile
import time
from pathlib import Path
from typing import Generator, Optional

import pytest

# Ensure project root is in path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QApplication

# =============================================================================
# QApplication Fixture (Session Scoped)
# =============================================================================


@pytest.fixture(scope="session")
def qapp() -> QCoreApplication:
    """
    Session-scoped QCoreApplication instance.
    Only one instance is created per test session.
    """
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    yield app
    # Don't quit here - pytest handles cleanup


@pytest.fixture(scope="session")
def qapp_widgets() -> QApplication:
    """
    Session-scoped QApplication with widgets support.
    Use this when tests need actual widgets.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


# =============================================================================
# Core System Fixtures (Session Scoped - Shared Registry)
# =============================================================================


@pytest.fixture(scope="session")
def signals():
    """Session-scoped FileOperationSignals."""
    from core.models.file_job import FileOperationSignals

    return FileOperationSignals()


@pytest.fixture(scope="session")
def backend_registry(signals):
    """
    Session-scoped BackendRegistry with default GIO backend.
    Shared across all tests to avoid creating multiple backends.
    """
    from core.registry import BackendRegistry
    from core.backends.gio.backend import GIOBackend

    registry = BackendRegistry()
    registry.set_default_io(GIOBackend())
    return registry


# =============================================================================
# File Operations Fixtures (Function Scoped - Clean per test)
# =============================================================================


@pytest.fixture
def file_ops(backend_registry) -> "FileOperations":
    """
    Function-scoped FileOperations instance.
    Creates fresh instance with registry for each test.
    """
    from core.managers import FileOperations

    fo = FileOperations()
    fo.setRegistry(backend_registry)
    yield fo
    fo.shutdown()


@pytest.fixture
def transaction_manager(file_ops) -> "TransactionManager":
    """
    Function-scoped TransactionManager connected to file_ops.
    """
    from core.managers import TransactionManager

    tm = TransactionManager()
    tm.setFileOperations(file_ops)
    file_ops.setTransactionManager(tm)
    yield tm


@pytest.fixture
def undo_manager(transaction_manager, file_ops) -> "UndoManager":
    """
    Function-scoped UndoManager connected to transaction_manager and file_ops.
    """
    from core.managers import UndoManager

    um = UndoManager(transaction_manager)
    um.setFileOperations(file_ops)
    yield um


@pytest.fixture
def file_ops_system(backend_registry, file_ops, transaction_manager):
    """
    Complete file operations system with all components connected.
    Convenience fixture for tests that need the full stack.

    Returns:
        dict with keys: registry, file_ops, tm
    """
    return {
        "registry": backend_registry,
        "file_ops": file_ops,
        "tm": transaction_manager,
    }


# =============================================================================
# Temporary Directory Fixtures
# =============================================================================


@pytest.fixture
def temp_dir(tmp_path) -> Path:
    """
    Provides a temporary directory for test files.
    Uses pytest's tmp_path fixture which auto-cleans.
    """
    return tmp_path


@pytest.fixture
def test_home_dir() -> Path:
    """
    Provides path to ~/Desktop/imbric_tests for tests requiring real filesystem.
    Creates directory if it doesn't exist.
    Some operations (trash, xattrs) require real filesystem, not /tmp.
    """
    base = Path.home() / "Desktop" / "imbric_tests"
    base.mkdir(parents=True, exist_ok=True)
    yield base
    # Cleanup after test
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def test_files(temp_dir) -> dict:
    """
    Creates standard test files in temp directory.

    Creates:
        - file1.txt, file2.txt, file3.txt (small text files)
        - large_file.bin (100KB random data)
        - subdir/ with nested.txt

    Returns dict with path strings for easy access.
    """
    files = {}

    # Small text files
    (temp_dir / "file1.txt").write_text("Hello World")
    (temp_dir / "file2.txt").write_text("Test File 2")
    (temp_dir / "file3.txt").write_text("Test File 3")
    files["file1"] = str(temp_dir / "file1.txt")
    files["file2"] = str(temp_dir / "file2.txt")
    files["file3"] = str(temp_dir / "file3.txt")

    # Large file for progress testing
    large = temp_dir / "large_file.bin"
    with open(large, "wb") as f:
        f.write(os.urandom(1024 * 100))  # 100KB
    files["large"] = str(large)

    # Subdirectory with nested file
    subdir = temp_dir / "subdir"
    subdir.mkdir()
    (subdir / "nested.txt").write_text("Nested file")
    files["subdir"] = str(subdir)
    files["nested"] = str(subdir / "nested.txt")

    return files


# =============================================================================
# Event Processing Helpers
# =============================================================================


@pytest.fixture
def process_events(qapp):
    """
    Returns a function that processes Qt events.

    Usage:
        def test_something(process_events):
            process_events()
    """

    def _process():
        qapp.processEvents()

    return _process


@pytest.fixture
def event_loop(qapp):
    """
    Provides an event loop fixture for async operations.
    """

    class EventLoop:
        def __init__(self, app):
            self.app = app
            self.timeout_ms = 5000
            self.sleep_step = 0.01

        def wait_until(self, condition_fn, timeout_ms: int = 5000):
            """Wait until condition returns True or timeout."""
            start = time.time()
            while not condition_fn():
                self.app.processEvents()
                if (time.time() - start) * 1000 > timeout_ms:
                    return False
                time.sleep(self.sleep_step)
            return True

        def wait_for_signal(self, signal, timeout_ms: int = 5000):
            """Wait for a signal to be emitted."""
            received = []

            def callback(*args):
                received.append(args)

            signal.connect(callback)
            try:
                return self.wait_until(lambda: len(received) > 0, timeout_ms)
            finally:
                signal.disconnect(callback)

        def wait_for_count(self, counter: list, expected: int, timeout_ms: int = 5000):
            """Wait for counter list to reach expected length."""
            return self.wait_until(lambda: len(counter) >= expected, timeout_ms)

    return EventLoop(qapp)


# =============================================================================
# Test Markers
# =============================================================================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Fast unit tests with mocked dependencies")
    config.addinivalue_line("markers", "integration: Integration tests using real GIO")
    config.addinivalue_line("markers", "stress: Stress/performance tests")
    config.addinivalue_line("markers", "stress_mock: Fast mocked stress tests")
    config.addinivalue_line("markers", "stress_real: Real filesystem stress tests")
    config.addinivalue_line("markers", "slow: Tests that take more than 5 seconds")
    config.addinivalue_line(
        "markers",
        "private_api: Tests that access private APIs (requires justification)",
    )


def pytest_collection_modifyitems(config, items):
    """Auto-mark tests based on directory location."""
    for item in items:
        # Auto-mark based on test location
        if "unit" in item.fspath.strpath:
            item.add_marker(pytest.mark.unit)
        elif "integration" in item.fspath.strpath:
            item.add_marker(pytest.mark.integration)
        elif "stress/mock" in item.fspath.strpath:
            item.add_marker(pytest.mark.stress)
            item.add_marker(pytest.mark.stress_mock)
        elif "stress/real" in item.fspath.strpath:
            item.add_marker(pytest.mark.stress)
            item.add_marker(pytest.mark.stress_real)
            item.add_marker(pytest.mark.slow)


# =============================================================================
# Cleanup Hook
# =============================================================================


@pytest.fixture(autouse=True)
def cleanup_temp_artifacts():
    """Auto-cleanup any temp artifacts left in tests/temp_artifacts/"""
    yield
    artifacts_dir = Path(__file__).parent / "temp_artifacts"
    if artifacts_dir.exists():
        for item in artifacts_dir.iterdir():
            if item.name.startswith("imbric_"):
                shutil.rmtree(item, ignore_errors=True)
