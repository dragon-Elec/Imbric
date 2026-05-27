import os
import signal
import subprocess
from dataclasses import dataclass
from typing import ClassVar

GRADLEW_PATTERN = "gradlew"
GRADLE_JAR_PATTERN = "gradle-wrapper.jar"
IMBRIC_APP_PATTERN = "com.imbric"
KOTLIN_DAEMON_PATTERN = "KotlinCompileDaemon"
GRADLE_DAEMON_PATTERN = "GradleDaemon"
HOTRELOAD_DEVTOOLS_PATTERN = "compose.devtools"

@dataclass
class ProcessInfo:
    pid: int
    cmd: str
    mem: str

class ProcessManager:
    """Find and kill Gradle/Kotlin/Imbric processes."""

    @staticmethod
    def find_processes(pattern: str) -> list[ProcessInfo]:
        try:
            result = subprocess.run(
                ["pgrep", "-a", "-f", pattern],
                capture_output=True, text=True, timeout=5
            )
            procs = []
            for line in result.stdout.strip().splitlines():
                if not line:
                    continue
                parts = line.split(None, 1)
                if len(parts) >= 2:
                    pid = int(parts[0])
                    cmd = parts[1]
                    if "pgrep" in cmd:
                        continue
                    procs.append(ProcessInfo(pid=pid, cmd=cmd, mem=""))
            return procs
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            return []

    @staticmethod
    def get_memory(pid: int) -> str:
        try:
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        kb = int(line.split()[1])
                        if kb > 1024 * 1024:
                            return f"{kb / 1024 / 1024:.1f}GB"
                        elif kb > 1024:
                            return f"{kb / 1024:.0f}MB"
                        return f"{kb}KB"
        except (FileNotFoundError, ValueError, IndexError):
            pass
        return "?"

    @staticmethod
    def is_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    @staticmethod
    def kill_pid(pid: int, sig: int = signal.SIGTERM) -> bool:
        try:
            os.kill(pid, sig)
            return True
        except (OSError, ProcessLookupError):
            return False

    @classmethod
    def kill_all(cls, force: bool = True, include_daemons: bool = True) -> list[str]:
        import time
        sig = signal.SIGKILL if force else signal.SIGTERM
        killed = []
        patterns = [GRADLEW_PATTERN, GRADLE_JAR_PATTERN, IMBRIC_APP_PATTERN,
                    HOTRELOAD_DEVTOOLS_PATTERN]
        if include_daemons:
            patterns.extend([KOTLIN_DAEMON_PATTERN, GRADLE_DAEMON_PATTERN])

        for pattern in patterns:
            for proc in cls.find_processes(pattern):
                if proc.pid == os.getpid():
                    continue
                if cls.kill_pid(proc.pid, sig):
                    killed.append(str(proc.pid))

        if killed:
            time.sleep(1)
            if not force:
                survivors = []
                for pattern in patterns:
                    for proc in cls.find_processes(pattern):
                        if proc.pid == os.getpid():
                            continue
                        if cls.kill_pid(proc.pid, signal.SIGKILL):
                            survivors.append(str(proc.pid))
                if survivors:
                    killed.extend(survivors)
                    time.sleep(1)

        return killed

    @classmethod
    def get_status(cls) -> dict[str, list[ProcessInfo]]:
        status = {
            "gradle_daemons": [],
            "kotlin_daemons": [],
            "app_processes": [],
            "gradlew_processes": [],
            "hotreload_devtools": [],
        }

        for p in cls.find_processes(GRADLE_DAEMON_PATTERN):
            p.mem = cls.get_memory(p.pid)
            status["gradle_daemons"].append(p)
            
        for p in cls.find_processes(KOTLIN_DAEMON_PATTERN):
            p.mem = cls.get_memory(p.pid)
            status["kotlin_daemons"].append(p)
            
        for p in cls.find_processes(IMBRIC_APP_PATTERN):
            p.mem = cls.get_memory(p.pid)
            status["app_processes"].append(p)
            
        for p in cls.find_processes(GRADLEW_PATTERN):
            p.mem = cls.get_memory(p.pid)
            status["gradlew_processes"].append(p)

        for p in cls.find_processes(HOTRELOAD_DEVTOOLS_PATTERN):
            p.mem = cls.get_memory(p.pid)
            status["hotreload_devtools"].append(p)

        return status
