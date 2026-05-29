import re
import sys
import time

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
        re.compile(r"^e: file://"),
        re.compile(r"error:", re.IGNORECASE),
        re.compile(r"Exception"),
        re.compile(r"^\* Try:"),
    ]

    BUILD_OK = re.compile(r"BUILD SUCCESSFUL")
    BUILD_FAIL = re.compile(r"BUILD FAILED")
    WARNING_PATTERN = re.compile(r"^w: ")
    BOOT_PATTERN = re.compile(r"^\[BOOT\]")

    def __init__(self, mode: str = "run"):
        self.mode = mode
        self.in_error = False
        self.dot_count = 0
        self.warnings: list[str] = []
        self.start_time = time.time()
        self.last_task = ""

    def filter_line(self, line: str) -> str | None:
        line = line.rstrip()
        if not line:
            return None

        if self.BUILD_OK.search(line):
            self._flush_dots()
            elapsed = self._elapsed()
            self.in_error = False
            return f"BUILD OK in {elapsed}"
            
        if self.BUILD_FAIL.search(line):
            self._flush_dots()
            elapsed = self._elapsed()
            self.in_error = False
            return f"BUILD FAILED in {elapsed}"

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

        if line.startswith("SLF4J") or line.startswith("[BOOT]"):
            self._flush_dots()
            return line

        if line.startswith("[PIPELINE]"):
            self._flush_dots()
            return line

        if not line.startswith("> ") and not line.startswith("* "):
            return line

        return None

    def _flush_dots(self):
        if self.dot_count > 0:
            sys.stderr.write("\n")
            sys.stderr.flush()
            self.dot_count = 0

    def _elapsed(self) -> str:
        secs = int(time.time() - self.start_time)
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m {secs % 60}s"

    def flush_warnings(self):
        if self.warnings:
            count = len(self.warnings)
            sys.stderr.write(f"\n[{count} warning{'s' if count != 1 else ''}]\n")
            sys.stderr.flush()

    def reset(self):
        self.in_error = False
        self.dot_count = 0
        self.warnings.clear()
        self.start_time = time.time()
