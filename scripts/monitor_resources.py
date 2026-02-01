import shlex
import psutil
import subprocess
import time
import csv
import argparse
import sys
import os
from datetime import datetime

def clear_screen():
    # ANSI escape code to clear screen and move cursor to top-left
    print("\033[2J\033[H", end="")

def print_dashboard(metrics, command, pid, log_file):
    clear_screen()
    print(f"\033[1;36m[Imbric Resource Monitor] - LIVE\033[0m")
    print("-" * 50)
    print(f"PID: \033[1m{pid}\033[0m | Command: \033[1m{command}\033[0m")
    print(f"Time: {metrics['timestamp']}")
    print("-" * 50)
    
    # Colorize CPU if high
    cpu_color = "\033[1;31m" if metrics['cpu'] > 50 else "\033[1;32m"
    print(f"CPU Usage:       {cpu_color}{metrics['cpu']:>6.1f}%\033[0m (Total incl. children)")
    
    print(f"Memory (RSS):    \033[1;33m{metrics['rss']:>6.2f} MB\033[0m (Total w/ arena)")
    print(f"Memory (USS):    \033[1;32m{metrics['uss']:>6.2f} MB\033[0m (Actual app usage)")
    print(f"Memory (VMS):    {metrics['vms']:>6.2f} MB")
    print(f"Threads:         {metrics['threads']:>6}")
    
    # Colorize FDs if high (danger zone usually > 800 for default limits)
    fd_color = "\033[1;31m" if metrics['fds'] > 800 else "\033[0m"
    print(f"File Descriptors:{fd_color}{metrics['fds']:>6}\033[0m")
    
    print("-" * 50)
    print(f"Disk Read:       {metrics['read_rate']:>6.2f} MB/s")
    print(f"Disk Write:      {metrics['write_rate']:>6.2f} MB/s")
    print("-" * 50)
    if log_file:
         print(f"App output redirected to: \033[4m{log_file}\033[0m")
    print(f"\033[2mPress Ctrl+C (or close app) to stop.\033[0m")

def monitor_pid(pid, interval, output_file, live_mode, app_cmd=None):
    try:
        proc = psutil.Process(pid)
        # Prime CPU reading
        proc.cpu_percent(interval=None)
        if app_cmd is None:
            try:
                app_cmd = " ".join(proc.cmdline())
            except:
                app_cmd = f"PID {pid}"
    except psutil.NoSuchProcess:
        print(f"Process {pid} not found.")
        return

    # Initialize IO and time for rate calculation
    try:
        io_start = proc.io_counters()
        prev_read = io_start.read_bytes
        prev_write = io_start.write_bytes
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        prev_read = 0
        prev_write = 0
    prev_time = time.time()

    # Prepare CSV
    csv_f = None
    writer = None
    if output_file:
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        csv_f = open(output_file, 'w', newline='')
        writer = csv.writer(csv_f)
        writer.writerow(['timestamp', 'cpu_percent', 'rss_mb', 'uss_mb', 'vms_mb', 'num_threads', 'num_fds', 'read_mb_s', 'write_mb_s'])

    try:
        while proc.is_running():
            try:
                curr_time = time.time()
                time_delta = curr_time - prev_time
                if time_delta <= 0: time_delta = 0.001

                timestamp_display = datetime.now().strftime("%H:%M:%S")
                timestamp_iso = datetime.now().isoformat()

                total_cpu = 0.0
                total_rss = 0.0
                total_vms = 0.0
                total_uss = 0.0  # Unique Set Size (actual app memory)
                total_threads = 0
                total_fds = 0
                total_read_bytes = 0
                total_write_bytes = 0

                procs_to_monitor = [proc]
                try:
                    procs_to_monitor.extend(proc.children(recursive=True))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

                for p in procs_to_monitor:
                    try:
                        with p.oneshot():
                            total_cpu += p.cpu_percent(interval=None)
                            mem = p.memory_info()
                            total_rss += mem.rss
                            total_vms += mem.vms
                            
                            # Get USS (Unique Set Size) - actual app memory
                            try:
                                mem_full = p.memory_full_info()
                                total_uss += mem_full.uss
                            except (AttributeError, psutil.AccessDenied):
                                # Fallback: USS not available on all platforms
                                total_uss += mem.rss  # Use RSS as approximation
                            
                            total_threads += p.num_threads()
                            try:
                                total_fds += p.num_fds()
                            except: pass
                            
                            io = p.io_counters()
                            total_read_bytes += io.read_bytes
                            total_write_bytes += io.write_bytes
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                read_rate = (total_read_bytes - prev_read) / (1024 * 1024) / time_delta
                write_rate = (total_write_bytes - prev_write) / (1024 * 1024) / time_delta
                read_rate = max(0, read_rate)
                write_rate = max(0, write_rate)

                metrics = {
                    'timestamp': timestamp_display,
                    'cpu': total_cpu,
                    'rss': total_rss / (1024 * 1024),
                    'uss': total_uss / (1024 * 1024),
                    'vms': total_vms / (1024 * 1024),
                    'threads': total_threads,
                    'fds': total_fds,
                    'read_rate': read_rate,
                    'write_rate': write_rate
                }

                if live_mode:
                    # In PID mode, we don't know the log file unless passed, but effectively we just show the dashboard
                    print_dashboard(metrics, app_cmd, pid, "Use main terminal for logs")
                
                if writer:
                    writer.writerow([timestamp_iso, f"{total_cpu:.1f}", f"{metrics['rss']:.2f}", f"{metrics['uss']:.2f}", f"{metrics['vms']:.2f}", 
                                   total_threads, total_fds, f"{read_rate:.2f}", f"{write_rate:.2f}"])
                    csv_f.flush()
                
                prev_read = total_read_bytes
                prev_write = total_write_bytes
                prev_time = curr_time
                
                time.sleep(interval)
                
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
    except KeyboardInterrupt:
        pass # Just exit cleaner
    finally:
        if csv_f: csv_f.close()
        # No process killing here, we just watched it.


if __name__ == "__main__":
    description = """
Imbric Resource Monitor - Simplified Usage Patterns:
  Basic Live:    python3 scripts/monitor_resources.py -l
  Profile Live:  python3 scripts/monitor_resources.py -lp
  Log to CSV:    python3 scripts/monitor_resources.py -o stats.csv
  Custom Cmd:    python3 scripts/monitor_resources.py -c "ls -R"
"""
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Find default command path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    default_main = os.path.join(root_dir, "main.py")
    
    if os.path.exists(default_main):
        default_cmd = f"python3 {default_main}"
    else:
        default_cmd = "python3 main.py"

    parser.add_argument("--command", "-c", default=default_cmd, 
                        help="Target command (default: Imbric main.py)")
    parser.add_argument("--interval", "-i", type=float, default=1.0, 
                        help="Check interval in seconds (default: 1.0)")
    parser.add_argument("--output", "-o", default=None, 
                        help="Save metrics to a CSV file (e.g. -o log.csv)")
    parser.add_argument("--live", "-l", action="store_true", 
                        help="Show real-time dashboard (TUI)")
    parser.add_argument("--profile", "-p", action="store_true", 
                        help="Enable Imbric internal profiling (adds --profile to app)")
    parser.add_argument("--pid", type=int, default=None,
                        help="Monitor existing PID instead of launching a command")

    args = parser.parse_args()
    
    if args.pid:
        monitor_pid(args.pid, args.interval, args.output, args.live)
    else:
        # Launcher Mode
        cmd = args.command
        if args.profile and "main.py" in cmd and "--profile" not in cmd:
            cmd += " --profile"
            
        if args.live:
            # Detached Launch Mode
            try:
                # 1. Launch the app in THIS terminal (so user sees logs)
                args_list = shlex.split(cmd)
                print(f"Launching application: {cmd}")
                proc = subprocess.Popen(args_list, shell=False) # Inherit stdout/stderr
            except Exception as e:
                print(f"Failed to launch command: {e}")
                sys.exit(1)
            
            # 2. Launch gnome-terminal to run the monitor attached to the new PID
            try:
                # Resolve absolute path to self to ensure we run the right script
                script_path = os.path.abspath(__file__)
                monitor_cmd = f"python3 {script_path} --pid {proc.pid} --live"
                if args.output:
                    monitor_cmd += f" --output {args.output}"
                
                # We spin up the monitor in a new window
                subprocess.Popen(["gnome-terminal", "--", "bash", "-c", f"{monitor_cmd}; exec bash"])
                print(f"Resource Monitor launched in a separate window (PID: {proc.pid})")
                print("App logs will appear below...")
                
                # Wait for app to finish
                try:
                    proc.wait()
                except KeyboardInterrupt:
                    proc.terminate()
            except FileNotFoundError:
                print("Error: gnome-terminal not found. Falling back to non-live monitoring.")
                monitor_pid(proc.pid, args.interval, args.output, False, cmd)
        
        else:
            # Non-live standard mode: Launch app and monitor in background (or text log)
            # Existing monitor logic can be reused or simplified. 
            # For simplicity, we just use subprocess to launch and then monitor_pid
            args_list = shlex.split(cmd)
            proc = subprocess.Popen(args_list, shell=False)
            monitor_pid(proc.pid, args.interval, args.output, False, cmd)
