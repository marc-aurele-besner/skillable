#!/usr/bin/env python3
"""Read-only static scan for common accessibility candidates in web source.

Usage:
  python3 -I a11y_scan.py <path> [--json] [--max N]

Walks HTML, JSX/TSX, Vue, Svelte, Astro, Angular templates, and CSS-family
files under <path> (skipping node_modules, build output, and VCS folders) and
prints candidate issues with file:line, a rule id, and the WCAG success
criterion it may fail.

Output is a list of CANDIDATES, not findings: regex scanning cannot see
props, wrapper components, or global styles. Verify each hit in context
before reporting it. Stdlib only; never writes, never executes project code,
never touches the network.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

MARKUP_EXT = {".html", ".htm", ".jsx", ".tsx", ".js", ".ts", ".vue", ".svelte", ".astro", ".hbs", ".njk", ".liquid", ".erb", ".php"}
STYLE_EXT = {".css", ".scss", ".sass", ".less", ".pcss"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".nuxt", ".svelte-kit", ".astro", "out", "coverage", ".turbo", ".cache", "vendor", "storybook-static"}
MAX_FILE_BYTES = 1_000_000

# (rule id, regex, WCAG SC, message). Applied per line to markup files.
MARKUP_RULES = [
    ("img-no-alt", re.compile(r"<img\b(?![^>]*\balt\s*=)[^>]*>", re.I), "1.1.1 Non-text Content (A)", "<img> without alt attribute"),
    ("click-non-interactive", re.compile(r"<(div|span|li|td|img|p|section|article)\b(?![^>]*\brole\s*=)[^>]*\b(onClick|@click|v-on:click|on:click|\(click\))\s*=", re.I), "2.1.1 Keyboard (A) / 4.1.2 Name, Role, Value (A)", "click handler on a non-interactive element with no role"),
    ("positive-tabindex", re.compile(r"\btab[iI]ndex\s*=\s*[\"'{]?\s*[1-9]"), "2.4.3 Focus Order (A)", "positive tabindex overrides natural focus order"),
    ("aria-hidden-focusable", re.compile(r"<(a|button|input|select|textarea)\b[^>]*\baria-hidden\s*=\s*[\"'{]?\s*true", re.I), "4.1.2 Name, Role, Value (A)", "aria-hidden on a focusable element"),
    ("viewport-no-zoom", re.compile(r"<meta[^>]*name\s*=\s*[\"']viewport[\"'][^>]*(user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(\.0)?\b)", re.I), "1.4.4 Resize Text (AA)", "viewport meta disables zoom"),
    ("anchor-no-href", re.compile(r"<a\b(?![^>]*\bhref\s*=)[^>]*\b(onClick|@click|on:click|\(click\))\s*=", re.I), "2.1.1 Keyboard (A)", "<a> with a click handler but no href is not focusable"),
    ("href-hash-button", re.compile(r"<a\b[^>]*\bhref\s*=\s*[\"']#?[\"'][^>]*\b(onClick|@click|on:click|\(click\))\s*=", re.I), "4.1.2 Name, Role, Value (A)", "link used as a button (href=\"#\" + click handler)"),
    ("placeholder-only", re.compile(r"<input\b(?![^>]*\b(aria-label|aria-labelledby|id)\s*=)(?![^>]*type\s*=\s*[\"'](hidden|submit|button|reset|image)[\"'])[^>]*\bplaceholder\s*=", re.I), "1.3.1 Info and Relationships (A) / 4.1.2 (A)", "input with placeholder but no id or ARIA label to attach a label to"),
    ("paste-blocked", re.compile(r"\b(onPaste|@paste|on:paste|\(paste\))\s*=\s*[^>]*preventDefault", re.I), "3.3.8 Accessible Authentication (Minimum) (AA)", "paste blocked (check if it is a password or OTP field)"),
    ("autoplay-media", re.compile(r"<(video|audio)\b[^>]*\bautoplay\b", re.I), "2.2.2 Pause, Stop, Hide (A) / 1.4.2 Audio Control (A)", "auto-playing media (check for pause control and muted)"),
    ("html-no-lang", re.compile(r"<html\b(?![^>]*\blang\s*=)[^>]*>", re.I), "3.1.1 Language of Page (A)", "<html> without lang"),
    ("redundant-role", re.compile(r"<(button)\b[^>]*\brole\s*=\s*[\"']button[\"']|<a\b[^>]*\bhref[^>]*\brole\s*=\s*[\"']link[\"']", re.I), "best practice (not a failure)", "redundant ARIA role on a native element"),
]

STYLE_RULES = [
    ("outline-none", re.compile(r"outline\s*:\s*(none|0)\b", re.I), "2.4.7 Focus Visible (AA)", "outline removed (check for a :focus-visible replacement)"),
]

ANIMATION_RE = re.compile(r"@keyframes|\banimation\s*:|\banimation-name\s*:|scroll-behavior\s*:\s*smooth", re.I)
REDUCED_MOTION_RE = re.compile(r"prefers-reduced-motion|useReducedMotion|reducedMotion|MotionConfig", re.I)


def iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in MARKUP_EXT | STYLE_EXT:
                yield p


def read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def scan(root: Path):
    hits = []
    animation_files = []
    reduced_motion_seen = False
    for path in iter_files(root):
        text = read_text(path)
        if text is None:
            continue
        ext = path.suffix.lower()
        # Single-file components and JSX can hold styles too.
        rules = []
        if ext in MARKUP_EXT:
            rules += MARKUP_RULES
        if ext in STYLE_EXT or ext in {".vue", ".svelte", ".astro", ".html", ".htm"} or "styled" in text or "css`" in text:
            rules += STYLE_RULES
        for lineno, line in enumerate(text.splitlines(), 1):
            for rule_id, rx, sc, msg in rules:
                if rx.search(line):
                    hits.append({"file": str(path), "line": lineno, "rule": rule_id, "wcag": sc, "message": msg, "snippet": line.strip()[:160]})
        if REDUCED_MOTION_RE.search(text):
            reduced_motion_seen = True
        m = ANIMATION_RE.search(text)
        if m:
            lineno = text.count("\n", 0, m.start()) + 1
            animation_files.append((str(path), lineno, bool(REDUCED_MOTION_RE.search(text))))
    if animation_files and not reduced_motion_seen:
        for f, lineno, _ in animation_files:
            hits.append({"file": f, "line": lineno, "rule": "no-reduced-motion", "wcag": "2.3.3 Animation from Interactions (AAA) / 2.2.2 if auto-playing (A)", "message": "animation with no prefers-reduced-motion handling anywhere in scope", "snippet": ""})
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only accessibility candidate scan.")
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--json", action="store_true", help="print JSON")
    ap.add_argument("--max", type=int, default=300, help="maximum hits to print (default 300)")
    args = ap.parse_args()
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"path not found: {args.path}", file=sys.stderr)
        return 2
    hits = scan(root)
    total = len(hits)
    hits = hits[: args.max]
    if args.json:
        print(json.dumps({"root": str(root), "total": total, "candidates": hits}, indent=2))
        return 0
    if not hits:
        print("No candidates. (A clean scan is not a clean audit: walk the keyboard flows and check contrast.)")
        return 0
    for h in hits:
        rel = os.path.relpath(h["file"], root) if root.is_dir() else h["file"]
        print(f"{rel}:{h['line']}  [{h['rule']}]  {h['message']}  — {h['wcag']}")
        if h["snippet"]:
            print(f"    {h['snippet']}")
    print(f"\n{total} candidate(s){' (truncated)' if total > len(hits) else ''}. Verify each in context before reporting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
