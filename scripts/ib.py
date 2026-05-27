#!/usr/bin/env python3
"""
Entry point for the Imbric Build Utility.
"""
import sys
from pathlib import Path

# Add scripts directory to path to allow importing ib module
scripts_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(scripts_dir))

from ib.cli import main

if __name__ == "__main__":
    main()
