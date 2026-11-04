#!/usr/bin/env python3
"""Find exported/public symbols that no test file references.

Heuristic, read-only, stdlib-only. It maps source files to their likely test
files by path convention, then lists the public symbols of each source file
that no test file mentions.

    python3 -I find_untested.py src tests
    python3 -I find_untested.py src tests --json
    python3 -I find_untested.py src tests --all    # include covered symbols

Test files are looked up both in the test directory and next to the source
they test, so Go and Rust repositories with colocated tests are handled.

Supported languages for symbol extraction: Python, JavaScript/TypeScript, Go,
Rust, Ruby, Java, Kotlin. Other languages are scanned for test files only.

A symbol counts as covered when its name appears, as a whole identifier, in
any file inside the test directory. That is a hint, not a proof: dynamic
dispatch, `getattr`, re-exports and reflection can hide a real call. Treat the
output as a shortlist to read, never as a coverage number.

Exit code is 0 even when gaps are found; it reports, it does not judge.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".gradle",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "__pycache__",
    "coverage",
    "dist",
    "build",
    "htmlcov",
    "node_modules",
    "obj",
    "out",
    "target",
    "vendor",
    "venv",
    ".venv",
}

# Path components that carry no identity: "src/pkg/calc.py" and
# "tests/pkg/test_calc.py" must end up with the same key.
NOISE_COMPONENTS = {
    "app",
    "java",
    "kotlin",
    "lib",
    "libs",
    "main",
    "packages",
    "pkg",
    "resources",
    "spec",
    "specs",
    "src",
    "test",
    "tests",
    "testing",
    "__tests__",
}

TEST_DIR_NAMES = {"test", "tests", "spec", "specs", "__tests__", "testing", "it", "e2e"}

LANG_BY_EXT = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
}

IDENT_CHARS = r"A-Za-z0-9_$"


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------


def is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def looks_like_test(path: Path) -> bool:
    name = path.name
    stem = path.stem
    if stem.startswith(("test_", "test-")) or stem.endswith(("_test", "_spec")):
        return True
    if re.search(r"\.(test|spec)\.", name):
        return True
    if re.search(r"(Test|Tests|Spec)$", stem):
        return True
    if TEST_DIR_NAMES.intersection(path.parts[:-1]):
        return True
    return False


def walk_files(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if is_skipped(path):
            continue
        yield path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# --------------------------------------------------------------------------
# path keys
# --------------------------------------------------------------------------


def strip_test_markers(stem: str) -> str:
    stem = stem.split(".")[0]
    stem = re.sub(r"^test[-_]", "", stem)
    stem = re.sub(r"^(Test|SPEC)", "", stem)
    stem = re.sub(r"_(test|spec)$", "", stem)
    stem = re.sub(r"(Test|Tests|Spec)$", "", stem)
    return stem


def path_key(path: Path, *, is_test: bool) -> str:
    parts = [part for part in path.parts[:-1] if part not in NOISE_COMPONENTS]
    stem = strip_test_markers(path.stem) if is_test else path.stem
    return "/".join([*parts, stem]).lower()


# --------------------------------------------------------------------------
# symbol extraction
# --------------------------------------------------------------------------


def python_symbols(text: str):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    found = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                found.append((node.name, "function", node.lineno))
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                found.append((node.name, "class", node.lineno))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    if not target.id.startswith("_"):
                        found.append((target.id, "constant", node.lineno))
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id.isupper():
                if not target.id.startswith("_"):
                    found.append((target.id, "constant", node.lineno))
    return found


JS_PATTERNS = (
    (re.compile(r"^export\s+default\s+(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)", re.M), "function"),
    (re.compile(r"^export\s+(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)", re.M), "function"),
    (re.compile(r"^export\s+(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)", re.M), "class"),
    (re.compile(r"^export\s+(?:const|let|var)\s+([A-Za-z_$][\w$]*)", re.M), "value"),
    (re.compile(r"^export\s+(?:interface|type|enum)\s+([A-Za-z_$][\w$]*)", re.M), "type"),
    (re.compile(r"^export\s+default\s+class\s+([A-Za-z_$][\w$]*)", re.M), "class"),
)

GO_PATTERNS = (
    (re.compile(r"^func\s+([A-Za-z_]\w*)\s*[\(\[]", re.M), "function"),
    (re.compile(r"^func\s+\([^)]*\)\s+([A-Za-z_]\w*)\s*\(", re.M), "method"),
    (re.compile(r"^type\s+([A-Za-z_]\w*)\s+(struct|interface)\b", re.M), "type"),
)

RUST_PATTERNS = (
    (re.compile(r"^\s*pub\s+(?:async\s+)?(?:unsafe\s+)?(?:extern\s+\"[^\"]*\"\s+)?fn\s+([A-Za-z_]\w*)", re.M), "function"),
    (re.compile(r"^\s*pub\s+(?:struct|enum|trait|union)\s+([A-Za-z_]\w*)", re.M), "type"),
    (re.compile(r"^\s*pub\s+(?:const|static)\s+([A-Za-z_]\w*)", re.M), "constant"),
    (re.compile(r"^\s*pub\s+mod\s+([A-Za-z_]\w*)", re.M), "module"),
)

RUBY_PATTERNS = (
    (re.compile(r"^\s*def\s+(?:self\.)?([A-Za-z_]\w*[?!=]?)", re.M), "method"),
    (re.compile(r"^\s*class\s+([A-Z]\w*)", re.M), "class"),
    (re.compile(r"^\s*module\s+([A-Z]\w*)", re.M), "module"),
)

JAVA_PATTERNS = (
    (re.compile(r"^\s*public\s+(?:final\s+|abstract\s+|static\s+)*(?:class|interface|enum|record)\s+([A-Za-z_]\w*)", re.M), "type"),
    (re.compile(r"^\s*public\s+(?:static\s+)?(?:final\s+)?[\w<>\[\],.?\s]+\s+([A-Za-z_]\w*)\s*\(", re.M), "method"),
)

KOTLIN_PATTERNS = (
    (re.compile(r"^\s*(?:public\s+)?(?:suspend\s+)?fun\s+([A-Za-z_]\w*)", re.M), "function"),
    (re.compile(r"^\s*(?:public\s+)?(?:data\s+|sealed\s+|abstract\s+)*(?:class|interface|object)\s+([A-Za-z_]\w*)", re.M), "type"),
    (re.compile(r"^\s*(?:public\s+)?(?:val|var)\s+([A-Za-z_]\w*)", re.M), "value"),
)

EXPORT_BLOCK_RE = re.compile(r"^export\s*\{([^}]*)\}", re.M)
CJS_EXPORT_RE = re.compile(r"^module\.exports\s*=\s*\{([^}]*)\}", re.M)


def js_symbols(text: str):
    found = []
    for pattern, kind in JS_PATTERNS:
        for match in pattern.finditer(text):
            found.append((match.group(1), kind, text.count("\n", 0, match.start()) + 1))
    for match in EXPORT_BLOCK_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        for chunk in match.group(1).split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            name = chunk.split(" as ")[-1].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", name):
                found.append((name, "export", line))
    for match in CJS_EXPORT_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        for chunk in match.group(1).split(","):
            name = chunk.split(":")[0].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", name):
                found.append((name, "export", line))
    return found


def regex_symbols(text: str, patterns):
    found = []
    for pattern, kind in patterns:
        for match in pattern.finditer(text):
            found.append((match.group(1), kind, text.count("\n", 0, match.start()) + 1))
    return found


def go_symbols(text: str):
    found = []
    for name, kind, line in regex_symbols(text, GO_PATTERNS):
        if name[:1].isupper():
            found.append((name, kind, line))
    return found


def rust_symbols(text: str):
    found = []
    for name, kind, line in regex_symbols(text, RUST_PATTERNS):
        found.append((name, kind, line))
    return found


def ruby_symbols(text: str):
    found = []
    for name, kind, line in regex_symbols(text, RUBY_PATTERNS):
        found.append((name.rstrip("?!="), kind, line))
    return found


def java_symbols(text: str):
    return regex_symbols(text, JAVA_PATTERNS)


def kotlin_symbols(text: str):
    return regex_symbols(text, KOTLIN_PATTERNS)


def extract_symbols(path: Path, text: str):
    language = LANG_BY_EXT.get(path.suffix.lower())
    if language == "python":
        return python_symbols(text)
    if language in ("javascript", "typescript"):
        return js_symbols(text)
    if language == "go":
        return go_symbols(text)
    if language == "rust":
        return rust_symbols(text)
    if language == "ruby":
        return ruby_symbols(text)
    if language == "java":
        return java_symbols(text)
    if language == "kotlin":
        return kotlin_symbols(text)
    return []


# --------------------------------------------------------------------------
# analysis
# --------------------------------------------------------------------------


def symbol_is_referenced(name: str, test_texts) -> list:
    pattern = re.compile(
        r"(?<![{chars}]){name}(?![{chars}])".format(
            chars=IDENT_CHARS, name=re.escape(name)
        )
    )
    hits = []
    for path, text in test_texts:
        if pattern.search(text):
            hits.append(path)
    return hits


def analyse(src_dir: Path, test_dir: Path):
    source_files = []
    for path in walk_files(src_dir):
        if looks_like_test(path):
            continue
        if path.suffix.lower() not in LANG_BY_EXT:
            continue
        source_files.append(path)

    # Test files may live in the test directory (Python, JS, Ruby, Rust
    # integration tests) or next to the source they test (Go, Rust unit
    # modules, some JS repos). Collect both.
    test_files = set()
    for root in (src_dir, test_dir):
        for path in walk_files(root):
            if looks_like_test(path):
                test_files.add(path)
    test_files = sorted(test_files)
    test_texts = [(path, read_text(path)) for path in test_files]

    key_index: dict = {}
    stem_index: dict = {}
    for path in test_files:
        key_index.setdefault(path_key(path, is_test=True), []).append(path)
        stem_index.setdefault(strip_test_markers(path.stem).lower(), []).append(path)

    results = []
    untested_count = 0
    uncovered_files = 0

    for path in source_files:
        text = read_text(path)
        symbols = extract_symbols(path, text)
        mapped = list(key_index.get(path_key(path, is_test=False), []))
        if not mapped:
            mapped = list(stem_index.get(path.stem.lower(), []))
        mapped = sorted(set(mapped))

        entries = []
        for name, kind, line in symbols:
            hits = symbol_is_referenced(name, test_texts)
            covered = bool(hits)
            if not covered:
                untested_count += 1
            entries.append(
                {
                    "name": name,
                    "kind": kind,
                    "line": line,
                    "covered": covered,
                    "referenced_in": [str(p) for p in hits[:5]],
                }
            )
        if not mapped:
            uncovered_files += 1
        results.append(
            {
                "source": str(path),
                "test_files": [str(p) for p in mapped],
                "symbols": entries,
            }
        )

    summary = {
        "source_files": len(source_files),
        "test_files": len(test_files),
        "symbols": sum(len(item["symbols"]) for item in results),
        "untested_symbols": untested_count,
        "source_files_without_test": uncovered_files,
    }
    return results, summary


def render_text(results, summary, show_all: bool) -> str:
    lines = []
    lines.append(
        "Untested symbols — {source_files} source file(s), {symbols} public symbol(s), "
        "{untested_symbols} with no test reference".format(**summary)
    )
    lines.append(
        "Test files scanned: {test_files}. Source files with no mapped test file: "
        "{source_files_without_test}.".format(**summary)
    )
    lines.append("")

    for item in results:
        entries = item["symbols"]
        if not show_all and all(entry["covered"] for entry in entries):
            continue
        if item["test_files"]:
            mapped = ", ".join(item["test_files"])
        else:
            mapped = "no test file mapped"
        lines.append("{source}  (tests: {mapped})".format(source=item["source"], mapped=mapped))
        for entry in entries:
            if not show_all and entry["covered"]:
                continue
            if entry["kind"] == "constant":
                # Constants are config-like and rarely the missing behavior:
                # they are listed compactly below the functions and classes.
                continue
            status = (
                "referenced by " + ", ".join(entry["referenced_in"])
                if entry["covered"]
                else "NO TEST REFERENCE"
            )
            lines.append(
                "  L{line:<5} {kind:<9} {name:<40} {status}".format(
                    line=entry["line"], kind=entry["kind"], name=entry["name"], status=status
                )
            )
        constants = [
            entry["name"]
            for entry in entries
            if entry["kind"] == "constant" and (show_all or not entry["covered"])
        ]
        if constants:
            lines.append("  constants: " + ", ".join(constants))
        lines.append("")

    if not show_all and summary["untested_symbols"] == 0:
        lines.append("No unreferenced public symbol found by this heuristic.")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List exported/public symbols that no test file references."
    )
    parser.add_argument("src_dir", help="directory holding the source code")
    parser.add_argument("test_dir", help="directory holding the tests")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--all", action="store_true", help="also list symbols that are referenced")
    args = parser.parse_args()

    src_dir = Path(args.src_dir)
    test_dir = Path(args.test_dir)
    if not src_dir.is_dir():
        print(f"error: source directory not found: {src_dir}", file=sys.stderr)
        return 2
    if not test_dir.is_dir():
        print(f"warning: test directory not found: {test_dir}", file=sys.stderr)
        print("warning: only tests colocated with the source are considered", file=sys.stderr)

    results, summary = analyse(src_dir, test_dir)

    if args.json:
        payload = {
            "src_dir": str(src_dir),
            "test_dir": str(test_dir),
            "summary": summary,
            "files": results,
        }
        print(json.dumps(payload, indent=2, sort_keys=False))
    else:
        print(render_text(results, summary, args.all))
    return 0


if __name__ == "__main__":
    sys.exit(main())
