#!/usr/bin/env python3
import sys
import signal
import os
import argparse
from pathlib import Path

# Switch to QApplication for Widgets support
from PySide6.QtWidgets import QApplication
from PySide6.QtQuickControls2 import QQuickStyle

# Add project root to path so imports work
sys.path.append(str(Path(__file__).parent))

from ui.main_window import MainWindow

def parse_args():
    parser = argparse.ArgumentParser(description="Imbric Photo Manager")
    parser.add_argument("path", nargs="?", help="Folder to open", default=None)
    parser.add_argument("--profile", action="store_true", help="Enable cProfile performance profiling")
    parser.add_argument("--monitor", "-m", action="store_true", help="Launch with resource monitor (TUI)")
    return parser.parse_args()

def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    args = parse_args()
    
    # [NEW] Monitor Wrapper Logic
    if args.monitor:
        monitor_script = Path(__file__).parent / "scripts" / "monitor_resources.py"
        if monitor_script.exists():
            import subprocess
            # Re-run ourselves without the -m flag, wrapped by monitor
            cmd_args = [sys.executable, str(monitor_script), "-l", "-c"]
            
            # Construct the inner command (removing -m/--monitor)
            inner_cmd = [sys.executable, str(Path(__file__).absolute())]
            if args.path: inner_cmd.append(args.path)
            if args.profile: inner_cmd.append("--profile")
            
            cmd_args.append(" ".join(inner_cmd))
            
            # Replace current process
            os.execv(sys.executable, cmd_args)
        else:
            print("Warning: Monitor script not found. Proceeding normally.")

    app = QApplication(sys.argv)
    app.setOrganizationName("Antigravity")
    app.setApplicationName("Imbric")

    # 1. Force Material Style for QML (Environment Variable)
    # This must be done before QQuickStyle is effectively used, though confusingly
    # QQuickStyle.setStyle() also does this. We do both to be safe as per demo.
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Material"
    
    # [FIX] Load Custom Configuration (Dense Variant)
    # Locate the config file relative to this script
    conf_path = Path(__file__).parent / "ui" / "qtquickcontrols2.conf"
    if conf_path.exists():
        os.environ["QT_QUICK_CONTROLS_CONF"] = str(conf_path)
        print(f"Loaded QML Config: {conf_path}")
    else:
        print(f"Warning: QML Config not found at {conf_path}")

    QQuickStyle.setStyle("Material")

    # 2. Force Fusion Style for Widgets (The Shell)
    # This serves as the base for our QSS patches.
    # [DISABLED] We disable this to allow QML SystemPalette to inherit the native (GTK) colors,
    # matching the experiment's look.
    # app.setStyle("Fusion")

    # 3. Apply Modern QSS Patches
    qss_path = Path(__file__).parent / "ui" / "styles" / "modern.qss"

    def apply_styles():
        """Reads and applies the QSS file to the application."""
        if qss_path.exists():
            with open(qss_path, "r") as f:
                # Re-applying the sheet forces palette() to be re-evaluated
                # which is crucial for handling light/dark mode switches.
                app.setStyleSheet(f.read())
        else:
            print(f"Warning: Stylesheet not found at {qss_path}")

    # Initial Load
    apply_styles()

    # Dynamic Reload: Listen for Palette changes (System Dark Mode toggle)
    app.paletteChanged.connect(lambda: apply_styles())
    
    print(f"Effective QML Style: {QQuickStyle.name()}")
    
    # Initialize Main Window
    window = MainWindow(start_path=args.path)
    window.show()

    # Profiling Wrapper
    if args.profile:
        import cProfile
        import pstats
        print("Profiling enabled...")
        profiler = cProfile.Profile()
        profiler.enable()

    # [NEW] Start Internal Memory Profiler (Tracemalloc)
    # This allows F12 diagnostics to work immediately without losing early history
    from core.diagnostics import MemoryProfiler
    MemoryProfiler.start()

    ret_code = app.exec()

    if args.profile:
        profiler.disable()
        print("\n--- Profiling Stats (Top 20 by Cumulative Time) ---")
        stats = pstats.Stats(profiler).sort_stats("cumulative")
        stats.print_stats(20)
        stats.dump_stats("imbric.prof")
        print(f"Profile data saved to '{os.path.abspath('imbric.prof')}'")

    sys.exit(ret_code)

if __name__ == "__main__":
    main()
