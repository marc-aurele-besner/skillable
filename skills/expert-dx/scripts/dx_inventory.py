#!/usr/bin/env python3
"""Inventory a project's developer-experience surface into JSON.

Stdlib-only and read-only: it reads files under the given path and never
executes anything from the target. It reports:

  - manifests found and the scripts/tasks each defines
    (package.json, pyproject.toml, Makefile, justfile, Taskfile.yml, Cargo.toml, go.mod)
  - package manager signals (lockfiles, packageManager field) and runtime pins
    (engines, .nvmrc, .node-version, .tool-versions, .python-version,
    requires-python, rust-toolchain)
  - README headings and the shell commands in its fenced code blocks
  - README commands that call a script no manifest defines
    (npm/pnpm/yarn/bun run X, make X, just X, task X)
  - README relative links that point at missing files
  - environment variables read by source code vs documented in .env.example / README
  - presence of CHANGELOG, examples/, docs/, CONTRIBUTING, type declarations, CI workflows

Every result is a lead for the reviewer to verify, not a finding.

Usage:
    python3 -I dx_inventory.py [path]
    python3 -I dx_inventory.py [path] --json out.json

Exit codes: 0 success, 1 error (path missing or not a directory).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", "out", "target", ".venv", "venv",
    "__pycache__", ".next", ".nuxt", ".turbo", "coverage", "vendor", ".cache",
}
SOURCE_EXTS = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py", ".go", ".rs", ".rb"}
MAX_SOURCE_FILES = 4000
MAX_FILE_BYTES = 512 * 1024

LOCKFILES = {
    "package-lock.json": "npm",
    "npm-shrinkwrap.json": "npm",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "bun.lock": "bun",
    "bun.lockb": "bun",
    "poetry.lock": "poetry",
    "uv.lock": "uv",
    "Pipfile.lock": "pipenv",
    "Cargo.lock": "cargo",
    "go.sum": "go",
}
PIN_FILES = (".nvmrc", ".node-version", ".tool-versions", ".python-version",
             "rust-toolchain", "rust-toolchain.toml")

FENCE_RE = re.compile(r"^```([A-Za-z0-9_+-]*)[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*#*\s*$", re.MULTILINE)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
SHELL_LANGS = {"", "sh", "bash", "shell", "console", "zsh", "terminal", "shell-session"}
RUN_RE = re.compile(
    r"^(?:\$\s*)?(npm|pnpm|yarn|bun)\s+(?:run\s+)?([A-Za-z0-9:_.-]+)"
)
TASK_RE = re.compile(r"^(?:\$\s*)?(make|just|task)\s+([A-Za-z0-9:_.-]+)")
PM_BUILTINS = {
    "install", "i", "add", "remove", "uninstall", "ci", "init", "create", "exec",
    "dlx", "x", "publish", "link", "update", "upgrade", "outdated", "audit",
    "why", "list", "ls", "view", "info", "pack", "help", "version", "config",
    "global", "rebuild", "prune", "dedupe", "login", "whoami", "-g", "--version",
}
ENV_PATTERNS = (
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]{2,})"),
    re.compile(r"process\.env\[['\"]([A-Z][A-Z0-9_]{2,})['\"]\]"),
    re.compile(r"import\.meta\.env\.([A-Z][A-Z0-9_]{2,})"),
    re.compile(r"os\.environ(?:\.get)?[\[(]\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"os\.getenv\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"os\.Getenv\(\s*\"([A-Z][A-Z0-9_]{2,})\""),
    re.compile(r"env::var\(\s*\"([A-Z][A-Z0-9_]{2,})\""),
    re.compile(r"ENV\[['\"]([A-Z][A-Z0-9_]{2,})['\"]\]"),
)
IGNORED_ENV = {"NODE_ENV", "HOME", "PATH", "PWD", "USER", "CI", "DEBUG", "TERM", "SHELL", "TZ"}


def read_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def first_existing(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        p = root / name
        if p.is_file():
            return p
    return None


def find_readme(root: Path) -> Path | None:
    for p in sorted(root.iterdir()):
        if p.is_file() and p.name.lower().startswith("readme"):
            return p
    return None


def node_manifest(root: Path, out: dict) -> set[str]:
    p = root / "package.json"
    if not p.is_file():
        return set()
    try:
        data = json.loads(read_text(p) or "{}")
    except json.JSONDecodeError as exc:
        out["manifests"].append({"file": "package.json", "error": f"invalid JSON: {exc}"})
        return set()
    scripts = data.get("scripts") or {}
    out["manifests"].append({
        "file": "package.json",
        "name": data.get("name"),
        "version": data.get("version"),
        "private": data.get("private", False),
        "has_bin": bool(data.get("bin")),
        "has_exports": bool(data.get("exports") or data.get("main") or data.get("module")),
        "types": data.get("types") or data.get("typings"),
        "workspaces": bool(data.get("workspaces")),
        "scripts": sorted(scripts),
    })
    if data.get("engines"):
        out["runtime_pins"]["package.json engines"] = data["engines"]
    if data.get("packageManager"):
        out["package_manager"]["packageManager_field"] = data["packageManager"]
    return set(scripts)


def pyproject_manifest(root: Path, out: dict) -> set[str]:
    p = root / "pyproject.toml"
    if not p.is_file():
        return set()
    entry: dict = {"file": "pyproject.toml"}
    names: set[str] = set()
    if tomllib is None:
        entry["note"] = "tomllib unavailable (Python < 3.11); not parsed"
    else:
        try:
            data = tomllib.loads(read_text(p))
        except tomllib.TOMLDecodeError as exc:
            entry["error"] = f"invalid TOML: {exc}"
            data = {}
        project = data.get("project", {})
        entry["name"] = project.get("name")
        entry["version"] = project.get("version")
        entry["console_scripts"] = sorted(project.get("scripts", {}))
        if project.get("requires-python"):
            out["runtime_pins"]["requires-python"] = project["requires-python"]
        tool = data.get("tool", {})
        for runner in ("poe", "pdm", "hatch"):
            tasks = tool.get(runner, {}).get("tasks") or tool.get(runner, {}).get("scripts")
            if isinstance(tasks, dict):
                entry[f"{runner}_tasks"] = sorted(tasks)
                names |= set(tasks)
    entry["py_typed"] = any(
        p for p in root.glob("**/py.typed") if not any(s in p.parts for s in SKIP_DIRS)
    )
    out["manifests"].append(entry)
    return names


def make_like(root: Path, out: dict) -> dict[str, set[str]]:
    targets: dict[str, set[str]] = {"make": set(), "just": set(), "task": set()}
    mk = first_existing(root, ("Makefile", "makefile", "GNUmakefile"))
    if mk:
        names = set(re.findall(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)\s*:(?!=)", read_text(mk), re.MULTILINE))
        targets["make"] = names
        out["manifests"].append({"file": mk.name, "targets": sorted(names)})
    jf = first_existing(root, ("justfile", "Justfile", ".justfile"))
    if jf:
        names = set(re.findall(r"^@?([A-Za-z0-9][A-Za-z0-9_-]*)(?:\s+[^:\n=]*)?:(?!=)", read_text(jf), re.MULTILINE))
        targets["just"] = names
        out["manifests"].append({"file": jf.name, "recipes": sorted(names)})
    tf = first_existing(root, ("Taskfile.yml", "Taskfile.yaml"))
    if tf:
        text = read_text(tf)
        block = text.split("tasks:", 1)[1] if "tasks:" in text else ""
        names = set(re.findall(r"^  ([A-Za-z0-9][A-Za-z0-9:_-]*):", block, re.MULTILINE))
        targets["task"] = names
        out["manifests"].append({"file": tf.name, "tasks": sorted(names)})
    for name in ("Cargo.toml", "go.mod", "Gemfile", "composer.json", "deno.json", "deno.jsonc"):
        if (root / name).is_file():
            out["manifests"].append({"file": name})
    return targets


def readme_facts(root: Path, readme: Path, scripts: set[str], targets: dict[str, set[str]], out: dict) -> str:
    text = read_text(readme)
    out["readme"] = {
        "file": readme.name,
        "lines": text.count("\n") + 1,
        "headings": [f"{'#' * len(h)} {t}" for h, t in HEADING_RE.findall(text)][:60],
        "shell_commands": [],
        "code_block_langs": {},
    }
    undefined: list[dict] = []
    for lang, body in FENCE_RE.findall(text):
        lang = lang.lower()
        out["readme"]["code_block_langs"][lang or "(none)"] = out["readme"]["code_block_langs"].get(lang or "(none)", 0) + 1
        if lang not in SHELL_LANGS:
            continue
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            out["readme"]["shell_commands"].append(line)
            for segment in re.split(r"\s*(?:&&|;|\|\|)\s*", line):
                m = RUN_RE.match(segment)
                if m and m.group(2) not in PM_BUILTINS and not m.group(2).startswith("-"):
                    if scripts and m.group(2) not in scripts:
                        undefined.append({"command": segment, "missing_script": m.group(2)})
                    continue
                m = TASK_RE.match(segment)
                if m and targets.get(m.group(1)) is not None:
                    defined = targets[m.group(1)]
                    if not defined:
                        undefined.append({"command": segment, "missing": f"no {m.group(1)} file found"})
                    elif m.group(2) not in defined:
                        undefined.append({"command": segment, "missing_target": m.group(2)})
    out["readme"]["shell_commands"] = out["readme"]["shell_commands"][:80]
    out["readme_commands_not_defined"] = undefined

    broken = []
    for target in LINK_RE.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#", "data:")):
            continue
        rel = target.split("#", 1)[0].split("?", 1)[0]
        if rel and not (root / rel).exists():
            broken.append(target)
    out["readme_broken_relative_links"] = sorted(set(broken))
    return text


def iter_source(root: Path):
    count = 0
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for p in entries:
            if p.is_dir():
                if p.name not in SKIP_DIRS and not p.is_symlink():
                    stack.append(p)
            elif p.suffix in SOURCE_EXTS and ".test." not in p.name and ".spec." not in p.name:
                count += 1
                if count > MAX_SOURCE_FILES:
                    return
                yield p


def env_facts(root: Path, readme_text: str, out: dict) -> None:
    used: dict[str, str] = {}
    for p in iter_source(root):
        text = read_text(p)
        for pat in ENV_PATTERNS:
            for name in pat.findall(text):
                if name not in IGNORED_ENV:
                    used.setdefault(name, str(p.relative_to(root)))
    example = first_existing(root, (".env.example", ".env.sample", ".env.template", "env.example"))
    documented: set[str] = set()
    if example:
        documented |= set(re.findall(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]+)\s*=", read_text(example), re.MULTILINE))
    in_readme = {n for n in used if n in readme_text}
    out["env_vars"] = {
        "example_file": example.name if example else None,
        "used_in_code": len(used),
        "undocumented": sorted(
            ({"name": n, "first_seen": f} for n, f in used.items() if n not in documented and n not in in_readme),
            key=lambda x: x["name"],
        )[:50],
    }


def presence(root: Path, out: dict) -> None:
    def any_glob(*patterns: str) -> list[str]:
        hits: list[str] = []
        for pat in patterns:
            hits += [str(p.relative_to(root)) for p in root.glob(pat) if not any(s in p.parts for s in SKIP_DIRS)]
        return sorted(set(hits))[:10]

    workflows = root / ".github" / "workflows"
    out["presence"] = {
        "changelog": any_glob("CHANGELOG*", "HISTORY*", "CHANGES*", "RELEASES*"),
        "contributing": any_glob("CONTRIBUTING*", ".github/CONTRIBUTING*", "docs/CONTRIBUTING*"),
        "examples": any_glob("examples", "example", "samples", "demo"),
        "docs": any_glob("docs", "doc", "website", "documentation"),
        "migration_guides": any_glob("MIGRATION*", "UPGRADING*", "docs/**/migrat*", "docs/**/upgrad*"),
        "type_declarations": any_glob("*.d.ts", "types/*.d.ts", "index.d.ts", "**/py.typed"),
        "openapi": any_glob("openapi.*", "swagger.*", "**/openapi.yaml", "**/openapi.json"),
        "ci_workflows": sorted(p.name for p in workflows.glob("*.y*ml")) if workflows.is_dir() else [],
        "devcontainer": any_glob(".devcontainer", ".devcontainer.json"),
        "agent_docs": any_glob("AGENTS.md", "CLAUDE.md"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory a project's DX surface (read-only).")
    parser.add_argument("path", nargs="?", default=".", help="project root (default: current directory)")
    parser.add_argument("--json", dest="json_out", help="also write the JSON to this file")
    args = parser.parse_args()

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 1

    out: dict = {"root": str(root), "manifests": [], "package_manager": {}, "runtime_pins": {}}
    out["package_manager"]["lockfiles"] = {n: m for n, m in LOCKFILES.items() if (root / n).is_file()}
    for name in PIN_FILES:
        p = root / name
        if p.is_file():
            out["runtime_pins"][name] = read_text(p).strip()[:200]

    scripts = node_manifest(root, out) | pyproject_manifest(root, out)
    targets = make_like(root, out)

    readme = find_readme(root)
    readme_text = ""
    if readme:
        readme_text = readme_facts(root, readme, scripts, targets, out)
    else:
        out["readme"] = None
    env_facts(root, readme_text, out)
    presence(root, out)

    payload = json.dumps(out, indent=2, sort_keys=False)
    print(payload)
    if args.json_out:
        Path(args.json_out).write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
