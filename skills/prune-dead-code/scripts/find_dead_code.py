#!/usr/bin/env python3
"""Conservative heuristic that lists public/exported symbols nothing references.

Read-only and stdlib-only. Point it at a source root and, optionally, a test
root:

    python3 -I scripts/find_dead_code.py src
    python3 -I scripts/find_dead_code.py src --test-dir tests
    python3 -I scripts/find_dead_code.py src --test-dir tests --json

It reports symbols that are DEFINED in one scanned file and whose name never
appears in any other scanned file. It is deliberately under-reporting:

  * only functions, classes, and exported constants are considered
  * a mention anywhere else - including in a comment, a docstring, a string
    literal, a config file, or a test - counts as a reference
  * definitions in entry points, test files, and public-API markers
    (__all__, `export {...}`, `pub use`) are never reported
  * a symbol whose name appears more than once in its own file is kept

Every reported symbol is a CANDIDATE, not a verdict. Prove it with the
checklist in SKILL.md before deleting anything.

Exit code is 0 even when candidates are found; it reports, it does not judge.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

MAX_FILE_BYTES = 2_000_000

SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "dist",
        "build",
        "out",
        "target",
        "vendor",
        "coverage",
        ".next",
        ".nuxt",
        ".svelte-kit",
        ".gradle",
        ".idea",
        ".cache",
    }
)

SKIP_FILES = frozenset(
    {
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lock",
        "bun.lockb",
        "Cargo.lock",
        "composer.lock",
        "Gemfile.lock",
        "poetry.lock",
    }
)

# Files whose contents are consumed by a framework or a tool rather than
# imported directly. Definitions inside them are never reported.
ENTRY_POINT_NAMES = frozenset(
    {
        "main.py",
        "__main__.py",
        "app.py",
        "cli.py",
        "server.py",
        "wsgi.py",
        "asgi.py",
        "manage.py",
        "setup.py",
        "conftest.py",
        "__init__.py",
        "index.js",
        "index.jsx",
        "index.ts",
        "index.tsx",
        "main.js",
        "main.ts",
        "lib.rs",
        "mod.rs",
        "main.go",
        "main.rs",
    }
)

TEST_NAME_RE = re.compile(
    r"(^test_.*\.py$)|(.*_test\.(go|py|js|ts)$)|(.*\.(test|spec)\.[jt]sx?$)|(^.*_spec\.rb$)",
    re.IGNORECASE,
)

TEST_DIR_NAMES = frozenset({"test", "tests", "spec", "specs", "__tests__", "e2e"})

WORD_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")

JS_EXPORT_PATTERNS = (
    re.compile(
        r"^export\s+(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][A-Za-z0-9_$]*)"
    ),
    re.compile(r"^export\s+(?:abstract\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)"),
    re.compile(r"^export\s+(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)"),
    re.compile(r"^export\s+(?:interface|type|enum|namespace)\s+([A-Za-z_$][A-Za-z0-9_$]*)"),
    re.compile(r"^(?:module\.)?exports\.([A-Za-z_$][A-Za-z0-9_$]*)\s*="),
)

JS_EXPORT_LIST_RE = re.compile(r"^[ \t]*export\s*\{([^}]*)\}", re.MULTILINE)
JS_EXPORT_STAR_RE = re.compile(r"^[ \t]*export\s*\*", re.MULTILINE)

GO_DEF_RE = re.compile(r"^func\s+([A-Z][A-Za-z0-9_]*)\s*\(")
GO_TYPE_RE = re.compile(r"^type\s+([A-Z][A-Za-z0-9_]*)\s+")

RUST_DEF_RE = re.compile(
    r"^pub(?:\([^)]*\))?\s+(?:async\s+)?(?:unsafe\s+)?(?:extern\s+\"[^\"]*\"\s+)?"
    r"(?:fn|struct|enum|trait|type|const|static|mod|union)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
RUST_USE_RE = re.compile(r"^pub\s+(?:use|extern\s+crate)", re.MULTILINE)


class Symbol:
    """One candidate definition."""

    __slots__ = ("name", "kind", "path", "line")

    def __init__(self, name: str, kind: str, path: Path, line: int) -> None:
        self.name = name
        self.kind = kind
        self.path = path
        self.line = line

    def as_dict(self, base: Path) -> dict:
        try:
            rel = self.path.relative_to(base).as_posix()
        except ValueError:
            rel = self.path.as_posix()
        return {"name": self.name, "kind": self.kind, "file": rel, "line": self.line}


def iter_files(root: Path):
    """Yield every readable text-ish file under root, skipping noise dirs."""
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for filename in sorted(filenames):
            if filename in SKIP_FILES or filename.startswith("."):
                continue
            path = Path(dirpath) / filename
            try:
                if not path.is_file() or path.is_symlink():
                    continue
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path


def read_text(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if b"\x00" in data[:4096]:
        return ""
    return data.decode("utf-8", errors="ignore")


def is_test_path(path: Path, roots: list[Path]) -> bool:
    if TEST_NAME_RE.search(path.name):
        return True
    for root in roots:
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part.lower() in TEST_DIR_NAMES for part in parts[:-1]):
            return True
    return False


def is_entry_point(path: Path) -> bool:
    return path.name in ENTRY_POINT_NAMES


def python_definitions(path: Path, text: str) -> tuple[list[Symbol], set[str]]:
    """Return (definitions, protected names) for a Python module."""
    definitions: list[Symbol] = []
    protected: set[str] = set()
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return definitions, protected

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if name.startswith("_"):
                continue
            definitions.append(Symbol(name, "function", path, node.lineno))
        elif isinstance(node, ast.ClassDef):
            name = node.name
            if name.startswith("_"):
                continue
            definitions.append(Symbol(name, "class", path, node.lineno))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    for item in ast.walk(node.value):
                        if isinstance(item, ast.Constant) and isinstance(item.value, str):
                            protected.add(item.value)
    return definitions, protected


def js_definitions(path: Path, text: str) -> tuple[list[Symbol], set[str]]:
    definitions: list[Symbol] = []
    protected: set[str] = set()

    if JS_EXPORT_STAR_RE.search(text):
        # `export *` re-exports an unknown surface: never report this file.
        return definitions, protected

    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        for pattern in JS_EXPORT_PATTERNS:
            match = pattern.match(stripped)
            if match:
                definitions.append(Symbol(match.group(1), "export", path, number))
                break

    for match in JS_EXPORT_LIST_RE.finditer(text):
        line_number = text.count("\n", 0, match.start()) + 1
        for chunk in match.group(1).split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            parts = chunk.split(" as ")
            local = parts[0].strip()
            exported = parts[-1].strip()
            if not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", local):
                continue
            if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", exported):
                definitions.append(Symbol(exported, "export", path, line_number))
            protected.add(local)
            protected.add(exported)

    return definitions, protected


def go_definitions(path: Path, text: str) -> tuple[list[Symbol], set[str]]:
    definitions: list[Symbol] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = GO_DEF_RE.match(line)
        if match:
            definitions.append(Symbol(match.group(1), "func", path, number))
            continue
        match = GO_TYPE_RE.match(line)
        if match:
            definitions.append(Symbol(match.group(1), "type", path, number))
    return definitions, set()


def rust_definitions(path: Path, text: str) -> tuple[list[Symbol], set[str]]:
    definitions: list[Symbol] = []
    protected: set[str] = set()
    if RUST_USE_RE.search(text):
        return definitions, protected
    for number, line in enumerate(text.splitlines(), start=1):
        match = RUST_DEF_RE.match(line)
        if match:
            definitions.append(Symbol(match.group(1), "pub", path, number))
    return definitions, protected


def collect_definitions(path: Path, text: str) -> tuple[list[Symbol], set[str]]:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return python_definitions(path, text)
    if suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}:
        return js_definitions(path, text)
    if suffix == ".go":
        return go_definitions(path, text)
    if suffix == ".rs":
        return rust_definitions(path, text)
    return [], set()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List public/exported symbols that no other scanned file references."
    )
    parser.add_argument("src_dir", help="Source root to scan")
    parser.add_argument("--test-dir", help="Optional test root to scan as well")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args()

    src_root = Path(args.src_dir).expanduser().resolve()
    if not src_root.is_dir():
        print(f"error: source directory not found: {args.src_dir}", file=sys.stderr)
        return 2

    test_root: Path | None = None
    if args.test_dir:
        candidate = Path(args.test_dir).expanduser().resolve()
        if not candidate.is_dir():
            print(f"error: test directory not found: {args.test_dir}", file=sys.stderr)
            return 2
        test_root = candidate

    # Reference corpus: every file under the roots counts as a potential
    # reference site, regardless of extension.
    corpus: list[Path] = list(iter_files(src_root))
    roots = [src_root]
    if test_root is not None:
        corpus.extend(iter_files(test_root))
        roots.append(test_root)

    # Token counts per file, used to decide whether a name is referenced.
    texts: dict[Path, str] = {}
    tokens: dict[Path, dict[str, int]] = {}
    for path in corpus:
        text = read_text(path)
        texts[path] = text
        counts: dict[str, int] = {}
        for word in WORD_RE.findall(text):
            counts[word] = counts.get(word, 0) + 1
        tokens[path] = counts

    candidates: list[Symbol] = []
    checked = 0
    skipped_files = 0

    for path in corpus:
        text = texts[path]
        definitions, protected = collect_definitions(path, text)
        if not definitions:
            continue
        if protected:
            # A file with a public-API marker is partly out of scope.
            definitions = [d for d in definitions if d.name not in protected]
        if not definitions:
            continue
        if is_entry_point(path) or is_test_path(path, roots):
            skipped_files += 1
            continue

        for symbol in definitions:
            checked += 1
            # Referenced inside its own file (recursion, docstring, re-export)?
            if tokens[path].get(symbol.name, 0) > 1:
                continue
            # Referenced anywhere else?
            referenced = False
            for other, counts in tokens.items():
                if other == path:
                    continue
                if counts.get(symbol.name, 0) > 0:
                    referenced = True
                    break
            if referenced:
                continue
            candidates.append(symbol)

    candidates.sort(key=lambda s: (s.path.as_posix(), s.line, s.name))

    if args.json:
        payload = {
            "source_root": str(src_root),
            "test_root": str(test_root) if test_root else None,
            "files_scanned": len(corpus),
            "symbols_checked": checked,
            "entry_point_or_test_files_skipped": skipped_files,
            "candidates": [symbol.as_dict(src_root) for symbol in candidates],
        }
        print(json.dumps(payload, indent=2))
        return 0

    print("Dead-code candidates (conservative heuristic)")
    print()
    print(f"source root: {src_root}")
    print(f"test root:   {test_root if test_root else '(none)'}")
    print(f"files scanned: {len(corpus)}")
    print(f"symbols checked: {checked}")
    print(f"entry point / test files skipped: {skipped_files}")
    print()

    if not candidates:
        print("No candidates found.")
        print("This tool under-reports on purpose. Absence of candidates is not proof of health.")
        return 0

    print(f"{'symbol':<40} {'kind':<10} location")
    print("-" * 78)
    for symbol in candidates:
        try:
            rel = symbol.path.relative_to(src_root).as_posix()
        except ValueError:
            rel = symbol.path.as_posix()
        print(f"{symbol.name:<40} {symbol.kind:<10} {rel}:{symbol.line}")

    print()
    print("Every line above is a CANDIDATE. Prove it before deleting anything:")
    print("  - grep the name as a string (dynamic import, registry, config)")
    print("  - check entry points, published exports, and build-time generation")
    print("  - when in doubt, keep the code and report it as reviewed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
