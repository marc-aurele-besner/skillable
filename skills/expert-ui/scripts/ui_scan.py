#!/usr/bin/env python3
"""Read-only helpers for the expert-ui review.

Subcommands:
  contrast FG BG [FG BG ...]
      Print the WCAG 2.x contrast ratio for each foreground/background pair
      and whether it passes AA / AAA for body and large text. Colors may be
      #rgb, #rrggbb, #rrggbbaa (alpha composited over BG), rgb()/rgba(), or
      hsl()/hsla().

  scan [PATH ...] [--json] [--top N]
      Walk style and component files (css, scss, sass, less, js, jsx, ts,
      tsx, vue, svelte, astro, html) and count hard-coded visual values that
      usually bypass design tokens: hex/rgb/hsl colors, px font sizes, px
      spacing (margin/padding/gap/inset), raw z-index numbers, arbitrary
      Tailwind values (e.g. `p-[13px]`, `text-[#333]`), inline style objects,
      and `!important`. Prints per-file counts plus the most common literal
      values, so the reviewer can spot drift and off-scale values quickly.

The script never writes, never runs project code, and never touches the
network. It uses the Python standard library only.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

EXTS = {
    ".css", ".scss", ".sass", ".less", ".js", ".jsx", ".ts", ".tsx",
    ".vue", ".svelte", ".astro", ".html", ".mdx",
}
SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", ".nuxt", ".svelte-kit",
    ".astro", "out", "coverage", "vendor", ".turbo", ".vercel", "storybook-static",
}
MAX_FILE_BYTES = 512 * 1024

PATTERNS = {
    "color": re.compile(
        r"(?<![\w-])(#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\))"
    ),
    "font_size_px": re.compile(
        r"font-?size\s*[:=]\s*['\"]?(\d+(?:\.\d+)?px)", re.IGNORECASE
    ),
    "spacing_px": re.compile(
        r"(?:margin|padding|gap|inset|top|left|right|bottom)"
        r"(?:-?(?:top|left|right|bottom|inline|block|x|y))?\s*[:=]\s*['\"]?"
        r"(-?\d+(?:\.\d+)?px)",
        re.IGNORECASE,
    ),
    "z_index": re.compile(r"z-?index\s*[:=]\s*['\"]?(-?\d+)", re.IGNORECASE),
    "tw_arbitrary": re.compile(
        r"(?<![\w-])(?:[a-z]+:)*-?[a-z][a-z0-9-]*-\[[^\]\s]+\]"
    ),
    "inline_style": re.compile(r"style=\{\{|style=\"[^\"]*:"),
    "important": re.compile(r"!important"),
}
# Lines that define tokens are the source of truth, not drift.
TOKEN_DEF = re.compile(r"(?:^|[{;\s])(--[\w-]+\s*:|\$[\w-]+\s*:|@[\w-]+\s*:)")


def iter_files(paths: list[str]):
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            if p.suffix in EXTS:
                yield p
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for name in files:
                fp = Path(root) / name
                if fp.suffix in EXTS and not name.endswith((".min.css", ".min.js", ".map")):
                    yield fp


def scan(paths: list[str], top: int) -> dict:
    per_file: dict[str, Counter] = defaultdict(Counter)
    values: dict[str, Counter] = defaultdict(Counter)
    first_seen: dict[tuple[str, str], str] = {}
    for fp in iter_files(paths):
        try:
            if fp.stat().st_size > MAX_FILE_BYTES:
                continue
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if TOKEN_DEF.search(line):
                continue
            for kind, rx in PATTERNS.items():
                for m in rx.finditer(line):
                    val = (m.group(1) if m.groups() else m.group(0)).strip()
                    per_file[str(fp)][kind] += 1
                    if kind in ("inline_style", "important"):
                        continue
                    key = val.lower()
                    values[kind][key] += 1
                    first_seen.setdefault((kind, key), f"{fp}:{lineno}")
    files = sorted(per_file.items(), key=lambda kv: -sum(kv[1].values()))
    return {
        "files": [{"file": f, **dict(c), "total": sum(c.values())} for f, c in files],
        "top_values": {
            kind: [
                {"value": v, "count": n, "first": first_seen[(kind, v)]}
                for v, n in counter.most_common(top)
            ]
            for kind, counter in values.items()
        },
    }


def parse_color(s: str, bg: tuple[float, float, float] | None = None):
    s = s.strip().lower()
    alpha = 1.0
    if s.startswith("#"):
        h = s[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) not in (6, 8) or not re.fullmatch(r"[0-9a-f]+", h):
            raise ValueError(f"bad hex color: {s}")
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        if len(h) == 8:
            alpha = int(h[6:8], 16) / 255
    else:
        m = re.fullmatch(r"(rgba?|hsla?)\(([^)]*)\)", s)
        if not m:
            raise ValueError(f"unsupported color: {s}")
        parts = [p for p in re.split(r"[\s,/]+", m.group(2).strip()) if p]
        if len(parts) < 3:
            raise ValueError(f"bad color: {s}")

        def num(p: str, scale: float) -> float:
            return float(p[:-1]) / 100 if p.endswith("%") else float(p.rstrip("deg")) / scale

        if m.group(1).startswith("rgb"):
            r, g, b = (num(p, 255) for p in parts[:3])
        else:
            hue = float(parts[0].rstrip("deg")) / 360
            sat, light = num(parts[1], 100), num(parts[2], 100)
            r, g, b = colorsys.hls_to_rgb(hue % 1, light, sat)
        if len(parts) > 3:
            alpha = num(parts[3], 1)
    if alpha < 1:
        base = bg or (1.0, 1.0, 1.0)
        r, g, b = (alpha * c + (1 - alpha) * k for c, k in zip((r, g, b), base))
    return (r, g, b)


def luminance(rgb) -> float:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str) -> dict:
    bg_rgb = parse_color(bg)
    fg_rgb = parse_color(fg, bg_rgb)
    l1, l2 = sorted((luminance(fg_rgb), luminance(bg_rgb)), reverse=True)
    ratio = (l1 + 0.05) / (l2 + 0.05)
    return {
        "fg": fg,
        "bg": bg,
        "ratio": round(ratio, 2),
        "AA_text": ratio >= 4.5,
        "AA_large_or_ui": ratio >= 3.0,
        "AAA_text": ratio >= 7.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("contrast", help="WCAG contrast for FG BG pairs")
    c.add_argument("colors", nargs="+")
    c.add_argument("--json", action="store_true")
    s = sub.add_parser("scan", help="count hard-coded visual values")
    s.add_argument("paths", nargs="*", default=["."])
    s.add_argument("--json", action="store_true")
    s.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    if args.cmd == "contrast":
        if len(args.colors) % 2:
            ap.error("contrast takes FG BG pairs")
        try:
            rows = [contrast(args.colors[i], args.colors[i + 1]) for i in range(0, len(args.colors), 2)]
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for r in rows:
                flags = " ".join(
                    f"{k}={'pass' if r[k] else 'FAIL'}" for k in ("AA_text", "AA_large_or_ui", "AAA_text")
                )
                print(f"{r['fg']} on {r['bg']}: {r['ratio']}:1  {flags}")
        return 0

    result = scan(args.paths, args.top)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"Files with hard-coded visual values: {len(result['files'])}")
    for row in result["files"][:25]:
        detail = ", ".join(f"{k}={v}" for k, v in row.items() if k not in ("file", "total"))
        print(f"  {row['total']:4d}  {row['file']}  ({detail})")
    for kind, vals in result["top_values"].items():
        print(f"\nMost common {kind}:")
        for v in vals:
            print(f"  {v['count']:4d}  {v['value']}  (first: {v['first']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
