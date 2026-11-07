#!/usr/bin/env python3
"""Audit a repository's governance and agent-facing hygiene artifacts.

Read-only, stdlib-only, no network. Point it at the root of any repository:

    python3 -I audit_repo_hygiene.py <repo-root>
    python3 -I audit_repo_hygiene.py <repo-root> --json

It reports which governance artifacts exist and which are missing, and it
validates the ones that can be validated mechanically:

  - LICENSE: present, non-empty, recognized license, consistent with the
    license declared in the package manifest
  - README.md: install / usage / contributing pointer / license section
  - CONTRIBUTING.md: every command it references exists in the project's
    manifest, and every path it references exists on disk
  - SECURITY.md: a real contact route and a supported-versions table
  - .gitignore: covers build output and .env files
  - issue and pull request templates: parse as YAML and carry the required
    fields

Exit code is 0 even when gaps are found; it reports, it does not judge. Use
--strict to exit 1 when a P0 check fails.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from fnmatch import fnmatch
from pathlib import Path

# --------------------------------------------------------------------------
# Minimal YAML subset parser (no third-party dependency available).
# Supports mappings, sequences, quoted scalars, comments and block scalars.
# It is not a full YAML implementation; it covers what GitHub templates use.
# --------------------------------------------------------------------------


class YamlError(Exception):
    """Raised when the input cannot be parsed by the subset parser."""


def _strip_comment(line: str) -> str:
    out = []
    quote = None
    for index, char in enumerate(line):
        if quote:
            out.append(char)
            if char == quote and (index == 0 or line[index - 1] != "\\"):
                quote = None
            continue
        if char in "\"'":
            quote = char
            out.append(char)
            continue
        if char == "#" and (index == 0 or line[index - 1] in " \t"):
            break
        out.append(char)
    return "".join(out).rstrip()


def _scalar(raw: str):
    raw = raw.strip()
    if raw == "":
        return None
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part) for part in inner.split(",")]
    lowered = raw.lower()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    if lowered in {"null", "~"}:
        return None
    return raw


def _tokenize(text: str):
    tokens = []
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.replace("\t", "    ")
        if not line.strip():
            continue
        stripped = _strip_comment(line)
        if not stripped.strip():
            continue
        if stripped.strip() in {"---", "..."}:
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        tokens.append((indent, stripped.strip(), number))
    return tokens


def _parse_block(tokens, index, indent):
    if index >= len(tokens):
        return None, index
    if tokens[index][1].startswith("- "):
        return _parse_sequence(tokens, index, indent)
    return _parse_mapping(tokens, index, indent)


def _parse_sequence(tokens, index, indent):
    items = []
    while index < len(tokens):
        cur_indent, content, _ = tokens[index]
        if cur_indent < indent:
            break
        if cur_indent > indent or not content.startswith("- "):
            break
        body = content[2:].strip()
        index += 1
        if body == "":
            value, index = _parse_block(tokens, index, tokens[index][0]) if index < len(tokens) else (None, index)
            items.append(value)
            continue
        if ":" in body and not body.startswith(("'", '"', "[", "{")):
            key, _, rest = body.partition(":")
            entry = {key.strip(): _scalar(rest)}
            while index < len(tokens) and tokens[index][0] > cur_indent:
                sub, index = _parse_mapping(tokens, index, tokens[index][0])
                if isinstance(sub, dict):
                    entry.update(sub)
            items.append(entry)
            continue
        items.append(_scalar(body))
    return items, index


def _parse_mapping(tokens, index, indent):
    mapping = {}
    while index < len(tokens):
        cur_indent, content, _ = tokens[index]
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise YamlError(f"unexpected indentation at line {tokens[index][2]}")
        if content.startswith("- "):
            break
        if ":" not in content:
            raise YamlError(f"expected 'key: value' at line {tokens[index][2]}")
        key, _, rest = content.partition(":")
        key = key.strip()
        if key.startswith(("'", '"')) and key.endswith(("'", '"')) and len(key) >= 2:
            key = key[1:-1]
        rest = rest.strip()
        index += 1
        if rest in {"|", ">", "|-", ">-", "|+", ">+"}:
            block = []
            while index < len(tokens) and tokens[index][0] > cur_indent:
                block.append(tokens[index][1])
                index += 1
            mapping[key] = "\n".join(block) if rest.startswith("|") else " ".join(block)
            continue
        if rest:
            mapping[key] = _scalar(rest)
            continue
        if index < len(tokens) and tokens[index][0] > cur_indent:
            value, index = _parse_block(tokens, index, tokens[index][0])
            mapping[key] = value
        elif index < len(tokens) and tokens[index][0] == cur_indent and tokens[index][1].startswith("- "):
            value, index = _parse_sequence(tokens, index, cur_indent)
            mapping[key] = value
        else:
            mapping[key] = None
    return mapping, index


def parse_yaml(text: str):
    """Parse the YAML subset used by GitHub templates. Raises YamlError."""
    tokens = _tokenize(text)
    if not tokens:
        return {}
    value, index = _parse_block(tokens, 0, tokens[0][0])
    if index != len(tokens):
        raise YamlError(f"unparsed content at line {tokens[index][2]}")
    return value


# --------------------------------------------------------------------------
# Result model
# --------------------------------------------------------------------------

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_WARN = "warn"
STATUS_MISSING = "missing"

SEVERITY_P0 = "P0"
SEVERITY_P1 = "P1"
SEVERITY_P2 = "P2"
SEVERITY_P3 = "P3"


class Result:
    def __init__(self, check_id, name, status, severity, detail="", path=""):
        self.check_id = check_id
        self.name = name
        self.status = status
        self.severity = severity
        self.detail = detail
        self.path = path

    def to_dict(self):
        return {
            "id": self.check_id,
            "name": self.name,
            "status": self.status,
            "severity": self.severity,
            "detail": self.detail,
            "path": self.path,
        }


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

LICENSE_SIGNATURES = [
    ("Apache-2.0", re.compile(r"apache license", re.IGNORECASE)),
    ("MIT", re.compile(r"\bMIT License\b", re.IGNORECASE)),
    ("BSD-3-Clause", re.compile(r"redistribution and use in source and binary forms", re.IGNORECASE)),
    ("BSD-2-Clause", re.compile(r"redistributions of source code", re.IGNORECASE)),
    ("GPL-3.0", re.compile(r"GNU GENERAL PUBLIC LICENSE\s*\n\s*Version 3", re.IGNORECASE)),
    ("GPL-2.0", re.compile(r"GNU GENERAL PUBLIC LICENSE\s*\n\s*Version 2", re.IGNORECASE)),
    ("AGPL-3.0", re.compile(r"GNU AFFERO GENERAL PUBLIC LICENSE", re.IGNORECASE)),
    ("LGPL-3.0", re.compile(r"GNU LESSER GENERAL PUBLIC LICENSE", re.IGNORECASE)),
    ("MPL-2.0", re.compile(r"mozilla public license", re.IGNORECASE)),
    ("ISC", re.compile(r"\bISC License\b", re.IGNORECASE)),
    ("Unlicense", re.compile(r"\bThis is free and unencumbered software released into the public domain", re.IGNORECASE)),
    ("CC0-1.0", re.compile(r"CC0 1\.0 Universal", re.IGNORECASE)),
]

PLACEHOLDER_PATTERNS = [
    re.compile(r"\bTODO\b"),
    re.compile(r"\bTBD\b"),
    re.compile(r"\bFIXME\b"),
    re.compile(r"\byour[-_](team|company|org|project|repo|email|name|username)\b", re.IGNORECASE),
    re.compile(r"\[your[-_ ]?(team|company|org|project|repo|email|name|username)?\]", re.IGNORECASE),
    re.compile(r"<your[-_ ]?(team|company|org|project|repo|email|name|username)?\s*>", re.IGNORECASE),
    re.compile(r"[\w.+-]+@example\.com\b", re.IGNORECASE),
    re.compile(r"\bYOUR_(TEAM|ORG|COMPANY|NAME|EMAIL)\b"),
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

BUILD_OUTPUT_BY_STACK = {
    "node": ["node_modules", "dist", "build", "out", ".next", ".nuxt", ".svelte-kit", ".turbo",
             ".cache", "coverage"],
    "python": ["__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache", "dist", "build",
               "*.egg-info"],
    "rust": ["target"],
    "go": ["bin", "vendor"],
    "java": ["target", "build", ".gradle"],
    "ruby": ["vendor/bundle", ".bundle", "coverage"],
    "php": ["vendor"],
    "elixir": ["_build", "deps"],
    "dotnet": ["bin", "obj"],
}

# Build output that must never be committed, per detected stack.
REQUIRED_IGNORE_BY_STACK = {
    "node": ["node_modules"],
    "python": ["__pycache__"],
    "rust": ["target"],
    "go": [],
    "java": ["target"],
    "ruby": [".bundle"],
    "php": ["vendor"],
    "elixir": ["_build"],
    "dotnet": ["bin", "obj"],
}

# Build output that is good practice to ignore, per detected stack.
OPTIONAL_IGNORE_BY_STACK = {
    "node": ["dist", "build", "coverage"],
    "python": [".venv", "venv", ".pytest_cache", ".mypy_cache", "dist", "build"],
    "rust": [],
    "go": ["bin"],
    "java": ["build", ".gradle"],
    "ruby": ["vendor/bundle", "coverage"],
    "php": [],
    "elixir": ["deps"],
    "dotnet": ["obj"],
}

ENV_SAMPLES = [".env", ".env.local"]
ENV_VARIANT_SAMPLES = [".env.local"]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def find_first(root: Path, candidates):
    for candidate in candidates:
        path = root / candidate
        if path.is_file():
            return path
    return None


def find_dir(root: Path, candidates):
    for candidate in candidates:
        path = root / candidate
        if path.is_dir():
            return path
    return None


def manifest_scripts(root: Path):
    """Return the set of command names the project's manifest defines."""
    names = set()

    package_json = root / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(read_text(package_json) or "{}")
        except json.JSONDecodeError:
            data = {}
        scripts = data.get("scripts")
        if isinstance(scripts, dict):
            names.update(str(key) for key in scripts)

    makefile = find_first(root, ["Makefile", "makefile", "GNUmakefile"])
    if makefile is not None:
        for line in read_text(makefile).splitlines():
            match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)\s*:(?!=)", line)
            if match:
                names.add(match.group(1))

    justfile = find_first(root, ["justfile", "Justfile", ".justfile"])
    if justfile is not None:
        for line in read_text(justfile).splitlines():
            match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\s+[^:]*)?:", line)
            if match and match.group(1) not in {"set", "export", "alias"}:
                names.add(match.group(1))

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = read_text(pyproject)
        for section in ("[tool.poetry.scripts]", "[project.scripts]", "[tool.hatch.envs.default.scripts]"):
            start = text.find(section)
            if start == -1:
                continue
            tail = text[start + len(section):]
            end = tail.find("\n[")
            body = tail if end == -1 else tail[:end]
            for line in body.splitlines():
                match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)\s*=", line)
                if match:
                    names.add(match.group(1))
        for line in text.splitlines():
            match = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)\s*=\s*[\"'](?:poetry|uv|pipx|uvx)", line)
            if match:
                names.add(match.group(1))

    composer = root / "composer.json"
    if composer.is_file():
        try:
            data = json.loads(read_text(composer) or "{}")
        except json.JSONDecodeError:
            data = {}
        scripts = data.get("scripts")
        if isinstance(scripts, dict):
            names.update(str(key) for key in scripts)

    taskfile = find_first(root, ["Taskfile.yml", "Taskfile.yaml", "Rakefile"])
    if taskfile is not None:
        for line in read_text(taskfile).splitlines():
            match = re.match(r"^\s{0,4}([A-Za-z0-9][A-Za-z0-9_:-]*)\s*:", line)
            if match:
                names.add(match.group(1).strip("\"'"))

    return names


def manifest_license(root: Path):
    package_json = root / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(read_text(package_json) or "{}")
        except json.JSONDecodeError:
            return None
        value = data.get("license")
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict) and isinstance(value.get("type"), str):
            return value["type"].strip()
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = read_text(pyproject)
        match = re.search(r"^\s*license\s*=\s*[\"']([^\"']+)[\"']", text, re.MULTILINE)
        if match:
            return match.group(1)
    return None


def normalize_license(value):
    if not value:
        return None
    text = value.strip().lower()
    if text in {"mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause", "gpl-3.0", "gpl-2.0",
                "agpl-3.0", "lgpl-3.0", "mpl-2.0", "isc", "unlicense", "cc0-1.0"}:
        return text
    if "apache" in text and "2.0" in text:
        return "apache-2.0"
    if "mit" in text:
        return "mit"
    if "bsd" in text:
        return "bsd-3-clause"
    if "gpl" in text and "agpl" not in text and "lgpl" not in text:
        return "gpl-3.0"
    return None


def detect_license(text: str):
    for name, pattern in LICENSE_SIGNATURES:
        if pattern.search(text):
            return name
    return None


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


def check_license(root, results):
    path = find_first(root, ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING"])
    if path is None:
        results.append(Result("license", "LICENSE", STATUS_MISSING, SEVERITY_P0,
                              "no LICENSE file at the repo root", "LICENSE"))
        return
    text = read_text(path)
    rel = path.relative_to(root).as_posix()
    if not text.strip():
        results.append(Result("license", "LICENSE", STATUS_FAIL, SEVERITY_P0,
                              "LICENSE is empty", rel))
        return
    detected = detect_license(text)
    if detected is None:
        results.append(Result("license", "LICENSE", STATUS_WARN, SEVERITY_P1,
                              "LICENSE has no recognizable license header", rel))
    else:
        results.append(Result("license", "LICENSE", STATUS_PASS, SEVERITY_P0,
                              f"license detected: {detected}", rel))

    declared_raw = manifest_license(root)
    declared = normalize_license(declared_raw)
    if declared_raw and detected:
        if declared and declared == detected.lower():
            results.append(Result("license-manifest", "LICENSE matches manifest", STATUS_PASS,
                                  SEVERITY_P1, f"manifest declares {declared_raw}", rel))
        else:
            results.append(Result("license-manifest", "LICENSE matches manifest", STATUS_FAIL,
                                  SEVERITY_P1,
                                  f"manifest declares {declared_raw!r} but LICENSE looks like {detected}",
                                  rel))
    elif declared_raw and not declared:
        results.append(Result("license-manifest", "LICENSE matches manifest", STATUS_WARN,
                              SEVERITY_P2, f"manifest declares an unrecognized license {declared_raw!r}",
                              rel))


def readme_sections(text: str):
    sections = set()
    for line in text.splitlines():
        match = re.match(r"^#{1,4}\s+(.+?)\s*$", line)
        if match:
            title = match.group(1).strip().lower()
            sections.add(re.sub(r"[^a-z0-9 ]+", "", title).strip())
    return sections


def check_readme(root, results):
    path = root / "README.md"
    if not path.is_file():
        results.append(Result("readme", "README.md", STATUS_MISSING, SEVERITY_P0,
                              "no README.md at the repo root", "README.md"))
        return
    text = read_text(path)
    sections = readme_sections(text)
    lowered = text.lower()

    def has(*words):
        return any(word in lowered for word in words)

    has_install = has("install", "installation", "getting started", "quick start")
    has_usage = has("usage", "how to use", "quick start")
    has_contributing = has("contributing", "contributions are welcome", "development")
    has_license = has("license") or "## license" in lowered
    has_badges = "shields.io" in lowered or "badge" in lowered or "![badge" in lowered

    if has_install:
        results.append(Result("readme-install", "README: install instructions", STATUS_PASS,
                              SEVERITY_P1, "found", "README.md"))
    else:
        results.append(Result("readme-install", "README: install instructions", STATUS_FAIL,
                              SEVERITY_P1, "no install / getting started section", "README.md"))

    if has_usage:
        results.append(Result("readme-usage", "README: usage", STATUS_PASS, SEVERITY_P1,
                              "found", "README.md"))
    else:
        results.append(Result("readme-usage", "README: usage", STATUS_FAIL, SEVERITY_P1,
                              "no usage section", "README.md"))

    if has_contributing:
        results.append(Result("readme-contributing", "README: contributing pointer", STATUS_PASS,
                              SEVERITY_P2, "found", "README.md"))
    else:
        results.append(Result("readme-contributing", "README: contributing pointer", STATUS_WARN,
                              SEVERITY_P2, "no pointer to CONTRIBUTING.md", "README.md"))

    if has_license:
        results.append(Result("readme-license", "README: license section", STATUS_PASS,
                              SEVERITY_P2, "found", "README.md"))
    else:
        results.append(Result("readme-license", "README: license section", STATUS_WARN,
                              SEVERITY_P2, "no license section", "README.md"))

    if has_badges:
        results.append(Result("readme-badges", "README: badges", STATUS_PASS, SEVERITY_P3,
                              "found", "README.md"))
    else:
        results.append(Result("readme-badges", "README: badges", STATUS_WARN, SEVERITY_P3,
                              "no badges found", "README.md"))

    for pattern in PLACEHOLDER_PATTERNS:
        match = pattern.search(text)
        if match:
            results.append(Result("readme-placeholder", "README: no placeholders", STATUS_FAIL,
                                  SEVERITY_P1, f"placeholder text found: {match.group(0)!r}", "README.md"))
            break
    else:
        results.append(Result("readme-placeholder", "README: no placeholders", STATUS_PASS,
                              SEVERITY_P1, "no placeholder markers", "README.md"))


# Package-manager verbs that never correspond to a manifest script.
IGNORED_COMMANDS = {
    "install", "i", "add", "remove", "rm", "uninstall", "ci", "publish", "pack", "link",
    "update", "upgrade", "init", "create", "list", "ls", "outdated", "why", "audit", "version",
    "run", "exec", "dlx", "x", "cache", "config", "help", "login", "logout", "whoami", "ping",
    "prune", "dedupe", "store", "licenses", "team", "unpublish", "view", "info", "sync",
    "lock", "shell", "venv", "tree", "pip", "compile", "sync", "self", "tool", "run-script",
    "workspace", "workspaces", "root", "bin", "global", "restart", "rebuild", "clean", "cold",
}

# Package-manager verbs that never correspond to a task-runner target.
IGNORED_TARGETS = {"help", "list", "clean", "install", "print", "variables", "shell"}

# Commands that are tools, not project scripts.
CONTRIBUTING_ALWAYS = {
    "npm", "pnpm", "yarn", "bun", "npx", "bunx", "node", "python", "python3", "pip", "pip3",
    "poetry", "uv", "uvx", "pipx", "pipenv", "cargo", "go", "rustc", "make", "just", "git",
    "docker", "docker-compose", "gh", "curl", "wget", "sh", "bash", "zsh", "deno", "dotnet",
    "java", "mvn", "gradle", "composer", "bundle", "rake", "pod", "swift", "mix", "elixir",
    "dart", "flutter", "terraform", "kubectl", "helm", "ansible", "prettier", "eslint", "ruff",
    "black", "pytest", "mypy", "tox", "hatch", "twine", "gcc", "clang", "sudo", "cd", "source",
    "export", "corepack", "nvm", "mise", "asdf", "rtx",
}

# Runner families.
JS_RUNNERS = ("npm", "pnpm", "yarn", "bun")
PY_RUNNERS = ("poetry", "uv", "pipenv")


def extract_commands(text: str):
    """Extract candidate project commands mentioned in a markdown document.

    Looks at fenced code blocks, inline code spans, and any plain line that
    begins with a known runner (a package manager, make, just, poetry, uv).
    """
    commands = set()
    for block in re.findall(r"```[^\n]*\n(.*?)```", text, re.DOTALL):
        for line in block.splitlines():
            line = line.strip().lstrip("$ ").strip()
            if line and not line.startswith("#"):
                commands.add(line)
    for span in re.findall(r"`([^`\n]{2,120})`", text):
        span = span.strip()
        if span and not span.startswith(("http", "www.")):
            commands.add(span)
    for line in text.splitlines():
        stripped = line.strip().lstrip("-*+ ").strip()
        if stripped.startswith(("npm ", "pnpm ", "yarn ", "bun ", "make ", "just ", "poetry ",
                                "uv ", "pipenv ")):
            commands.add(stripped.split("\n")[0].strip())
    return commands


def command_target(command: str):
    """Return (target_name, kind) for a command, or (None, None) when it is
    not a project script or task reference."""
    parts = command.split()
    if not parts:
        return None, None
    runner = parts[0]
    args = parts[1:]

    if runner in JS_RUNNERS:
        if not args:
            return None, None
        if args[0] in {"run", "run-script"}:
            if len(args) < 2:
                return None, None
            name = args[1]
            if name in IGNORED_COMMANDS and name not in {"test", "lint", "build", "typecheck",
                                                         "format", "dev", "start"}:
                return None, None
            return name, "script"
        if args[0] in IGNORED_COMMANDS:
            return None, None
        return args[0], "script"

    if runner in PY_RUNNERS:
        if not args:
            return None, None
        if args[0] == "run":
            if len(args) < 2:
                return None, None
            return args[1], "script"
        return None, None

    if runner in {"make", "just"}:
        if not args:
            return None, None
        if args[0] in IGNORED_TARGETS:
            return None, None
        return args[0], "target"

    return None, None


def extract_referenced_paths(text: str):
    """Extract file paths referenced from markdown links and inline code.

    Only paths that look like paths (contain a slash) or explicit markdown
    link targets are returned; a bare word like ``SKILL.md`` in prose is not
    treated as a repo-relative path.
    """
    paths = set()
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        target = target.split("#", 1)[0].strip()
        if not target:
            continue
        if target.startswith(("http://", "https://", "mailto:", "#", "<")):
            continue
        if "<" in target or ">" in target:
            continue
        if "/" in target:
            paths.add(target)
    for span in re.findall(r"`([^`\n]{2,120})`", text):
        span = span.strip()
        if not span or " " in span:
            continue
        if span.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if "<" in span or ">" in span:
            continue
        if re.match(r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+/?$", span):
            paths.add(span)
    return paths


def check_contributing(root, results):
    path = find_first(root, ["CONTRIBUTING.md", "CONTRIBUTING", ".github/CONTRIBUTING.md",
                             "docs/CONTRIBUTING.md"])
    if path is None:
        results.append(Result("contributing", "CONTRIBUTING.md", STATUS_MISSING, SEVERITY_P0,
                              "no CONTRIBUTING.md", "CONTRIBUTING.md"))
        return
    rel = path.relative_to(root).as_posix()
    text = read_text(path)
    results.append(Result("contributing", "CONTRIBUTING.md", STATUS_PASS, SEVERITY_P0, "found", rel))

    for pattern in PLACEHOLDER_PATTERNS:
        match = pattern.search(text)
        if match:
            results.append(Result("contributing-placeholder", "CONTRIBUTING: no placeholders",
                                  STATUS_FAIL, SEVERITY_P1, f"placeholder text: {match.group(0)!r}", rel))
            break
    else:
        results.append(Result("contributing-placeholder", "CONTRIBUTING: no placeholders",
                              STATUS_PASS, SEVERITY_P1, "no placeholder markers", rel))

    scripts = manifest_scripts(root)
    manifest_present = bool(
        (root / "package.json").is_file()
        or (root / "Makefile").is_file()
        or (root / "justfile").is_file()
        or (root / "pyproject.toml").is_file()
        or (root / "composer.json").is_file()
        or (root / "Taskfile.yml").is_file()
    )

    referenced = set()
    for command in sorted(extract_commands(text)):
        name, kind = command_target(command)
        if name:
            referenced.add((name, kind))

    if not manifest_present:
        results.append(Result("contributing-commands", "CONTRIBUTING: commands exist in manifest",
                              STATUS_WARN, SEVERITY_P2,
                              "no package manifest found; command references not verified", rel))
    else:
        missing = sorted({name for name, _ in referenced if name not in scripts})
        if missing:
            results.append(Result("contributing-commands", "CONTRIBUTING: commands exist in manifest",
                                  STATUS_FAIL, SEVERITY_P1,
                                  "referenced but not in the manifest: " + ", ".join(missing), rel))
        elif referenced:
            results.append(Result("contributing-commands", "CONTRIBUTING: commands exist in manifest",
                                  STATUS_PASS, SEVERITY_P1,
                                  f"{len(referenced)} referenced command(s) exist in the manifest", rel))
        else:
            results.append(Result("contributing-commands", "CONTRIBUTING: commands exist in manifest",
                                  STATUS_WARN, SEVERITY_P2,
                                  "no script or task references found to verify", rel))

    broken = []
    for candidate in sorted(extract_referenced_paths(text)):
        cleaned = candidate.rstrip("/")
        if cleaned.startswith("./"):
            cleaned = cleaned[2:]
        if (root / cleaned).exists():
            continue
        if (path.parent / cleaned).exists():
            continue
        if "*" in cleaned or "?" in cleaned:
            continue
        broken.append(candidate)
    if broken:
        results.append(Result("contributing-paths", "CONTRIBUTING: referenced paths exist",
                              STATUS_FAIL, SEVERITY_P1, "missing: " + ", ".join(broken), rel))
    else:
        results.append(Result("contributing-paths", "CONTRIBUTING: referenced paths exist",
                              STATUS_PASS, SEVERITY_P1, "all referenced paths resolve", rel))


def check_code_of_conduct(root, results):
    path = find_first(root, ["CODE_OF_CONDUCT.md", "CODE_OF_CONDUCT", ".github/CODE_OF_CONDUCT.md",
                             "docs/CODE_OF_CONDUCT.md"])
    if path is None:
        results.append(Result("code-of-conduct", "CODE_OF_CONDUCT.md", STATUS_MISSING, SEVERITY_P2,
                              "no CODE_OF_CONDUCT.md (needs owner approval before writing)", "CODE_OF_CONDUCT.md"))
        return
    rel = path.relative_to(root).as_posix()
    text = read_text(path)
    if not text.strip():
        results.append(Result("code-of-conduct", "CODE_OF_CONDUCT.md", STATUS_FAIL, SEVERITY_P2,
                              "file is empty", rel))
        return
    results.append(Result("code-of-conduct", "CODE_OF_CONDUCT.md", STATUS_PASS, SEVERITY_P2, "found", rel))
    for pattern in PLACEHOLDER_PATTERNS:
        match = pattern.search(text)
        if match:
            results.append(Result("code-of-conduct-placeholder", "CODE_OF_CONDUCT: no placeholders",
                                  STATUS_FAIL, SEVERITY_P1, f"placeholder text: {match.group(0)!r}", rel))
            break
    else:
        results.append(Result("code-of-conduct-placeholder", "CODE_OF_CONDUCT: no placeholders",
                              STATUS_PASS, SEVERITY_P1, "no placeholder markers", rel))


def check_security(root, results):
    path = find_first(root, ["SECURITY.md", "SECURITY", ".github/SECURITY.md", "docs/SECURITY.md"])
    if path is None:
        results.append(Result("security", "SECURITY.md", STATUS_MISSING, SEVERITY_P1,
                              "no SECURITY.md (needs a real contact route from the user)", "SECURITY.md"))
        return
    rel = path.relative_to(root).as_posix()
    text = read_text(path)
    results.append(Result("security", "SECURITY.md", STATUS_PASS, SEVERITY_P1, "found", rel))

    has_email = bool(EMAIL_RE.search(text))
    has_contact_link = bool(re.search(r"(github\.com/[^/\s]+/[^/\s]+/security/advisories|security@)", text, re.IGNORECASE))
    if has_email or has_contact_link:
        results.append(Result("security-contact", "SECURITY: contact route", STATUS_PASS,
                              SEVERITY_P1, "a contact route is present", rel))
    else:
        results.append(Result("security-contact", "SECURITY: contact route", STATUS_FAIL,
                              SEVERITY_P1, "no email address or advisories link found", rel))

    has_table = bool(re.search(r"\|\s*version", text, re.IGNORECASE)) and "|" in text
    has_supported = bool(re.search(r"supported", text, re.IGNORECASE))
    if has_table and has_supported:
        results.append(Result("security-versions", "SECURITY: supported-versions table", STATUS_PASS,
                              SEVERITY_P2, "found", rel))
    else:
        results.append(Result("security-versions", "SECURITY: supported-versions table", STATUS_FAIL,
                              SEVERITY_P2, "no supported-versions table found", rel))


def check_codeowners(root, results):
    path = find_first(root, ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"])
    if path is None:
        results.append(Result("codeowners", "CODEOWNERS", STATUS_MISSING, SEVERITY_P3,
                              "no CODEOWNERS file", "CODEOWNERS"))
        return
    rel = path.relative_to(root).as_posix()
    text = read_text(path)
    if not text.strip():
        results.append(Result("codeowners", "CODEOWNERS", STATUS_FAIL, SEVERITY_P3, "file is empty", rel))
        return
    results.append(Result("codeowners", "CODEOWNERS", STATUS_PASS, SEVERITY_P3, "found", rel))


def check_issue_templates(root, results):
    directory = find_dir(root, [".github/ISSUE_TEMPLATE", "ISSUE_TEMPLATE", ".issue_template"])
    found_any = False
    if directory is not None:
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".yml", ".yaml", ".md"}:
                continue
            found_any = True
            rel = path.relative_to(root).as_posix()
            text = read_text(path)
            if path.suffix.lower() in {".yml", ".yaml"}:
                try:
                    data = parse_yaml(text)
                except YamlError as exc:
                    results.append(Result(f"issue-template:{path.name}", f"Issue template {path.name}",
                                          STATUS_FAIL, SEVERITY_P1, f"YAML parse error: {exc}", rel))
                    continue
                if not isinstance(data, dict):
                    results.append(Result(f"issue-template:{path.name}", f"Issue template {path.name}",
                                          STATUS_FAIL, SEVERITY_P1, "top level is not a mapping", rel))
                    continue
                if path.name == "config.yml":
                    results.append(Result(f"issue-template:{path.name}", f"Issue template {path.name}",
                                          STATUS_PASS, SEVERITY_P2, "parses as YAML", rel))
                    continue
                missing = [key for key in ("name", "description", "body") if not data.get(key)]
                if missing:
                    results.append(Result(f"issue-template:{path.name}", f"Issue template {path.name}",
                                          STATUS_FAIL, SEVERITY_P1,
                                          "missing required field(s): " + ", ".join(missing), rel))
                else:
                    results.append(Result(f"issue-template:{path.name}", f"Issue template {path.name}",
                                          STATUS_PASS, SEVERITY_P1, "parses as YAML with required fields", rel))
                continue
            # Markdown template: optional YAML frontmatter.
            match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", text, re.DOTALL)
            if match:
                try:
                    data = parse_yaml(match.group(1))
                except YamlError as exc:
                    results.append(Result(f"issue-template:{path.name}", f"Issue template {path.name}",
                                          STATUS_FAIL, SEVERITY_P1, f"frontmatter YAML error: {exc}", rel))
                    continue
                missing = [key for key in ("name", "about") if not (isinstance(data, dict) and data.get(key))]
                if missing:
                    results.append(Result(f"issue-template:{path.name}", f"Issue template {path.name}",
                                          STATUS_FAIL, SEVERITY_P1,
                                          "frontmatter missing: " + ", ".join(missing), rel))
                else:
                    results.append(Result(f"issue-template:{path.name}", f"Issue template {path.name}",
                                          STATUS_PASS, SEVERITY_P1, "frontmatter parses with required fields", rel))
            else:
                results.append(Result(f"issue-template:{path.name}", f"Issue template {path.name}",
                                      STATUS_WARN, SEVERITY_P3, "markdown template without frontmatter", rel))

    if not found_any:
        results.append(Result("issue-templates", "Issue templates", STATUS_MISSING, SEVERITY_P1,
                              "no issue templates found in .github/ISSUE_TEMPLATE", ".github/ISSUE_TEMPLATE"))


def check_pr_template(root, results):
    candidates = [
        ".github/pull_request_template.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/pull_request_template.md",
        "PULL_REQUEST_TEMPLATE.md",
        "docs/pull_request_template.md",
    ]
    directory = find_dir(root, [".github/PULL_REQUEST_TEMPLATE", ".github/pull_request_template"])
    path = find_first(root, candidates)
    if path is None and directory is not None:
        for candidate in sorted(directory.iterdir()):
            if candidate.is_file() and candidate.suffix.lower() == ".md":
                path = candidate
                break
    if path is None:
        results.append(Result("pr-template", "Pull request template", STATUS_MISSING, SEVERITY_P1,
                              "no pull request template found", ".github/pull_request_template.md"))
        return
    rel = path.relative_to(root).as_posix()
    text = read_text(path)
    if not text.strip():
        results.append(Result("pr-template", "Pull request template", STATUS_FAIL, SEVERITY_P1,
                              "template is empty", rel))
        return
    results.append(Result("pr-template", "Pull request template", STATUS_PASS, SEVERITY_P1, "found", rel))

    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", text, re.DOTALL)
    if match:
        try:
            data = parse_yaml(match.group(1))
        except YamlError as exc:
            results.append(Result("pr-template-frontmatter", "PR template frontmatter", STATUS_FAIL,
                                  SEVERITY_P2, f"YAML error: {exc}", rel))
            return
        missing = [key for key in ("name", "description", "body") if not (isinstance(data, dict) and data.get(key))]
        if missing:
            results.append(Result("pr-template-frontmatter", "PR template frontmatter", STATUS_FAIL,
                                  SEVERITY_P2, "missing: " + ", ".join(missing), rel))
        else:
            results.append(Result("pr-template-frontmatter", "PR template frontmatter", STATUS_PASS,
                                  SEVERITY_P2, "parses as YAML with required fields", rel))
    else:
        has_checklist = bool(re.search(r"^\s*[-*]\s+\[[ xX]\]", text, re.MULTILINE))
        has_sections = bool(re.search(r"^#{1,4}\s+", text, re.MULTILINE))
        if has_checklist or has_sections:
            results.append(Result("pr-template-body", "PR template body", STATUS_PASS, SEVERITY_P3,
                                  "has sections or a checklist", rel))
        else:
            results.append(Result("pr-template-body", "PR template body", STATUS_WARN, SEVERITY_P3,
                                  "no sections or checklist in the template body", rel))


def check_funding(root, results):
    path = find_first(root, [".github/FUNDING.yml", ".github/FUNDING.yaml", "FUNDING.yml"])
    if path is None:
        results.append(Result("funding", ".github/FUNDING.yml", STATUS_MISSING, SEVERITY_P3,
                              "no funding configuration", ".github/FUNDING.yml"))
        return
    rel = path.relative_to(root).as_posix()
    text = read_text(path)
    try:
        data = parse_yaml(text)
    except YamlError as exc:
        results.append(Result("funding", ".github/FUNDING.yml", STATUS_FAIL, SEVERITY_P3,
                              f"YAML parse error: {exc}", rel))
        return
    if isinstance(data, dict) and data:
        results.append(Result("funding", ".github/FUNDING.yml", STATUS_PASS, SEVERITY_P3,
                              f"parses as YAML with {len(data)} platform(s)", rel))
    else:
        results.append(Result("funding", ".github/FUNDING.yml", STATUS_FAIL, SEVERITY_P3,
                              "no funding platform configured", rel))


def check_editorconfig(root, results):
    path = root / ".editorconfig"
    if not path.is_file():
        results.append(Result("editorconfig", ".editorconfig", STATUS_MISSING, SEVERITY_P3,
                              "no .editorconfig", ".editorconfig"))
        return
    text = read_text(path)
    rel = ".editorconfig"
    if "root = true" not in text:
        results.append(Result("editorconfig", ".editorconfig", STATUS_WARN, SEVERITY_P3,
                              "missing 'root = true'", rel))
    else:
        results.append(Result("editorconfig", ".editorconfig", STATUS_PASS, SEVERITY_P3, "found", rel))


def detect_stacks(root: Path):
    """Return the set of language stacks visible in the repo root."""
    stacks = set()
    if (root / "package.json").is_file():
        stacks.add("node")
    if (root / "pyproject.toml").is_file() or (root / "setup.py").is_file() \
            or (root / "requirements.txt").is_file():
        stacks.add("python")
    if (root / "Cargo.toml").is_file():
        stacks.add("rust")
    if (root / "go.mod").is_file():
        stacks.add("go")
    if (root / "pom.xml").is_file() or (root / "build.gradle").is_file() \
            or (root / "build.gradle.kts").is_file():
        stacks.add("java")
    if (root / "Gemfile").is_file():
        stacks.add("ruby")
    if (root / "composer.json").is_file():
        stacks.add("php")
    if (root / "mix.exs").is_file():
        stacks.add("elixir")
    if (root / "global.json").is_file() or find_first(root, ["*.csproj", "*.sln"]) is not None:
        stacks.add("dotnet")
    return stacks


def gitignore_covers(lines, path: str) -> bool:
    """True when a .gitignore entry list would ignore the given concrete path.

    Follows gitignore semantics: an entry matches the path itself and
    everything under it, and glob patterns are matched with fnmatch.
    """
    normalized = path.rstrip("/")
    for line in lines:
        entry = line.strip().rstrip("/")
        if not entry:
            continue
        if entry == "*":
            return True
        if entry == normalized:
            return True
        if normalized.startswith(entry + "/"):
            return True
        if fnmatch(normalized, entry):
            return True
        if fnmatch(normalized, entry + "/*"):
            return True
    return False


def check_gitignore(root, results):
    path = root / ".gitignore"
    if not path.is_file():
        results.append(Result("gitignore", ".gitignore", STATUS_MISSING, SEVERITY_P0,
                              "no .gitignore", ".gitignore"))
        return
    rel = ".gitignore"
    text = read_text(path)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)

    stacks = detect_stacks(root)
    required = []
    optional = []
    for stack in sorted(stacks):
        required.extend(REQUIRED_IGNORE_BY_STACK.get(stack, []))
        optional.extend(OPTIONAL_IGNORE_BY_STACK.get(stack, []))
    required = sorted(set(required))
    optional = sorted(set(optional) - set(required))

    if not stacks:
        results.append(Result("gitignore-build", ".gitignore: build output", STATUS_PASS,
                              SEVERITY_P3, "no language stack detected; nothing to check", rel))
        missing_optional = []
    else:
        missing_required = [item for item in required if not gitignore_covers(lines, item)]
        if missing_required:
            results.append(Result("gitignore-build", ".gitignore: build output", STATUS_FAIL,
                                  SEVERITY_P1, "not ignored: " + ", ".join(missing_required), rel))
        else:
            results.append(Result("gitignore-build", ".gitignore: build output", STATUS_PASS,
                                  SEVERITY_P1,
                                  f"build output for {', '.join(sorted(stacks))} is ignored", rel))
        missing_optional = [item for item in optional if not gitignore_covers(lines, item)]

    if missing_optional:
        results.append(Result("gitignore-build-extra", ".gitignore: other build output", STATUS_WARN,
                              SEVERITY_P3, "not ignored: " + ", ".join(missing_optional), rel))
    else:
        results.append(Result("gitignore-build-extra", ".gitignore: other build output", STATUS_PASS,
                              SEVERITY_P3, "common build output is ignored", rel))

    if not gitignore_covers(lines, ".env"):
        results.append(Result("gitignore-env", ".gitignore: environment files", STATUS_FAIL,
                              SEVERITY_P0, ".env is not ignored", rel))
    else:
        results.append(Result("gitignore-env", ".gitignore: environment files", STATUS_PASS,
                              SEVERITY_P0, ".env is ignored", rel))

    missing_env_variants = [item for item in ENV_VARIANT_SAMPLES
                            if not gitignore_covers(lines, item)]
    if missing_env_variants:
        results.append(Result("gitignore-env-variants", ".gitignore: env file variants", STATUS_WARN,
                              SEVERITY_P1, "not ignored: " + ", ".join(missing_env_variants), rel))
    else:
        results.append(Result("gitignore-env-variants", ".gitignore: env file variants", STATUS_PASS,
                              SEVERITY_P1, "env file variants are ignored", rel))

    if re.search(r"^\*\.pem$|^\.pem$|id_rsa|\.p12$|^\*\.key$|^\.key$", text, re.MULTILINE):
        results.append(Result("gitignore-secrets", ".gitignore: secret material", STATUS_PASS,
                              SEVERITY_P2, "key material is ignored", rel))
    else:
        results.append(Result("gitignore-secrets", ".gitignore: secret material", STATUS_WARN,
                              SEVERITY_P2, "no private key patterns (.pem, id_rsa, .key)", rel))


def check_env_example(root, results):
    path = find_first(root, [".env.example", ".env.sample", ".env.template", "env.example",
                             ".env.dist", ".env.defaults"])
    if path is None:
        results.append(Result("env-example", ".env.example", STATUS_MISSING, SEVERITY_P2,
                              "no .env.example (only needed when the project reads env vars)", ".env.example"))
        return
    rel = path.relative_to(root).as_posix()
    text = read_text(path)
    results.append(Result("env-example", ".env.example", STATUS_PASS, SEVERITY_P2, "found", rel))
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if value.strip() and not re.search(r"your|changeme|example|placeholder|xxx|todo", value, re.IGNORECASE):
            results.append(Result("env-example-secrets", ".env.example: no real values", STATUS_WARN,
                                  SEVERITY_P1, f"line assigns a literal value: {key.strip()}", rel))
            break
    else:
        results.append(Result("env-example-secrets", ".env.example: no real values", STATUS_PASS,
                              SEVERITY_P1, "only empty or placeholder values", rel))


def check_agent_instructions(root, results):
    path = find_first(root, ["AGENTS.md", "CLAUDE.md", ".github/AGENTS.md", ".github/CLAUDE.md",
                             "docs/AGENTS.md"])
    if path is None:
        results.append(Result("agent-instructions", "AGENTS.md / CLAUDE.md", STATUS_MISSING,
                              SEVERITY_P1, "no agent-facing instructions file", "AGENTS.md"))
        return
    rel = path.relative_to(root).as_posix()
    text = read_text(path)
    if len(text.strip()) < 40:
        results.append(Result("agent-instructions", "AGENTS.md / CLAUDE.md", STATUS_FAIL,
                              SEVERITY_P1, "file is present but too short to be useful", rel))
        return
    results.append(Result("agent-instructions", "AGENTS.md / CLAUDE.md", STATUS_PASS,
                          SEVERITY_P1, "found", rel))
    has_commands = bool(re.search(r"(npm|pnpm|yarn|bun|make|cargo|go test|pytest|poetry run|uv run)", text))
    if has_commands:
        results.append(Result("agent-commands", "Agent file: build/test commands", STATUS_PASS,
                              SEVERITY_P1, "commands are mentioned", rel))
    else:
        results.append(Result("agent-commands", "Agent file: build/test commands", STATUS_FAIL,
                              SEVERITY_P1, "no build/test/lint commands mentioned", rel))


def check_automation(root, results):
    dependabot = find_first(root, [".github/dependabot.yml", ".github/dependabot.yaml",
                                   ".github/dependabot.json"])
    renovate = find_first(root, ["renovate.json", ".renovaterc", ".renovaterc.json", ".github/renovate.json",
                                  ".github/renovate.json5"])
    if dependabot is not None:
        results.append(Result("dependency-automation", "Dependency automation", STATUS_PASS,
                              SEVERITY_P2, "Dependabot configured", ".github/dependabot.yml"))
    elif renovate is not None:
        results.append(Result("dependency-automation", "Dependency automation", STATUS_PASS,
                              SEVERITY_P2, "Renovate configured", renovate.relative_to(root).as_posix()))
    else:
        results.append(Result("dependency-automation", "Dependency automation", STATUS_MISSING,
                              SEVERITY_P3, "no Dependabot or Renovate configuration", ".github/dependabot.yml"))

    workflows_dir = find_dir(root, [".github/workflows"])
    release_workflow = None
    if workflows_dir is not None:
        for candidate in sorted(workflows_dir.iterdir()):
            if not candidate.is_file():
                continue
            name = candidate.name.lower()
            if "release" in name or "publish" in name:
                release_workflow = candidate
                break
    if release_workflow is not None:
        results.append(Result("release-workflow", "Release workflow", STATUS_PASS, SEVERITY_P2,
                              "found", release_workflow.relative_to(root).as_posix()))
    else:
        results.append(Result("release-workflow", "Release workflow", STATUS_MISSING, SEVERITY_P3,
                              "no release or publish workflow in .github/workflows", ".github/workflows"))

    labels_config = find_first(root, [".github/labels.yml", ".github/labels.yaml", ".github/labels.json"])
    if labels_config is not None:
        results.append(Result("labels-config", "Label configuration", STATUS_PASS, SEVERITY_P3,
                              "found", labels_config.relative_to(root).as_posix()))
    else:
        results.append(Result("labels-config", "Label configuration", STATUS_MISSING, SEVERITY_P3,
                              "no label config file (GitHub-side labels are checked with gh)", ".github/labels.yml"))


def check_docs(root, results):
    directory = find_dir(root, ["docs", "doc", "documentation"])
    if directory is None:
        results.append(Result("docs", "docs/ structure", STATUS_MISSING, SEVERITY_P3,
                              "no docs directory (add one only if the project warrants it)", "docs/"))
        return
    entries = [item for item in directory.rglob("*") if item.is_file()]
    results.append(Result("docs", "docs/ structure", STATUS_PASS if entries else STATUS_WARN,
                          SEVERITY_P3, f"{len(entries)} file(s) under {directory.relative_to(root).as_posix()}",
                          directory.relative_to(root).as_posix()))


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def print_report(results, root: Path) -> None:
    order = {STATUS_FAIL: 0, STATUS_MISSING: 1, STATUS_WARN: 2, STATUS_PASS: 3}
    grouped = {}
    for result in results:
        grouped.setdefault(result.status, []).append(result)

    print(f"Repository hygiene audit: {root}")
    print("=" * 72)
    counts = {}
    for status in (STATUS_PASS, STATUS_WARN, STATUS_MISSING, STATUS_FAIL):
        counts[status] = len(grouped.get(status, []))
    print(
        f"pass {counts[STATUS_PASS]}  |  warn {counts[STATUS_WARN]}  |  "
        f"missing {counts[STATUS_MISSING]}  |  fail {counts[STATUS_FAIL]}"
    )
    print()

    for status in (STATUS_FAIL, STATUS_MISSING, STATUS_WARN, STATUS_PASS):
        items = grouped.get(status, [])
        if not items:
            continue
        print(f"--- {status.upper()} " + "-" * max(0, 68 - len(status)))
        for result in sorted(items, key=lambda item: (item.severity, item.check_id)):
            location = f" ({result.path})" if result.path else ""
            print(f"[{result.severity}] {result.name}{location}: {result.detail}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit a repository's governance and agent-facing artifacts."
    )
    parser.add_argument("repo_root", help="Path to the repository root to audit")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 when a P0 check fails")
    args = parser.parse_args()

    root = Path(args.repo_root).expanduser().resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    results = []
    check_license(root, results)
    check_readme(root, results)
    check_contributing(root, results)
    check_code_of_conduct(root, results)
    check_security(root, results)
    check_codeowners(root, results)
    check_issue_templates(root, results)
    check_pr_template(root, results)
    check_funding(root, results)
    check_editorconfig(root, results)
    check_gitignore(root, results)
    check_env_example(root, results)
    check_agent_instructions(root, results)
    check_automation(root, results)
    check_docs(root, results)

    if args.json:
        payload = {
            "repo_root": str(root),
            "summary": {
                "pass": sum(1 for item in results if item.status == STATUS_PASS),
                "warn": sum(1 for item in results if item.status == STATUS_WARN),
                "missing": sum(1 for item in results if item.status == STATUS_MISSING),
                "fail": sum(1 for item in results if item.status == STATUS_FAIL),
            },
            "checks": [item.to_dict() for item in results],
        }
        json.dump(payload, sys.stdout, indent=2, sort_keys=False)
        sys.stdout.write("\n")
    else:
        print_report(results, root)

    if args.strict and any(
        item.status in (STATUS_FAIL, STATUS_MISSING) and item.severity == SEVERITY_P0
        for item in results
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
