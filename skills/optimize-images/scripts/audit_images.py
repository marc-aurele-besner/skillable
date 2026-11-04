#!/usr/bin/env python3
"""Audit image usage in a project folder and report what can be optimized.

Read-only and stdlib-only. Point it at a source folder or a whole repo:

    python3 -I audit_images.py .
    python3 -I audit_images.py . --json
    python3 -I audit_images.py dist --include-build
    python3 -I audit_images.py . --budget-file image-budget.json

It scans HTML, JSX/TSX, Vue, Svelte, Astro, MDX, Markdown, CSS and plain
JS/TS for image references (`<img>`, `<source>`, framework `<Image>` components,
CSS `url()`, Markdown `![alt](...)`, static image imports) and reports, per
reference:

  - missing explicit dimensions (width/height attributes or aspect-ratio)
  - missing responsive sources (srcset, and sizes when srcset exists)
  - missing loading/decoding hints (loading="lazy" below the fold,
    decoding="async" for non-critical images)
  - missing fetchpriority="high" on the likely LCP image of a page
  - the on-disk byte size and intrinsic pixel size of the referenced file
  - referenced files that do not exist, and image files nothing references

Optional budgets (JSON file):

    {
      "max_image_bytes": 250000,
      "max_total_bytes": 2000000,
      "max_page_bytes": {"index.html": 800000, "*": 1000000}
    }

Exit code is 0 when the audit ran (findings are reported, not judged). It is 1
only when a budget is exceeded, so the script can be used as a CI gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

IMAGE_EXTENSIONS = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".gif": "gif",
    ".svg": "svg",
    ".webp": "webp",
    ".avif": "avif",
    ".jxl": "jxl",
    ".bmp": "bmp",
    ".ico": "ico",
    ".tif": "tiff",
    ".tiff": "tiff",
    ".apng": "png",
}

TEXT_EXTENSIONS = {
    ".html": "html",
    ".htm": "html",
    ".jsx": "jsx",
    ".tsx": "jsx",
    ".js": "jsx",
    ".mjs": "jsx",
    ".cjs": "jsx",
    ".ts": "jsx",
    ".mts": "jsx",
    ".vue": "vue",
    ".svelte": "svelte",
    ".astro": "astro",
    ".mdx": "mdx",
    ".md": "markdown",
    ".markdown": "markdown",
    ".css": "css",
    ".scss": "css",
    ".sass": "css",
    ".less": "css",
}

SKIP_DIRS = {
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
    "vendor",
    "coverage",
    ".turbo",
    ".cache",
}

BUILD_DIRS = {
    "dist",
    "build",
    "out",
    ".next",
    ".nuxt",
    ".output",
    ".svelte-kit",
    ".astro",
    ".vercel",
    ".netlify",
    "storybook-static",
    "target",
}

# Contexts where markup-level checks (dimensions, srcset, loading) make sense.
MARKUP_CONTEXTS = {"html", "jsx", "vue", "svelte", "astro", "mdx"}

TAG_RE = re.compile(r"<\s*(img|source|image|picture)\b([^>]*?)/?>", re.IGNORECASE)
ATTR_RE = re.compile(
    r"""(?P<name>[:@#a-zA-Z_][-\w:.#]*)\s*=\s*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|\{`(?P<bt>[^`]*)`\}|\{(?P<br>[^}]*)\})"""
)
CSS_URL_RE = re.compile(r"""url\(\s*(?:"([^"]*)"|'([^']*)'|([^)'"]+))\s*\)""", re.IGNORECASE)
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)")
IMPORT_RE = re.compile(
    r"""import\s+(?P<default>[A-Za-z_$][\w$]*)?\s*(?:\{(?P<named>[^}]*)\})?\s*from\s*['"](?P<path>[^'"]+)['"]"""
)
NEW_URL_RE = re.compile(r"""new\s+URL\(\s*['"]([^'"]+)['"]""")
BARE_IDENT_RE = re.compile(r"^[A-Za-z_$][\w$]*$")

MAX_TEXT_BYTES = 8_000_000

ISSUE_ORDER = [
    "missing-file",
    "missing-dimensions",
    "missing-srcset",
    "missing-sizes",
    "missing-loading",
    "missing-decoding",
    "missing-fetchpriority",
    "lcp-lazy",
    "possible-upscale",
    "oversized-image",
]

SEVERITY = {
    "missing-file": "high",
    "missing-dimensions": "medium",
    "missing-srcset": "medium",
    "missing-sizes": "low",
    "missing-loading": "low",
    "missing-decoding": "low",
    "missing-fetchpriority": "medium",
    "lcp-lazy": "high",
    "possible-upscale": "medium",
    "oversized-image": "high",
}


def read_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# --------------------------------------------------------------------------
# Intrinsic image sizes (stdlib only, best effort)
# --------------------------------------------------------------------------


def png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def gif_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 10 or data[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    width, height = struct.unpack("<HH", data[6:10])
    return int(width), int(height)


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    index = 2
    length = len(data)
    while index + 9 < length:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        if index + 4 > length:
            break
        seg_len = struct.unpack(">H", data[index + 2 : index + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height, width = struct.unpack(">HH", data[index + 5 : index + 9])
            return int(width), int(height)
        index += 2 + seg_len
    return None


def webp_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 16 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    if chunk == b"VP8 " and len(data) >= 30:
        if data[23:26] != b"\x9d\x01\x2a":
            return None
        width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return int(width), int(height)
    if chunk == b"VP8L" and len(data) >= 25:
        if data[20] != 0x2F:
            return None
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return int(width), int(height)
    return None


def avif_size(data: bytes) -> tuple[int, int] | None:
    index = data.find(b"ispe")
    if index < 0 or index + 16 > len(data):
        return None
    width, height = struct.unpack(">II", data[index + 8 : index + 16])
    return int(width), int(height)


def svg_size(data: bytes) -> tuple[int, int] | None:
    head = data[:4096].decode("utf-8", errors="replace")
    viewbox = re.search(r"viewBox\s*=\s*[\"']\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)", head)
    if viewbox:
        return int(float(viewbox.group(1))), int(float(viewbox.group(2)))
    width = re.search(r"\bwidth\s*=\s*[\"']\s*([\d.]+)", head)
    height = re.search(r"\bheight\s*=\s*[\"']\s*([\d.]+)", head)
    if width and height:
        return int(float(width.group(1))), int(float(height.group(1)))
    return None


def intrinsic_size(path: Path, fmt: str) -> tuple[int, int] | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > 32_000_000:
        return None
    if fmt == "png":
        return png_size(data)
    if fmt == "gif":
        return gif_size(data)
    if fmt == "jpeg":
        return jpeg_size(data)
    if fmt == "webp":
        return webp_size(data)
    if fmt == "avif":
        return avif_size(data)
    if fmt == "svg":
        return svg_size(data)
    return None


# --------------------------------------------------------------------------
# File walking
# --------------------------------------------------------------------------


def iter_files(root: Path, extra_skip: set[str], include_build: bool) -> list[Path]:
    skip = set(SKIP_DIRS) | set(extra_skip)
    if not include_build:
        skip |= BUILD_DIRS
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip and not d.startswith("."))
        for name in sorted(filenames):
            found.append(Path(dirpath) / name)
    return found


# --------------------------------------------------------------------------
# Reference extraction
# --------------------------------------------------------------------------


def parse_attrs(raw: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in ATTR_RE.finditer(raw):
        name = match.group("name").lower().lstrip(":@#")
        value = match.group("dq")
        if value is None:
            value = match.group("sq")
        if value is None:
            value = match.group("bt")
        if value is None:
            value = match.group("br")
        if value is None:
            value = ""
        attrs[name] = value.strip()
    return attrs


def import_aliases(text: str) -> dict[str, str]:
    """Map local identifiers to the image path they were imported from."""
    aliases: dict[str, str] = {}
    for match in IMPORT_RE.finditer(text):
        path = match.group("path")
        if PurePosixPath(path).suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        default = match.group("default")
        if default:
            aliases[default] = path
        named = match.group("named") or ""
        for part in named.split(","):
            part = part.strip()
            if not part:
                continue
            bits = re.split(r"\s+as\s+", part)
            if len(bits) == 2:
                aliases[bits[1].strip()] = path
            elif len(bits) == 1:
                aliases[bits[0].strip()] = path
    return aliases


def is_dynamic(value: str) -> bool:
    if not value:
        return False
    if value.startswith(("data:", "http://", "https://", "//")):
        return False
    if "$" in value or "{" in value or "}" in value:
        return True
    return bool(BARE_IDENT_RE.fullmatch(value))


def clean_src(value: str) -> str:
    value = value.strip().strip("\"'")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme in ("http", "https", "data"):
        return ""
    path = parsed.path or value
    path = unquote(path.split("?")[0].split("#")[0])
    return path.strip()


def parse_srcset(value: str) -> list[tuple[str, str]]:
    """Return [(url, descriptor)] from a srcset attribute."""
    entries: list[tuple[str, str]] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split()
        entries.append((bits[0], bits[1] if len(bits) > 1 else ""))
    return entries


def max_srcset_width(value: str) -> int | None:
    widest = None
    for _url, descriptor in parse_srcset(value):
        match = re.fullmatch(r"([\d.]+)w", descriptor)
        if match:
            width = int(float(match.group(1)))
            widest = width if widest is None else max(widest, width)
    return widest


def resolve_path(src: str, base_dir: Path, root: Path, aliases: dict[str, str]) -> Path | None:
    """Best-effort resolution of an image path to a file on disk."""
    if not src:
        return None
    if src.startswith(("http://", "https://", "//", "data:")):
        return None
    candidate = src
    if candidate.startswith("~"):
        candidate = candidate[1:]
    options: list[Path] = []
    if candidate.startswith("/"):
        options.append(root / candidate.lstrip("/"))
        options.append(root / "public" / candidate.lstrip("/"))
        options.append(root / "static" / candidate.lstrip("/"))
    else:
        options.append(base_dir / candidate)
        options.append(root / candidate)
        options.append(root / "public" / candidate)
        options.append(root / "static" / candidate)
    for option in options:
        try:
            if option.is_file():
                return option
        except OSError:
            continue
    return options[0] if options else None


def make_reference(
    *,
    root: Path,
    source: Path,
    line: int,
    kind: str,
    context: str,
    src: str,
    attrs: dict[str, str],
    aliases: dict[str, str],
) -> dict:
    ref: dict = {
        "file": source.relative_to(root).as_posix(),
        "line": line,
        "kind": kind,
        "context": context,
        "src": src,
        "srcset": attrs.get("srcset", ""),
        "sizes": attrs.get("sizes", ""),
        "width": attrs.get("width", ""),
        "height": attrs.get("height", ""),
        "loading": attrs.get("loading", ""),
        "decoding": attrs.get("decoding", ""),
        "fetchpriority": attrs.get("fetchpriority", ""),
        "alt": attrs.get("alt", ""),
        "aspect_ratio": "aspect-ratio" in attrs.get("style", "").replace(" ", ""),
        "dynamic": False,
        "remote": src.startswith(("http://", "https://", "//")),
        "resolved": None,
        "exists": None,
        "bytes": None,
        "format": None,
        "intrinsic_width": None,
        "intrinsic_height": None,
        "issues": [],
    }

    raw_src = src
    if is_dynamic(src) and src in aliases:
        raw_src = aliases[src]
        ref["dynamic"] = False
    elif is_dynamic(src):
        ref["dynamic"] = True
        ref["issues"].append("dynamic-src")
        return ref

    path = resolve_path(clean_src(raw_src), source.parent, root, aliases)
    ref["resolved"] = clean_src(raw_src)
    if path is None:
        return ref

    ref["_abs"] = str(path)
    try:
        ref["resolved"] = path.resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        ref["resolved"] = str(path)

    try:
        exists = path.is_file()
    except OSError:
        exists = False
    ref["exists"] = exists
    if not exists:
        ref["issues"].append("missing-file")
        return ref

    try:
        ref["bytes"] = path.stat().st_size
    except OSError:
        ref["bytes"] = None
    fmt = IMAGE_EXTENSIONS.get(path.suffix.lower())
    ref["format"] = fmt
    if fmt:
        size = intrinsic_size(path, fmt)
        if size:
            ref["intrinsic_width"], ref["intrinsic_height"] = size
    return ref


def find_references(root: Path, source: Path, text: str, context: str) -> list[dict]:
    aliases = import_aliases(text)
    refs: list[dict] = []
    lines = text.splitlines()

    def line_of(offset: int) -> int:
        return text.count("\n", 0, offset) + 1

    for match in TAG_RE.finditer(text):
        attrs = parse_attrs(match.group(2))
        tag = match.group(1).lower()
        src = attrs.get("src", "")
        if tag == "source" and not src:
            srcset = attrs.get("srcset", "")
            src = parse_srcset(srcset)[0][0] if srcset else ""
        if not src:
            if not attrs.get("srcset"):
                continue
        refs.append(
            make_reference(
                root=root,
                source=source,
                line=line_of(match.start()),
                kind=tag,
                context=context,
                src=src,
                attrs=attrs,
                aliases=aliases,
            )
        )

    if context == "css":
        for match in CSS_URL_RE.finditer(text):
            raw = match.group(1) or match.group(2) or match.group(3) or ""
            if not raw.strip():
                continue
            refs.append(
                make_reference(
                    root=root,
                    source=source,
                    line=line_of(match.start()),
                    kind="css-url",
                    context=context,
                    src=raw.strip(),
                    attrs={},
                    aliases=aliases,
                )
            )

    if context == "markdown":
        for match in MD_IMAGE_RE.finditer(text):
            refs.append(
                make_reference(
                    root=root,
                    source=source,
                    line=line_of(match.start()),
                    kind="markdown-image",
                    context=context,
                    src=match.group(1),
                    attrs={},
                    aliases=aliases,
                )
            )

    for match in NEW_URL_RE.finditer(text):
        raw = match.group(1)
        if PurePosixPath(raw).suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        refs.append(
            make_reference(
                root=root,
                source=source,
                line=line_of(match.start()),
                kind="new-url",
                context=context,
                src=raw,
                attrs={},
                aliases=aliases,
            )
        )

    return refs


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


def is_decorative(ref: dict) -> bool:
    """True for images that carry no information (empty alt, CSS background)."""
    if ref.get("kind") == "css-url":
        return True
    return ref.get("alt", "").strip().lower() in ("", "decorative")


def check_reference(ref: dict) -> None:
    issues = ref["issues"]
    if ref["context"] not in MARKUP_CONTEXTS:
        return
    if ref["kind"] == "source":
        return

    has_dimensions = bool(ref["width"] and ref["height"]) or ref["aspect_ratio"]
    if not has_dimensions:
        issues.append("missing-dimensions")

    if ref["srcset"]:
        if not ref["sizes"]:
            issues.append("missing-sizes")
    elif not is_decorative(ref):
        issues.append("missing-srcset")

    if not ref["loading"]:
        issues.append("missing-loading")

    if not ref["decoding"]:
        issues.append("missing-decoding")

    intrinsic_width = ref.get("intrinsic_width")
    rendered = None
    if intrinsic_width and ref["width"].isdigit():
        rendered = int(ref["width"])
    elif intrinsic_width:
        rendered = max_srcset_width(ref.get("srcset", ""))
    if rendered and intrinsic_width and rendered > intrinsic_width:
        issues.append("possible-upscale")


def find_lcp_candidates(refs: list[dict]) -> dict[str, list[dict]]:
    """Group references per source file and pick the likely LCP image.

    The LCP image is the largest image the browser can paint without
    scrolling. An explicit fetchpriority="high" wins; otherwise the largest
    non-lazy image in the file is the best proxy, with the first non-lazy
    image as a fallback when the intrinsic size is unknown.
    """
    per_file: dict[str, list[dict]] = {}
    for ref in refs:
        if ref["context"] not in MARKUP_CONTEXTS:
            continue
        if ref["kind"] == "source":
            continue
        per_file.setdefault(ref["file"], []).append(ref)

    def area(ref: dict) -> int:
        width = ref.get("intrinsic_width") or 0
        height = ref.get("intrinsic_height") or 0
        return int(width) * int(height)

    candidates: dict[str, list[dict]] = {}
    for path, group in per_file.items():
        group.sort(key=lambda item: item["line"])
        explicit = [r for r in group if r["fetchpriority"] == "high"]
        if explicit:
            candidates[path] = explicit
            continue
        eager = [r for r in group if r["loading"] != "lazy"]
        sized = [r for r in eager if area(r) > 0]
        if sized:
            candidates[path] = [max(sized, key=area)]
        elif eager:
            candidates[path] = [eager[0]]
        elif group:
            candidates[path] = [group[0]]
    return candidates


def apply_lcp_checks(refs: list[dict], candidates: dict[str, list[dict]]) -> None:
    for path, group in candidates.items():
        for ref in group:
            if ref["fetchpriority"] == "high":
                continue
            ref["issues"].append("missing-fetchpriority")
            if ref["loading"] == "lazy":
                ref["issues"].append("lcp-lazy")


# --------------------------------------------------------------------------
# Budgets
# --------------------------------------------------------------------------


def load_budget(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Could not read budget file {path}: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(f"Budget file {path} must contain a JSON object")
    return data


def check_budgets(budget: dict, refs: list[dict], root: Path) -> list[dict]:
    failures: list[dict] = []
    max_image = budget.get("max_image_bytes")
    max_total = budget.get("max_total_bytes")
    max_page = budget.get("max_page_bytes") or {}

    unique_files: dict[str, int] = {}
    per_page: dict[str, int] = {}
    for ref in refs:
        size = ref.get("bytes")
        if not size:
            continue
        key = ref.get("resolved") or ref.get("src") or "?"
        unique_files[key] = max(unique_files.get(key, 0), size)
        per_page[ref["file"]] = per_page.get(ref["file"], 0) + size

    if isinstance(max_image, int):
        for key, size in sorted(unique_files.items(), key=lambda item: -item[1]):
            if size > max_image:
                failures.append(
                    {
                        "rule": "max_image_bytes",
                        "target": key,
                        "bytes": size,
                        "limit": max_image,
                        "message": f"{key} is {size} bytes, over the {max_image} byte per-image budget",
                    }
                )

    if isinstance(max_total, int):
        total = sum(unique_files.values())
        if total > max_total:
            failures.append(
                {
                    "rule": "max_total_bytes",
                    "target": "all referenced images",
                    "bytes": total,
                    "limit": max_total,
                    "message": f"referenced images total {total} bytes, over the {max_total} byte budget",
                }
            )

    if isinstance(max_page, dict):
        default = max_page.get("*")
        for page, size in sorted(per_page.items(), key=lambda item: -item[1]):
            limit = max_page.get(page, default)
            if isinstance(limit, int) and size > limit:
                failures.append(
                    {
                        "rule": "max_page_bytes",
                        "target": page,
                        "bytes": size,
                        "limit": limit,
                        "message": f"{page} loads {size} bytes of images, over the {limit} byte page budget",
                    }
                )
    return failures


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def human_bytes(count: int | None) -> str:
    if count is None:
        return "?"
    value = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def build_report(root: Path, refs: list[dict], unused: list[dict], budgets: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for ref in refs:
        for issue in ref["issues"]:
            counts[issue] = counts.get(issue, 0) + 1

    unique: dict[str, int] = {}
    for ref in refs:
        size = ref.get("bytes")
        key = ref.get("resolved") or ref.get("src")
        if size and key:
            unique[key] = max(unique.get(key, 0), size)

    by_format: dict[str, int] = {}
    for ref in refs:
        size = ref.get("bytes")
        fmt = ref.get("format")
        if size and fmt:
            by_format[fmt] = by_format.get(fmt, 0) + size

    page_bytes: dict[str, int] = {}
    for ref in refs:
        size = ref.get("bytes")
        if size:
            page_bytes[ref["file"]] = page_bytes.get(ref["file"], 0) + size

    return {
        "root": str(root),
        "totals": {
            "references": len(refs),
            "distinct_files": len(unique),
            "total_bytes": sum(unique.values()),
            "unused_files": len(unused),
            "unused_bytes": sum(item["bytes"] for item in unused),
            "issues": counts,
        },
        "bytes_by_format": by_format,
        "bytes_by_page": page_bytes,
        "references": refs,
        "unused_files": unused,
        "budget_failures": budgets,
    }


def print_report(report: dict) -> None:
    totals = report["totals"]
    print(f"Image audit - {report['root']}")
    print()
    print(
        f"{totals['references']} references to {totals['distinct_files']} distinct files "
        f"({human_bytes(totals['total_bytes'])} on disk)"
    )
    print(
        f"Unreferenced image files: {totals['unused_files']} "
        f"({human_bytes(totals['unused_bytes'])})"
    )
    print()

    counts = totals["issues"]
    if counts:
        print("Findings")
        print("--------")
        for issue in ISSUE_ORDER:
            if counts.get(issue):
                print(f"  {issue:<22} {counts[issue]}")
        extra = sorted(set(counts) - set(ISSUE_ORDER))
        for issue in extra:
            print(f"  {issue:<22} {counts[issue]}")
        print()
    else:
        print("No findings.")
        print()

    print("Heaviest referenced files")
    print("------------------------")
    seen: dict[str, dict] = {}
    for ref in report["references"]:
        size = ref.get("bytes")
        key = ref.get("resolved") or ref.get("src")
        if not size or not key:
            continue
        if key not in seen:
            seen[key] = {"bytes": size, "format": ref.get("format"), "refs": 0}
        seen[key]["refs"] += 1
    for key, info in sorted(seen.items(), key=lambda item: -item[1]["bytes"])[:15]:
        print(
            f"  {human_bytes(info['bytes']):>9}  {info['format'] or '?':<5} "
            f"{info['refs']:>2} ref(s)  {key}"
        )
    print()

    if report["unused_files"]:
        print("Unreferenced image files")
        print("------------------------")
        for item in sorted(report["unused_files"], key=lambda entry: -entry["bytes"])[:20]:
            print(f"  {human_bytes(item['bytes']):>9}  {item['file']}")
        if len(report["unused_files"]) > 20:
            print(f"  ... and {len(report['unused_files']) - 20} more")
        print()

    if report["budget_failures"]:
        print("Budget failures")
        print("--------------")
        for failure in report["budget_failures"]:
            print(f"  {failure['message']}")
        print()

    problems = [
        ref
        for ref in report["references"]
        if any(issue in SEVERITY for issue in ref["issues"])
    ]
    if problems:
        print("Details")
        print("-------")
        for ref in problems[:60]:
            flags = ", ".join(i for i in ref["issues"] if i in SEVERITY)
            src = ref.get("src") or ref.get("resolved") or "?"
            print(f"  {ref['file']}:{ref['line']}  {src}  [{flags}]")
        if len(problems) > 60:
            print(f"  ... and {len(problems) - 60} more")
        print()


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit image references, responsive hints, and bytes in a project folder."
    )
    parser.add_argument("path", nargs="?", default=".", help="Folder or repo to scan (default: .)")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a text report")
    parser.add_argument(
        "--include-build",
        action="store_true",
        help="Also scan build output folders (dist, build, .next, ...)",
    )
    parser.add_argument(
        "--skip-dir",
        action="append",
        default=[],
        help="Extra directory name to skip (repeatable)",
    )
    parser.add_argument(
        "--budget-file",
        help="JSON budget file; the script exits 1 when a budget is exceeded",
    )
    args = parser.parse_args()

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2

    refs: list[dict] = []
    referenced_paths: set[Path] = set()
    scanned = 0
    image_files: list[Path] = []

    for path in iter_files(root, set(args.skip_dir), args.include_build):
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            image_files.append(path)
        context = TEXT_EXTENSIONS.get(suffix)
        if context is None:
            continue
        text = read_text(path)
        if not text:
            continue
        scanned += 1
        for ref in find_references(root, path, text, context):
            refs.append(ref)
            absolute = ref.get("_abs")
            if absolute and ref.get("exists"):
                referenced_paths.add(Path(absolute))

    for ref in refs:
        check_reference(ref)
    apply_lcp_checks(refs, find_lcp_candidates(refs))

    unused: list[dict] = []
    for path in image_files:
        if path in referenced_paths:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        unused.append({"file": path.relative_to(root).as_posix(), "bytes": size})

    failures: list[dict] = []
    if args.budget_file:
        budget = load_budget(Path(args.budget_file).expanduser().resolve())
        failures = check_budgets(budget, refs, root)

    report = build_report(root, refs, unused, failures)
    report["totals"]["files_scanned"] = scanned

    if args.json:
        for ref in report["references"]:
            ref.pop("_abs", None)
        print(json.dumps(report, indent=2, sort_keys=False))
    else:
        print(f"Scanned {scanned} text files.")
        print_report(report)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
