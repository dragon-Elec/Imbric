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
    print(f"CPU Usage:       {cpu_color}{metrics['cpu']:>6.1f}%\033[0m")
    
    print(f"Memory (RSS):    \033[1;33m{metrics['rss']:>6.2f} MB\033[0m")
    print(f"Memory (VMS):    {metrics['vms']:>6.2f} MB")
    print(f"Threads:         {metrics['threads']:>6}")
    
    # Colorize FDs if high (danger zone usually > 800 for default limits)
    fd_color = "\033[1;31m" if metrics['fds'] > 800 else "\033[0m"
    print(f"File Descriptors:{fd_color}{metrics['fds']:>6}\033[0m")
    
    print("-" * 50)
    print(f"Disk Read:       {metrics['read_bytes'] / 1024 / 1024:>6.2f} MB")
    print(f"Disk Write:      {metrics['write_bytes'] / 1024 / 1024:>6.2f} MB")
    print("-" * 50)
    if log_file:
         print(f"App output redirected to: \033[4m{log_file}\033[0m")
    print("\033[2mPress Ctrl+C to stop.\033[0m")

def monitor_process(command, interval, output_file, live_mode):
    if not live_mode:
        print(f"Starting process: {command}")
        if output_file:
            print(f"Logging to: {output_file}")
    
    # Handle log redirection for live mode
    app_log_file = None
    stdout_dest = None
    stderr_dest = None
    
    if live_mode:
        app_log_file = "app_output.log"
        f_log = open(app_log_file, "w")
        stdout_dest = f_log
        stderr_dest = subprocess.STDOUT
        print(f"Live mode enabled. Redirecting app output to {app_log_file}...")
    
    # Launch the process
    try:
        args_list = shlex.split(command)
        proc = subprocess.Popen(args_list, shell=False, stdout=stdout_dest, stderr=stderr_dest)
    except Exception as e:
        print(f"Failed to launch command: {e}")
        return

    pid = proc.pid
    if not live_mode:
        print(f"Process launched with PID: {pid}")

    try:
        ps_proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        print("Process died immediately.")
        if live_mode and f_log: f_log.close()
        return

    # Prepare CSV
    csv_f = None
    writer = None
    if output_file:
        # Ensure output directory exists
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        csv_f = open(output_file, 'w', newline='')
        writer = csv.writer(csv_f)
        writer.writerow(['timestamp', 'cpu_percent', 'rss_mb', 'vms_mb', 'num_threads', 'num_fds', 'read_bytes', 'write_bytes'])

    try:
        while proc.poll() is None:
            try:
                with ps_proc.oneshot():
                    timestamp_iso = datetime.now().isoformat()
                    # For live display, we want a human readable time
                    timestamp_display = datetime.now().strftime("%H:%M:%S")
                    
                    cpu = ps_proc.cpu_percent(interval=None)
                    mem = ps_proc.memory_info()
                    rss = mem.rss / (1024 * 1024)
                    vms = mem.vms / (1024 * 1024)
                    threads = ps_proc.num_threads()
                    try:
                        fds = ps_proc.num_fds()
                    except: 
                        fds = 0
                    
                    io = ps_proc.io_counters()
                    read_bytes = io.read_bytes
                    write_bytes = io.write_bytes

                metrics = {
                    'timestamp': timestamp_display,
                    'cpu': cpu,
                    'rss': rss,
                    'vms': vms,
                    'threads': threads,
                    'fds': fds,
                    'read_bytes': read_bytes,
                    'write_bytes': write_bytes
                }

                if live_mode:
                    print_dashboard(metrics, command, pid, app_log_file)
                
                if writer:
                    writer.writerow([timestamp_iso, cpu, f"{rss:.2f}", f"{vms:.2f}", threads, fds, read_bytes, write_bytes])
                    csv_f.flush()
                
                time.sleep(interval)
                
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
    except KeyboardInterrupt:
        if not live_mode: 
            print("\nMonitoring stopped by user.")
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
    finally:
        if csv_f: csv_f.close()
        if live_mode and f_log: f_log.close()

    if not live_mode:
        print(f"Monitoring finished.")
        if output_file:
            print(f"Log saved to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor process resource usage.")
    parser.add_argument("--command", required=True, help="Command to run (e.g. 'python3 main.py')")
    parser.add_argument("--interval", type=float, default=1.0, help="Monitoring interval in seconds")
    parser.add_argument("--output", default=None, help="Optional output CSV file path")
    parser.add_argument("--live", action="store_true", help="Enable live TUI dashboard")

    args = parser.parse_args()
    
    monitor_process(args.command, args.interval, args.output, args.live)
