import re
import sys
from pathlib import Path
from ..daemon import PROJECT_ROOT

SKIP_NAMES = {
    "init", "equals", "hashCode", "toString",
    "component1", "component2", "component3", "component4", "component5",
}

_RE_DECL = re.compile(
    r"""
    ^\s*
    (?:(?:private|internal|protected|public|override|abstract|open|final|expect|actual|data|sealed|inline|suspend|operator|infix|tailrec|external|const|lateinit|inner|value|fun)\s+)*
    (?P<kind>fun|val|var|class|interface|object|enum\s+class)
    \s+
    (?:[a-zA-Z_]\w*\.)?                     # optional receiver type (extension fun/val)
    (?P<name>[a-zA-Z_]\w*)
    """,
    re.VERBOSE,
)

_RE_HAS_COMPANION = re.compile(r"\bcompanion\s+object\b")
_RE_HAS_FUN = re.compile(r"\bfun\b")
_RE_HAS_CLASS_KW = re.compile(r"\b(class|interface|object)\b")
_RE_HAS_BLOCK_KW = re.compile(r"\b(init|get|set)\b")

def _clean_source(text: str) -> str:
    pattern = re.compile(
        r"(/\*[\s\S]*?\*/)|(//.*$)|(\"\"\"[\s\S]*?\"\"\")|(\"([^\"\\]|\\.)*\")|('([^'\\]|\\.)*')",
        re.MULTILINE
    )
    def replace(match):
        item = match.group(0)
        if item.startswith("/*"):
            return re.sub(r"[^\n]", " ", item)
        elif item.startswith("//"):
            return ""
        elif item.startswith("\"\"\""):
            return '""' + re.sub(r"[^\n]", " ", item[3:-3]) + '""'
        elif item.startswith("\"") or item.startswith("'"):
            return '""'
        return item
    return pattern.sub(replace, text)

def extract_public_declarations(source_path: Path) -> set[str]:
    text = source_path.read_text(encoding="utf-8")
    text = _clean_source(text)

    declarations = set()
    scope_stack = [(False, "toplevel")]

    pending_kind = None
    pending_is_private = False
    paren_depth = 0

    def _current_private():
        return scope_stack[-1][0] if scope_stack else False

    def _current_kind():
        return scope_stack[-1][1] if scope_stack else "toplevel"

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        line_has_private = False
        m_decl = _RE_DECL.match(stripped)
        if m_decl:
            kind = m_decl.group("kind")
            before_keyword = stripped.split(kind)[0]
            before_keyword_stripped = re.sub(r"\(.*\)", "", before_keyword)
            line_has_private = bool(re.search(r"\b(private|internal)\b", before_keyword_stripped))

        if _RE_HAS_COMPANION.search(stripped):
            pending_kind = "companion"
            pending_is_private = line_has_private
        elif _RE_HAS_FUN.search(stripped) and not _RE_HAS_CLASS_KW.search(stripped):
            pending_kind = "fun"
            pending_is_private = line_has_private
        elif _RE_HAS_CLASS_KW.search(stripped):
            pending_kind = "class"
            pending_is_private = line_has_private

        m = _RE_DECL.match(stripped)
        if m:
            kind = m.group("kind")
            name = m.group("name")
            before_keyword = stripped.split(kind)[0]
            before_keyword_stripped = re.sub(r"\(.*\)", "", before_keyword)
            has_private_mod = bool(re.search(r"\b(private|internal)\b", before_keyword_stripped))
            in_private_scope = _current_private()

            if not in_private_scope and not has_private_mod:
                if name not in SKIP_NAMES:
                    if not re.search(r"\boverride\b", before_keyword):
                        current = _current_kind()
                        if kind == "fun" and current in ("toplevel", "class", "companion"):
                            declarations.add(name)
                        elif kind in ("val", "var") and current in ("toplevel", "class", "companion"):
                            declarations.add(name)
                        elif kind in ("class", "interface", "object", "enum class",
                                      "sealed class", "data class"):
                            declarations.add(name)

        for char in stripped:
            if char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth = max(0, paren_depth - 1)
            elif char == "{":
                if paren_depth > 0:
                    scope_stack.append((_current_private(), "lambda"))
                else:
                    if pending_kind is not None:
                        scope_stack.append((_current_private() or pending_is_private, pending_kind))
                        pending_kind = None
                        pending_is_private = False
                    else:
                        before_brace = stripped.split("{")[0] if "{" in stripped else stripped
                        before_brace_stripped = re.sub(r"\(.*\)", "", before_brace)
                        new_is_private = (
                            _current_private()
                            or bool(re.search(r"\b(private|internal)\b", before_brace_stripped))
                        )
                        if _RE_HAS_COMPANION.search(before_brace):
                            new_kind = "companion"
                        elif _RE_HAS_FUN.search(before_brace):
                            new_kind = "fun"
                        elif _RE_HAS_CLASS_KW.search(before_brace):
                            new_kind = "class"
                        elif _RE_HAS_BLOCK_KW.search(before_brace):
                            new_kind = "lambda"
                        else:
                            new_kind = _current_kind()
                            if new_kind == "toplevel":
                                new_kind = "lambda"
                        scope_stack.append((new_is_private, new_kind))
            elif char == "}":
                if len(scope_stack) > 1:
                    scope_stack.pop()

    return declarations

def _extract_audit_block(context_path: Path, filename: str) -> str | None:
    if not context_path.is_file():
        return None
    text = context_path.read_text(encoding="utf-8")
    marker = f"### [FILE: {filename}]"

    lines = text.splitlines()
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith(marker):
            start_idx = i
            break

    if start_idx is None:
        return None

    block_lines = []
    for line in lines[start_idx + 1:]:
        if line.strip().startswith("### [FILE:"):
            break
        block_lines.append(line)

    return "\n".join(block_lines).strip()

_SKIP_DOC_NAMES = {
    "API", "DNA", "Role", "SrcDeps", "SysDeps", "Caveat",
    "WIP", "TODO", "FIXME", "HACK", "XXX",
    "Stable", "Experimental", "Deprecated",
}

def _extract_documented_names(block: str) -> set[str]:
    names = set()
    for m in re.finditer(r"[-*]\s+(?:suspend\s+)?(?:fun|val|var)\s+([a-zA-Z_]\w*)", block):
        name = m.group(1)
        if name not in _SKIP_DOC_NAMES:
            names.add(name)

    for m in re.finditer(r"\b([a-zA-Z_]\w{2,})\b(?=\s*[/(]|\s+=>|\s*:)", block):
        name = m.group(1)
        if name not in _SKIP_DOC_NAMES:
            names.add(name)

    return names

def find_context_file(source_path: Path) -> Path | None:
    dir_path = source_path.parent
    dirname = dir_path.name
    
    # Check for {dirname}context.md
    ctx_file = dir_path / f"{dirname}context.md"
    if ctx_file.is_file():
        return ctx_file
        
    # Fallback: check for any *context.md in the directory
    for f in dir_path.glob("*context.md"):
        return f
        
    return None

def validate_file(source_path: Path, context_path: Path) -> tuple[set[str], set[str]]:
    src_decls = extract_public_declarations(source_path)
    block = _extract_audit_block(context_path, source_path.name)
    if block is None:
        return src_decls, set()
    ctx_decls = _extract_documented_names(block)
    missing = src_decls - ctx_decls
    return src_decls, missing

def register(subparsers):
    p = subparsers.add_parser("audit", help="Validate Kotlin public declarations against context audit blocks")
    p.add_argument("file", nargs="?", help="Specific Kotlin file to validate (scans all if omitted)")

def run(args):
    if args.file:
        source_path = Path(args.file).resolve()
        if not source_path.is_file():
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
            
        context_path = find_context_file(source_path)
        if not context_path:
            print(f"Error: No context file found for {source_path.name}", file=sys.stderr)
            sys.exit(1)
            
        src_decls, missing = validate_file(source_path, context_path)
        print(f"### Validation Results: {source_path.name} ###")
        if not missing:
            print("[✓] All public declarations are documented in the audit block.")
        else:
            print("[!] Declarations in source but missing from audit block:")
            for name in sorted(missing):
                print(f"  - {name}")
            print(f"\n({len(missing)} missing / {len(src_decls)} total public declarations)")
    else:
        print("Scanning codebase for Kotlin files and context files...")
        kt_files = list(PROJECT_ROOT.glob("src/**/*.kt"))
        
        total_files = 0
        total_missing = 0
        
        for kt_file in sorted(kt_files):
            context_path = find_context_file(kt_file)
            if not context_path:
                continue
                
            src_decls, missing = validate_file(kt_file, context_path)
            if missing:
                total_files += 1
                total_missing += len(missing)
                print(f"\n[!] {kt_file.relative_to(PROJECT_ROOT)}:")
                for name in sorted(missing):
                    print(f"  - {name}")
                    
        if total_files == 0:
            print("\n[✓] All public declarations across the codebase are fully documented!")
        else:
            print(f"\nFound {total_missing} missing declarations across {total_files} files.")
