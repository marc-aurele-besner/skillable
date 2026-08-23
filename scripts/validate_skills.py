#!/usr/bin/env python3
"""Validate Skillable skills against repo conventions and the Agent Skills spec.

Checks:
  - Directory layout (SKILL.md required; optional supporting files)
  - YAML frontmatter (required name/description, allowed fields, name format)
  - SKILL.md body length, leftover template copy, broken relative links
  - README.md "Available skills" table lists every published skill

On pull requests, newly added skill directories are called out explicitly and
must appear in README.md.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
README_PATH = REPO_ROOT / "README.md"
TEMPLATE_DIR_NAME = "_template"

MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_COMPATIBILITY_LENGTH = 500
MAX_SKILL_MD_LINES = 500
MIN_DESCRIPTION_LENGTH = 40

GENERIC_NAMES = frozenset({"helper", "utils", "tools", "tool", "misc", "other"})

SPEC_FIELDS = frozenset(
    {
        "name",
        "description",
        "license",
        "compatibility",
        "metadata",
        "allowed-tools",
    }
)
CURSOR_FIELDS = frozenset(
    {
        "paths",
        "globs",
        "disable-model-invocation",
        "icon",
        "color",
        "argument-hint",
    }
)
ALLOWED_FIELDS = SPEC_FIELDS | CURSOR_FIELDS

CURSOR_COLORS = frozenset(
    {
        "default",
        "green",
        "cyan",
        "blue",
        "purple",
        "magenta",
        "orange",
        "yellow",
        "red",
        "brand",
    }
)

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
README_ROW_RE = re.compile(
    r"^\|\s*\[([^\]]+)\]\((skills/[^)]+)\)\s*\|\s*(.+?)\s*\|\s*$"
)
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
TEMPLATE_LEFTOVERS = (
    "your-skill-name",
    "Scenario 1 where this skill applies",
    "User request: \"...\"",
    "Brief overview of the skill's purpose (1–2 sentences).",
)

SECRET_PATTERNS = (
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "possible OpenAI-style API key"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "possible GitHub personal access token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "possible GitHub fine-grained token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "possible AWS access key"),
)

FIRST_PERSON_RE = re.compile(
    r"^(i|i'm|i'll|you|you'll|you can|we|we'll)\b", re.IGNORECASE
)


class Issue:
    def __init__(self, path: Path, message: str, line: int | None = None) -> None:
        self.path = path
        self.message = message
        self.line = line

    def __str__(self) -> str:
        rel = self.path.relative_to(REPO_ROOT).as_posix()
        loc = f"{rel}:{self.line}" if self.line else rel
        return f"{loc}: {self.message}"

    def github_annotation(self) -> str:
        rel = self.path.relative_to(REPO_ROOT).as_posix()
        loc = f"file={rel}"
        if self.line:
            loc += f",line={self.line}"
        return f"::error {loc}::{self.message}"


def _parse_scalar(value: str):
    value = value.strip()
    if value == "":
        return None
    lowered = value.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if lowered in {"null", "~"}:
        return None
    if (len(value) >= 2) and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _collect_indented_block(lines: list[str], start: int) -> tuple[list[str], int]:
    collected: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            collected.append("")
            index += 1
            continue
        if not line.startswith((" ", "\t")):
            break
        collected.append(line)
        index += 1
    while collected and collected[-1] == "":
        collected.pop()
    return collected, index


def parse_frontmatter_mapping(raw: str) -> dict:
    """Parse the YAML subset used in SKILL.md frontmatter (stdlib only)."""
    lines = raw.splitlines()
    data: dict = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line.startswith((" ", "\t")):
            raise ValueError(f"unexpected indentation in frontmatter: {line!r}")
        if ":" not in line:
            raise ValueError(f"expected 'key: value' in frontmatter, got {line!r}")

        key, rest = line.split(":", 1)
        key = key.strip()
        rest = rest.strip()
        if not key:
            raise ValueError(f"missing frontmatter key in {line!r}")

        if rest in {">", ">-", ">+", "|", "|-", "|+"}:
            block, index = _collect_indented_block(lines, index + 1)
            stripped = [item[2:] if item.startswith("  ") else item.lstrip("\t") for item in block]
            if rest.startswith(">"):
                data[key] = " ".join(part.strip() for part in stripped if part.strip())
            else:
                data[key] = "\n".join(stripped).strip("\n")
            continue

        if rest == "":
            block, index = _collect_indented_block(lines, index + 1)
            if not block:
                data[key] = None
                continue
            if all(item.lstrip().startswith("- ") or item == "" for item in block):
                data[key] = [_parse_scalar(item.lstrip()[2:]) for item in block if item.strip()]
                continue
            nested: dict = {}
            for item in block:
                if not item.strip() or item.lstrip().startswith("#"):
                    continue
                nested_line = item.lstrip()
                if ":" not in nested_line:
                    raise ValueError(f"expected nested 'key: value', got {item!r}")
                nested_key, nested_rest = nested_line.split(":", 1)
                nested[nested_key.strip()] = _parse_scalar(nested_rest)
            data[key] = nested
            continue

        data[key] = _parse_scalar(rest)
        index += 1
    return data


def parse_frontmatter(text: str, skill_md: Path) -> tuple[dict | None, str, list[Issue]]:
    issues: list[Issue] = []
    if not text.startswith("---"):
        issues.append(Issue(skill_md, "SKILL.md must start with YAML frontmatter (---)"))
        return None, text, issues

    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", text, re.DOTALL)
    if not match:
        issues.append(Issue(skill_md, "SKILL.md frontmatter is not closed with a second ---"))
        return None, text, issues

    raw = match.group(1)
    body = text[match.end() :]
    try:
        data = parse_frontmatter_mapping(raw)
    except ValueError as exc:
        issues.append(Issue(skill_md, f"Invalid YAML frontmatter: {exc}", line=1))
        return None, body, issues

    if not data:
        issues.append(Issue(skill_md, "YAML frontmatter is empty", line=1))
        return None, body, issues
    return data, body, issues


def validate_name(name: object, skill_dir: Path, skill_md: Path) -> list[Issue]:
    issues: list[Issue] = []
    if not isinstance(name, str) or not name.strip():
        issues.append(Issue(skill_md, "Frontmatter field 'name' must be a non-empty string", line=1))
        return issues

    name = name.strip()
    if len(name) > MAX_NAME_LENGTH:
        issues.append(
            Issue(
                skill_md,
                f"name '{name}' exceeds {MAX_NAME_LENGTH} characters ({len(name)})",
                line=1,
            )
        )
    if not NAME_RE.fullmatch(name):
        issues.append(
            Issue(
                skill_md,
                "name must be lowercase letters, numbers, and single hyphens only "
                "(no leading, trailing, or consecutive hyphens)",
                line=1,
            )
        )
    if name != skill_dir.name:
        issues.append(
            Issue(
                skill_md,
                f"name '{name}' must match the parent directory name '{skill_dir.name}'",
                line=1,
            )
        )
    if name in GENERIC_NAMES:
        issues.append(
            Issue(
                skill_md,
                f"name '{name}' is too generic; use a specific hyphenated workflow name",
                line=1,
            )
        )
    return issues


def validate_description(description: object, skill_md: Path, *, is_new: bool) -> list[Issue]:
    issues: list[Issue] = []
    if not isinstance(description, str) or not description.strip():
        issues.append(
            Issue(skill_md, "Frontmatter field 'description' must be a non-empty string", line=1)
        )
        return issues

    text = " ".join(description.split())
    if len(text) > MAX_DESCRIPTION_LENGTH:
        issues.append(
            Issue(
                skill_md,
                f"description exceeds {MAX_DESCRIPTION_LENGTH} characters ({len(text)})",
                line=1,
            )
        )
    if len(text) < MIN_DESCRIPTION_LENGTH:
        issues.append(
            Issue(
                skill_md,
                f"description is too short ({len(text)} chars); include what the skill "
                f"does and when the agent should use it",
                line=1,
            )
        )
    if FIRST_PERSON_RE.match(text):
        issues.append(
            Issue(
                skill_md,
                "description must be written in third person "
                "(do not start with I/you/we)",
                line=1,
            )
        )
    if is_new and not re.search(r"\b(use|when|whenever)\b", text, re.IGNORECASE):
        issues.append(
            Issue(
                skill_md,
                "description should include trigger language (what the skill does and "
                "when to use it)",
                line=1,
            )
        )
    return issues


def validate_optional_fields(meta: dict, skill_md: Path) -> list[Issue]:
    issues: list[Issue] = []
    extra = sorted(set(meta) - ALLOWED_FIELDS)
    if extra:
        allowed = ", ".join(sorted(ALLOWED_FIELDS))
        issues.append(
            Issue(
                skill_md,
                f"Unexpected frontmatter fields: {', '.join(extra)}. Allowed: {allowed}",
                line=1,
            )
        )

    compatibility = meta.get("compatibility")
    if compatibility is not None:
        if not isinstance(compatibility, str):
            issues.append(Issue(skill_md, "compatibility must be a string", line=1))
        elif len(compatibility) > MAX_COMPATIBILITY_LENGTH:
            issues.append(
                Issue(
                    skill_md,
                    f"compatibility exceeds {MAX_COMPATIBILITY_LENGTH} characters",
                    line=1,
                )
            )

    metadata = meta.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        issues.append(Issue(skill_md, "metadata must be a mapping", line=1))

    allowed_tools = meta.get("allowed-tools")
    if allowed_tools is not None and not isinstance(allowed_tools, str):
        issues.append(Issue(skill_md, "allowed-tools must be a space-separated string", line=1))

    disable = meta.get("disable-model-invocation")
    if disable is not None and not isinstance(disable, bool):
        issues.append(Issue(skill_md, "disable-model-invocation must be a boolean", line=1))

    color = meta.get("color")
    if color is not None:
        if not isinstance(color, str) or color not in CURSOR_COLORS:
            issues.append(
                Issue(
                    skill_md,
                    "color must be one of: " + ", ".join(sorted(CURSOR_COLORS)),
                    line=1,
                )
            )

    paths = meta.get("paths")
    if paths is not None and not isinstance(paths, (str, list)):
        issues.append(Issue(skill_md, "paths must be a glob string or a list of globs", line=1))

    argument_hint = meta.get("argument-hint")
    if argument_hint is not None and not isinstance(argument_hint, str):
        issues.append(Issue(skill_md, "argument-hint must be a string", line=1))

    return issues


def validate_body(body: str, skill_dir: Path, skill_md: Path) -> list[Issue]:
    issues: list[Issue] = []
    lines = skill_md.read_text(encoding="utf-8").splitlines()
    if len(lines) > MAX_SKILL_MD_LINES:
        issues.append(
            Issue(
                skill_md,
                f"SKILL.md is {len(lines)} lines; keep it under {MAX_SKILL_MD_LINES} "
                "and move detail into reference files",
                line=MAX_SKILL_MD_LINES + 1,
            )
        )

    if not body.strip():
        issues.append(Issue(skill_md, "SKILL.md is missing a markdown body after the frontmatter"))

    if "\\" in body and re.search(r"[A-Za-z0-9_]\.[A-Za-z0-9]+\\|[A-Za-z0-9_]+\\[A-Za-z0-9_]", body):
        issues.append(
            Issue(skill_md, "Use forward slashes in paths (scripts/helper.py), not Windows-style backslashes")
        )

    full_text = skill_md.read_text(encoding="utf-8")
    for pattern, label in SECRET_PATTERNS:
        if pattern.search(full_text):
            issues.append(Issue(skill_md, f"Possible secret detected ({label}); do not commit credentials"))

    for leftover in TEMPLATE_LEFTOVERS:
        if leftover in body:
            issues.append(
                Issue(
                    skill_md,
                    f"Looks like leftover template text ({leftover!r}); replace the "
                    "template with real skill instructions",
                )
            )
            break

    for link in MD_LINK_RE.findall(body):
        target = link.split("#", 1)[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        resolved = (skill_dir / target).resolve()
        try:
            resolved.relative_to(skill_dir.resolve())
        except ValueError:
            issues.append(Issue(skill_md, f"Relative link '{target}' points outside the skill directory"))
            continue
        if not resolved.exists():
            issues.append(Issue(skill_md, f"Broken relative link: {target}"))

    scripts_dir = skill_dir / "scripts"
    if scripts_dir.is_dir() and any(scripts_dir.iterdir()):
        if "scripts/" not in body:
            issues.append(
                Issue(
                    skill_md,
                    "scripts/ exists but SKILL.md never references scripts/; document how to run them",
                )
            )

    return issues


def validate_skill(skill_dir: Path, *, is_new: bool) -> list[Issue]:
    issues: list[Issue] = []
    is_template = skill_dir.name == TEMPLATE_DIR_NAME
    skill_md = skill_dir / "SKILL.md"

    if not NAME_RE.fullmatch(skill_dir.name) and not is_template:
        issues.append(
            Issue(
                skill_dir,
                "Skill directory name must be lowercase letters, numbers, and single hyphens",
            )
        )

    if not skill_md.is_file():
        issues.append(Issue(skill_dir, "Missing required file: SKILL.md"))
        return issues

    text = skill_md.read_text(encoding="utf-8")
    meta, body, fm_issues = parse_frontmatter(text, skill_md)
    issues.extend(fm_issues)
    if meta is None:
        return issues

    issues.extend(validate_optional_fields(meta, skill_md))

    if is_template:
        if "name" not in meta:
            issues.append(Issue(skill_md, "Missing required field in frontmatter: name", line=1))
        if "description" not in meta:
            issues.append(Issue(skill_md, "Missing required field in frontmatter: description", line=1))
        return issues

    if "name" not in meta:
        issues.append(Issue(skill_md, "Missing required field in frontmatter: name", line=1))
    else:
        issues.extend(validate_name(meta["name"], skill_dir, skill_md))

    if "description" not in meta:
        issues.append(Issue(skill_md, "Missing required field in frontmatter: description", line=1))
    else:
        issues.extend(validate_description(meta["description"], skill_md, is_new=is_new))

    issues.extend(validate_body(body, skill_dir, skill_md))
    return issues


def published_skill_dirs() -> list[Path]:
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir() and not path.name.startswith("."))


def parse_readme_table(readme: Path) -> tuple[dict[str, str], list[Issue]]:
    issues: list[Issue] = []
    if not readme.is_file():
        return {}, [Issue(readme, "README.md is missing")]

    rows: dict[str, str] = {}
    in_table = False
    seen_header = False
    for line_no, line in enumerate(readme.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip() == "## Available skills":
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        if not in_table:
            continue
        if not line.startswith("|"):
            continue
        if re.match(r"^\|\s*[-:| ]+\|\s*$", line):
            seen_header = True
            continue
        if not seen_header:
            continue
        match = README_ROW_RE.match(line)
        if not match:
            issues.append(
                Issue(
                    readme,
                    "Skill table row must be `| [name](skills/name/) | description |`",
                    line=line_no,
                )
            )
            continue
        name, href, description = match.group(1), match.group(2), match.group(3).strip()
        href_name = href.rstrip("/").removeprefix("skills/")
        if name != href_name:
            issues.append(
                Issue(
                    readme,
                    f"Skill table link text '{name}' does not match target '{href}'",
                    line=line_no,
                )
            )
        if not description:
            issues.append(Issue(readme, f"Skill '{name}' is missing a description in README", line=line_no))
        if name in rows:
            issues.append(Issue(readme, f"Skill '{name}' is listed more than once in README", line=line_no))
        rows[name] = description

    if not rows:
        issues.append(Issue(readme, "README.md is missing an 'Available skills' table"))
    return rows, issues


def git_skill_dirs_at(ref: str) -> set[str] | None:
    try:
        result = subprocess.run(
            ["git", "ls-tree", "-d", "--name-only", f"{ref}:skills"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def resolve_base_ref(cli_base: str | None) -> str | None:
    if cli_base:
        return cli_base
    sha = os.environ.get("SKILLABLE_BASE_SHA") or os.environ.get("GITHUB_BASE_SHA")
    if sha:
        return sha
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if base_ref:
        return f"origin/{base_ref}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Skillable skills and README catalog entries.")
    parser.add_argument(
        "--base",
        help="Git ref to diff against when detecting newly added skill directories (e.g. origin/main)",
    )
    args = parser.parse_args()

    issues: list[Issue] = []
    skill_dirs = published_skill_dirs()
    if not skill_dirs:
        issues.append(Issue(SKILLS_DIR, "No skill directories found under skills/"))

    base_ref = resolve_base_ref(args.base)
    previous_dirs = git_skill_dirs_at(base_ref) if base_ref else None
    current_names = {path.name for path in skill_dirs}
    new_names = sorted(current_names - previous_dirs) if previous_dirs is not None else []

    readme_rows, readme_issues = parse_readme_table(README_PATH)
    issues.extend(readme_issues)

    listed = set(readme_rows)
    for missing in sorted(current_names - listed):
        issues.append(
            Issue(
                README_PATH,
                f"New or unpublished skill '{missing}' is not listed in the README "
                "'Available skills' table. Add a row: "
                f"| [{missing}](skills/{missing}/) | <short description> |",
            )
        )
    for stale in sorted(listed - current_names):
        issues.append(
            Issue(
                README_PATH,
                f"README lists skill '{stale}' but skills/{stale}/ does not exist",
            )
        )

    names = list(readme_rows)
    if TEMPLATE_DIR_NAME in names and names[0] != TEMPLATE_DIR_NAME:
        issues.append(
            Issue(
                README_PATH,
                f"'{TEMPLATE_DIR_NAME}' should be the first row in the Available skills table",
            )
        )

    catalog = [name for name in readme_rows if name != TEMPLATE_DIR_NAME]
    if catalog != sorted(catalog):
        issues.append(
            Issue(
                README_PATH,
                "Available skills table must list skills alphabetically "
                f"(expected: {', '.join(sorted(catalog))})",
            )
        )

    for skill_dir in skill_dirs:
        issues.extend(validate_skill(skill_dir, is_new=skill_dir.name in set(new_names)))

    in_github = os.environ.get("GITHUB_ACTIONS") == "true"
    if new_names:
        print("New skill directories in this PR:")
        for name in new_names:
            print(f"  - {name}")
        print()
    elif base_ref:
        print(f"No new skill directories compared with {base_ref}.")
        print()

    if issues:
        print(f"Skill validation failed ({len(issues)} issue(s)):\n")
        for issue in issues:
            print(f"  - {issue}")
            if in_github:
                print(issue.github_annotation())
        return 1

    print(f"OK: {len(skill_dirs)} skill(s) passed structure, formatting, and README checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
