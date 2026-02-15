"""
Diagnostics Module for Imbric

Provides internal memory profiling using 'gc' and 'tracemalloc'.
Used to detect memory leaks and object retention issues.
"""

import gc
import tracemalloc
import os
import psutil
import ctypes
from collections import Counter

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

    @staticmethod
    def print_report():
        """
        Force garbage collection, trim memory, and print a detailed report.
        """
        print("\n" + "="*60)
        print("MEMORY DIAGNOSTICS REPORT")
        print("="*60)

        # 1. Force GC
        unreachable = gc.collect()
        print(f"GC: Collected {unreachable} unreachable objects.")
        
        # 2. Force OS Memory Reclaim (malloc_trim)
        # This tells glibc to release free memory back to the OS immediately
        try:
            libc = ctypes.CDLL("libc.so.6")
            libc.malloc_trim(0)
            print("System: malloc_trim(0) called (Force OS reclaim).")
        except Exception as e:
            print(f"System: malloc_trim failed: {e}")

        # 3. Current Process Memory (RSS)
        try:
            process = psutil.Process(os.getpid())
            mem = process.memory_info()
            print(f"RSS Memory: {mem.rss / 1024 / 1024:.2f} MB")
            print(f"VMS Memory: {mem.vms / 1024 / 1024:.2f} MB")
        except Exception:
            print("RSS Memory: Unavailable")

        # 4. Object Counts (Focus on Imbric classes)
        print("\n--- Active Object Counts (Imbric) ---")
        
        target_classes = [
            'BrowserTab', 'FileScanner', 'ThumbnailProvider', 
            'ThumbnailResponse', 'JustifiedView',
            'QQuickView', 'QImage', 'QNetworkReply'
        ]
        
        counts = Counter()
        for obj in gc.get_objects():
            try:
                cls_name = type(obj).__name__
                if cls_name in target_classes:
                    counts[cls_name] += 1
                elif 'Imbric' in str(type(obj)): # Catch other custom classes
                    counts[cls_name] += 1
            except:
                pass
                
        for name, count in counts.most_common():
            print(f"{name:<30}: {count}")

        # 3. Tracemalloc Statistics
        if tracemalloc.is_tracing():
            print("\n--- Top Memory Allocators (Current) ---")
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')

            for stat in top_stats[:10]:
                print(stat)

            if MemoryProfiler._snapshot:
                print("\n--- Difference since last Snapshot ---")
                top_stats_diff = snapshot.compare_to(MemoryProfiler._snapshot, 'lineno')
                for stat in top_stats_diff[:10]:
                    print(stat)
            
            # Update snapshot for next diff
            MemoryProfiler._snapshot = snapshot
        else:
            print("\n[Warn] Tracemalloc not running. Call start() early.")

        print("="*60 + "\n")
