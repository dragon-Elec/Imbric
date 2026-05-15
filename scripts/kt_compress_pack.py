#!/usr/bin/env python3
"""
kt_compress_pack.py — Post-processor for Repomix packs.

Reads a Repomix JSON pack, compresses all .kt files inside it using tree-sitter,
and outputs the final result as an AI-optimized XML pack.

Usage:
    repomix --style json -o raw-pack.json [your flags...]
    python3 scripts/kt_compress_pack.py raw-pack.json final-pack.xml
"""

import argparse
import ctypes
import json
import os
import re
import sys
import warnings
from pathlib import Path
from tree_sitter import Language, Parser, Node

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GRAMMAR = PROJECT_ROOT / "languages" / "tree-sitter-kotlin" / "build" / "libtree-sitter-kotlin.so"

BODY_TYPES = {"function_body", "anonymous_initializer"}
ACCESSOR_TYPES = {"getter", "setter"}
MARKER = b" \u22ee--- "

def load_language(so_path: str) -> Language:
    if not os.path.isfile(so_path):
        print(f"Grammar not found: {so_path}", file=sys.stderr)
        sys.exit(1)
    lib = ctypes.CDLL(so_path)
    lib.tree_sitter_kotlin.restype = ctypes.c_void_p
    ptr = lib.tree_sitter_kotlin()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return Language(ptr)

def collect_bodies(node: Node, acc: list[Node]) -> None:
    if node.type in BODY_TYPES:
        acc.append(node)
        return
    if node.type in ACCESSOR_TYPES:
        for child in node.children:
            if child.type in BODY_TYPES:
                acc.append(child)
        return
    for child in node.children:
        collect_bodies(child, acc)

def compress_source(source: str, parser: Parser) -> str:
    encoded = source.encode("utf-8")
    tree = parser.parse(encoded)

    bodies: list[Node] = []
    collect_bodies(tree.root_node, bodies)
    if not bodies:
        return source

    bodies.sort(key=lambda n: n.start_byte, reverse=True)
    buf = bytearray(encoded)

    for body in bodies:
        start = body.start_byte
        end = body.end_byte
        if start >= end:
            continue

        body_bytes = body.text
        if body_bytes is None:
            continue

        if len(body_bytes) < 100 and b"\n" not in body_bytes:
            continue

        if body_bytes.startswith(b"{") and b"}" in body_bytes:
            brace_open = 0
            brace_close = body_bytes.rstrip().rfind(b"}")
            if brace_close > brace_open:
                interior_start = start + brace_open + 1
                interior_end = start + brace_close
                buf[interior_start:interior_end] = MARKER

    return buf.decode("utf-8")

def json_to_xml(data: dict) -> str:
    lines = []
    if "fileSummary" in data:
        summary = data["fileSummary"]
        if "generationHeader" in summary:
            lines.append(summary["generationHeader"])
            lines.append("")
        lines.append("<file_summary>")
        lines.append("This section contains a summary of this file.\n")
        for k, v in summary.items():
            if k == "generationHeader": continue
            tag = re.sub(r'(?<!^)(?=[A-Z])', '_', k).lower()
            lines.append(f"<{tag}>\n{v}\n</{tag}>\n")
        lines.append("</file_summary>\n")
    
    if "directoryStructure" in data:
        lines.append("<directory_structure>")
        lines.append(data["directoryStructure"])
        lines.append("</directory_structure>\n")
        
    if "files" in data:
        lines.append("<files>")
        for path, content in data["files"].items():
            lines.append(f'<file path="{path}">\n{content}\n</file>')
        lines.append("</files>\n")
        
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser(description="Post-process Repomix JSON pack to compress Kotlin files")
    ap.add_argument("input_json", type=str)
    ap.add_argument("output_xml", type=str)
    ap.add_argument("--grammar", type=str, default=str(DEFAULT_GRAMMAR))
    args = ap.parse_args()

    print(f"Loading grammar: {args.grammar}")
    lang = load_language(args.grammar)
    parser = Parser()
    parser.language = lang

    print(f"Reading {args.input_json}...")
    with open(args.input_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    files = data.get("files", {})
    kt_count = 0
    saved_bytes = 0

    for path, content in files.items():
        if path.endswith(".kt"):
            original_len = len(content.encode("utf-8"))
            compressed = compress_source(content, parser)
            new_len = len(compressed.encode("utf-8"))
            
            if new_len < original_len:
                files[path] = compressed
                kt_count += 1
                saved_bytes += (original_len - new_len)

    print(f"Compressed {kt_count} Kotlin files. Saved {saved_bytes:,} bytes.")
    
    print(f"Writing {args.output_xml}...")
    xml_out = json_to_xml(data)
    with open(args.output_xml, "w", encoding="utf-8") as f:
        f.write(xml_out)
    print("Done.")

if __name__ == "__main__":
    main()
