#!/usr/bin/env python3
"""Inventory Solidity contracts and installed audit tooling for a scoped review.

Read-only and stdlib-only. It never compiles, installs, or executes project
code; it only reads .sol files and checks which tools are on PATH.

    python3 -I scripts/scope_inventory.py <project-root>
    python3 -I scripts/scope_inventory.py <project-root> --json
    python3 -I scripts/scope_inventory.py <project-root> --include-tests

For each in-scope .sol file it reports:
  nsloc       normalized source lines (no blank lines, no comments)
  pragma      the `pragma solidity` constraint
  contracts   contract/library/interface/abstract names with their parents
  entry       count of external/public functions (non-view, non-pure)
  flags       risky constructs worth a closer look: delegatecall, assembly,
              selfdestruct, ecrecover, unchecked, tx.origin, low-level call,
              upgradeable base, initializer, permit, oracle reads

It also detects the framework (foundry.toml, hardhat.config.*) and which of
forge, slither, aderyn, echidna, medusa, solc, and halmos are installed.

Skipped by default: lib/, node_modules/, test/, tests/, script/, scripts/,
out/, cache/, artifacts/, and files or folders named like mocks.

Exit codes:
  0  inventory printed
  2  usage error (root not found)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

SKIP_DIRS = {
    "lib", "node_modules", "out", "cache", "artifacts", "cache_forge",
    "broadcast", ".git", "typechain", "typechain-types", "coverage",
}
TEST_DIRS = {"test", "tests", "script", "scripts"}
MOCK_RE = re.compile(r"mock", re.IGNORECASE)

TOOLS = ("forge", "slither", "aderyn", "echidna", "medusa", "solc", "halmos")

FLAG_PATTERNS = {
    "delegatecall": re.compile(r"\.delegatecall\s*\(|\bdelegatecall\s*\("),
    "assembly": re.compile(r"\bassembly\s*(\(\s*\"memory-safe\"\s*\)\s*)?\{"),
    "selfdestruct": re.compile(r"\bselfdestruct\s*\("),
    "ecrecover": re.compile(r"\becrecover\s*\(|ECDSA\.(recover|tryRecover)"),
    "unchecked": re.compile(r"\bunchecked\s*\{"),
    "tx.origin": re.compile(r"\btx\.origin\b"),
    "low-level-call": re.compile(r"\.call\s*[\({]"),
    "upgradeable": re.compile(r"Upgradeable\b|UUPS|ERC1967|Initializable"),
    "initializer": re.compile(r"\binitializer\b|\breinitializer\s*\("),
    "permit": re.compile(r"\bpermit\s*\("),
    "oracle": re.compile(r"latestRoundData|getReserves|slot0|observe\s*\(|getPrice"),
    "transient": re.compile(r"\btransient\b|\btstore\b|\btload\b"),
}

PRAGMA_RE = re.compile(r"pragma\s+solidity\s+([^;]+);")
CONTRACT_RE = re.compile(
    r"^\s*(abstract\s+contract|contract|library|interface)\s+([A-Za-z_]\w*)"
    r"(?:\s+is\s+([^{]+))?\s*\{",
    re.MULTILINE,
)
FUNC_RE = re.compile(r"\bfunction\s+\w+\s*\([^)]*\)([^{;]*)[{;]", re.DOTALL)


def strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", src)


def nsloc(code: str) -> int:
    return sum(1 for line in code.splitlines() if line.strip())


def entry_points(code: str) -> int:
    count = 0
    for match in FUNC_RE.finditer(code):
        attrs = match.group(1)
        if not re.search(r"\b(external|public)\b", attrs):
            continue
        if re.search(r"\b(view|pure)\b", attrs):
            continue
        count += 1
    return count


def in_scope(path: Path, root: Path, include_tests: bool) -> bool:
    parts = path.relative_to(root).parts
    for part in parts[:-1]:
        if part in SKIP_DIRS:
            return False
        if not include_tests and (part in TEST_DIRS or MOCK_RE.search(part)):
            return False
    name = parts[-1]
    if not include_tests and (name.endswith(".t.sol") or name.endswith(".s.sol") or MOCK_RE.search(name)):
        return False
    return True


def scan_file(path: Path, root: Path) -> dict:
    raw = path.read_text(encoding="utf-8", errors="replace")
    code = strip_comments(raw)
    pragma = PRAGMA_RE.search(code)
    contracts = []
    for kind, name, parents in CONTRACT_RE.findall(code):
        contracts.append({
            "kind": " ".join(kind.split()),
            "name": name,
            "parents": [p.strip().split("(")[0] for p in parents.split(",")] if parents else [],
        })
    flags = sorted(flag for flag, pattern in FLAG_PATTERNS.items() if pattern.search(code))
    return {
        "file": path.relative_to(root).as_posix(),
        "nsloc": nsloc(code),
        "pragma": pragma.group(1).strip() if pragma else None,
        "contracts": contracts,
        "entry": entry_points(code),
        "flags": flags,
    }


def detect_framework(root: Path) -> list[str]:
    found = []
    if (root / "foundry.toml").exists():
        found.append("foundry")
    if any(root.glob("hardhat.config.*")):
        found.append("hardhat")
    if (root / "ape-config.yaml").exists():
        found.append("ape")
    if (root / "brownie-config.yaml").exists():
        found.append("brownie")
    if (root / "echidna.yaml").exists() or (root / "echidna.config.yaml").exists():
        found.append("echidna-config")
    if (root / "medusa.json").exists():
        found.append("medusa-config")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", default=".", help="project root (default: .)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    parser.add_argument("--include-tests", action="store_true", help="include tests, scripts, and mocks")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for filename in filenames:
            if filename.endswith(".sol"):
                path = Path(dirpath) / filename
                if in_scope(path, root, args.include_tests):
                    files.append(scan_file(path, root))
    files.sort(key=lambda f: f["file"])

    tools = {tool: bool(shutil.which(tool)) for tool in TOOLS}
    result = {
        "root": str(root),
        "framework": detect_framework(root),
        "tools": tools,
        "total_nsloc": sum(f["nsloc"] for f in files),
        "pragmas": sorted({f["pragma"] for f in files if f["pragma"]}),
        "files": files,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"Root: {root}")
    print(f"Framework: {', '.join(result['framework']) or 'none detected'}")
    print("Tools: " + ", ".join(f"{t}={'yes' if ok else 'no'}" for t, ok in tools.items()))
    print(f"Pragmas: {', '.join(result['pragmas']) or 'none'}")
    print(f"Files: {len(files)}  Total nSLOC: {result['total_nsloc']}\n")
    width = max((len(f["file"]) for f in files), default=4)
    print(f"{'file'.ljust(width)}  nsloc  entry  flags")
    for f in files:
        print(f"{f['file'].ljust(width)}  {str(f['nsloc']).rjust(5)}  {str(f['entry']).rjust(5)}  {', '.join(f['flags'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
