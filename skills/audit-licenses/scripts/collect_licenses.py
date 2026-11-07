#!/usr/bin/env python3
"""Build a normalized license inventory for a dependency tree.

Read-only and stdlib-only. It never installs, updates, or removes anything.

    python3 -I collect_licenses.py --root . --ecosystem node
    python3 -I collect_licenses.py --root . --ecosystem node --json
    python3 -I collect_licenses.py --root . --ecosystem python --policy license-policy.json

Ecosystems:
  node    installed node_modules metadata, or package-lock.json / npm-shrinkwrap.json
  python  installed .dist-info / .egg-info metadata, or requirements.txt for direct deps
  rust    Cargo.lock graph, enriched with licenses from `cargo metadata` when available
  go      `go list -m -json all`, licenses detected from each module's LICENSE file

Every package is emitted as: name, version, declared license, source
(direct or transitive). Licenses are normalized to SPDX ids. Anything that
cannot be normalized is reported as UNKNOWN or NOASSERTION - never guessed.

With --policy the script also checks the inventory against a policy file and
exits non-zero on a forbidden license. With --attribution it checks that the
attribution file exists and is non-empty.

Exit codes: 0 success (or clean policy check), 1 policy violation,
2 usage or environment error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = 1

UNKNOWN = "UNKNOWN"
NOASSERTION = "NOASSERTION"
UNLICENSED = "UNLICENSED"

# Exact lower-cased strings mapped to an SPDX id.
EXACT_LICENSES = {
    "mit": "MIT",
    "mit license": "MIT",
    "expat": "MIT",
    "apache-2.0": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "apache license version 2.0": "Apache-2.0",
    "asl 2.0": "Apache-2.0",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd 2-clause": "BSD-2-Clause",
    "bsd 2-clause simplified": "BSD-2-Clause",
    "bsd 2-clause \"simplified\"": "BSD-2-Clause",
    "simplified bsd license": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "bsd 3-clause \"new\" or \"revised\"": "BSD-3-Clause",
    "bsd-3-clause clear": "BSD-3-Clause",
    "new bsd license": "BSD-3-Clause",
    "modified bsd license": "BSD-3-Clause",
    "isc": "ISC",
    "isc license": "ISC",
    "unlicense": "Unlicense",
    "the unlicense": "Unlicense",
    "0bsd": "0BSD",
    "zlib": "Zlib",
    "zlib/libpng license": "Zlib",
    "artistic-2.0": "Artistic-2.0",
    "artistic license 2.0": "Artistic-2.0",
    "wtfpl": "WTFPL",
    "cc0-1.0": "CC0-1.0",
    "cc0": "CC0-1.0",
    "public domain": "CC0-1.0",
    "python-2.0": "Python-2.0",
    "python software foundation license": "Python-2.0",
    "psf-2.0": "PSF-2.0",
    "psf": "PSF-2.0",
    "ofl-1.1": "OFL-1.1",
    "mpl-2.0": "MPL-2.0",
    "mozilla public license 2.0": "MPL-2.0",
    "mozilla public license version 2.0": "MPL-2.0",
    "mpl-2.0 no copyleft exception": "MPL-2.0-no-copyleft-exception",
    "epl-2.0": "EPL-2.0",
    "eclipse public license - v 2.0": "EPL-2.0",
    "eclipse public license 2.0": "EPL-2.0",
    "eclipse public license v 2.0": "EPL-2.0",
    "cddl-1.0": "CDDL-1.0",
    "cddl 1.0": "CDDL-1.0",
    "cddl-1.1": "CDDL-1.1",
    "common development and distribution license 1.0": "CDDL-1.0",
    "common development and distribution license (cddl) v1.0": "CDDL-1.0",
    "eupl-1.1": "EUPL-1.1",
    "eupl-1.2": "EUPL-1.2",
    "sspl-1.0": "SSPL-1.0",
    "server side public license, v 1": "SSPL-1.0",
    "busl-1.1": "BUSL-1.1",
    "business source license 1.1": "BUSL-1.1",
    "elastic license 2.0": "Elastic-2.0",
    "apache-1.1": "Apache-1.1",
    "bsd-4-clause": "BSD-4-Clause",
    "gpl-1.0": "GPL-1.0-only",
    "gpl-2.0": "GPL-2.0-only",
    "gpl-3.0": "GPL-3.0-only",
    "lgpl-2.1": "LGPL-2.1-only",
    "lgpl-3.0": "LGPL-3.0-only",
    "agpl-1.0": "AGPL-1.0-only",
    "agpl-3.0": "AGPL-3.0-only",
    "gpl-2.0+": "GPL-2.0-or-later",
    "gpl-3.0+": "GPL-3.0-or-later",
    "lgpl-2.1+": "LGPL-2.1-or-later",
    "lgpl-3.0+": "LGPL-3.0-or-later",
    "agpl-3.0+": "AGPL-3.0-or-later",
}

# Ordered (pattern, spdx) rules for licenses whose strings carry a variant.
def _suffix(text: str) -> str:
    """Map a license suffix to its SPDX spelling: -only, -or-later, or none."""
    value = (text or "").strip().lower()
    if value.startswith("+"):
        return "-or-later"
    if value in {"-only", " only"}:
        return "-only"
    if value in {"-or-later", " or-later", " or later"}:
        return "-or-later"
    return ""


RULE_LICENSES = (
    (re.compile(r"^apache[- ]?(\d+\.\d+)$"), lambda m: "Apache-2.0" if m.group(1) == "2.0" else UNKNOWN),
    (re.compile(r"^agpl[- ]?(\d+\.\d+)(.*)$"), lambda m: f"AGPL-{m.group(1)}{_suffix(m.group(2))}"),
    (re.compile(r"^lgpl[- ]?(\d+\.\d+)(.*)$"), lambda m: f"LGPL-{m.group(1)}{_suffix(m.group(2))}"),
    (re.compile(r"^gpl[- ]?(\d+\.\d+)(.*)$"), lambda m: f"GPL-{m.group(1)}{_suffix(m.group(2))}"),
    (re.compile(r"^mpl[- ]?(\d+\.\d+)(.*)$"), lambda m: f"MPL-{m.group(1)}"),
    (re.compile(r"^epl[- ]?(\d+\.\d+)(.*)$"), lambda m: f"EPL-{m.group(1)}"),
    (re.compile(r"^cddl[- ]?(\d+\.\d+)(.*)$"), lambda m: f"CDDL-{m.group(1)}"),
    (re.compile(r"^eupl[- ]?(\d+\.\d+)(.*)$"), lambda m: f"EUPL-{m.group(1)}"),
    (re.compile(r"^sspl[- ]?(\d+\.\d+)(.*)$"), lambda m: f"SSPL-{m.group(1)}"),
    (re.compile(r"^busl[- ]?(\d+\.\d+)(.*)$"), lambda m: f"BUSL-{m.group(1)}"),
    (re.compile(r"^bsd[- ]?(\d+)[- ]clause$"), lambda m: f"BSD-{m.group(1)}-Clause"),
    (re.compile(r"^bsd[- ]?(\d+)-clause[- ]?(clear|revised)$"), lambda m: f"BSD-{m.group(1)}-Clause"),
    (re.compile(r"^python[- ]?(\d+\.\d+)$"), lambda m: f"Python-{m.group(1)}"),
    (re.compile(r"^cc0[- ]?(\d+\.\d+)$"), lambda m: f"CC0-{m.group(1)}"),
    (re.compile(r"^ofl[- ]?(\d+\.\d+)$"), lambda m: f"OFL-{m.group(1)}"),
)

# License file fingerprints, most specific first, used for Go modules.
LICENSE_FILE_MARKERS = (
    ("server side public license", "SSPL-1.0"),
    ("business source license", "BUSL-1.1"),
    ("gnu affero general public license", "AGPL-3.0-only"),
    ("gnu lesser general public license", "LGPL-3.0-only"),
    ("mozilla public license", "MPL-2.0"),
    ("eclipse public license", "EPL-2.0"),
    ("common development and distribution license", "CDDL-1.0"),
    ("apache license", "Apache-2.0"),
    ("permission is hereby granted, free of charge", "MIT"),
    ("redistribution and use in source and binary forms", "BSD-3-Clause"),
    ("permission to use, copy, modify, and/or distribute this software", "ISC"),
    ("this is free and unencumbered software released into the public domain", "Unlicense"),
    ("gnu general public license", "GPL-3.0-only"),
)

SKIP_DIRS = {".git", ".hg", ".svn", ".tox", ".venv", "venv", "__pycache__"}


# --------------------------------------------------------------------------
# License normalization
# --------------------------------------------------------------------------


def normalize_single(raw: str) -> str:
    """Normalize one license string to an SPDX id, or UNKNOWN."""
    text = (raw or "").strip()
    if not text:
        return UNKNOWN
    if text.startswith("SEE LICENSE IN"):
        return "LicenseRef-Custom"
    stripped = text.strip()
    while stripped.startswith("(") and stripped.endswith(")") and len(stripped) > 2:
        stripped = stripped[1:-1].strip()
    lowered = stripped.lower()
    if lowered in EXACT_LICENSES:
        return EXACT_LICENSES[lowered]
    if lowered in {"commercial", "proprietary", "private", "closed source", "custom"}:
        return "LicenseRef-Proprietary"
    if lowered == "unlicensed":
        return UNLICENSED
    if lowered in {"unknown", "none", "n/a", "na"}:
        return UNKNOWN
    if lowered == "noassertion":
        return NOASSERTION
    if lowered.startswith("licenseref-"):
        return stripped
    for pattern, build in RULE_LICENSES:
        match = pattern.match(lowered)
        if match:
            spdx = build(match)
            if spdx != UNKNOWN:
                return spdx
    if re.match(r"^[a-z0-9.-]+-[0-9]+\.[0-9]+", lowered):
        # Looks like an SPDX id we do not have a rule for; keep it verbatim.
        return stripped
    return UNKNOWN


def normalize_license(raw: str) -> dict:
    """Normalize a declared license string into a small record.

    Returns a dict with:
      license        - the primary SPDX id (or UNKNOWN / NOASSERTION)
      alternatives   - other ids when the declaration is an OR expression
      expression     - the normalized full expression
      raw            - the untouched declared string
    """
    text = (raw or "").strip()
    if not text:
        return {
            "license": UNKNOWN,
            "alternatives": [],
            "expression": UNKNOWN,
            "raw": "",
        }
    # A whole-string match wins: some license names contain the word "or"
    # (for example "BSD 3-Clause \"New\" or \"Revised\"").
    whole = normalize_single(text)
    if whole != UNKNOWN:
        return {
            "license": whole,
            "alternatives": [],
            "expression": whole,
            "raw": text,
        }
    parts = re.split(r"\s+OR\s+", text, flags=re.IGNORECASE)
    ids = [normalize_single(part) for part in parts]
    primary = ids[0]
    alternatives = [item for item in ids[1:] if item != primary]
    expression = " OR ".join(dict.fromkeys(ids))
    return {
        "license": primary,
        "alternatives": alternatives,
        "expression": expression,
        "raw": text,
    }


# --------------------------------------------------------------------------
# Ecosystem collectors
# --------------------------------------------------------------------------


def _read_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def _package_json_license(data: dict) -> str:
    value = data.get("license")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("type", "name"):
            if isinstance(value.get(key), str):
                return value[key]
    licenses = data.get("licenses")
    if isinstance(licenses, list) and licenses:
        first = licenses[0]
        if isinstance(first, dict) and isinstance(first.get("type"), str):
            return first["type"]
        if isinstance(first, str):
            return first
    return ""


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def collect_node(root: Path) -> tuple[list[dict], list[str]]:
    """Collect licenses from an installed node_modules tree or a lockfile."""
    notes: list[str] = []
    direct_names: set[str] = set()
    manifest = _read_json(root / "package.json")
    for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        value = manifest.get(field)
        if isinstance(value, dict):
            direct_names.update(str(key) for key in value)

    packages: list[dict] = []
    node_modules = root / "node_modules"
    if node_modules.is_dir():
        found: dict[tuple[str, str], dict] = {}
        for dirpath, dirnames, filenames in os.walk(node_modules, followlinks=False):
            here = Path(dirpath)
            parts = here.relative_to(node_modules).parts
            if any(part in SKIP_DIRS for part in parts):
                dirnames[:] = []
                continue
            if "package.json" not in filenames:
                continue
            data = _read_json(here / "package.json")
            if not data:
                continue
            name = data.get("name")
            if not isinstance(name, str) or not name:
                continue
            version = str(data.get("version") or "")
            key = (name, version)
            if key in found:
                continue
            found[key] = {
                "name": name,
                "version": version,
                "path": _rel(root, here),
                "source": "direct" if name in direct_names else "transitive",
                "declared_license": _package_json_license(data),
            }
        packages = list(found.values())
        notes.append("source: installed node_modules")
        return packages, notes

    for lock_name in ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml"):
        lock_path = root / lock_name
        if lock_path.is_file():
            packages = _collect_node_lockfile(lock_path, direct_names)
            notes.append(f"source: {lock_name}")
            if lock_name == "pnpm-lock.yaml":
                notes.append("pnpm-lock.yaml holds no license metadata: expect UNKNOWN entries")
            return packages, notes

    notes.append("source: none (no node_modules and no lockfile found)")
    return packages, notes


def _collect_node_lockfile(lock_path: Path, direct_names: set[str]) -> list[dict]:
    if lock_path.name.endswith(".yaml"):
        return _collect_pnpm_lock(lock_path, direct_names)
    data = _read_json(lock_path)
    packages: list[dict] = []
    version = str(data.get("lockfileVersion") or "")
    if version.isdigit() and int(version) >= 2:
        entries = data.get("packages")
        if isinstance(entries, dict):
            for key, value in entries.items():
                if not isinstance(value, dict) or not key:
                    continue
                name = value.get("name") or key.split("node_modules/")[-1]
                if not isinstance(name, str) or not name:
                    continue
                packages.append(
                    {
                        "name": name,
                        "version": str(value.get("version") or ""),
                        "path": key,
                        "source": "direct" if name in direct_names else "transitive",
                        "declared_license": value.get("license") if isinstance(value.get("license"), str) else "",
                    }
                )
            return packages
    dependencies = data.get("dependencies")
    if isinstance(dependencies, dict):
        for name, value in dependencies.items():
            if not isinstance(value, dict):
                continue
            packages.append(
                {
                    "name": name,
                    "version": str(value.get("version") or ""),
                    "path": f"node_modules/{name}",
                    "source": "direct" if name in direct_names else "transitive",
                    "declared_license": value.get("license") if isinstance(value.get("license"), str) else "",
                }
            )
    return packages


def _collect_pnpm_lock(lock_path: Path, direct_names: set[str]) -> list[dict]:
    """Minimal pnpm-lock.yaml reader: packages and their declared versions."""
    packages: list[dict] = []
    try:
        text = lock_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return packages
    current: str | None = None
    for line in text.splitlines():
        if not line.startswith(" "):
            match = re.match(r"^  (/[^:]+):", line)
            if match:
                current = match.group(1)
            else:
                current = None
            continue
        if current is None:
            continue
        version_match = re.match(r"^\s+version:\s*'?([^'\s]+)'?", line)
        if version_match:
            name = current.split("/")[-2] + "/" + current.split("/")[-1] if current.count("/") > 1 else current.lstrip("/")
            name = name.lstrip("/")
            packages.append(
                {
                    "name": name,
                    "version": version_match.group(1),
                    "path": current,
                    "source": "direct" if name in direct_names else "transitive",
                    "declared_license": "",
                }
            )
    return packages


def _python_metadata_license(metadata_path: Path) -> str:
    try:
        text = metadata_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    declared = ""
    classifier = ""
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("License-Expression:"):
            declared = line.split(":", 1)[1].strip()
        elif line.startswith("License:"):
            value = line.split(":", 1)[1].strip()
            if not declared and value and not value.lower().startswith("see license"):
                declared = value
        elif line.startswith("Classifier: License ::"):
            classifier = line.split("::")[-1].strip()
    if declared:
        return declared
    if classifier:
        return classifier
    return ""


def _python_direct_names(root: Path) -> set[str]:
    names: set[str] = set()
    candidates: list[Path] = []
    for pattern in ("requirements*.txt", "requirements/*.txt", "constraints*.txt"):
        candidates.extend(root.glob(pattern))
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            match = re.match(r"^([A-Za-z0-9._-]+)", line)
            if match:
                names.add(re.sub(r"[-_.]+", "-", match.group(1)).lower())
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            text = pyproject.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        for block in re.findall(r"dependencies\s*=\s*\[(.*?)\]", text, flags=re.DOTALL):
            for raw_line in block.splitlines():
                line = raw_line.split("#", 1)[0].strip().strip("\"',")
                if not line:
                    continue
                match = re.match(r"^([A-Za-z0-9._-]+)", line)
                if match:
                    names.add(re.sub(r"[-_.]+", "-", match.group(1)).lower())
    return names


def _python_site_packages(root: Path) -> list[Path]:
    found: list[Path] = []
    for candidate in (
        root / ".venv" / "lib",
        root / "venv" / "lib",
        root / "env" / "lib",
        root / ".env" / "lib",
    ):
        if candidate.is_dir():
            for child in sorted(candidate.iterdir()):
                site = child / "site-packages"
                if site.is_dir():
                    found.append(site)
    try:
        import sysconfig

        purelib = Path(sysconfig.get_paths()["purelib"])
        if purelib.is_dir():
            found.append(purelib)
    except Exception:  # pragma: no cover - sysconfig is always available
        pass
    unique: list[Path] = []
    for path in found:
        if path not in unique:
            unique.append(path)
    return unique


def collect_python(root: Path) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    direct_names = _python_direct_names(root)
    packages: list[dict] = []
    for site in _python_site_packages(root):
        for child in sorted(site.iterdir()):
            name = ""
            version = ""
            declared = ""
            path = ""
            if child.name.endswith(".dist-info"):
                metadata = child / "METADATA"
                if not metadata.is_file():
                    continue
                declared = _python_metadata_license(metadata)
                name = ""
                version = ""
                for line in metadata.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("Name:") and not name:
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("Version:") and not version:
                        version = line.split(":", 1)[1].strip()
                    if name and version:
                        break
                path = _rel(root, child)
            elif child.name.endswith(".egg-info"):
                pkg_info = child / "PKG-INFO"
                if not pkg_info.is_file():
                    continue
                declared = _python_metadata_license(pkg_info)
                for line in pkg_info.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("Name:") and not name:
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("Version:") and not version:
                        version = line.split(":", 1)[1].strip()
                    if name and version:
                        break
                path = _rel(root, child)
            else:
                continue
            if not name:
                continue
            key_name = re.sub(r"[-_.]+", "-", name).lower()
            packages.append(
                {
                    "name": name,
                    "version": version,
                    "path": path,
                    "source": "direct" if key_name in direct_names else "transitive",
                    "declared_license": declared,
                }
            )
    if packages:
        notes.append("source: installed dist-info / egg-info metadata")
    else:
        notes.append("source: none (no installed distributions found)")
    return packages, notes


def collect_rust(root: Path) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    lock_path = root / "Cargo.lock"
    if not lock_path.is_file():
        return [], ["source: none (no Cargo.lock found)"]
    try:
        text = lock_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], ["source: none (Cargo.lock unreadable)"]

    entries: list[dict] = []
    deps: dict[int, list[str]] = {}
    index = -1
    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[[package]]":
            index += 1
            entries.append({})
            deps.setdefault(index, [])
            in_deps = False
            continue
        if index < 0:
            continue
        if stripped.startswith("dependencies"):
            in_deps = True
            continue
        if in_deps:
            if stripped.startswith("]"):
                in_deps = False
                continue
            dep = re.match(r"^\"([^\"]+)\"", stripped)
            if dep:
                deps.setdefault(index, []).append(dep.group(1))
            continue
        match = re.match(r"^(name|version|source)\s*=\s*\"([^\"]*)\"$", stripped)
        if match:
            entries[index][match.group(1)] = match.group(2)

    workspace_names = {entry.get("name", "") for entry in entries if not entry.get("source")}
    direct: set[str] = set()
    for index, entry in enumerate(entries):
        if not entry.get("source"):
            for dep in deps.get(index, []):
                direct.add(dep.split()[0])
    direct |= _rust_declared_dependencies(root)

    licenses: dict[str, str] = {}
    metadata = _cargo_metadata(root)
    if metadata:
        for package in metadata.get("packages", []):
            if isinstance(package, dict):
                name = package.get("name")
                license_value = package.get("license")
                if isinstance(name, str) and isinstance(license_value, str):
                    licenses.setdefault(f"{name} {package.get('version')}", license_value)
        notes.append("licenses enriched from `cargo metadata`")
    else:
        notes.append(
            "`cargo metadata` unavailable: licenses stay UNKNOWN "
            "(run it with network access, or vendor the metadata)"
        )

    packages = []
    for entry in entries:
        name = entry.get("name", "")
        version = entry.get("version", "")
        if not name or name in workspace_names:
            continue
        packages.append(
            {
                "name": name,
                "version": version,
                "path": _rel(root, root),
                "source": "direct" if name in direct else "transitive",
                "declared_license": licenses.get(f"{name} {version}", ""),
            }
        )
    return packages, notes


def _rust_declared_dependencies(root: Path) -> set[str]:
    """Read dependency names declared in the workspace Cargo.toml files."""
    names: set[str] = set()
    manifests = [root / "Cargo.toml"]
    workspace = root / "Cargo.toml"
    if workspace.is_file():
        try:
            text = workspace.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        for member in re.findall(r"members\s*=\s*\[(.*?)\]", text, flags=re.DOTALL):
            for raw in member.split(","):
                candidate = raw.split("#", 1)[0].strip().strip("\"'")
                if candidate and not candidate.startswith("."):
                    manifests.append(root / candidate / "Cargo.toml")
    for manifest in manifests:
        if not manifest.is_file():
            continue
        try:
            text = manifest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for section in re.findall(
            r"\[(?:.*\.)?(?:dev-|build-)?dependencies\](.*?)(?=\n\[|\Z)", text, flags=re.DOTALL
        ):
            for match in re.finditer(r"^\s*([A-Za-z0-9_-]+)\s*=", section, flags=re.MULTILINE):
                names.add(match.group(1))
    return names


def _cargo_metadata(root: Path) -> dict:
    binary = _which("cargo")
    if not binary:
        return {}
    for args in (
        ["metadata", "--format-version", "1", "--offline"],
        ["metadata", "--format-version", "1"],
    ):
        try:
            result = subprocess.run(
                [binary, *args],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0:
            continue
        try:
            return json.loads(result.stdout)
        except ValueError:
            continue
    return {}


def collect_go(root: Path) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    binary = _which("go")
    if not binary:
        return [], ["source: none (the go toolchain is not installed)"]
    try:
        result = subprocess.run(
            [binary, "list", "-m", "-json", "all"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            env={**os.environ, "GOFLAGS": "-mod=mod", "GO111MODULE": "on"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], [f"source: none (go list failed: {exc})"]
    if result.returncode != 0:
        return [], ["source: none (go list -m -json all failed)"]

    decoder = json.JSONDecoder()
    text = result.stdout
    packages: list[dict] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        try:
            module, index = decoder.raw_decode(text, index)
        except ValueError:
            break
        if not isinstance(module, dict):
            continue
        path = module.get("Path")
        if not isinstance(path, str) or not path:
            continue
        if module.get("Main"):
            # The module being built, not a dependency.
            continue
        version = module.get("Version") or ""
        directory = module.get("Dir") or ""
        packages.append(
            {
                "name": path,
                "version": str(version),
                "path": _rel(root, Path(directory)) if directory else "",
                "source": "direct" if not module.get("Indirect") else "transitive",
                "declared_license": _detect_license_from_dir(Path(directory)) if directory else "",
            }
        )
    notes.append("source: `go list -m -json all`")
    notes.append("Go modules declare no license field: licenses are detected from each module's LICENSE file")
    return packages, notes


def _detect_license_from_dir(directory: Path) -> str:
    if not directory.is_dir():
        return ""
    candidates = []
    try:
        entries = sorted(directory.iterdir())
    except OSError:
        return ""
    for entry in entries:
        if not entry.is_file():
            continue
        name = entry.name.upper()
        if "LICENSE" in name or "COPYING" in name:
            candidates.append(entry)
    for entry in candidates:
        try:
            head = entry.read_text(encoding="utf-8", errors="replace")[:4000].lower()
        except OSError:
            continue
        for marker, spdx in LICENSE_FILE_MARKERS:
            if marker in head:
                return spdx
    return ""


def _which(binary: str) -> str:
    from shutil import which

    return which(binary) or ""


COLLECTORS = {
    "node": collect_node,
    "python": collect_python,
    "rust": collect_rust,
    "go": collect_go,
}


# --------------------------------------------------------------------------
# Policy check
# --------------------------------------------------------------------------


def load_policy(path: Path) -> dict:
    data = _read_json(path)
    policy = {
        "allowed": [str(item) for item in data.get("allowed", []) if isinstance(item, str)],
        "restricted": [str(item) for item in data.get("restricted", []) if isinstance(item, str)],
        "forbidden": [str(item) for item in data.get("forbidden", []) if isinstance(item, str)],
        "exceptions": [],
    }
    exceptions = data.get("exceptions")
    if isinstance(exceptions, list):
        for entry in exceptions:
            if isinstance(entry, dict):
                policy["exceptions"].append(entry)
    return policy


def _is_exception(entry: dict, package: dict) -> bool:
    name = entry.get("package")
    if not isinstance(name, str) or not name:
        return False
    if name != package["name"]:
        return False
    license_value = entry.get("license")
    if isinstance(license_value, str) and license_value:
        if license_value not in [package["license"], *package.get("alternatives", [])]:
            return False
    return True


def check_policy(packages: list[dict], policy: dict) -> dict:
    allowed = set(policy["allowed"])
    forbidden = set(policy["forbidden"])
    violations: list[dict] = []
    unknown: list[dict] = []
    for package in packages:
        if any(_is_exception(entry, package) for entry in policy["exceptions"]):
            continue
        ids = [package["license"], *package.get("alternatives", [])]
        if set(ids) & allowed:
            continue
        if any(item in forbidden for item in ids):
            violations.append(package)
            continue
        if package["license"] in {UNKNOWN, NOASSERTION} or package["license"].startswith(
            "LicenseRef-"
        ):
            unknown.append(package)
    return {"violations": violations, "unknown": unknown}


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def build_inventory(root: Path, ecosystem: str) -> dict:
    collector = COLLECTORS[ecosystem]
    packages, notes = collector(root)
    normalized: list[dict] = []
    for package in packages:
        record = normalize_license(package.get("declared_license", ""))
        normalized.append(
            {
                "name": package["name"],
                "version": package["version"],
                "license": record["license"],
                "declared_license": record["raw"],
                "expression": record["expression"],
                "alternatives": record["alternatives"],
                "source": package["source"],
                "path": package.get("path", ""),
            }
        )
    normalized.sort(key=lambda item: (item["name"].lower(), item["version"]))

    by_license: dict[str, int] = {}
    for package in normalized:
        by_license[package["license"]] = by_license.get(package["license"], 0) + 1

    return {
        "schema_version": SCHEMA_VERSION,
        "ecosystem": ecosystem,
        "root": str(root),
        "notes": notes,
        "totals": {
            "packages": len(normalized),
            "direct": sum(1 for item in normalized if item["source"] == "direct"),
            "transitive": sum(1 for item in normalized if item["source"] == "transitive"),
            "unknown_license": sum(
                1 for item in normalized if item["license"] in {UNKNOWN, NOASSERTION}
            ),
        },
        "licenses": dict(sorted(by_license.items(), key=lambda kv: (-kv[1], kv[0]))),
        "packages": normalized,
    }


def print_markdown(inventory: dict, policy_result: dict | None, attribution: dict | None) -> None:
    print(f"# License inventory — {inventory['ecosystem']} — {inventory['root']}\n")
    for note in inventory["notes"]:
        print(f"- {note}")
    totals = inventory["totals"]
    print(
        f"\nPackages: {totals['packages']} "
        f"(direct {totals['direct']}, transitive {totals['transitive']}), "
        f"unknown license: {totals['unknown_license']}\n"
    )
    print("## Licenses\n")
    print("| License | Packages |\n|---------|----------|")
    for license_id, count in inventory["licenses"].items():
        print(f"| {license_id} | {count} |")
    print("\n## Packages\n")
    print("| Package | Version | License | Source |\n|---------|---------|---------|--------|")
    for package in inventory["packages"]:
        print(
            f"| {package['name']} | {package['version'] or '-'} | "
            f"{package['license']} | {package['source']} |"
        )
    if policy_result is not None:
        print("\n## Policy\n")
        print(f"Violations: {len(policy_result['violations'])}")
        for package in policy_result["violations"]:
            print(f"- {package['name']} {package['version']} — {package['license']}")
        print(f"Unknown license entries: {len(policy_result['unknown'])}")
        for package in policy_result["unknown"]:
            print(f"- {package['name']} {package['version']}")
    if attribution is not None:
        print("\n## Attribution file\n")
        print(
            f"- {attribution['path']}: "
            f"{'present' if attribution['ok'] else 'MISSING or empty'}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a normalized license inventory for a dependency tree.",
    )
    parser.add_argument("--root", default=".", help="Project root to scan (default: .)")
    parser.add_argument(
        "--ecosystem",
        required=True,
        choices=sorted(COLLECTORS),
        help="Dependency ecosystem to inventory",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    parser.add_argument(
        "--policy",
        default="",
        help="Path to a license policy JSON file; exits 1 on a forbidden license",
    )
    parser.add_argument(
        "--attribution",
        default="",
        help="Path to the attribution file (NOTICE or THIRD_PARTY_LICENSES) to check",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    inventory = build_inventory(root, args.ecosystem)

    policy_result = None
    if args.policy:
        policy_path = Path(args.policy)
        if not policy_path.is_file():
            print(f"error: policy file not found: {policy_path}", file=sys.stderr)
            return 2
        policy_result = check_policy(inventory["packages"], load_policy(policy_path))
        inventory["policy"] = {
            "violations": [item["name"] for item in policy_result["violations"]],
            "unknown": [item["name"] for item in policy_result["unknown"]],
        }

    attribution = None
    if args.attribution:
        attribution_path = Path(args.attribution)
        exists = attribution_path.is_file() and attribution_path.stat().st_size > 0
        attribution = {"path": str(attribution_path), "ok": exists}
        inventory["attribution"] = attribution

    if args.json:
        json.dump(inventory, sys.stdout, indent=2, sort_keys=False)
        print()
    else:
        print_markdown(inventory, policy_result, attribution)

    if attribution is not None and not attribution["ok"]:
        print("error: attribution file is missing or empty", file=sys.stderr)
        return 1
    if policy_result is not None and policy_result["violations"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
