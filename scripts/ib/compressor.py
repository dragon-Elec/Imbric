import re
from collections import defaultdict
from pathlib import Path

# Compute project root without circular import dependency
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ROOT_STR = str(PROJECT_ROOT)

# Match Kotlin compiler diagnostics: w: / e: file:///path/to/File.kt:123:45 Message
_DIAG_PATTERN = re.compile(
    r"^(?:([we]):\s+)?(?:file://)?(.*?):(\d+)(?::(\d+))?\s*(.*)$"
)

# Match GLib / GIO C-level native warnings: (com.imbric:12345): GLib-GIO-CRITICAL **: message
_GLIB_PATTERN = re.compile(
    r"^(?:\([^)]+\):\s+)?(GLib(?:-[A-Za-z0-9]+)?-[A-Za-z]+)\s+\*\*:\s+(.*)$"
)

# Match [PIPELINE] log lines: [PIPELINE] 135ms (ui_click=+0ms -> gio_list_done=+134ms [990] -> ui_rendered=+245ms)
_PIPELINE_PATTERN = re.compile(
    r"^\[PIPELINE\]\s+(\d+ms)\s+\((.*?)\)$"
)

# Common noisy framework packages in JVM stack traces
_FRAMEWORK_FRAMES = (
    "org.gradle.",
    "worker.org.gradle.",
    "org.jetbrains.kotlin.compilerRunner.",
    "jdk.internal.",
    "java.lang.reflect.",
    "java.base/java.lang.reflect.",
    "java.base/jdk.internal.",
    "kotlinx.coroutines.internal.",
    "sun.reflect.",
    "org.junit.",
    "org.opentest4j.",
)

def clean_path(filepath: str) -> str:
    """Strips file:// and project root prefixes to produce a clean relative path."""
    if not filepath:
        return ""
    p = filepath.strip()
    if p.startswith("file://"):
        p = p[len("file://"):]
    if p.startswith(_ROOT_STR):
        p = p[len(_ROOT_STR):].lstrip("/")
    return p

def compress_warnings(warning_lines: list[str]) -> str:
    """
    Compresses Kotlin compiler warnings:
    - Strips long absolute paths.
    - Groups warnings by file.
    - Merges identical messages within the same file: 'L103, L117, L167 (3x): ...'
    """
    if not warning_lines:
        return ""

    grouped: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    unparsed: list[str] = []

    for raw in warning_lines:
        line = raw.strip()
        if not line:
            continue

        match = _DIAG_PATTERN.match(line)
        if match:
            kind, filepath, lineno, col, msg = match.groups()
            rel_path = clean_path(filepath)
            msg = msg.strip() if msg else "(no message)"
            grouped[rel_path][msg].append(lineno)
        else:
            unparsed.append(line)

    output: list[str] = []
    for filepath, messages in sorted(grouped.items()):
        output.append(f"\n  📁 {filepath}")
        for msg, lines in sorted(messages.items(), key=lambda x: int(x[1][0]) if x[1][0].isdigit() else 0):
            if len(lines) == 1:
                output.append(f"     • L{lines[0]}: {msg}")
            else:
                line_str = ", ".join(f"L{l}" for l in lines)
                output.append(f"     • {line_str} ({len(lines)}x): {msg}")

    if unparsed:
        output.append("\n  [Other Warnings / Unparsed]")
        for u in unparsed:
            output.append(f"     • {u}")

    return "\n".join(output)

def compress_errors(error_lines: list[str]) -> str:
    """
    Compresses Kotlin compiler errors by file with clear line pointers.
    Passes through unparsed errors safely.
    """
    if not error_lines:
        return ""

    grouped: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    unparsed: list[str] = []

    for raw in error_lines:
        line = raw.strip()
        if not line:
            continue

        match = _DIAG_PATTERN.match(line)
        if match and match.group(1) == 'e':
            kind, filepath, lineno, col, msg = match.groups()
            rel_path = clean_path(filepath)
            grouped[rel_path].append((lineno, col or "", msg.strip()))
        else:
            unparsed.append(line)

    output: list[str] = []
    for filepath, errs in sorted(grouped.items()):
        output.append(f"\n  ❌ {filepath}")
        for lineno, col, msg in errs:
            pos = f"L{lineno}:{col}" if col else f"L{lineno}"
            output.append(f"     • {pos}: {msg}")

    if unparsed:
        output.append("\n  [Unparsed Errors]")
        for u in unparsed:
            output.append(f"  • {u}")

    return "\n".join(output)

def compress_stacktrace(trace_lines: list[str], max_app_frames: int = 15) -> str:
    """
    Compresses JVM stacktraces:
    - Retains app/project frames (`com.imbric.*`).
    - Collapses consecutive internal framework frames (`org.gradle`, `jdk.internal`, etc.)
      into a single summary count: '[... 18 internal framework frames skipped ...]'.
    """
    if not trace_lines:
        return ""

    output: list[str] = []
    skipped_framework_count = 0
    app_frame_count = 0

    for line in trace_lines:
        trimmed = line.strip()
        if not trimmed.startswith("at "):
            if skipped_framework_count > 0:
                output.append(f"        [... {skipped_framework_count} internal framework frames skipped ...]")
                skipped_framework_count = 0
            output.append(line)
            continue

        frame_content = trimmed[3:]
        is_framework = any(frame_content.startswith(fw) for fw in _FRAMEWORK_FRAMES)

        if is_framework:
            skipped_framework_count += 1
        else:
            if skipped_framework_count > 0:
                output.append(f"        [... {skipped_framework_count} internal framework frames skipped ...]")
                skipped_framework_count = 0
            if app_frame_count < max_app_frames:
                output.append(line)
                app_frame_count += 1
            elif app_frame_count == max_app_frames:
                output.append("        [... additional app frames omitted ...]")
                app_frame_count += 1

    if skipped_framework_count > 0:
        output.append(f"        [... {skipped_framework_count} internal framework frames skipped ...]")

    return "\n".join(output)

def compress_glib_warnings(glib_lines: list[str]) -> str:
    """
    Compresses repetitive C/FFI GLib/GIO native warnings:
    - Deduplicates repeated native messages (e.g. 500 identical byte-string critical warnings).
    - Summarizes with occurrence count: '[GLib-GIO-CRITICAL] (500x) g_file_info_...'.
    """
    if not glib_lines:
        return ""

    counts: dict[tuple[str, str], int] = defaultdict(int)
    unparsed: list[str] = []

    for raw in glib_lines:
        line = raw.strip()
        if not line:
            continue
        match = _GLIB_PATTERN.match(line)
        if match:
            level, msg = match.groups()
            counts[(level, msg.strip())] += 1
        else:
            unparsed.append(line)

    output: list[str] = []
    for (level, msg), count in sorted(counts.items(), key=lambda x: -x[1]):
        count_str = f"({count}x) " if count > 1 else ""
        output.append(f"  ⚠️ [{level}] {count_str}{msg}".rstrip())

    if unparsed:
        for u in unparsed:
            output.append(f"  ⚠️ {u}")

    return "\n".join(output)

def format_pipeline_timer(pipeline_line: str) -> str:
    """
    Formats [PIPELINE] log lines into clean, readable steps:
    [PIPELINE] 135ms total
      1. ui_click (+0ms)
      2. gio_list_done (+134ms) [990 items]
      3. ui_rendered (+245ms)
    """
    line = pipeline_line.strip()
    match = _PIPELINE_PATTERN.match(line)
    if not match:
        return line

    total_time, chain = match.groups()
    steps = [s.strip() for s in chain.split("→") if s.strip()]
    if len(steps) <= 1:
        # try ascii arrow
        steps = [s.strip() for s in chain.split("->") if s.strip()]

    output = [f"\n⏱️  [PIPELINE TIMELINE] Total: {total_time}"]
    for idx, step in enumerate(steps, 1):
        output.append(f"   {idx}. {step}")
    return "\n".join(output)
