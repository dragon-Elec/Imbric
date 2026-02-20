"""
Diagnostics Module for Imbric

Unified diagnostics tool — replaces both the old diagnostics.py and
monitor_resources.py with a single module that handles:

  1. Internal Profiling (F12):  gc, tracemalloc, object counts
  2. External Monitoring (CLI): CPU, RSS, USS, Disk I/O via psutil + PID
  3. System Profiling:          GPU, FDs, /proc/self/status

Renders a clean, resize-aware TUI dashboard.
When run via `watch`, handles clearing/resizing automatically.
"""

import gc
import sys
import os
import time
import tracemalloc
import ctypes
import subprocess
import shutil
import argparse
from collections import Counter
from datetime import datetime


# ── ANSI Helpers ──────────────────────────────────────────────────────────────

_IS_TTY = None  # Lazy-detected


def _is_tty() -> bool:
    """Check if stdout is a real terminal (not a pipe/file)."""
    global _IS_TTY
    if _IS_TTY is None:
        _IS_TTY = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    return _IS_TTY


def _ansi(code: str) -> str:
    """Return ANSI code if TTY, empty string otherwise."""
    return code if _is_tty() else ""


# Codes
RESET = lambda: _ansi("\033[0m")
BOLD = lambda: _ansi("\033[1m")
DIM = lambda: _ansi("\033[2m")
RED = lambda: _ansi("\033[1;31m")
GREEN = lambda: _ansi("\033[1;32m")
YELLOW = lambda: _ansi("\033[1;33m")
CYAN = lambda: _ansi("\033[1;36m")
CLEAR_SCREEN = lambda: _ansi("\033[H\033[J")


def _get_term_size() -> tuple[int, int]:
    """Return (columns, rows). Falls back to 80x24."""
    try:
        size = shutil.get_terminal_size(fallback=(80, 24))
        return size.columns, size.lines
    except Exception:
        return 80, 24


def _visible_len(s: str) -> int:
    """Length of string excluding ANSI escape sequences."""
    import re
    return len(re.sub(r'\033\[[0-9;]*m', '', s))


def _side_by_side(left: str, right: str, mid: int, total: int) -> str:
    """Join two strings into a side-by-side row with a │ divider."""
    vl = _visible_len(left)
    pad = max(0, mid - 1 - vl)
    return left + " " * pad + "│" + right


# ── SystemProfiler ────────────────────────────────────────────────────────────

class SystemProfiler:
    """System-level diagnostics via /proc and optional shell tools."""

    @staticmethod
    def get_fd_count(pid: int | None = None) -> int:
        """Count open file descriptors via /proc (fast, no subprocess)."""
        target_pid = pid or os.getpid()
        try:
            return len(os.listdir(f"/proc/{target_pid}/fd"))
        except OSError:
            return -1

    @staticmethod
    def get_fd_limit() -> int:
        """Get the soft FD limit for this process."""
        try:
            import resource
            soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
            return soft
        except Exception:
            return -1

    @staticmethod
    def get_fd_breakdown(pid: int | None = None) -> dict[str, int]:
        """Categorise open FDs by type (socket, pipe, file, etc.)."""
        target_pid = pid or os.getpid()
        breakdown: dict[str, int] = {}
        fd_dir = f"/proc/{target_pid}/fd"
        try:
            for fd in os.listdir(fd_dir):
                try:
                    link = os.readlink(os.path.join(fd_dir, fd))
                    if link.startswith("socket:"):
                        key = "socket"
                    elif link.startswith("pipe:"):
                        key = "pipe"
                    elif link.startswith("anon_inode:"):
                        key = "anon_inode"
                    elif link.startswith("/dev/"):
                        key = "device"
                    else:
                        key = "file"
                    breakdown[key] = breakdown.get(key, 0) + 1
                except OSError:
                    breakdown["unknown"] = breakdown.get("unknown", 0) + 1
        except OSError:
            pass
        return breakdown

    @staticmethod
    def get_gpu_info() -> str:
        """Try nvidia-smi, then /sys for Intel/AMD. Returns short string."""
        # 1. NVIDIA
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
                 "--format=csv,noheader,nounits"],
                timeout=2, stderr=subprocess.DEVNULL
            ).decode().strip()
            if out:
                parts = out.split(", ")
                if len(parts) >= 3:
                    load = f" ({parts[2]}% Load)" if parts[2].isdigit() else ""
                    return f"{parts[0]} / {parts[1]} MiB{load}"
                elif len(parts) == 2:
                    return f"{parts[0]} / {parts[1]} MiB"
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass

        # 2. Intel / AMD via sysfs
        drm_path = "/sys/class/drm"
        try:
            for card in sorted(os.listdir(drm_path)):
                vram_used = os.path.join(drm_path, card, "device", "mem_info_vram_used")
                vram_total = os.path.join(drm_path, card, "device", "mem_info_vram_total")
                if os.path.exists(vram_used) and os.path.exists(vram_total):
                    with open(vram_used) as f:
                        used = int(f.read().strip()) // (1024 * 1024)
                    with open(vram_total) as f:
                        total = int(f.read().strip()) // (1024 * 1024)
                    return f"{used} / {total} MiB ({card})"
        except Exception:
            pass

        return "N/A"

    @staticmethod
    def get_gpu_renderer() -> str:
        """Get OpenGL renderer string via glxinfo (detects HW acceleration)."""
        try:
            out = subprocess.check_output(
                ["glxinfo", "-B"], 
                timeout=2, stderr=subprocess.DEVNULL
            ).decode()
            for line in out.splitlines():
                if "OpenGL renderer string:" in line:
                    return line.split(":", 1)[1].strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        return "Unknown"

    @staticmethod
    def get_process_state(pid: int | None = None) -> dict[str, str]:
        """Parse /proc/<pid>/status for key metrics."""
        target_pid = pid or "self"
        info: dict[str, str] = {}
        keys_of_interest = {
            "Threads", "VmPeak", "VmRSS", "VmSwap",
            "voluntary_ctxt_switches", "nonvoluntary_ctxt_switches",
        }
        try:
            with open(f"/proc/{target_pid}/status") as f:
                for line in f:
                    parts = line.split(":", 1)
                    if len(parts) == 2 and parts[0].strip() in keys_of_interest:
                        info[parts[0].strip()] = parts[1].strip()
        except OSError:
            pass
        return info


# ── ProcessMonitor (External PID Monitoring) ─────────────────────────────────

class ProcessMonitor:
    """
    External process monitoring via psutil.
    Produces a single snapshot of metrics for a given PID.
    Designed to be called repeatedly by `watch`.
    """

    @staticmethod
    def snapshot(pid: int) -> dict | None:
        """
        Collect one snapshot of metrics for the given PID.
        Returns None if the process is gone.
        """
        try:
            import psutil
        except ImportError:
            return {"error": "psutil not installed"}

        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return None

        total_cpu = 0.0
        total_rss = 0.0
        total_vms = 0.0
        total_uss = 0.0
        total_threads = 0
        total_fds = 0
        total_read = 0
        total_write = 0
        cmd = ""

        try:
            cmd = " ".join(proc.cmdline())
        except Exception:
            cmd = f"PID {pid}"

        procs = [proc]
        try:
            procs.extend(proc.children(recursive=True))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # Pass 1: Prime cpu_percent (first call always returns 0)
        for p in procs:
            try:
                p.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Brief sleep so CPU delta accumulates
        time.sleep(0.15)

        # Pass 2: Collect real metrics
        for p in procs:
            try:
                with p.oneshot():
                    # CPU: uses interval=0.1 for a quick sample
                    total_cpu += p.cpu_percent(interval=None)
                    mem = p.memory_info()
                    total_rss += mem.rss
                    total_vms += mem.vms

                    try:
                        mem_full = p.memory_full_info()
                        total_uss += mem_full.uss
                    except (AttributeError, psutil.AccessDenied):
                        total_uss += mem.rss

                    total_threads += p.num_threads()
                    try:
                        total_fds += p.num_fds()
                    except Exception:
                        pass

                    try:
                        io = p.io_counters()
                        total_read += io.read_bytes
                        total_write += io.write_bytes
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return {
            "pid": pid,
            "cmd": cmd,
            "cpu": total_cpu,
            "rss": total_rss / (1024 * 1024),
            "uss": total_uss / (1024 * 1024),
            "vms": total_vms / (1024 * 1024),
            "threads": total_threads,
            "fds": total_fds,
            "read_bytes": total_read,
            "write_bytes": total_write,
        }

    @staticmethod
    def print_snapshot(pid: int):
        """Print a single-shot monitor dashboard for the given PID."""
        metrics = ProcessMonitor.snapshot(pid)

        if metrics is None:
            print(f"Process {pid} not found.")
            sys.exit(1)

        if "error" in metrics:
            print(f"Error: {metrics['error']}")
            sys.exit(1)

        cols, rows = _get_term_size()
        lines: list[str] = []
        now = datetime.now().strftime("%H:%M:%S")
        bar = "═" * cols

        # System metrics (from /proc, works cross-process)
        fd_count = SystemProfiler.get_fd_count(pid)
        fd_breakdown = SystemProfiler.get_fd_breakdown(pid)
        gpu_info = SystemProfiler.get_gpu_info()
        gpu_rend = SystemProfiler.get_gpu_renderer()
        proc_state = SystemProfiler.get_process_state(pid)

        lines.append(f"{CYAN()}{bar}{RESET()}")
        lines.append(f" {BOLD()}IMBRIC MONITOR{RESET()}"
                      f"{' ' * max(1, cols - 26)}{DIM()}{now}{RESET()}")
        lines.append(f"{CYAN()}{bar}{RESET()}")

        # Command line (truncated)
        cmd_display = metrics["cmd"][:cols - 10] if len(metrics["cmd"]) > cols - 10 else metrics["cmd"]
        lines.append(f" PID: {BOLD()}{pid}{RESET()} │ {DIM()}{cmd_display}{RESET()}")
        lines.append("─" * cols)

        # ── Side-by-side or stacked ───────────────────────────────────
        use_side_by_side = cols >= 60
        mid = cols // 2 if use_side_by_side else cols

        cpu_color = RED() if metrics["cpu"] > 50 else GREEN()

        if use_side_by_side:
            divider = "─" * (mid - 1) + "┼" + "─" * (cols - mid)
            left_header = f" {BOLD()}PROCESS{RESET()}"
            right_header = f" {BOLD()}SYSTEM{RESET()}"
            lines.append(_side_by_side(left_header, right_header, mid, cols))
            lines.append(divider)

            lines.append(_side_by_side(
                f"  CPU:  {cpu_color}{metrics['cpu']:>7.1f}%{RESET()}",
                f"  GPU:  {gpu_rend[:20]}",
                mid, cols))
            lines.append(_side_by_side(
                f"  RSS:  {YELLOW()}{metrics['rss']:>8.2f} MB{RESET()}",
                f"  VRAM: {gpu_info}",
                mid, cols))
            lines.append(_side_by_side(
                f"  USS:  {GREEN()}{metrics['uss']:>8.2f} MB{RESET()}",
                f"  FDs:  {GREEN()}{fd_count:>6}{RESET()}",
                mid, cols))
            lines.append(_side_by_side(
                f"  VMS:  {metrics['vms']:>8.2f} MB",
                f"  Swap: {proc_state.get('VmSwap', 'N/A')}",
                mid, cols))
        else:
            lines.append(f" {BOLD()}PROCESS{RESET()}")
            lines.append(f"  CPU:  {cpu_color}{metrics['cpu']:>7.1f}%{RESET()}")
            lines.append(f"  RSS:  {YELLOW()}{metrics['rss']:>8.2f} MB{RESET()}")
            lines.append(f"  USS:  {GREEN()}{metrics['uss']:>8.2f} MB{RESET()}")
            lines.append(f"  VMS:  {metrics['vms']:>8.2f} MB")
            lines.append("─" * cols)
            lines.append(f" {BOLD()}SYSTEM{RESET()}")
            lines.append(f"  GPU:  {gpu_rend}")
            lines.append(f"  VRAM: {gpu_info}")
            lines.append(f"  FDs:  {fd_count}")

        # ── Disk I/O ──────────────────────────────────────────────────
        lines.append("─" * cols)
        read_mb = metrics["read_bytes"] / (1024 * 1024)
        write_mb = metrics["write_bytes"] / (1024 * 1024)
        lines.append(f" {BOLD()}DISK I/O (cumulative){RESET()}")
        lines.append(f"  Read:   {read_mb:>10.2f} MB")
        lines.append(f"  Write:  {write_mb:>10.2f} MB")

        # ── FD Breakdown ──────────────────────────────────────────────
        if fd_breakdown:
            lines.append("─" * cols)
            lines.append(f" {BOLD()}FD BREAKDOWN{RESET()}")
            for kind, count in sorted(fd_breakdown.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {kind:<12}: {count}")

        lines.append(f"{CYAN()}{bar}{RESET()}")

        output = "\n".join(lines) + "\n"
        try:
            sys.stdout.write(output)
            sys.stdout.flush()
        except Exception:
            print(output)


# ── MemoryProfiler (Internal — F12) ──────────────────────────────────────────

class MemoryProfiler:
    _snapshot = None

    @staticmethod
    def start():
        """Start tracking memory allocations."""
        if not tracemalloc.is_tracing():
            tracemalloc.start()
            print("[Diagnostics] Tracemalloc started.")

    @staticmethod
    def take_snapshot():
        """Take a snapshot for comparison."""
        MemoryProfiler._snapshot = tracemalloc.take_snapshot()
        print("[Diagnostics] Snapshot taken.")

    # ── Report Rendering ──────────────────────────────────────────────────

    @staticmethod
    def print_report():
        """
        Force garbage collection, trim memory, and render a
        resize-aware TUI dashboard.
        """
        cols, rows = _get_term_size()
        lines: list[str] = []

        # ── Collect Data ──────────────────────────────────────────────

        # 1. GC
        unreachable = gc.collect()

        # 2. malloc_trim
        trim_ok = False
        try:
            libc = ctypes.CDLL("libc.so.6")
            libc.malloc_trim(0)
            trim_ok = True
        except Exception:
            pass

        # 3. Process Memory (psutil)
        rss_mb = vms_mb = -1.0
        try:
            import psutil
            proc = psutil.Process(os.getpid())
            mem = proc.memory_info()
            rss_mb = mem.rss / 1024 / 1024
            vms_mb = mem.vms / 1024 / 1024
        except Exception:
            pass

        # 4. System Metrics
        fd_count = SystemProfiler.get_fd_count()
        fd_limit = SystemProfiler.get_fd_limit()
        fd_breakdown = SystemProfiler.get_fd_breakdown()
        gpu_info = SystemProfiler.get_gpu_info()
        gpu_rend = SystemProfiler.get_gpu_renderer()
        proc_state = SystemProfiler.get_process_state()

        # 5. Object Counts
        target_classes = [
            'BrowserTab', 'FileScanner', 'ThumbnailProvider',
            'ThumbnailResponse', 'JustifiedView', 'RowBuilder',
            'TransactionManager', 'Transaction', 'UndoManager',
            'FileMonitor', 'FileWorker', 'ThumbnailCache',
            'TabManager', 'TabModel', 'ActionManager',
            'FileManager', 'NavigationManager', 'ViewManager',
            'AppBridge', 'FileSystemModel', 'SidebarModel',
            'QQuickView', 'QImage', 'QNetworkReply'
        ]
        counts = Counter()
        for obj in gc.get_objects():
            try:
                cls_name = type(obj).__name__
                if cls_name in target_classes:
                    counts[cls_name] += 1
                elif 'Imbric' in str(type(obj)):
                    counts[cls_name] += 1
            except Exception:
                pass
        sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)

        # 6. Tracemalloc
        top_allocs: list[str] = []
        diff_allocs: list[str] = []
        if tracemalloc.is_tracing():
            snapshot = tracemalloc.take_snapshot()
            for stat in snapshot.statistics('lineno')[:5]:
                fname = str(stat.traceback)
                top_allocs.append(f"  {stat.size / 1024:.1f} KB  {fname}")
            if MemoryProfiler._snapshot:
                for stat in snapshot.compare_to(MemoryProfiler._snapshot, 'lineno')[:5]:
                    sign = "+" if stat.size_diff > 0 else ""
                    diff_allocs.append(f"  {sign}{stat.size_diff / 1024:.1f} KB  {stat.traceback}")
            MemoryProfiler._snapshot = snapshot

        # ── Render Dashboard ──────────────────────────────────────────

        now = datetime.now().strftime("%H:%M:%S")
        bar = "═" * cols

        # Clear screen (TTY only)
        if _is_tty():
            lines.append(CLEAR_SCREEN())

        lines.append(f"{CYAN()}{bar}{RESET()}")
        lines.append(f" {BOLD()}IMBRIC DIAGNOSTICS{RESET()}"
                      f"{' ' * max(1, cols - 30)}{DIM()}{now}{RESET()}")
        lines.append(f"{CYAN()}{bar}{RESET()}")

        # ── Side-by-side or stacked layout ────────────────────────────
        use_side_by_side = cols >= 60
        mid = cols // 2 if use_side_by_side else cols

        if use_side_by_side:
            divider = "─" * (mid - 1) + "┼" + "─" * (cols - mid)
            left_header = f" {BOLD()}MEMORY{RESET()}"
            right_header = f" {BOLD()}SYSTEM{RESET()}"
            lines.append(_side_by_side(left_header, right_header, mid, cols))
            lines.append(divider)
            # Row: RSS / FDs
            rss_str = f"  RSS:  {YELLOW()}{rss_mb:>8.2f} MB{RESET()}" if rss_mb >= 0 else "  RSS:       N/A"
            fd_color = RED() if (fd_limit > 0 and fd_count > fd_limit * 0.8) else GREEN()
            fd_str = f"  FDs:  {fd_color}{fd_count:>6}{RESET()} / {fd_limit}" if fd_limit > 0 else f"  FDs:  {fd_count}"
            lines.append(_side_by_side(rss_str, fd_str, mid, cols))

            # Row: VMS / GPU Renderer
            vms_str = f"  VMS:  {vms_mb:>8.2f} MB" if vms_mb >= 0 else "  VMS:       N/A"
            rend_str = f"  GPU:  {gpu_rend[:20]}"
            lines.append(_side_by_side(vms_str, rend_str, mid, cols))

            # Row: GC / VRAM
            gc_str = f"  GC:   {GREEN()}{unreachable:>6} freed{RESET()}"
            vram_str = f"  VRAM: {gpu_info}"
            lines.append(_side_by_side(gc_str, vram_str, mid, cols))

            # Row: Trim / Threads
            trim_str = f"  Trim: {'ok' if trim_ok else 'fail'}"
            threads = proc_state.get("Threads", "?")
            thr_str = f"  Thr:  {threads}"
            lines.append(_side_by_side(trim_str, thr_str, mid, cols))

        else:
            lines.append(f" {BOLD()}MEMORY{RESET()}")
            lines.append(f"  RSS:  {YELLOW()}{rss_mb:>8.2f} MB{RESET()}" if rss_mb >= 0 else "  RSS:  N/A")
            lines.append(f"  VMS:  {vms_mb:>8.2f} MB" if vms_mb >= 0 else "  VMS:  N/A")
            lines.append(f"  GC:   {GREEN()}{unreachable} freed{RESET()}")
            lines.append(f"  Trim: {'ok' if trim_ok else 'fail'}")
            lines.append("─" * cols)
            fd_color = RED() if (fd_limit > 0 and fd_count > fd_limit * 0.8) else GREEN()
            lines.append(f" {BOLD()}SYSTEM{RESET()}")
            lines.append(f"  FDs:  {fd_color}{fd_count}{RESET()} / {fd_limit}" if fd_limit > 0 else f"  FDs:  {fd_count}")
            lines.append(f"  GPU:  {gpu_info}")
            threads = proc_state.get("Threads", "?")
            lines.append(f"  Thr:  {threads}")

        # ── FD Breakdown ──────────────────────────────────────────────
        if fd_breakdown:
            lines.append("─" * cols)
            lines.append(f" {BOLD()}FD BREAKDOWN{RESET()}")
            for kind, count in sorted(fd_breakdown.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {kind:<12}: {count}")

        # ── Object Counts ─────────────────────────────────────────────
        if sorted_counts:
            lines.append("─" * cols)
            lines.append(f" {BOLD()}ACTIVE OBJECTS (Imbric){RESET()}")
            for name, count in sorted_counts[:12]:
                lines.append(f"  {name:<28}: {count}")

        # ── Top Allocators ────────────────────────────────────────────
        if top_allocs:
            lines.append("─" * cols)
            lines.append(f" {BOLD()}TOP ALLOCATORS (tracemalloc){RESET()}")
            for a in top_allocs:
                lines.append(a[:cols])

        # ── Diff since last snapshot ──────────────────────────────────
        if diff_allocs:
            lines.append("─" * cols)
            lines.append(f" {BOLD()}DIFF SINCE LAST F12{RESET()}")
            for a in diff_allocs:
                lines.append(a[:cols])

        lines.append(f"{CYAN()}{bar}{RESET()}")

        output = "\n".join(lines) + "\n"
        try:
            sys.stdout.write(output)
            sys.stdout.flush()
        except Exception:
            print(output)


# ── PersistentMonitor (Optimized Loop) ───────────────────────────────────────

class PersistentMonitor:
    """
    Long-running monitor process.
    - Caches static data (cmdline, GPU renderer).
    - Handles SIGWINCH for resize.
    - Sleeps efficiently.
    """
    
    def __init__(self, pid: int):
        self.pid = pid
        self.gpu_renderer = SystemProfiler.get_gpu_renderer()
        self.resize_event = False
        
        # Cache static process info
        try:
            import psutil
            p = psutil.Process(pid)
            self.cmd = " ".join(p.cmdline())
        except Exception:
            self.cmd = f"PID {pid}"
            
        # Handle resize
        import signal
        signal.signal(signal.SIGWINCH, self._handle_resize)

    def _handle_resize(self, signum, frame):
        self.resize_event = True

    def run(self):
        try:
            import psutil
        except ImportError:
            print("Error: psutil not installed.")
            return

        # Prime CPU
        try:
            proc = psutil.Process(self.pid)
            proc.cpu_percent(interval=None)
        except psutil.NoSuchProcess:
            print(f"Process {self.pid} not found.")
            return

        print(CLEAR_SCREEN(), end="")

        while True:
            # Check if process is alive
            if not psutil.pid_exists(self.pid):
                print(f"\nProcess {self.pid} ended.")
                break

            # If resized, clear screen
            if self.resize_event:
                print(CLEAR_SCREEN(), end="")
                self.resize_event = False

            # Render frame
            self.render_frame()
            time.sleep(1.0)

    def render_frame(self):
        # We reuse ProcessMonitor.print_snapshot logic but optimized
        # to use cached data and move cursor home instead of clearing
        
        # Fetch dynamic metrics
        metrics = ProcessMonitor.snapshot(self.pid)
        if not metrics:
            return

        # Overwrite cached cmd with what we have (optional)
        metrics["cmd"] = self.cmd
        
        # Render
        cols, rows = _get_term_size()
        lines: list[str] = []
        now = datetime.now().strftime("%H:%M:%S")
        bar = "═" * cols

        fd_count = SystemProfiler.get_fd_count(self.pid)
        fd_breakdown = SystemProfiler.get_fd_breakdown(self.pid)
        gpu_info = SystemProfiler.get_gpu_info()
        proc_state = SystemProfiler.get_process_state(self.pid)

        # Move cursor to Home (0,0)
        lines.append("\033[H") 
        
        lines.append(f"{CYAN()}{bar}{RESET()}")
        lines.append(f" {BOLD()}IMBRIC MONITOR (Live){RESET()}"
                      f"{' ' * max(1, cols - 33)}{DIM()}{now}{RESET()}")
        lines.append(f"{CYAN()}{bar}{RESET()}")

        cmd_display = self.cmd[:cols - 10] if len(self.cmd) > cols - 10 else self.cmd
        lines.append(f" PID: {BOLD()}{self.pid}{RESET()} │ {DIM()}{cmd_display}{RESET()}")
        lines.append("─" * cols)

        # Layout (Side-by-side)
        use_side_by_side = cols >= 60
        mid = cols // 2 if use_side_by_side else cols
        cpu_color = RED() if metrics["cpu"] > 50 else GREEN()

        if use_side_by_side:
            divider = "─" * (mid - 1) + "┼" + "─" * (cols - mid)
            left_header = f" {BOLD()}PROCESS{RESET()}"
            right_header = f" {BOLD()}SYSTEM{RESET()}"
            lines.append(_side_by_side(left_header, right_header, mid, cols))
            lines.append(divider)

            lines.append(_side_by_side(
                f"  CPU:  {cpu_color}{metrics['cpu']:>7.1f}%{RESET()}",
                f"  GPU:  {self.gpu_renderer[:20]}",
                mid, cols))
            lines.append(_side_by_side(
                f"  RSS:  {YELLOW()}{metrics['rss']:>8.2f} MB{RESET()}",
                f"  VRAM: {gpu_info}",
                mid, cols))
            lines.append(_side_by_side(
                f"  USS:  {GREEN()}{metrics['uss']:>8.2f} MB{RESET()}",
                f"  FDs:  {GREEN()}{fd_count:>6}{RESET()}",
                mid, cols))
            lines.append(_side_by_side(
                f"  VMS:  {metrics['vms']:>8.2f} MB",
                f"  Swap: {proc_state.get('VmSwap', 'N/A')}",
                mid, cols))
        else:
            lines.append(f" {BOLD()}PROCESS{RESET()}")
            lines.append(f"  CPU:  {cpu_color}{metrics['cpu']:>7.1f}%{RESET()}")
            lines.append(f"  RSS:  {YELLOW()}{metrics['rss']:>8.2f} MB{RESET()}")
            lines.append(f"  USS:  {GREEN()}{metrics['uss']:>8.2f} MB{RESET()}")
            lines.append(f"  VMS:  {metrics['vms']:>8.2f} MB")
            lines.append("─" * cols)
            lines.append(f" {BOLD()}SYSTEM{RESET()}")
            lines.append(f"  GPU:  {self.gpu_renderer}")
            lines.append(f"  VRAM: {gpu_info}")
            lines.append(f"  FDs:  {fd_count}")

        # Disk I/O
        lines.append("─" * cols)
        read_mb = metrics["read_bytes"] / (1024 * 1024)
        write_mb = metrics["write_bytes"] / (1024 * 1024)
        lines.append(f" {BOLD()}DISK I/O (cumulative){RESET()}")
        lines.append(f"  Read:   {read_mb:>10.2f} MB")
        lines.append(f"  Write:  {write_mb:>10.2f} MB")

        # FD Breakdown
        if fd_breakdown:
            lines.append("─" * cols)
            lines.append(f" {BOLD()}FD BREAKDOWN{RESET()}")
            for kind, count in sorted(fd_breakdown.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {kind:<12}: {count}")
        
        # Fill rest of screen to clear old junk if shrinking?
        # ANSI \033[J handles clearing below cursor if we use it.
        lines.append(f"{CYAN()}{bar}{RESET()}")
        lines.append("\033[J") 

        output = "\n".join(lines)
        sys.stdout.write(output)
        sys.stdout.flush()


# ── CLI Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Imbric Diagnostics — Internal profiler & External monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Internal (F12):   Called automatically via F12 inside Imbric
  External monitor: python3 scripts/diagnostics.py --monitor-live 1234
  Snapshot:         python3 scripts/diagnostics.py --monitor-pid 1234
"""
    )
    parser.add_argument(
        "--monitor-pid", type=int, default=None,
        help="Snapshot mode: Monitor PID once and exit"
    )
    parser.add_argument(
        "--monitor-live", type=int, default=None,
        help="Live mode: Monitor PID continuously (low lag)"
    )

    args = parser.parse_args()

    if args.monitor_live:
        monitor = PersistentMonitor(args.monitor_live)
        try:
            monitor.run()
        except KeyboardInterrupt:
            print("\nMonitor stopped.")
            
    elif args.monitor_pid:
        ProcessMonitor.print_snapshot(args.monitor_pid)
    else:
        # Default: run internal diagnostics (useful for testing)
        MemoryProfiler.start()
        MemoryProfiler.print_report()
