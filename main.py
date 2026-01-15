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

    # Force Material Style
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Material"
    QQuickStyle.setStyle("Material")
    
    print(f"Effective Style: {QQuickStyle.name()}")
    
    # Initialize Main Window
    window = MainWindow(start_path=args.path)
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
