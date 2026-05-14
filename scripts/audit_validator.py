#!/usr/bin/env python3
"""
audit_validator.py — Kotlin Audit Block Validator

Usage:
    python3 scripts/audit_validator.py <source.kt> <context.md>

Logic: Isolates the specific file's audit block from a context.md and detects
public declarations in the Kotlin source that are missing from the block.

Python counterpart to audit_validator.sh, with brace-depth visibility tracking
for Kotlin (no more fragile grep one-liners).
"""

import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# 1. Kotlin Declaration Extraction (line-by-line state machine)
# ---------------------------------------------------------------------------

# Declarations in these well-known sets are always excluded (auto-generated or
# universal overrides that no audit block should list).
# Auto-generated names to exclude (data class componentN, JVM overrides).
# We do NOT filter `copy`, `invoke`, `get`, `set` — these are valid
# user-defined function names in many Kotlin interfaces and classes.
SKIP_NAMES = {
    "init", "equals", "hashCode", "toString",
    "component1", "component2", "component3", "component4", "component5",
}

# Regex:  optional modifiers → keyword → name
_RE_DECL = re.compile(
    r"""
    ^\s*
    (?:(?:private|internal|protected|public|override|abstract|open|final|expect|actual|data|sealed|inline|suspend|operator|infix|tailrec|external|const|lateinit)\s+)*
    (?P<kind>fun|val|var|class|interface|object|enum\s+class)
    \s+
    (?:[a-zA-Z_]\w*\.)?                     # optional receiver type (extension fun/val)
    (?P<name>[a-zA-Z_]\w*)
    """,
    re.VERBOSE,
)

# Regex to detect a private/internal modifier on a line (before any other token).
_RE_PRIVATE = re.compile(r"^\s*(private|internal)\s+")

# Quick tests for what kind of scope a `{` opens.
_RE_HAS_FUN = re.compile(r"\bfun\b")
_RE_HAS_COMPANION = re.compile(r"\bcompanion\s+object\b")
_RE_HAS_CLASS_KW = re.compile(r"\b(class|interface|object)\b")

# Lines that open a block scope but are NOT class/interface/object bodies.
# Inside these, val/var are local variables, not member properties.
_RE_HAS_BLOCK_KW = re.compile(r"\b(init|get|set)\b")


def _strip_comments(text: str) -> str:
    """Remove // and /* */ comments from Kotlin source.

    Block comments are stripped FIRST because KDoc / Javadoc lines often
    contain ``//`` inside URLs (e.g. ``smb://server/file``).  If we stripped
    single-line comments first, the ``//`` would match and eat the closing
    ``*/`` of the block comment.
    """
    # 1. Block comments (non-greedy; does NOT handle nesting — fine for a
    #    documentation validator where we only need shallow stripping).
    while "/*" in text:
        start = text.index("/*")
        end = text.index("*/", start + 2)
        if end == -1:
            break  # unclosed block comment — stop to avoid infinite loop
        text = text[:start] + text[end + 2:]

    # 2. Single-line comments
    text = re.sub(r"//.*$", "", text, flags=re.MULTILINE)
    return text


def extract_public_declarations(source_path: str) -> set[str]:
    """
    Return the set of public declaration names found in a Kotlin source file.

    Uses a scope-kind state machine that tracks what each brace-enclosed
    region represents:

      Scope kinds:
        toplevel   — file-level (depth 0, no enclosing braces)
        class      — class / interface / object / enum body
        companion  — companion object body
        fun        — function / method body
        lambda     — lambda / init / property-getter / other block

    Visibility rules:
    - A `private`/`internal` modifier on the same line as a declaration
      excludes it.
    - If a class/object is declared private, everything inside is private.

    Extraction rules per declaration kind:
      fun  — extracted inside toplevel, class, companion scopes
             (skipped inside fun/lambda — local functions)
      val/var — extracted inside toplevel, class, companion scopes
             (skipped inside fun/lambda — local variables)
      class/interface/object/enum/sealed/data — extracted everywhere
             (nested classes are always public API)
    """
    text = Path(source_path).read_text(encoding="utf-8")
    text = _strip_comments(text)

    declarations: set[str] = set()
    scope_stack: list[tuple[bool, str]] = [(False, "toplevel")]

    # Pending scope kind for multi-line declarations where `{` is on a
    # different line from the keyword (e.g. `class Foo(\n...\n) {` or
    # `fun foo(\n...\n) {`).  Reset when a structural `{` is consumed.
    pending_kind: str | None = None

    def _current_private() -> bool:
        return scope_stack[-1][0] if scope_stack else False

    def _current_kind() -> str:
        return scope_stack[-1][1] if scope_stack else "toplevel"

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # --- Detect multi-line declaration keywords -----------------------
        # Must be checked BEFORE brace counting — a `fun` keyword on this
        # line may be a multi-line function whose body `{` appears later.
        if _RE_HAS_COMPANION.search(stripped):
            pending_kind = "companion"
        elif _RE_HAS_FUN.search(stripped) and not _RE_HAS_CLASS_KW.search(stripped):
            pending_kind = "fun"
        elif _RE_HAS_CLASS_KW.search(stripped):
            pending_kind = "class"

        opens = stripped.count("{")
        closes = stripped.count("}")

        # --- Net depth change --------------------------------------------
        net = opens - closes

        if net < 0:
            for _ in range(-net):
                if len(scope_stack) > 1:
                    scope_stack.pop()

        # --- effective visibility for THIS line ----------------------------
        in_private_scope = _current_private()
        has_private_mod = bool(_RE_PRIVATE.match(stripped))

        # --- extract declarations -----------------------------------------
        if not in_private_scope and not has_private_mod:
            m = _RE_DECL.match(stripped)
            if m:
                kind = m.group("kind")
                name = m.group("name")
                if name in SKIP_NAMES:
                    continue

                current = _current_kind()
                if kind == "fun" and current in ("toplevel", "class", "companion"):
                    declarations.add(name)
                elif kind in ("val", "var") and current in ("toplevel", "class", "companion"):
                    declarations.add(name)
                elif kind in ("class", "interface", "object", "enum class",
                              "sealed class", "data class"):
                    declarations.add(name)

        # --- push scopes for net-opening braces ---------------------------
        if net > 0:
            before_brace = stripped.split("{")[0] if "{" in stripped else stripped

            new_is_private = (
                _current_private()
                or bool(re.search(r"\b(private|internal)\b", before_brace))
            )

            # Scope kind: prefer pending_kind (for multi-line decls), then
            # keyword on the current line, otherwise inherit from parent.
            if pending_kind is not None:
                new_kind = pending_kind
                pending_kind = None  # consumed
            elif _RE_HAS_COMPANION.search(before_brace):
                new_kind = "companion"
            elif _RE_HAS_FUN.search(before_brace):
                new_kind = "fun"
            elif _RE_HAS_CLASS_KW.search(before_brace):
                new_kind = "class"
            elif _RE_HAS_BLOCK_KW.search(before_brace):
                # init / get / set blocks — treat as function-like scopes
                # where val/var are local variables, not member properties.
                new_kind = "lambda"
            else:
                new_kind = _current_kind()
                # toplevel never gets bare blocks
                if new_kind == "toplevel":
                    new_kind = "lambda"

            for _ in range(net):
                scope_stack.append((new_is_private, new_kind))

    return declarations


# ---------------------------------------------------------------------------
# 2. Context Markdown Parsing
# ---------------------------------------------------------------------------

def _extract_audit_block(context_path: str, filename: str) -> str | None:
    """
    Isolate the audit block for *filename* from the context markdown file.
    Returns the raw text of the block, or None if not found.
    """
    text = Path(context_path).read_text(encoding="utf-8")
    marker = f"### [FILE: {filename}]"

    # Find the file's marker
    lines = text.splitlines()
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith(marker):
            start_idx = i
            break

    if start_idx is None:
        return None

    # Collect lines until the next `### [FILE:` marker (or end of file)
    block_lines = []
    for line in lines[start_idx + 1:]:
        if line.strip().startswith("### [FILE:"):
            break
        block_lines.append(line)

    return "\n".join(block_lines).strip()


# Keywords that appear in context.md structure but are NOT declaration names.
# These come from the markdown schema (Role, /DNA/, API headers, dependency
# annotations) and should be excluded from the documented-name set.
_SKIP_DOC_NAMES = {
    "API", "DNA", "Role", "SrcDeps", "SysDeps", "Caveat",
    "WIP", "TODO", "FIXME", "HACK", "XXX",
    "Stable", "Experimental", "Deprecated",
}


def _extract_documented_names(block: str) -> set[str]:
    """
    Extract declaration-like names from an audit block.

    Recognises:
    - `- fun name(` / `fun name(`   in API sections
    - `- val name` / `- var name`
    - identifiers followed by `(`, `/`, `=>`, or `:`  (the bash-compatible
      delimiter pattern).

    Returns a set of names found.
    """
    names: set[str] = set()

    # 1. Explicit `- fun/val/var name` patterns (most reliable, no skip check)
    for m in re.finditer(r"[-*]\s+(?:suspend\s+)?(?:fun|val|var)\s+([a-zA-Z_]\w*)", block):
        name = m.group(1)
        if name not in _SKIP_DOC_NAMES:
            names.add(name)

    # 2. Backward-compatible delimiter pattern (mirrors bash grep)
    for m in re.finditer(r"\b([a-zA-Z_]\w{2,})\b(?=\s*[/(]|\s+=>|\s*:)", block):
        name = m.group(1)
        if name not in _SKIP_DOC_NAMES:
            names.add(name)

    return names


# ---------------------------------------------------------------------------
# 3. Main
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python3 scripts/audit_validator.py <source.kt> <context.md>")
        sys.exit(1)

    src_path = sys.argv[1]
    ctx_path = sys.argv[2]
    filename = Path(src_path).name

    for p in (src_path, ctx_path):
        if not Path(p).is_file():
            print(f"Error: {p} not found.", file=sys.stderr)
            sys.exit(1)

    # Extract from source
    src_decls = extract_public_declarations(src_path)

    # Extract from context
    block = _extract_audit_block(ctx_path, filename)
    if block is None:
        print(f"Error: Could not isolate audit block for {filename} in {ctx_path}.",
              file=sys.stderr)
        sys.exit(1)

    ctx_decls = _extract_documented_names(block)

    # Compare
    missing = src_decls - ctx_decls
    print(f"### Validation Results: {filename} ###")

    if not missing:
        print("[✓] All public declarations are documented in the audit block.")
    else:
        print("[!] Declarations in source but missing from audit block:")
        for name in sorted(missing):
            print(f"  - {name}")
        print()
        print(f"({len(missing)} missing / {len(src_decls)} total public declarations)")


if __name__ == "__main__":
    main()
