#!/usr/bin/env python3
"""
Isolated test script to verify FileScanner async behavior.
Run this script to check if the scanner blocks the main thread.

Usage: python3 tests/verify_scanner_async.py [path_to_scan]
"""

import sys
import os
import signal

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import QCoreApplication, QTimer, QObject, Slot
from core.gio_bridge.scanner import FileScanner


class AsyncVerifier(QObject):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.scanner = FileScanner()
        self.scanner.filesFound.connect(self.on_files)
        self.scanner.scanFinished.connect(self.on_finished)
        self.scanner.scanError.connect(self.on_error)
        self.scanner.fileAttributeUpdated.connect(self.on_attribute_updated)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(10)  # 10ms tick
        
        self.tick_count = 0
        self.batch_count = 0
        self.count_updates = 0
        self.scan_done = False
        
        print(f"Starting scan of: {self.path}")
        print("Expected behavior: 'Tick' should print continuously mixed with 'Batch'.")
        print("Count updates should arrive asynchronously.")
        print("-" * 40)
        
        self.scanner.scan_directory(self.path)

    @Slot()
    def on_tick(self):
        self.tick_count += 1
        # Print every tick to see if we have ANY life
        sys.stdout.write(".")
        sys.stdout.flush()

    @Slot(list)
    def on_files(self, files):
        self.batch_count += 1
        dir_count = sum(1 for f in files if f.get("isDir", False))
        print(f"\n[Batch {self.batch_count}] Found {len(files)} files ({dir_count} dirs)")

    @Slot()
    def on_finished(self):
        self.scan_done = True
        print(f"\nScan Finished in {self.tick_count * 10}ms roughly!")
        print("Waiting for count updates...")
        # Give worker time to finish counts
        QTimer.singleShot(2000, self.final_report)

    @Slot(str, str, object)
    def on_attribute_updated(self, path, attr, value):
        self.count_updates += 1
        if self.count_updates <= 5:  # Only show first 5
            print(f"  [Count] {os.path.basename(path)}: {value} items")
        elif self.count_updates == 6:
            print("  ... (more counts arriving)")

    def final_report(self):
        print(f"\n{'='*40}")
        print(f"FINAL REPORT:")
        print(f"  Ticks: {self.tick_count}")
        print(f"  Batches: {self.batch_count}")
        print(f"  Count Updates: {self.count_updates}")
        if self.count_updates > 0:
            print("  STATUS: PASS (async counting working!)")
        else:
            print("  STATUS: FAIL (no count updates received)")
        print(f"{'='*40}")
        QCoreApplication.quit()

    @Slot(str)
    def on_error(self, err):
        print(f"\nScan Error: {err}")
        QCoreApplication.quit()


def main():
    app = QCoreApplication(sys.argv)
    
    # Allow Ctrl+C
    signal.signal(signal.SIGINT, lambda sig, frame: app.quit())
    
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~")
    
    verifier = AsyncVerifier(path)
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
