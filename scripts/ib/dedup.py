"""Universal streaming repeated-line compressor.

DedupEngine collapses CONSECUTIVE runs of the same logical line. It is
the general layer under the format-specific compressors in compressor.py:
any flood of identical events — GLib criticals, daemon chatter, progress
spam, formats we haven't seen yet — collapses to a single "[Nx] <line>"
summary wherever the flood occurred.

Design (Tier 1 volatile-token normalization):

- Comparison key: the line with volatile tokens stripped. Volatile
  tokens are the parts that make identical events look different —
  PIDs, timestamps, hex addresses, thread ids. The token list is
  configurable (constructor param) with a conservative default set.
- Policy:
  - run of 1 -> emit the line once, verbatim
  - run of 2 -> emit both, verbatim (a small repeat is information,
    don't hide it)
  - run >= threshold (default 3) -> emit "[Nx] <cleaned sample>"
- Flush boundaries: a different normalized key, a "> Task ..." line,
  and stream end. The summary appears where the flood occurred, not
  all at exit.
- Consecutive-only: a single pending run (the last line). Alternating
  A B A B is interleaved distinct output and is never collapsed —
  collapsing it would reorder or hide real output.
- Failures are sacred: lines matching a failure pattern (FAILED,
  error:, e: , FAILURE:, Exception/Error, stack-trace frames) pass
  through verbatim and never start or join a run.
"""

import re


class DedupEngine:
    # Volatile tokens, deliberately conservative. A bare number like
    # the "1" in "file/a/1.txt" is NOT volatile — it distinguishes
    # real content — so bare numbers are excluded; only structured
    # volatile shapes match. Each pattern may also consume an optional
    # trailing ": " so the cleaned line doesn't keep orphan colons
    # where a "(pid)" or timestamp was removed.
    DEFAULT_VOLATILE_PATTERNS = [
        r"\(\w[\w.]*:\d+\)(?:\s*:\s*)?",        # (process:1234), (com.imbric:12345)
        r"\(\d+\)",                              # (12345)
        r"\b\d{1,2}:\d{2}:\d{2}(?:\.\d+)?(?:\s*:\s*)?",  # 12:25:14.025
        r"\b0x[0-9a-fA-F]+\b",                   # 0x7ffd1234
        r"\b(?:pid|tid|port|process)\s*[:=]\s*\d+\b",  # pid=1234, tid:5678
        r"\bThread[-\s]\d+\b",                   # Thread-12, Thread 12
    ]

    # Failure patterns: never deduped. Mirrors test.py's _IMPORTANT set
    # (anchored Exception/Error — a passing test named testExceptionPath()
    # must not match) plus stack-trace frames.
    DEFAULT_FAILURE_PATTERNS = [
        r"FAILED",
        r"(?i)^\s*error:",
        r"^\s*e: ",
        r"^\s*FAILURE:",
        r"^\s*(?:Caused by:\s*)?[\w.$]*(?:Exception|Error)\b",
        r"^\s*at ",
    ]

    DEFAULT_TASK_BOUNDARY = r"^> Task "

    def __init__(self, volatile_patterns=None, failure_patterns=None,
                 threshold=3, task_boundary_pattern=None):
        patterns = (self.DEFAULT_VOLATILE_PATTERNS if volatile_patterns is None
                    else volatile_patterns)
        self._volatile = [re.compile(p) for p in patterns]
        failures = (self.DEFAULT_FAILURE_PATTERNS if failure_patterns is None
                    else failure_patterns)
        self._failures = [re.compile(p) for p in failures]
        self._task_boundary = re.compile(
            task_boundary_pattern or self.DEFAULT_TASK_BOUNDARY)
        if threshold < 1:
            raise ValueError("threshold must be >= 1")
        self._threshold = threshold
        self._pending_key = None
        # Samples for the pending run, capped at `threshold`
        # entries: below the threshold every line is emitted
        # verbatim (a 2x run of DISTINCT lines must keep both
        # actual lines, not the first one twice); at or above
        # it only the count and the cleaned first sample
        # matter. Caps memory on unbounded floods.
        self._pending_samples: list[str] = []
        self._pending_count = 0

    def feed(self, line: str) -> list[str]:
        """Feed one output line; return the lines to emit.

        [] while a run is pending, [line] for a single occurrence,
        [line, line] for a 2x run, or ["[Nx] <cleaned>"] once a run
        reaches the threshold.
        """
        raw = line.rstrip()
        if not raw:
            # Blank lines never start a run; they flush the pending
            # run (a paragraph break separates two floods).
            return self._flush_pending() + [""]
        if self._task_boundary.search(raw):
            # Structural boundary: flush, never accumulate.
            return self._flush_pending() + [raw]
        if self._is_failure(raw):
            # Failures are sacred: pass through, never deduped.
            return self._flush_pending() + [raw]
        key = self._normalize(raw)
        if self._pending_key is not None and key == self._pending_key:
            self._pending_count += 1
            if len(self._pending_samples) < self._threshold:
                self._pending_samples.append(raw)
            return []
        emitted = self._flush_pending()
        self._pending_key = key
        self._pending_samples = [raw]
        self._pending_count = 1
        return emitted

    def flush(self) -> list[str]:
        """Stream-end flush: emit any pending run."""
        return self._flush_pending()

    def _flush_pending(self) -> list[str]:
        count = self._pending_count
        if count == 0:
            return []
        samples = self._pending_samples
        self._pending_key = None
        self._pending_samples = []
        self._pending_count = 0
        if count >= self._threshold:
            return [f"[{count}x] {self._normalize(samples[0])}"]
        return samples

    def _is_failure(self, line: str) -> bool:
        return any(p.search(line) for p in self._failures)

    def _normalize(self, line: str) -> str:
        """Comparison key and cleaned sample: volatile tokens removed,
        whitespace normalized."""
        cleaned = line
        for pattern in self._volatile:
            cleaned = pattern.sub("", cleaned)
        return " ".join(cleaned.split())
