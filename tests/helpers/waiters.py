"""
Event waiting utilities for async Qt operations.

These helpers replace busy-wait loops and hardcoded sleeps with
proper signal-based synchronization.
"""

import time
from typing import Callable, Optional, Any
from contextlib import contextmanager

from PySide6.QtCore import QTimer


class WaitTimeout(Exception):
    """Raised when wait_for exceeds timeout."""

    pass


def wait_for(
    condition: Callable[[], bool],
    timeout_ms: int = 5000,
    poll_interval_ms: int = 10,
    message: Optional[str] = None,
) -> bool:
    """
    Wait for a condition to become True.

    Args:
        condition: Callable that returns bool
        timeout_ms: Maximum time to wait in milliseconds
        poll_interval_ms: How often to check condition
        message: Optional message for timeout error

    Returns:
        True if condition met, False if timeout

    Raises:
        WaitTimeout: If raise_on_timeout=True and condition not met
    """
    start = time.time()
    timeout_sec = timeout_ms / 1000
    poll_sec = poll_interval_ms / 1000

    while not condition():
        if (time.time() - start) > timeout_sec:
            return False
        time.sleep(poll_sec)

    return True


def wait_for_with_events(
    qapp,
    condition: Callable[[], bool],
    timeout_ms: int = 5000,
    poll_interval_ms: int = 10,
) -> bool:
    """
    Wait for condition while processing Qt events.

    Use this when waiting for signals to be emitted.
    """
    start = time.time()
    timeout_sec = timeout_ms / 1000
    poll_sec = poll_interval_ms / 1000

    while not condition():
        qapp.processEvents()
        if (time.time() - start) > timeout_sec:
            return False
        time.sleep(poll_sec)

    return True


class SignalWatcher:
    """
    Watch for signal emissions with optional assertions.

    Usage:
        watcher = SignalWatcher(qapp)
        watcher.watch(signal, lambda args: assert condition)
        watcher.wait(timeout_ms=5000)
        watcher.assert_all_passed()
    """

    def __init__(self, qapp):
        self.qapp = qapp
        self._signals: list = []
        self._callbacks: dict = {}
        self._received: dict = {}
        self._errors: list = []

    def watch(
        self, signal, callback: Optional[Callable] = None, key: Optional[str] = None
    ):
        """
        Watch a signal.

        Args:
            signal: Qt signal to watch
            callback: Optional callback(signal, *args) to run when signal fires
            key: Optional key to identify this signal (defaults to signal name)
        """
        if key is None:
            key = str(signal)

        self._signals.append(signal)
        self._callbacks[key] = callback
        self._received[key] = []

        def proxy(*args):
            self._received[key].append(args)
            if callback:
                try:
                    callback(*args)
                except AssertionError as e:
                    self._errors.append((key, e))

        signal.connect(proxy)
        return proxy

    def wait(self, timeout_ms: int = 5000, require_all: bool = False) -> bool:
        """
        Wait for signals to fire.

        Args:
            timeout_ms: Maximum wait time
            require_all: If True, wait for all watched signals. If False, wait for any.

        Returns:
            True if condition met, False if timeout
        """
        if require_all:
            condition = lambda: all(len(v) > 0 for v in self._received.values())
        else:
            condition = lambda: any(len(v) > 0 for v in self._received.values())

        return wait_for_with_events(self.qapp, condition, timeout_ms)

    def assert_received(self, key: str, min_count: int = 1):
        """Assert that signal was received at least min_count times."""
        received = self._received.get(key, [])
        if len(received) < min_count:
            raise AssertionError(
                f"Signal '{key}' received {len(received)} times, expected {min_count}"
            )

    def assert_any_received(self):
        """Assert that at least one signal was received."""
        total = sum(len(v) for v in self._received.values())
        if total == 0:
            raise AssertionError("No signals were received")

    def get_last(self, key: str) -> Optional[Any]:
        """Get last arguments received for signal."""
        received = self._received.get(key, [])
        return received[-1] if received else None

    def get_all(self, key: str) -> list:
        """Get all arguments received for signal."""
        return self._received.get(key, [])

    def assert_all_passed(self):
        """Assert that no callback errors occurred."""
        if self._errors:
            errors_str = "\n".join(f"  {k}: {e}" for k, e in self._errors)
            raise AssertionError(f"Callback errors:\n{errors_str}")


class Counter:
    """Thread-safe counter for tracking event counts."""

    def __init__(self, initial: int = 0):
        self._count = initial
        self._lock = __import__("threading").Lock()

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def increment(self, by: int = 1):
        with self._lock:
            self._count += by

    def reset(self):
        with self._lock:
            self._count = 0

    def wait_for(self, target: int, timeout_ms: int = 5000) -> bool:
        """Wait until counter reaches target."""
        return wait_for(lambda: self.count >= target, timeout_ms)


@contextmanager
def timeout_context(qapp, timeout_ms: int = 5000):
    """
    Context manager that fails if block takes too long.

    Usage:
        with timeout_context(qapp, 2000):
            do_something()
    """
    result = {"timed_out": False}

    def on_timeout():
        result["timed_out"] = True

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(on_timeout)
    timer.start(timeout_ms)

    try:
        yield result
    finally:
        if timer.isActive():
            timer.stop()
        qapp.processEvents()

    if result["timed_out"]:
        raise WaitTimeout(f"Operation exceeded {timeout_ms}ms timeout")


def retry_with_backoff(
    fn: Callable,
    max_attempts: int = 3,
    base_delay_ms: int = 100,
    max_delay_ms: int = 2000,
) -> Any:
    """
    Retry a function with exponential backoff.

    Args:
        fn: Function to retry (should return truthy on success)
        max_attempts: Maximum number of attempts
        base_delay_ms: Initial delay between retries
        max_delay_ms: Maximum delay cap

    Returns:
        Result of successful fn call

    Raises:
        Last exception if all attempts fail
    """
    delay = base_delay_ms / 1000
    last_error = None

    for attempt in range(max_attempts):
        try:
            result = fn()
            if result:
                return result
        except Exception as e:
            last_error = e

        if attempt < max_attempts - 1:
            time.sleep(delay)
            delay = min(delay * 2, max_delay_ms / 1000)

    if last_error:
        raise last_error
    return None
