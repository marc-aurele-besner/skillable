#!/usr/bin/env python3
"""Map a web app's UX surface from source: routes, forms, and state handling.

Read-only and stdlib-only. It walks a source tree, skips dependency and build
folders, and prints JSON describing, per UI file:

  - whether it looks like a route/page (file-based routing conventions)
  - form, input, and button counts
  - signals of loading, empty, and error handling
  - toast/notification calls and confirmation dialogs
  - generic copy that often needs review ("Submit", "Something went wrong", ...)

It also prints a summary with the files that render data or forms but show no
loading, empty, or error signal. Those are leads for the reviewer, not
findings: a parent layout or shared component may handle the state.

    python3 -I scripts/ux_inventory.py <repo-root>
    python3 -I scripts/ux_inventory.py <repo-root> --path src/features/checkout
    python3 -I scripts/ux_inventory.py <repo-root> --summary-only

Exit codes:
  0  scan completed
  2  usage error (missing or unreadable directory)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

UI_EXTENSIONS = {
    ".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".astro",
    ".html", ".erb", ".hbs", ".njk", ".liquid", ".php", ".twig",
}
SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", "out", ".next", ".nuxt",
    ".svelte-kit", ".output", "coverage", "vendor", ".turbo", ".cache",
    "__pycache__", ".venv", "venv", "storybook-static",
}
SKIP_FILE_PATTERNS = re.compile(r"\.(test|spec|stories|d)\.[a-z]+$|\.min\.js$")
MAX_FILE_BYTES = 512 * 1024

ROUTE_PATTERNS = [
    re.compile(r"(^|/)app/(.+/)?(page|layout|error|not-found|loading)\.(t|j)sx?$"),
    re.compile(r"(^|/)pages/.+\.(t|j)sx?$|(^|/)pages/.+\.vue$"),
    re.compile(r"(^|/)routes/.+\.(t|j)sx?$|(^|/)routes/.+\+page\.svelte$"),
    re.compile(r"(^|/)src/pages/.+\.astro$"),
    re.compile(r"(^|/)views/.+"),
]

SIGNALS = {
    "forms": re.compile(r"<form\b|useForm\(|<Form\b|handleSubmit", re.I),
    "inputs": re.compile(r"<(input|textarea|select)\b|<(Input|TextField|Select|Textarea|Checkbox)\b"),
    "buttons": re.compile(r"<button\b|<Button\b"),
    "data_fetch": re.compile(
        r"\b(useQuery|useSWR|useFetch|fetch\(|axios\.|useLoaderData|useAsyncData|createResource|load\s*\()"
    ),
    "loading": re.compile(
        r"isLoading|isPending|loading\b|Skeleton|Spinner|<Suspense|isFetching|aria-busy|pending\b", re.I
    ),
    "empty": re.compile(
        r"\.length\s*===?\s*0|length\s*<\s*1|EmptyState|no\s+\w+\s+yet|nothing\s+here|isEmpty|!\w+\.length",
        re.I,
    ),
    "error": re.compile(
        r"isError|\berror\b|ErrorBoundary|onError|catch\s*\(|\.catch\(|notFound\(|errorElement", re.I
    ),
    "toast": re.compile(r"\btoast\b|notify\(|enqueueSnackbar|showNotification|useToast|Snackbar", re.I),
    "confirm": re.compile(r"\bconfirm\(|ConfirmDialog|AlertDialog|useConfirm|are you sure", re.I),
    "disabled_submit": re.compile(r"disabled=\{[^}]*(isSubmitting|isPending|loading|submitting)", re.I),
}

GENERIC_COPY = re.compile(
    r"""(['">])\s*(Submit|OK|Click here|Something went wrong|An error occurred|Invalid input|"""
    r"""Invalid value|No data|Error|Are you sure\??|Success!?)\s*(['"<])""",
    re.I,
)


def is_route(rel: str) -> bool:
    return any(p.search(rel) for p in ROUTE_PATTERNS)


def scan_file(path: Path, rel: str) -> dict | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    counts = {name: len(rx.findall(text)) for name, rx in SIGNALS.items()}
    if not any(counts[k] for k in ("forms", "inputs", "buttons", "data_fetch")) and not is_route(rel):
        return None

    copy_hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in GENERIC_COPY.finditer(line):
            copy_hits.append({"line": lineno, "text": m.group(2)})
        if len(copy_hits) >= 20:
            break

    renders_data = counts["data_fetch"] > 0
    has_form = counts["forms"] > 0 or counts["inputs"] > 0
    leads = []
    if renders_data and not counts["loading"]:
        leads.append("fetches data but shows no loading signal")
    if renders_data and not counts["empty"]:
        leads.append("fetches data but shows no empty-state signal")
    if (renders_data or has_form) and not counts["error"]:
        leads.append("no error-handling signal")
    if counts["forms"] and not counts["disabled_submit"]:
        leads.append("form submit has no visible pending/disabled guard")

    return {
        "file": rel,
        "route": is_route(rel),
        "counts": counts,
        "generic_copy": copy_hits,
        "leads": leads,
    }


def walk(root: Path, sub: Path):
    # Prune skipped and hidden directories before descending: rglob would
    # enter node_modules and nested worktrees (.claude/worktrees, .git),
    # which takes minutes on real apps.
    for dirpath, dirnames, filenames in os.walk(sub):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if not path.is_file() or path.is_symlink():
                continue
            if path.suffix.lower() not in UI_EXTENSIONS or SKIP_FILE_PATTERNS.search(name):
                continue
            yield path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", help="repository root")
    parser.add_argument("--path", help="limit the scan to this subdirectory of root")
    parser.add_argument("--summary-only", action="store_true", help="print only the summary")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    sub = (root / args.path).resolve() if args.path else root
    if not sub.is_dir() or (sub != root and root not in sub.parents):
        print(f"error: --path must be a directory inside {root}", file=sys.stderr)
        return 2

    files = []
    for path in walk(root, sub):
        entry = scan_file(path, path.relative_to(root).as_posix())
        if entry:
            files.append(entry)

    summary = {
        "root": str(root),
        "scanned_path": sub.relative_to(root).as_posix() or ".",
        "ui_files": len(files),
        "routes": [f["file"] for f in files if f["route"]],
        "files_with_forms": [f["file"] for f in files if f["counts"]["forms"]],
        "files_with_leads": [{"file": f["file"], "leads": f["leads"]} for f in files if f["leads"]],
        "generic_copy_hits": sum(len(f["generic_copy"]) for f in files),
        "note": "Leads are heuristics from keywords; verify each in the code or running app before reporting.",
    }
    out = {"summary": summary} if args.summary_only else {"summary": summary, "files": files}
    json.dump(out, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
