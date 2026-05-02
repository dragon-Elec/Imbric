#!/usr/bin/env python3
import sys
import time

# [DIAGNOSTICS] Capture absolute start time and base module count
_START_TIME = time.perf_counter()
_BASE_MODULE_COUNT = len(sys.modules)
import signal
import os
import argparse
import traceback
from pathlib import Path

# Switch to QApplication for Widgets support
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from PySide6.QtQuickControls2 import QQuickStyle

# Add project root to path so imports work
sys.path.append(str(Path(__file__).parent))

from application.main_window import MainWindow


def parse_args():
    parser = argparse.ArgumentParser(description="Imbric Photo Manager")
    parser.add_argument("path", nargs="?", help="Folder to open", default=None)
    parser.add_argument(
        "--profile", action="store_true", help="Enable cProfile performance profiling"
    )
    parser.add_argument(
        "--monitor",
        "-m",
        action="store_true",
        help="Launch with resource monitor (TUI)",
    )
    return parser.parse_args()


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # [DIAGNOSTICS] GLib Critical Interceptor — prints Python traceback on GIO errors
    # This identifies WHICH Python file triggered the C-level critical.
    import gi

    gi.require_version("GLib", "2.0")
    from gi.repository import GLib

    def _gio_critical_handler(log_domain, log_level, message):
        # Print the GLib message
        print(f"\n[GIO-TRACE] {log_domain}: {message}")
        # Print the Python call stack that led here
        traceback.print_stack(limit=8)
        print()

    GLib.log_set_handler(
        "GLib-GIO", GLib.LogLevelFlags.LEVEL_CRITICAL, _gio_critical_handler
    )

    args = parse_args()

    # [MONITOR] Launch app + dedicated gnome-terminal with `watch`
    if args.monitor:
        import subprocess as _sp

        # 1. Build the inner command (the app itself, without -m)
        inner_cmd = [sys.executable, str(Path(__file__).absolute())]
        if args.path:
            inner_cmd.append(args.path)
        if args.profile:
            inner_cmd.append("--profile")

        # 2. Launch the app as a subprocess
        app_proc = _sp.Popen(inner_cmd)
        print(f"[Monitor] App launched (PID: {app_proc.pid})")

        # 3. Spawn gnome-terminal running `PersistentMonitor` loop
        diag_script = str(Path(__file__).parent / "scripts" / "diagnostics.py")
        # Direct Python execution (no `watch`)
        live_cmd = f"python3 {diag_script} --monitor-live {app_proc.pid}"

        try:
            _sp.Popen(
                [
                    "gnome-terminal",
                    "--title=Imbric Monitor",
                    "--",
                    "bash",
                    "-c",
                    live_cmd,
                ]
            )
            print("[Monitor] Dashboard launched in new terminal window.")
        except FileNotFoundError:
            print("[Monitor] gnome-terminal not found. Run manually:")
            print(f"  {live_cmd}")

        # 4. Wait for app to finish, then exit
        try:
            app_proc.wait()
        except KeyboardInterrupt:
            app_proc.terminate()
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setOrganizationName("Antigravity")
    app.setApplicationName("Imbric")

    # [NEW] Register Material Symbols Rounded font
    font_path = (
        Path(__file__).parent
        / "application"
        / "assets"
        / "fonts"
        / "MaterialSymbolsRounded.ttf"
    )
    if font_path.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            print(f"Loaded Font Family: {families[0]}")
        else:
            print(f"Error: Failed to load font from {font_path}")
    else:
        print(f"Warning: Material Symbols font not found at {font_path}")

    # 1. Force Material Style for QML (Environment Variable)
    # This must be done before QQuickStyle is effectively used, though confusingly
    # QQuickStyle.setStyle() also does this. We do both to be safe as per demo.
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Material"

    # [FIX] Load Custom Configuration (Dense Variant)
    # Locate the config file relative to this script
    conf_path = Path(__file__).parent / "application" / "qtquickcontrols2.conf"
    if conf_path.exists():
        os.environ["QT_QUICK_CONTROLS_CONF"] = str(conf_path)
        print(f"Loaded QML Config: {conf_path}")
    else:
        print(f"Warning: QML Config not found at {conf_path}")

    QQuickStyle.setStyle("Material")

    # 2. Native Style Integration
    # We allow the app to inherit the system theme (e.g. GTK/Adwaita) for the top-level shell.
    # Event tracking is now stabilized in MainLayout.qml, making 'Fusion' unnecessary.
    # app.setStyle("Fusion")

    # 3. Apply Modern QSS Patches
    qss_path = Path(__file__).parent / "application" / "styles" / "modern.qss"

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
    from scripts.diagnostics import MemoryProfiler

    MemoryProfiler.start()

    # [DIAGNOSTICS] Print final startup metrics just before handing off to the Qt Event Loop
    startup_ms = (time.perf_counter() - _START_TIME) * 1000
    total_modules = len(sys.modules)
    app_modules = total_modules - _BASE_MODULE_COUNT
    print(f"\n[Diagnostics] Imbric Engine Initialized:")
    print(f"  └─ Boot Time:  {startup_ms:.1f} ms")
    print(
        f"  └─ Footprint:  {total_modules} total modules loaded into RAM ({app_modules} application-specific)"
    )

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
