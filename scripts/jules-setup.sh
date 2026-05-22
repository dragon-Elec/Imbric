#!/bin/bash
# jules-setup.sh — Environment setup for Jules bot (Google's AI coding agent)
#
# Jules runs in a sandboxed Ubuntu VM with:
#   - JDK 21 pre-installed (we need 25)
#   - Gradle 8.8 on PATH (we need 9.5.1 via wrapper)
#   - Network: GitHub/Maven OK, services.gradle.org may be slow
#
# This script is designed to be pasted into the Jules UI
# (Configuration → Initial Setup) and then "Run and Snapshot".
#
# It handles:
#   1. JDK 25 installation
#   2. Building the patched java-gi generator from the submodule
#   3. Generating GNOME 46 bindings
#   4. Compiling the project

set -e

# --- JDK 25 ---
sudo apt-get update -qq
sudo apt-get install -y -qq openjdk-25-jdk
export JAVA_HOME=/usr/lib/jvm/java-25-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH

# --- Build patched java-gi generator ---
# The submodule has its own Gradle wrapper (9.4.1).
# If services.gradle.org is slow, increase the timeout first.
WRAPPER_PROPS="ref/java-gi_patched/gradle/wrapper/gradle-wrapper.properties"
if [ -f "$WRAPPER_PROPS" ]; then
    sed -i 's/networkTimeout=10000/networkTimeout=120000/' "$WRAPPER_PROPS"
fi
cd ref/java-gi_patched && ./gradlew installDist --quiet && cd ../..

# --- Generate bindings ---
./scripts/generate_bindings.sh

# --- Verify compilation ---
./gradlew compileKotlin --quiet

# --- Clean working tree (Jules rejects dirty state) ---
git checkout -- ref/java-gi_patched

echo "==> Jules setup complete."
