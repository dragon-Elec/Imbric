#!/bin/bash
set -e

# Configuration
VERSION="0.15.0"
PROJECT_DIR="/home/ray/Desktop/files/wrk/Imbric/imbric-kt"
TOOL_DIR="${PROJECT_DIR}/build/native-gen/tools"
GEN_DIR="${PROJECT_DIR}/build/native-gen/bindings"
TEMP_GEN="${PROJECT_DIR}/build/native-gen/temp_raw"

echo "==> [1/5] Infrastructure Setup"
mkdir -p "$TOOL_DIR"
mkdir -p "$GEN_DIR"
rm -rf "$GEN_DIR"/*
rm -rf "$TEMP_GEN"

# Download Tooling
if [ ! -f "${TOOL_DIR}/java-gi-${VERSION}.zip" ]; then
    echo "    Downloading java-gi ${VERSION}..."
    wget -q -O "${TOOL_DIR}/java-gi-${VERSION}.zip" "https://codeberg.org/java-gi/java-gi/releases/download/${VERSION}/java-gi-${VERSION}.zip"
    unzip -q -o "${TOOL_DIR}/java-gi-${VERSION}.zip" -d "$TOOL_DIR"
fi

# Download Foundation Sources
if [ ! -f "${TOOL_DIR}/glib-${VERSION}-sources.jar" ]; then
    echo "    Fetching official sources from Maven Central..."
    wget -q -O "${TOOL_DIR}/glib-${VERSION}-sources.jar" "https://repo.maven.apache.org/maven2/org/java-gi/glib/${VERSION}/glib-${VERSION}-sources.jar"
fi

echo "==> [2/5] Extracting Stable Foundation & Hand-written types"
# Extract core logic that never changes
unzip -q -o "${TOOL_DIR}/glib-${VERSION}-sources.jar" "org/javagi/*" -d "$GEN_DIR"
unzip -q -o "${TOOL_DIR}/glib-${VERSION}-sources.jar" "org/gnome/glib/List.java" -d "$GEN_DIR"
unzip -q -o "${TOOL_DIR}/glib-${VERSION}-sources.jar" "org/gnome/glib/SList.java" -d "$GEN_DIR"
unzip -q -o "${TOOL_DIR}/glib-${VERSION}-sources.jar" "org/gnome/glib/HashTable.java" -d "$GEN_DIR"
unzip -q -o "${TOOL_DIR}/glib-${VERSION}-sources.jar" "org/gnome/glib/ByteArray.java" -d "$GEN_DIR"

echo "==> [3/5] Generating Native GNOME 46 Bindings"
mkdir -p "$TEMP_GEN"
"${TOOL_DIR}/java-gi-${VERSION}/bin/java-gi" -S -s "Imbric Native Bindings" \
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
# Patch MountOperation.java:
# 1. Add missing Alias import
# 2. Change broken Pid.get...Values -> Alias.getAddressValues
# 3. Change hardcoded size 4 -> 8 (Pointer size on 64-bit)
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

echo "DONE: Bindings generated and patched successfully."
