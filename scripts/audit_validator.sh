#!/bin/bash
# audit_validator.sh - Expert Version
# Logic: Isolates the specific file's audit block and detects documented methods with flexible delimiters.

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <source_file.py> <context_file.md>"
    exit 1
fi

SRC="$1"
CONTEXT="$2"
FILE_NAME=$(basename "$SRC")

if [ ! -f "$SRC" ]; then echo "Error: Source file $SRC not found."; exit 1; fi
if [ ! -f "$CONTEXT" ]; then echo "Error: Context file $CONTEXT not found."; exit 1; fi

# 1. Extract Public Methods from Python source
# Filters out: private (_), dunder (__), and standard Qt overrides like 'parent'
METHODS_SRC=$(grep -oP 'def \K[a-zA-Z][a-zA-Z0-9_]+(?=\()' "$SRC" | grep -vE "^_|parent|__" | sort -u)

# 2. Extract the specific Audit Block for this file
# This prevents name collisions where method names overlap across different files in the context.
BLOCK=$(awk "/### \[FILE: $FILE_NAME\]/{p=1;print;next} /### \[FILE:/{p=0} p" "$CONTEXT")

# Fallback for some awk versions or if block is last in file
if [[ -z "$BLOCK" ]]; then
    BLOCK=$(sed -n "/### \[FILE: $FILE_NAME\]/,\$p" "$CONTEXT")
    # If there is a next block, trim it
    NEXT_BLOCK=$(grep -n "### \[FILE: " <<< "$BLOCK" | sed -n '2p' | cut -d: -f1)
    if [[ ! -z "$NEXT_BLOCK" ]]; then
        BLOCK=$(head -n $((NEXT_BLOCK - 1)) <<< "$BLOCK")
    fi
fi

if [[ -z "$BLOCK" ]]; then
    echo "Error: Could not isolate audit block for $FILE_NAME."
    exit 1
fi

# 3. Extract documented methods from the isolated block
# Delimiters:
# (\s*[/(]) : Followed by ( or / (method call or shorthand separator)
# (\s+=>)    : Followed by => (return type arrow)
# (\s*:)     : Followed by a colon (API detail line)
METHODS_CONTEXT=$(echo "$BLOCK" | grep -oP '\b[a-zA-Z0-9_]{3,}\b(?=\s*[/(]|\s+=>|\s*:)' | sort -u)

# 4. Compare and Report
echo "### Validation Results: $FILE_NAME ###"
MISSING=$(comm -23 <(echo "$METHODS_SRC") <(echo "$METHODS_CONTEXT"))

if [[ -z "$MISSING" ]]; then
    echo "[✓] Audit block accurate."
else
    echo "[!] Methods in source but missing/misformatted in API block:"
    echo "$MISSING" | sed 's/^/  - /'
fi
