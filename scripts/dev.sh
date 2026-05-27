#!/bin/bash
# Imbric Development Script
# Thin wrapper around ib.py daemon.
exec python3 "$(dirname "${BASH_SOURCE[0]}")/ib.py" dev
