#!/bin/bash
set -e

# Configuration
VERSION="0.15.0"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL_DIR="${PROJECT_DIR}/build/native-gen/tools"
GEN_DIR="${PROJECT_DIR}/build/native-gen/bindings"
TEMP_GEN="${PROJECT_DIR}/build/native-gen/temp_raw"
PATCHED_JAVA_GI="${PROJECT_DIR}/ref/java-gi_patched/generator/build/install/java-gi/bin/java-gi"

echo "==> [1/5] Infrastructure Setup"
mkdir -p "$TOOL_DIR"
mkdir -p "$GEN_DIR"
rm -rf "$GEN_DIR"/*
rm -rf "$TEMP_GEN"

# Download Foundation Sources (needed for org.javagi.* classes)
if [ ! -f "${TOOL_DIR}/glib-${VERSION}-sources.jar" ]; then
    echo "    Fetching official sources from Maven Central..."
    wget -q -O "${TOOL_DIR}/glib-${VERSION}-sources.jar" "https://repo.maven.apache.org/maven2/org/java-gi/glib/${VERSION}/glib-${VERSION}-sources.jar"
fi

echo "==> [2/5] Extracting Stable Foundation & Hand-written types"
# Extract foundation classes from the downloaded sources jar
unzip -q -o "${TOOL_DIR}/glib-${VERSION}-sources.jar" "org/javagi/*" -d "$GEN_DIR"
# Copy our local foundation classes (including our patches and missing types like Filename)
cp -r "${PROJECT_DIR}/ref/java-gi_patched/modules/glib/src/main/java/org" "$GEN_DIR"

echo "==> [3/5] Generating Native GNOME 46 Bindings (using PATCHED generator)"
mkdir -p "$TEMP_GEN"

# We use our locally built, patched java-gi generator.
# Patch 1: Automatically upgrades scope="call" to "async" for _async functions.
# Patch 2: Allows CLI-provided GIR files to override bundled ones.

# Prefer submodule GIR files (guaranteed compatible), fall back to system
GIR_DIR="${PROJECT_DIR}/ref/java-gi_patched/ext/gir-files/linux"
if [ ! -f "$GIR_DIR/GLib-2.0.gir" ]; then
    GIR_DIR="/usr/share/gir-1.0"
fi

"$PATCHED_JAVA_GI" -S -s "Imbric Native Bindings" \
    -d org.gnome \
    -o "$TEMP_GEN" \
    "$GIR_DIR/GLib-2.0.gir" \
    "$GIR_DIR/GObject-2.0.gir" \
    "$GIR_DIR/Gio-2.0.gir" \
    "$GIR_DIR/GdkPixbuf-2.0.gir"

echo "==> [4/5] Flattening & Merging Structure"
# Move all library-specific org/gnome subfolders into the shared root
find "$TEMP_GEN" -path "*/org/gnome/*" -type f | while read -r file; do
    # Extract the relative path from 'org/gnome' onwards
    rel_path=$(echo "$file" | sed 's|.*org/gnome/|org/gnome/|')
    dest_path="$GEN_DIR/$rel_path"
    mkdir -p "$(dirname "$dest_path")"
    cp "$file" "$dest_path"
done
rm -rf "$TEMP_GEN"

# Cleanup
echo "    Removing module-info.java..."
find "$GEN_DIR" -name "module-info.java" -delete

echo "DONE: Bindings generated and patched successfully with the fix."
