import os
import subprocess
from ..process import ProcessManager, ProcessInfo

def register(subparsers):
    p = subparsers.add_parser("memory", help="Show memory usage of Gradle/Kotlin/Imbric processes")
    p.add_argument("--verbose", "-v", action="store_true", help="Show detailed memory breakdown")

def _get_memory_breakdown(pid: int) -> dict:
    """Get detailed memory breakdown from /proc/pid/smaps_rollup."""
    breakdown = {
        "rss": 0,
        "pss": 0,
        "shared": 0,
        "private": 0,
        "swap": 0,
    }
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Rss:"):
                    breakdown["rss"] = int(line.split()[1])
                elif line.startswith("Pss:"):
                    breakdown["pss"] = int(line.split()[1])
                elif line.startswith("Shared_Clean:") or line.startswith("Shared_Dirty:"):
                    breakdown["shared"] += int(line.split()[1])
                elif line.startswith("Private_Clean:") or line.startswith("Private_Dirty:"):
                    breakdown["private"] += int(line.split()[1])
                elif line.startswith("Swap:"):
                    breakdown["swap"] = int(line.split()[1])
    except (FileNotFoundError, ValueError, IndexError):
        pass
    
    # Fallback to /proc/pid/status if smaps_rollup not available
    if breakdown["rss"] == 0:
        try:
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        breakdown["rss"] = int(line.split()[1])
                    elif line.startswith("VmSize:"):
                        breakdown["pss"] = int(line.split()[1])
        except (FileNotFoundError, ValueError, IndexError):
            pass
    
    return breakdown

def _format_bytes(kb: int) -> str:
    """Format kilobytes to human readable."""
    if kb > 1024 * 1024:
        return f"{kb / 1024 / 1024:.1f}GB"
    elif kb > 1024:
        return f"{kb / 1024:.0f}MB"
    return f"{kb}KB"

def _format_process(proc: ProcessInfo, verbose: bool = False) -> str:
    """Format a process for display."""
    breakdown = _get_memory_breakdown(proc.pid)
    rss = _format_bytes(breakdown["rss"])
    pss = _format_bytes(breakdown["pss"])
    shared = _format_bytes(breakdown["shared"])
    private = _format_bytes(breakdown["private"])
    swap = _format_bytes(breakdown["swap"])
    
    if verbose:
        return f"  {proc.pid:>6}  {rss:>6}  {pss:>6}  {shared:>6}  {private:>6}  {swap:>6}  {proc.cmd[:50]}"
    else:
        return f"  {proc.pid:>6}  {rss:>6}  {proc.cmd[:60]}"

def run(args):
    print("=== Memory Usage ===")
    print()
    
    status = ProcessManager.get_status()
    total_rss = 0
    total_pss = 0
    total_procs = 0
    
    for category, procs in status.items():
        if not procs:
            continue
        print(f"{category.replace('_', ' ').title()}:")
        if args.verbose:
            print(f"  {'PID':>6}  {'RSS':>6}  {'PSS':>6}  {'SHRD':>6}  {'PRVT':>6}  {'SWAP':>6}  COMMAND")
        else:
            print(f"  {'PID':>6}  {'MEM':>6}  COMMAND")
        for p in procs:
            print(_format_process(p, args.verbose))
            breakdown = _get_memory_breakdown(p.pid)
            total_rss += breakdown["rss"]
            total_pss += breakdown["pss"]
            total_procs += 1
        print()
    
    if total_procs == 0:
        print("No processes running.")
    else:
        print(f"Total: {total_procs} process(es)")
        print(f"Total RSS: {_format_bytes(total_rss)}")
        if args.verbose:
            print(f"Total PSS: {_format_bytes(total_pss)}")
    
    # Show system memory info
    print()
    print("System Memory:")
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    print(f"  Total: {_format_bytes(kb)}")
                elif line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    print(f"  Available: {_format_bytes(kb)}")
                elif line.startswith("MemFree:"):
                    kb = int(line.split()[1])
                    print(f"  Free: {_format_bytes(kb)}")
    except Exception:
        print("  Could not read /proc/meminfo")
