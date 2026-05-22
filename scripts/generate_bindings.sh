#!/bin/bash
set -e

# Configuration
VERSION="0.15.0"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL_DIR="${PROJECT_DIR}/build/native-gen/tools"
GEN_DIR="${PROJECT_DIR}/build/native-gen/bindings"
TEMP_GEN="${PROJECT_DIR}/build/native-gen/temp_raw"
PATCHED_JAVA_GI="${PROJECT_DIR}/ref/java-gi/generator/build/install/java-gi/bin/java-gi"

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
# Copy foundation classes from the local java-gi repo
cp -r "${PROJECT_DIR}/ref/java-gi/modules/glib/src/main/java/org" "$GEN_DIR"
# Copy specific hand-written types from the local java-gi repo
# (These are already copied by the cp -r above if they are in org/gnome/glib)
# But let's make sure we have the latest versions from the repo.
mkdir -p "$GEN_DIR/org/gnome/glib/"
cp "${PROJECT_DIR}/ref/java-gi/modules/glib/src/main/java/org/gnome/glib/List.java" "$GEN_DIR/org/gnome/glib/"
cp "${PROJECT_DIR}/ref/java-gi/modules/glib/src/main/java/org/gnome/glib/SList.java" "$GEN_DIR/org/gnome/glib/"
cp "${PROJECT_DIR}/ref/java-gi/modules/glib/src/main/java/org/gnome/glib/HashTable.java" "$GEN_DIR/org/gnome/glib/"
cp "${PROJECT_DIR}/ref/java-gi/modules/glib/src/main/java/org/gnome/glib/ByteArray.java" "$GEN_DIR/org/gnome/glib/"

echo "==> [3/5] Generating Native GNOME 46 Bindings (using PATCHED generator)"
mkdir -p "$TEMP_GEN"

# We use our locally built, patched java-gi generator.
# Patch 1: Automatically upgrades scope="call" to "async" for _async functions.
# Patch 2: Allows CLI-provided GIR files to override bundled ones.

"$PATCHED_JAVA_GI" -S -s "Imbric Native Bindings" \
    -d org.gnome \
    -o "$TEMP_GEN" \
    /usr/share/gir-1.0/GLib-2.0.gir \
    /usr/share/gir-1.0/GObject-2.0.gir \
    /usr/share/gir-1.0/Gio-2.0.gir \
    "${PROJECT_DIR}/gir/GdkPixbuf-2.0.gir"

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

echo "==> [5/5] Surgical Patching (GPid Pointer Bug)"
MO_FILE="$GEN_DIR/org/gnome/gio/MountOperation.java"
if [ -f "$MO_FILE" ]; then
    echo "    Patching MountOperation.java..."
    # Add import at line 20
    sed -i '20i import org.javagi.base.Alias;' "$MO_FILE"
    # Replace broken call using a more aggressive regex for mangled names
    sed -i 's/Pid\.get[a-zA-Z0-9.]*Values(processes)/Alias.getAddressValues(processes)/g' "$MO_FILE"
    # Adjust element size for pointers (4 bytes -> 8 bytes)
    sed -i 's/processes.length, 4)/processes.length, 8)/g' "$MO_FILE"
fi

# Cleanup
echo "    Removing module-info.java..."
find "$GEN_DIR" -name "module-info.java" -delete

echo "DONE: Bindings generated and patched successfully with the fix."
