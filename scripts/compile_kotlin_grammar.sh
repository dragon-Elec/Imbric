#!/usr/bin/env bash
set -euo pipefail
# Compile tree-sitter-kotlin grammar to .so for use by kt_compress.py
# Deps: git, clang

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GRAMMAR_DIR="$ROOT/languages/tree-sitter-kotlin"
OUT="$GRAMMAR_DIR/build/libtree-sitter-kotlin.so"

if [ ! -d "$GRAMMAR_DIR" ]; then
    echo "Cloning tree-sitter-kotlin grammar..."
    git clone --depth 1 https://github.com/fwcd/tree-sitter-kotlin.git "$GRAMMAR_DIR"
fi

echo "Compiling grammar (clang)..."
mkdir -p "$GRAMMAR_DIR/build"

# note: -dynamiclib for macOS, -shared for Linux
clang -shared -fPIC -O2 \
    "$GRAMMAR_DIR/src/parser.c" \
    "$GRAMMAR_DIR/src/scanner.c" \
    -o "$OUT"

echo "Done: $OUT"
