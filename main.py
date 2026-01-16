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
    return parser.parse_args()

def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    args = parse_args()

    app = QApplication(sys.argv)
    app.setOrganizationName("Antigravity")
    app.setApplicationName("Imbric")

    # 1. Force Material Style for QML (Environment Variable)
    # This must be done before QQuickStyle is effectively used, though confusingly
    # QQuickStyle.setStyle() also does this. We do both to be safe as per demo.
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Material"
    QQuickStyle.setStyle("Material")

    # 2. Force Fusion Style for Widgets (The Shell)
    # This serves as the base for our QSS patches.
    app.setStyle("Fusion")

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

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
