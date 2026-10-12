#!/usr/bin/env python3
"""Detect Kotlin imports whose simple name never appears in the file body.

Replaces the old `grep -r "import.*unused"` check, which matched nothing in any
real Kotlin file and therefore reported "no unused imports" unconditionally.

An import is reported when its simple name occurs exactly once in the file — at
the import line itself. Wildcard and alias imports are skipped (a wildcard has no
simple name; an alias binds a different one). `*` in the path glob is handled by
simple name only, so a name used only inside a string or comment still counts as
used — this is a lint hint, not a compiler.

Exit codes: 0 = ran (stdout lists findings, possibly empty), 2 = could not run.
"""
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SRC = PROJECT_ROOT / "src" / "main" / "kotlin"

_IMPORT_RE = re.compile(r"^\s*import\s+([\w.]+(?:\.\*)?)(?:\s+as\s+(\w+))?\s*$")

# Kotlin's operator convention: these are invoked implicitly by the compiler and
# are therefore never referenced by name. `import kotlin.reflect.KProperty.getValue`
# exists solely so `val x by ...` compiles — the symbol never appears in the body,
# so a naive "name must appear again" check reports it unused and deleting it
# breaks the build. Same for every operator overload below.
_OPERATOR_NAMES = frozenset({
    "getValue", "setValue", "provideDelegate",
    "iterator", "next", "hasNext", "nextInt", "nextLong",
    "compareTo", "equals", "hashCode", "toString",
    "plus", "minus", "times", "div", "rem", "mod",
    "unaryPlus", "unaryMinus", "not", "inc", "dec",
    "rangeTo", "rangeUntil", "contains", "get", "set",
    "invoke", "and", "or", "xor", "inv", "shl", "shr", "ushr",
    "component1", "component2", "component3", "component4", "component5",
})


def unused_in(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    imports: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = _IMPORT_RE.match(line)
        if not m:
            continue
        fqn, alias = m.groups()
        if fqn.endswith(".*"):
            continue  # wildcard: imports many names, none is individually unused
        name = alias or fqn.rsplit(".", 1)[-1]
        if name in _OPERATOR_NAMES:
            continue  # resolved implicitly by the compiler, never by name
        imports.append((i, name))

    body = "\n".join(line for i, line in enumerate(lines)
                     if not _IMPORT_RE.match(line))

    return [f"{path.relative_to(PROJECT_ROOT)}:{i + 1}: unused import '{name}'"
            for i, name in imports if not re.search(rf"\b{re.escape(name)}\b", body)]


def main() -> int:
    if not SRC.is_dir():
        print(f"missing source dir: {SRC}", file=sys.stderr)
        return 2
    for kt in sorted(SRC.rglob("*.kt")):
        for finding in unused_in(kt):
            print(finding)
    return 0


if __name__ == "__main__":
    sys.exit(main())