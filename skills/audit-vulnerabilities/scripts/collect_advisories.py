#!/usr/bin/env python3
"""Normalize advisory output from ecosystem auditors into a single table.

Runs the target project's own auditor (npm, pnpm, yarn, pip-audit, cargo,
osv-scanner, govulncheck) and converts whatever JSON it emits into one
normalized list of advisories:

    python3 -I scripts/collect_advisories.py --tool npm --json
    python3 -I scripts/collect_advisories.py --tool npm
    python3 -I scripts/collect_advisories.py --tool pip-audit --cwd ./service
    python3 -I scripts/collect_advisories.py --tool auto --json

Stdlib only, Python 3.8+. Read-only: it invokes an auditor, it never installs,
updates, or writes into the audited project.

Exit codes:
  0  the auditor ran and its output was parsed (advisories may be present)
  1  usage error
  2  the auditor is missing, failed, or produced unparsable output
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SEVERITY_ORDER = ["critical", "high", "medium", "low", "unknown"]
SEVERITY_ALIASES = {
    "critical": "critical",
    "high": "high",
    "moderate": "medium",
    "medium": "medium",
    "low": "low",
    "minor": "low",
    "info": "low",
    "informational": "low",
    "none": "unknown",
    "unknown": "unknown",
}

GHSA_RE = re.compile(r"GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}")
CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def normalize_severity(value: object) -> str:
    """Map any tool's severity string onto critical/high/medium/low/unknown."""
    if value is None:
        return "unknown"
    text = str(value).strip().lower()
    if not text:
        return "unknown"
    if text in SEVERITY_ALIASES:
        return SEVERITY_ALIASES[text]
    match = re.search(r"(critical|high|moderate|medium|low)", text)
    if match:
        return SEVERITY_ALIASES.get(match.group(1), "unknown")
    return "unknown"


def clean_version(value: object) -> str:
    """Reduce a patched-version field to a single comparable version string."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        parts = [clean_version(item) for item in value]
        parts = [part for part in parts if part]
        return parts[0] if parts else ""
    text = str(value).strip()
    if not text:
        return ""
    # ">=1.2.3" / "> 0.1.0" / "1.2.3, <2.0.0" / "^1.2.3" / "~1.2.3"
    text = text.split(",")[0].strip()
    text = re.sub(r"^[<>=~^v\s]+", "", text).strip()
    text = text.split()[0] if text.split() else ""
    return text


def extract_ids(*sources: object) -> tuple[str, list[str]]:
    """Return (primary_id, aliases) from advisory URLs, ids and alias lists."""
    primary = ""
    aliases: list[str] = []

    def add(text: object) -> None:
        nonlocal primary
        raw = str(text or "")
        for token in GHSA_RE.findall(raw):
            if not primary:
                primary = token
            elif token != primary:
                aliases.append(token)
        for token in CVE_RE.findall(raw):
            if not primary:
                primary = token
            elif token != primary and token not in aliases:
                aliases.append(token)

    for source in sources:
        if source is None:
            continue
        if isinstance(source, (list, tuple)):
            for item in source:
                add(item)
        else:
            add(source)
    return primary, sorted(set(aliases))


def pick_id(native: str, *sources: object) -> tuple[str, list[str]]:
    """Keep the ecosystem-native advisory id primary, GHSA/CVE as aliases.

    RUSTSEC-, GO-, PYSEC- and GHSA- ids are all meaningful; prefer the one the
    source itself used, and keep the other identifiers discoverable.
    """
    native = str(native or "").strip()
    found, aliases = extract_ids(*sources)
    if native:
        if found and found != native:
            aliases = sorted(set(aliases) | {found})
        return native, aliases
    return found, aliases


# --------------------------------------------------------------------------
# CVSS v3 base score (used when a source exposes only a vector)
# --------------------------------------------------------------------------

_CVSS3_WEIGHTS = {
    "AV": {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2},
    "AC": {"L": 0.77, "H": 0.44},
    "UI": {"N": 0.85, "R": 0.62},
    "C": {"H": 0.56, "L": 0.22, "N": 0.0},
    "I": {"H": 0.56, "L": 0.22, "N": 0.0},
    "A": {"H": 0.56, "L": 0.22, "N": 0.0},
}
_CVSS3_PR_UNCHANGED = {"N": 0.85, "L": 0.62, "H": 0.27}
_CVSS3_PR_CHANGED = {"N": 0.85, "L": 0.68, "H": 0.5}


def _roundup(value: float) -> float:
    scaled = int(round(value * 100000))
    if scaled % 10000 == 0:
        return scaled / 100000.0
    return (scaled // 10000 + 1) / 10.0


def cvss3_base_score(vector: str) -> float | None:
    """Compute a CVSS v3.x base score from a vector string, or None."""
    if not vector or "/" not in vector:
        return None
    parts = dict(
        piece.split(":", 1) for piece in vector.split("/") if ":" in piece
    )
    if not all(key in parts for key in ("AV", "AC", "PR", "UI", "S", "C", "I", "A")):
        return None
    try:
        scope_changed = parts["S"] == "C"
        pr_weights = _CVSS3_PR_CHANGED if scope_changed else _CVSS3_PR_UNCHANGED
        iss = 1.0 - (
            (1.0 - _CVSS3_WEIGHTS["C"][parts["C"]])
            * (1.0 - _CVSS3_WEIGHTS["I"][parts["I"]])
            * (1.0 - _CVSS3_WEIGHTS["A"][parts["A"]])
        )
        if scope_changed:
            impact = 7.52 * (iss - 0.029) - 3.25 * (pow(iss - 0.02, 15))
        else:
            impact = 6.42 * iss
        if impact <= 0:
            return 0.0
        exploitability = (
            8.22
            * _CVSS3_WEIGHTS["AV"][parts["AV"]]
            * _CVSS3_WEIGHTS["AC"][parts["AC"]]
            * pr_weights[parts["PR"]]
            * _CVSS3_WEIGHTS["UI"][parts["UI"]]
        )
        raw = impact + exploitability
        if scope_changed:
            raw = 1.08 * raw
        return _roundup(min(raw, 10.0))
    except (KeyError, ValueError, TypeError):
        return None


def severity_from_score(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    if score > 0:
        return "low"
    return "unknown"


def severity_from_osv(advisory: dict) -> str:
    """Derive a severity from an OSV-shaped advisory record."""
    database_specific = advisory.get("database_specific") or {}
    if isinstance(database_specific, dict):
        for key in ("severity", "cvss_severity"):
            if database_specific.get(key):
                return normalize_severity(database_specific[key])
    ecosystem_specific = advisory.get("ecosystem_specific") or {}
    if isinstance(ecosystem_specific, dict) and ecosystem_specific.get("severity"):
        return normalize_severity(ecosystem_specific["severity"])
    for entry in advisory.get("severity") or []:
        if not isinstance(entry, dict):
            continue
        score = entry.get("score")
        if isinstance(score, (int, float)):
            return severity_from_score(float(score))
        text = str(score or "")
        if re.match(r"^\d+(\.\d+)?$", text):
            return severity_from_score(float(text))
        base = cvss3_base_score(text)
        if base is not None:
            return severity_from_score(base)
    # cargo audit stores a bare CVSS vector string under "cvss".
    cvss = advisory.get("cvss")
    if isinstance(cvss, str):
        if re.match(r"^\d+(\.\d+)?$", cvss.strip()):
            return severity_from_score(float(cvss.strip()))
        base = cvss3_base_score(cvss)
        if base is not None:
            return severity_from_score(base)
    elif isinstance(cvss, (int, float)):
        return severity_from_score(float(cvss))
    return "unknown"


# --------------------------------------------------------------------------
# normalized record
# --------------------------------------------------------------------------


def make_record(
    *,
    advisory_id: str = "",
    aliases: object = None,
    package: str = "",
    ecosystem: str = "",
    installed_version: str = "",
    fixed_version: str = "",
    severity: str = "unknown",
    direct: bool | None = None,
    title: str = "",
    url: str = "",
    via: object = None,
    source: str = "",
) -> dict:
    return {
        "id": advisory_id,
        "aliases": sorted({str(item) for item in (aliases or []) if item}),
        "package": package,
        "ecosystem": ecosystem,
        "installed_version": installed_version,
        "fixed_version": fixed_version,
        "severity": severity,
        "direct": direct,
        "title": (title or "").strip(),
        "url": url,
        "via": sorted({str(item) for item in (via or []) if item}),
        "source": source,
    }


def dedupe(records: list[dict]) -> list[dict]:
    """Collapse records that describe the same advisory for the same package."""
    merged: dict[tuple, dict] = {}
    for record in records:
        key = (
            record.get("id") or record.get("package"),
            record.get("package"),
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = record
            continue
        for field in ("installed_version", "fixed_version", "title", "url"):
            if not existing.get(field) and record.get(field):
                existing[field] = record[field]
        if existing.get("severity") in (None, "unknown") and record.get("severity"):
            existing["severity"] = record["severity"]
        if existing.get("direct") is None and record.get("direct") is not None:
            existing["direct"] = record["direct"]
        for field in ("aliases", "via"):
            existing[field] = sorted(set(existing.get(field) or []) | set(record.get(field) or []))
    return sorted(
        merged.values(),
        key=lambda item: (
            SEVERITY_ORDER.index(item["severity"]),
            item["package"],
            item["id"],
        ),
    )


# --------------------------------------------------------------------------
# lockfile version lookup (best effort)
# --------------------------------------------------------------------------


def _versions_from_package_lock(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    found: dict[str, str] = {}
    packages = data.get("packages")
    if isinstance(packages, dict):
        for location, meta in packages.items():
            if not isinstance(meta, dict):
                continue
            name = meta.get("name") or location.split("node_modules/")[-1]
            version = meta.get("version")
            if name and version:
                found.setdefault(str(name), str(version))
    dependencies = data.get("dependencies")
    if isinstance(dependencies, dict):
        for name, meta in dependencies.items():
            if isinstance(meta, dict) and meta.get("version"):
                found.setdefault(str(name), str(meta["version"]))
    return found


def _versions_from_pnpm_lock(path: Path) -> dict:
    found: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return found
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.endswith(":") or stripped.startswith("#"):
            continue
        key = stripped[:-1].strip().strip("'\"")
        if not key.startswith("/") and "/" not in key and " " not in key:
            if not re.match(r"^@?[^@\s]+@", key):
                continue
        key = key.lstrip("/")
        if "@" not in key:
            continue
        name, _, version = key.rpartition("@")
        name = name.strip()
        version = version.strip()
        if not name or not re.match(r"^\d", version):
            continue
        found.setdefault(name, version)
    return found


def _versions_from_yarn_lock(path: Path) -> dict:
    found: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return found
    current_name = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if not raw.startswith((" ", "\t")):
            header = line.strip().rstrip(":").strip("'\"")
            header = header.split(",")[0].strip().strip("'\"")
            if "@" in header:
                base = header.rpartition("@")[0]
                if base.startswith("@"):
                    base = base[1:]
                current_name = base
            else:
                current_name = header
            continue
        match = re.match(r'\s+version:?\s+"?([^"\s]+)"?', line)
        if match and current_name:
            found.setdefault(current_name, match.group(1))
    return found


def _versions_from_cargo_lock(path: Path) -> dict:
    found: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return found
    name = ""
    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r'name\s*=\s*"([^"]+)"', stripped)
        if match:
            name = match.group(1)
            continue
        match = re.match(r'version\s*=\s*"([^"]+)"', stripped)
        if match and name:
            found.setdefault(name, match.group(1))
    return found


def _versions_from_go_sum(path: Path) -> dict:
    found: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return found
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith("v"):
            found.setdefault(parts[0], parts[1].lstrip("v"))
    return found


def _versions_from_requirements(path: Path) -> dict:
    found: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return found
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        match = re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*([^\s;]+)", line)
        if match:
            found.setdefault(match.group(1).lower().replace("_", "-"), match.group(2))
    return found


def _versions_from_poetry_lock(path: Path) -> dict:
    found: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return found
    name = ""
    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r'name\s*=\s*"([^"]+)"', stripped)
        if match:
            name = match.group(1)
            continue
        match = re.match(r'version\s*=\s*"([^"]+)"', stripped)
        if match and name:
            found.setdefault(name.lower().replace("_", "-"), match.group(1))
    return found


def _versions_from_composer_lock(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    found: dict[str, str] = {}
    for key in ("packages", "packages-dev"):
        for item in data.get(key) or []:
            if isinstance(item, dict) and item.get("name") and item.get("version"):
                found.setdefault(str(item["name"]), str(item["version"]))
    return found


def _versions_from_gemfile_lock(path: Path) -> dict:
    found: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return found
    for line in text.splitlines():
        match = re.match(r"^\s{4,}([A-Za-z0-9_.\-]+)\s+\(([^)]+)\)\s*$", line)
        if match:
            found.setdefault(match.group(1), match.group(2))
    return found


def _versions_from_json_lock(path: Path, keys: tuple = ()) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    found: dict[str, str] = {}
    packages = data.get("packages") if isinstance(data, dict) else None
    if isinstance(packages, dict):
        for location, meta in packages.items():
            if not isinstance(meta, dict):
                continue
            name = meta.get("name") or str(location).split("node_modules/")[-1]
            version = meta.get("version")
            if name and version:
                found.setdefault(str(name), str(version))
    elif isinstance(packages, list):
        for item in packages:
            if isinstance(item, dict) and item.get("name") and item.get("version"):
                found.setdefault(str(item["name"]), str(item["version"]))
    for key in keys:
        section = data.get(key) if isinstance(data, dict) else None
        if isinstance(section, dict):
            for name, meta in section.items():
                if isinstance(meta, dict) and meta.get("version"):
                    found.setdefault(str(name), str(meta["version"]))
    return found


LOCKFILE_READERS = (
    ("package-lock.json", _versions_from_package_lock),
    ("npm-shrinkwrap.json", _versions_from_package_lock),
    ("pnpm-lock.yaml", _versions_from_pnpm_lock),
    ("yarn.lock", _versions_from_yarn_lock),
    ("packages-lock.json", _versions_from_json_lock),
    ("Cargo.lock", _versions_from_cargo_lock),
    ("go.sum", _versions_from_go_sum),
    ("poetry.lock", _versions_from_poetry_lock),
    ("composer.lock", _versions_from_composer_lock),
    ("Gemfile.lock", _versions_from_gemfile_lock),
)


def installed_versions(root: Path) -> dict:
    """Best-effort map of package name -> installed version, read from lockfiles."""
    found: dict[str, str] = {}
    for entry in LOCKFILE_READERS:
        filename, reader = entry[0], entry[1]
        extra = entry[2] if len(entry) > 2 else ()
        path = root / filename
        if not path.is_file():
            continue
        try:
            found.update(reader(path, *extra) if extra else reader(path))
        except Exception:  # noqa: BLE001 - a broken lockfile must not stop the scan
            continue
    for path in sorted(root.glob("requirements*.txt")):
        try:
            found.update(_versions_from_requirements(path))
        except OSError:
            continue
    return found


# --------------------------------------------------------------------------
# tool adapters
# --------------------------------------------------------------------------


def parse_npm(data: dict) -> list[dict]:
    """npm audit --json (npm >= 7, "vulnerabilities") and npm 6 ("advisories")."""
    records: list[dict] = []
    vulnerabilities = data.get("vulnerabilities")
    if isinstance(vulnerabilities, dict):
        for name, entry in vulnerabilities.items():
            if not isinstance(entry, dict):
                continue
            severity = normalize_severity(entry.get("severity"))
            fixed = ""
            fix_available = entry.get("fixAvailable")
            if isinstance(fix_available, dict):
                fixed = clean_version(fix_available.get("version"))
            direct = entry.get("isDirect")
            via_entries = entry.get("via") or []
            advisories = [item for item in via_entries if isinstance(item, dict)]
            if not advisories:
                advisories = [{}]
            for advisory in advisories:
                url = advisory.get("url") or ""
                advisory_id, aliases = extract_ids(url, advisory.get("source"))
                if not advisory_id:
                    advisory_id = f"{name}@{entry.get('range', '')}".strip("@")
                advisory_severity = advisory.get("severity")
                records.append(
                    make_record(
                        advisory_id=advisory_id,
                        aliases=aliases,
                        package=name,
                        ecosystem="npm",
                        fixed_version=fixed,
                        severity=normalize_severity(advisory_severity)
                        if advisory_severity
                        else severity,
                        direct=direct,
                        title=advisory.get("title") or "",
                        url=url,
                        via=[name],
                        source="npm audit",
                    )
                )
        return records

    advisories = data.get("advisories")
    if isinstance(advisories, dict):
        for key, entry in advisories.items():
            if not isinstance(entry, dict):
                continue
            name = entry.get("module_name") or ""
            url = entry.get("url") or ""
            advisory_id, aliases = extract_ids(url, key)
            findings = entry.get("findings") or []
            versions = []
            for finding in findings:
                if isinstance(finding, dict) and finding.get("version"):
                    versions.append(str(finding["version"]))
            records.append(
                make_record(
                    advisory_id=advisory_id or str(key),
                    aliases=aliases,
                    package=name,
                    ecosystem="npm",
                    installed_version=versions[0] if versions else "",
                    fixed_version=clean_version(entry.get("patched_versions")),
                    severity=normalize_severity(entry.get("severity")),
                    title=entry.get("title") or "",
                    url=url,
                    via=[name],
                    source="npm audit",
                )
            )
    return records


def parse_pnpm(data: dict) -> list[dict]:
    """pnpm audit --json: npm-v7 style or the older "advisories" shape."""
    if isinstance(data.get("vulnerabilities"), dict):
        records = parse_npm(data)
        for record in records:
            record["ecosystem"] = "npm"
            record["source"] = "pnpm audit"
        return records
    return parse_advisory_map(data, "pnpm audit", "npm")


def parse_yarn(ndjson: list) -> list[dict]:
    """yarn npm audit --json / yarn audit --json: NDJSON auditAdvisory records."""
    advisories: dict = {}
    for line in ndjson:
        if not isinstance(line, dict):
            continue
        if line.get("type") != "auditAdvisory":
            continue
        advisory = (line.get("data") or {}).get("advisory") or {}
        if not isinstance(advisory, dict):
            continue
        key = str(advisory.get("id") or advisory.get("module_name") or len(advisories))
        advisories[key] = advisory
    records = []
    for advisory in advisories.values():
        name = advisory.get("module_name") or ""
        url = advisory.get("url") or ""
        advisory_id, aliases = extract_ids(url, advisory.get("id"))
        versions = [
            str(finding.get("version"))
            for finding in (advisory.get("findings") or [])
            if isinstance(finding, dict) and finding.get("version")
        ]
        records.append(
            make_record(
                advisory_id=advisory_id or str(advisory.get("id") or name),
                aliases=aliases,
                package=name,
                ecosystem="npm",
                installed_version=versions[0] if versions else "",
                fixed_version=clean_version(advisory.get("patched_versions")),
                severity=normalize_severity(advisory.get("severity")),
                title=advisory.get("title") or "",
                url=url,
                via=[name],
                source="yarn npm audit",
            )
        )
    return records


def parse_advisory_map(data: dict, source: str, ecosystem: str) -> list[dict]:
    """Shared parser for the {"advisories": {...}} shape (npm 6, pnpm legacy)."""
    advisories = data.get("advisories")
    if not isinstance(advisories, dict):
        return []
    records = []
    for key, entry in advisories.items():
        if not isinstance(entry, dict):
            continue
        name = entry.get("module_name") or ""
        url = entry.get("url") or ""
        advisory_id, aliases = extract_ids(url, key)
        versions = [
            str(finding.get("version"))
            for finding in (entry.get("findings") or [])
            if isinstance(finding, dict) and finding.get("version")
        ]
        records.append(
            make_record(
                advisory_id=advisory_id or str(key),
                aliases=aliases,
                package=name,
                ecosystem=ecosystem,
                installed_version=versions[0] if versions else "",
                fixed_version=clean_version(entry.get("patched_versions")),
                severity=normalize_severity(entry.get("severity")),
                title=entry.get("title") or "",
                url=url,
                via=[name],
                source=source,
            )
        )
    return records


def parse_pip_audit(data: dict) -> list[dict]:
    """pip-audit --format json: {"dependencies": [{name, version, vulns: []}]}."""
    records: list[dict] = []
    dependencies = data.get("dependencies")
    if not isinstance(dependencies, list):
        return records
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            continue
        name = str(dependency.get("name") or "")
        version = str(dependency.get("version") or "")
        vulns = dependency.get("vulns")
        if isinstance(vulns, dict):
            vulns = [dict(item, id=key) for key, item in vulns.items() if isinstance(item, dict)]
        for vuln in vulns or []:
            if not isinstance(vuln, dict):
                continue
            advisory_id = str(vuln.get("id") or "")
            aliases = vuln.get("aliases") or []
            identifiers, more = pick_id(advisory_id, aliases)
            records.append(
                make_record(
                    advisory_id=identifiers,
                    aliases=more,
                    package=name,
                    ecosystem="PyPI",
                    installed_version=version,
                    fixed_version=clean_version(vuln.get("fix_versions")),
                    severity=normalize_severity(vuln.get("severity")),
                    title=(vuln.get("description") or "").split("\n", 1)[0],
                    via=[name],
                    source="pip-audit",
                )
            )
    return records


def parse_cargo_audit(data: dict) -> list[dict]:
    """cargo audit --json: {"vulnerabilities": {"list": [...]}}."""
    records: list[dict] = []
    vulnerabilities = data.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return records
    for entry in vulnerabilities.get("list") or []:
        if not isinstance(entry, dict):
            continue
        advisory = entry.get("advisory") or {}
        package = entry.get("package") or {}
        versions = entry.get("versions") or {}
        url = advisory.get("url") or ""
        advisory_id, aliases = pick_id(
            advisory.get("id"), url, advisory.get("aliases")
        )
        patched = versions.get("patched") if isinstance(versions, dict) else None
        records.append(
            make_record(
                advisory_id=advisory_id,
                aliases=aliases,
                package=str(package.get("name") or ""),
                ecosystem="crates.io",
                installed_version=str(package.get("version") or ""),
                fixed_version=clean_version(patched),
                severity=severity_from_osv(advisory) if advisory else "unknown",
                title=str(advisory.get("title") or ""),
                url=url,
                via=[str(package.get("name") or "")],
                source="cargo audit",
            )
        )
    return records


def parse_osv_scanner(data: object) -> list[dict]:
    """osv-scanner --format json: v1 array or v2 {"results": [...]}."""
    records: list[dict] = []
    groups: list = []
    if isinstance(data, list):
        groups = data
    elif isinstance(data, dict):
        results = data.get("results")
        if isinstance(results, list):
            groups = results
        elif data.get("packages"):
            groups = [data]
    for group in groups:
        if not isinstance(group, dict):
            continue
        for package_entry in group.get("packages") or []:
            if not isinstance(package_entry, dict):
                continue
            package = package_entry.get("package") or {}
            name = str(package.get("name") or "")
            version = str(package.get("version") or "")
            ecosystem = str(package.get("ecosystem") or "")
            for vuln in package_entry.get("vulnerabilities") or []:
                if not isinstance(vuln, dict):
                    continue
                url = ""
                for reference in vuln.get("references") or []:
                    if isinstance(reference, dict) and reference.get("type") == "ADVISORY":
                        url = reference.get("url") or ""
                        break
                if not url:
                    for reference in vuln.get("references") or []:
                        if isinstance(reference, dict) and reference.get("url"):
                            url = reference["url"]
                            break
                advisory_id, aliases = pick_id(vuln.get("id"), url, vuln.get("aliases"))
                fixed = ""
                for affected in vuln.get("affected") or []:
                    if not isinstance(affected, dict):
                        continue
                    for range_entry in affected.get("ranges") or []:
                        if not isinstance(range_entry, dict):
                            continue
                        for event in range_entry.get("events") or []:
                            if isinstance(event, dict) and event.get("fixed"):
                                fixed = clean_version(event["fixed"])
                                break
                        if fixed:
                            break
                    if fixed:
                        break
                records.append(
                    make_record(
                        advisory_id=advisory_id,
                        aliases=aliases,
                        package=name,
                        ecosystem=ecosystem,
                        installed_version=version,
                        fixed_version=fixed,
                        severity=severity_from_osv(vuln),
                        title=str(vuln.get("summary") or ""),
                        url=url,
                        via=[name],
                        source="osv-scanner",
                    )
                )
    return records


def parse_govulncheck(ndjson: list) -> list[dict]:
    """govulncheck -json: NDJSON with "osv" and "finding" messages."""
    osv_by_id: dict[str, dict] = {}
    findings: list[dict] = []
    for message in ndjson:
        if not isinstance(message, dict):
            continue
        if isinstance(message.get("osv"), dict):
            osv = message["osv"]
            osv_by_id[str(osv.get("id") or "")] = osv
        elif isinstance(message.get("finding"), dict):
            findings.append(message["finding"])
    records: list[dict] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        osv_id = str(finding.get("osv") or "")
        osv = osv_by_id.get(osv_id, {})
        module = ""
        version = ""
        for frame in finding.get("trace") or []:
            if isinstance(frame, dict) and frame.get("module"):
                module = str(frame["module"])
                version = str(frame.get("version") or "")
                break
        aliases = osv.get("aliases") or []
        identifiers, extra = pick_id(osv_id, aliases)
        records.append(
            make_record(
                advisory_id=identifiers,
                aliases=extra,
                package=module,
                ecosystem="Go",
                installed_version=version,
                fixed_version=clean_version(finding.get("fixed_version")),
                severity=severity_from_osv(osv) if osv else "unknown",
                title=str(osv.get("summary") or ""),
                via=[module],
                source="govulncheck",
            )
        )
    return records


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------

TOOL_COMMANDS = {
    "npm": ["npm", "audit", "--json"],
    "pnpm": ["pnpm", "audit", "--json"],
    "yarn": ["yarn", "npm", "audit", "--json"],
    "pip-audit": ["pip-audit", "--format", "json"],
    "cargo": ["cargo", "audit", "--json"],
    "osv-scanner": ["osv-scanner", "--format", "json"],
    "govulncheck": ["govulncheck", "-json"],
}

TOOL_ALIASES = {
    "pip": "pip-audit",
    "pip_audit": "pip-audit",
    "pipa": "pip-audit",
    "osv": "osv-scanner",
    "osv_scanner": "osv-scanner",
    "govuln": "govulncheck",
    "go": "govulncheck",
}

DETECT_ORDER = ("pnpm", "yarn", "npm", "cargo", "pip-audit", "osv-scanner", "govulncheck")
DETECT_FILES = {
    "npm": ("package-lock.json", "npm-shrinkwrap.json"),
    "pnpm": ("pnpm-lock.yaml",),
    "yarn": ("yarn.lock",),
    "cargo": ("Cargo.lock",),
    "pip-audit": ("poetry.lock", "requirements.txt", "Pipfile.lock"),
    "osv-scanner": (),
    "govulncheck": ("go.mod",),
}


def detect_tool(root: Path) -> str:
    for tool in DETECT_ORDER:
        for filename in DETECT_FILES[tool]:
            if (root / filename).exists():
                return tool
    return ""


def parse_output(tool: str, stdout: str) -> list[dict]:
    text = stdout.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        # govulncheck and some yarn versions emit NDJSON
        messages = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except ValueError:
                continue
        if not messages:
            raise
        data = messages
    if tool == "npm":
        return parse_npm(data)
    if tool == "pnpm":
        return parse_pnpm(data)
    if tool == "yarn":
        return parse_yarn(data if isinstance(data, list) else [data])
    if tool == "pip-audit":
        return parse_pip_audit(data)
    if tool == "cargo":
        return parse_cargo_audit(data)
    if tool == "osv-scanner":
        return parse_osv_scanner(data)
    if tool == "govulncheck":
        return parse_govulncheck(data if isinstance(data, list) else [data])
    return []


def run_tool(tool: str, cwd: Path, timeout: int) -> tuple[list[dict], str]:
    command = TOOL_COMMANDS[tool]
    executable = shutil.which(command[0])
    if executable is None:
        return [], f"'{command[0]}' is not installed or not on PATH"
    env = dict(os.environ)
    env.setdefault("CI", "1")
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [], f"'{command[0]}' timed out after {timeout}s"
    except OSError as exc:
        return [], f"could not run '{command[0]}': {exc}"
    if not completed.stdout.strip():
        detail = (completed.stderr or "").strip().splitlines()
        message = detail[-1] if detail else f"exit code {completed.returncode}"
        return [], f"'{command[0]}' produced no JSON output ({message})"
    try:
        records = parse_output(tool, completed.stdout)
    except ValueError as exc:
        return [], f"could not parse '{command[0]}' output: {exc}"
    return records, ""


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------


def summarize(records: list[dict]) -> dict:
    summary = {name: 0 for name in SEVERITY_ORDER}
    for record in records:
        summary[record["severity"]] = summary.get(record["severity"], 0) + 1
    summary["total"] = len(records)
    return summary


def render_table(records: list[dict]) -> str:
    header = "| ID | Package | Installed | Fixed | Severity | Title |"
    divider = "|----|--------|-----------|-------|----------|-------|"
    lines = [header, divider]
    for record in records:
        title = record["title"].replace("|", "\\|")
        if len(title) > 90:
            title = title[:87] + "..."
        lines.append(
            "| {id} | {pkg} | {installed} | {fixed} | {severity} | {title} |".format(
                id=record["id"] or "-",
                pkg=record["package"] or "-",
                installed=record["installed_version"] or "-",
                fixed=record["fixed_version"] or "-",
                severity=record["severity"],
                title=title or "-",
            )
        )
    if not records:
        lines.append("| - | - | - | - | - | no advisories reported by this source |")
    return "\n".join(lines)


def render_text(records: list[dict], payload: dict) -> str:
    summary = payload["summary"]
    parts = [
        "Advisories: {total} (critical {critical}, high {high}, medium {medium}, low {low}, unknown {unknown})".format(
            **summary
        ),
        "",
        render_table(records),
    ]
    if payload.get("errors"):
        parts.extend(["", "Errors:", *[f"- {item}" for item in payload["errors"]]])
    return "\n".join(parts)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize ecosystem auditor output into one advisory table."
    )
    parser.add_argument(
        "--tool",
        required=True,
        help="npm | pnpm | yarn | pip-audit | cargo | osv-scanner | govulncheck | auto",
    )
    parser.add_argument(
        "--cwd",
        default=".",
        help="Directory to audit (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit normalized JSON instead of a markdown table",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Seconds to wait for the auditor (default: 300)",
    )
    args = parser.parse_args(argv)

    tool = TOOL_ALIASES.get(args.tool.lower(), args.tool.lower())
    root = Path(args.cwd).expanduser().resolve()
    if not root.is_dir():
        print(f"error: '{root}' is not a directory", file=sys.stderr)
        return 1
    if tool == "auto":
        tool = detect_tool(root)
        if not tool:
            print(
                "error: could not detect an ecosystem from lockfiles; pass --tool explicitly",
                file=sys.stderr,
            )
            return 1
    if tool not in TOOL_COMMANDS:
        supported = ", ".join(sorted(TOOL_COMMANDS))
        print(f"error: unknown tool '{args.tool}'. Supported: {supported}", file=sys.stderr)
        return 1

    records, error = run_tool(tool, root, args.timeout)

    if records:
        # Some auditors only report versions through a lockfile lookup.
        versions = installed_versions(root)
        for record in records:
            if not record["installed_version"]:
                record["installed_version"] = versions.get(record["package"], "")

    if error:
        records = []

    payload = {
        "tool": tool,
        "root": str(root),
        "summary": summarize(records),
        "advisories": records,
        "errors": [error] if error else [],
        "status": "error" if error else "ok",
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_text(records, payload))

    return 2 if error else 0


if __name__ == "__main__":
    sys.exit(main())
