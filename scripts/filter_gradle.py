#!/usr/bin/env python3
"""
filter_gradle.py — Filter Gradle test output.

Replaces PASSED lines with dots, prints FAILED lines with full stack traces,
and shows task progress. Gives a clean, concise overview of test runs.

Usage:
    ./gradlew test 2>&1 | python3 scripts/filter_gradle.py

    # Targeted test
    ./gradlew test --tests "ClassName" 2>&1 | python3 scripts/filter_gradle.py

    # Full suite with auto-continue
    ./gradlew test --continue 2>&1 | python3 scripts/filter_gradle.py
"""

import re
import sys

_PASSED = re.compile(r" > .* PASSED")
_TASK_START = re.compile(r"^> Task ")

_IMPORTANT = [
    re.compile(r"FAILED"),
    re.compile(r"error:"),
    re.compile(r"Exception"),
    re.compile(r"BUILD SUCCESSFUL"),
    re.compile(r"BUILD FAILED"),
    re.compile(r"^> Task :test"),
]

# Gradle noise — always suppressed, even inside error blocks
_GRADLE_NOISE = [
    re.compile(r"^Reusing configuration cache"),
    re.compile(r"^Configuration cache entry reused"),
    re.compile(r"^\d+ actionable tasks"),
    re.compile(r"^Downloading "),
    re.compile(r"^Welcome to Gradle"),
    re.compile(r"^Starting a Gradle Daemon"),
]


def filter_gradle() -> None:
    in_error: bool = False
    dot_count: int = 0

    for raw in sys.stdin:
        line: str = raw.rstrip()
        if not line:
            continue

        # Failure or important line → show full output immediately
        if any(p.search(line) for p in _IMPORTANT):
            if not in_error and dot_count > 0:
                print()
            print(line, flush=True)
            in_error = True
            continue

        # Passed test → single dot
        if _PASSED.search(line):
            print(".", end="", flush=True)
            dot_count += 1
            continue

        # Gradle noise → always suppress
        if any(p.search(line) for p in _GRADLE_NOISE):
            continue

        # Inside an error block → keep printing until next task boundary
        if in_error:
            if _TASK_START.match(line):
                in_error = False
                print(f"\n{line}", flush=True)
            else:
                print(line, flush=True)
            continue

        # Test task boundary → show as progress marker
        if _TASK_START.match(line) and ":test" in line:
            print(f"\n{line}", flush=True)
            continue

        # Non-test Gradle task line → suppress
        if _TASK_START.match(line):
            continue

        # Non-Gradle output (e.g. binding generation scripts) → pass through
        print(line, flush=True)


if __name__ == "__main__":
    filter_gradle()
