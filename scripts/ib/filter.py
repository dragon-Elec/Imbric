import re
import sys
import time
from .compressor import (
    _GLIB_PATTERN,
    compress_glib_warnings,
    compress_stacktrace,
    compress_warnings,
    format_pipeline_timer,
)

class OutputFilter:
    NOISE_PATTERNS = [
        re.compile(r"^Reusing configuration cache"),
        re.compile(r"^Configuration cache entry"),
        re.compile(r"^\d+ actionable task"),
        re.compile(r"^Downloading "),
        re.compile(r"^Welcome to Gradle"),
        re.compile(r"^Starting a Gradle Daemon"),
        re.compile(r"^Calculating task graph"),
        re.compile(r"^> Task .*(UP-TO-DATE|NO-SOURCE|SKIPPED)"),
    ]

    TASK_PATTERN = re.compile(r"^> Task :(\S+)")

    ERROR_PATTERNS = [
        re.compile(r"FAILED"),
        re.compile(r"^FAILURE:"),
        re.compile(r"^\* What went wrong:"),
        re.compile(r"^e: file://"),
        # Anchored: a mid-line "error:" (including inside `w:` warning
        # lines) must not flip into error mode.
        re.compile(r"^\s*error:", re.IGNORECASE),
        # Only exception-shaped lines at line start. The old bare
        # `Exception` token matched ANY line containing the word — a
        # passing test named testExceptionPath() flipped in_error and
        # flooded every following line until the next task line.
        re.compile(r"^\s*(?:Caused by:\s*)?[\w.$]*(?:Exception|Error)\b"),
        re.compile(r"^\* Try:"),
    ]

    BUILD_OK = re.compile(r"BUILD SUCCESSFUL")
    BUILD_FAIL = re.compile(r"BUILD FAILED")
    WARNING_PATTERN = re.compile(r"^w: ")
    BOOT_PATTERN = re.compile(r"^\[BOOT\]")

    def __init__(self, mode: str = "run", show_warnings: bool = False):
        self.mode = mode
        self.show_warnings = show_warnings
        self.in_error = False
        self.dot_count = 0
        self.warnings: list[str] = []
        self._glib_buffer: list[str] = []
        self._stack_buffer: list[str] = []
        self.start_time = time.time()
        self.last_task = ""

    def filter_line(self, line: str) -> str | None:
        line = line.rstrip()

        # GLib/GIO native warnings: buffer (dedup) instead of streaming
        # every critical — a single GIO scan can emit hundreds of
        # identical lines. Flushed by the next non-GLib line or by
        # flush_warnings().
        if _GLIB_PATTERN.search(line):
            self._flush_stack()
            self._glib_buffer.append(line)
            return None

        # Stack trace frames: buffer consecutive "at " lines so framework
        # frames can be collapsed into a skip count on flush. JVM frames
        # are indented, so match after lstrip (same as compress_stacktrace).
        if line.lstrip().startswith("at "):
            self._flush_glib()
            self._stack_buffer.append(line)
            return None

        self._flush_glib()
        self._flush_stack()

        if not line:
            return None

        if self.BUILD_OK.search(line):
            self._flush_dots()
            self.in_error = False
            return None
            
        if self.BUILD_FAIL.search(line):
            self._flush_dots()
            self.in_error = False
            return None

        if any(p.search(line) for p in self.ERROR_PATTERNS):
            self._flush_dots()
            self.in_error = True
            return line

        if self.in_error:
            if self.TASK_PATTERN.match(line):
                self.in_error = False
            else:
                return line

        if self.WARNING_PATTERN.search(line):
            self.warnings.append(line)
            return None

        if self.BOOT_PATTERN.search(line):
            self._flush_dots()
            return line

        if any(p.search(line) for p in self.NOISE_PATTERNS):
            return None

        task_match = self.TASK_PATTERN.match(line)
        if task_match:
            task_name = task_match.group(1)
            if task_name in ("run", "test", "compileKotlin", "compileTestKotlin", "build"):
                self._flush_dots()
                self.last_task = task_name
                return None
            self.dot_count += 1
            self.last_task = task_name
            sys.stderr.write(".")
            sys.stderr.flush()
            return None

        if line.startswith("SLF4J"):
            self._flush_dots()
            return line

        if line.startswith("[PIPELINE]"):
            self._flush_dots()
            return format_pipeline_timer(line)

        if not line.startswith("> ") and not line.startswith("* "):
            return line

        return None

    def _flush_dots(self):
        if self.dot_count > 0:
            sys.stderr.write("\n")
            sys.stderr.flush()
            self.dot_count = 0

    def _flush_glib(self):
        """Write the deduped GLib/GIO native warning summary."""
        if not self._glib_buffer:
            return
        self._flush_dots()
        sys.stderr.write(f"\n{compress_glib_warnings(self._glib_buffer)}\n")
        sys.stderr.flush()
        self._glib_buffer.clear()

    def _flush_stack(self):
        """Write the compressed stack trace (framework frames collapsed)."""
        if not self._stack_buffer:
            return
        self._flush_dots()
        sys.stderr.write(f"\n{compress_stacktrace(self._stack_buffer)}\n")
        sys.stderr.flush()
        self._stack_buffer.clear()

    def _elapsed(self) -> str:
        secs = int(time.time() - self.start_time)
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m {secs % 60}s"

    def flush_warnings(self):
        self._flush_glib()
        self._flush_stack()
        if self.warnings:
            count = len(self.warnings)
            if not self.show_warnings:
                sys.stderr.write(f"\n[{count} warning{'s' if count != 1 else ''} (use -w / --warnings to view)]\n")
            else:
                formatted = compress_warnings(self.warnings)
                sys.stderr.write(f"\n--- {count} Compiler Warning{'s' if count != 1 else ''} ---{formatted}\n")
            sys.stderr.flush()

    def reset(self):
        self.in_error = False
        self.dot_count = 0
        self.warnings.clear()
        self._glib_buffer.clear()
        self._stack_buffer.clear()
        self.start_time = time.time()
