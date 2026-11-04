#!/usr/bin/env python3
"""Plan, install, and verify an IndexNow key file for a website.

Stdlib-only and read-only except for `install`, which writes one text file.

    python3 -I indexnow_setup.py keygen
    python3 -I indexnow_setup.py plan --root .
    python3 -I indexnow_setup.py install --root . --key <key>
    python3 -I indexnow_setup.py audit --host https://example.com --key <key>

`keygen` prints a new random key (32 lowercase hex characters, inside the
protocol's 8-128 [a-zA-Z0-9-] range).

`plan` detects the stack, the directory whose contents are served at the site
root, existing key files, and whether a sitemap or robots.txt already exists.

`install` writes `<key>.txt` (containing only the key) into that directory and
prints the URL the file will be served at.

`audit` fetches the live key file and checks it is reachable, not a redirect,
and contains exactly the key. It also reports sitemap.xml and robots.txt.

Exit code is 0 unless a command genuinely failed; `audit` exits 1 when the key
file is missing or does not match.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

KEY_RE = re.compile(r"^[a-zA-Z0-9-]{8,128}$")
KEY_FILE_RE = re.compile(r"^[a-zA-Z0-9-]{8,128}\.txt$")

# Directory whose contents are served at the site root, per stack.
STACK_PUBLIC_DIRS = (
    ("next", ("next.config.js", "next.config.mjs", "next.config.ts")),
    ("astro", ("astro.config.mjs", "astro.config.ts", "astro.config.js")),
    ("nuxt", ("nuxt.config.ts", "nuxt.config.js")),
    ("sveltekit", ("svelte.config.js", "svelte.config.ts")),
    ("gatsby", ("gatsby-config.js", "gatsby-config.ts")),
    ("remix", ("remix.config.js", "remix.config.ts")),
    ("docusaurus", ("docusaurus.config.js", "docusaurus.config.ts")),
    ("vitepress", (".vitepress",)),
    ("hugo", ("hugo.toml", "hugo.yaml", "hugo.json")),
    ("jekyll", ("_config.yml", "_config.yaml")),
    ("eleventy", (".eleventy.js", "eleventy.config.js")),
    ("angular", ("angular.json",)),
    ("django", ("manage.py",)),
    ("rails", ("config/application.rb",)),
    ("laravel", ("artisan",)),
)

# Candidate directories, best first, per stack (relative to repo root).
STACK_KEY_DIRS = {
    "next": ("public", "static"),
    "astro": ("public", "static"),
    "nuxt": ("public", "static"),
    "sveltekit": ("static", "public"),
    "gatsby": ("static", "public"),
    "remix": ("public", "public"),
    "docusaurus": ("static",),
    "vitepress": (".vitepress/dist", "public"),
    "hugo": ("static",),
    "jekyll": (".",),
    "eleventy": ("_site", "."),
    "angular": ("src/assets", "public"),
    "django": ("static",),
    "rails": ("public",),
    "laravel": ("public",),
    "plain": (".", "public", "static"),
}

USER_AGENT = "setup-seo-skill/1.0 (+https://github.com/marc-aurele-besner/skillable)"


def detect_stack(root: Path) -> str:
    for stack, markers in STACK_PUBLIC_DIRS:
        for marker in markers:
            if (root / marker).exists():
                return stack
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        for dep, stack in (
            ("next", "next"),
            ("astro", "astro"),
            ("nuxt", "nuxt"),
            ("@sveltejs/kit", "sveltekit"),
            ("gatsby", "gatsby"),
            ("@remix-run/react", "remix"),
            ("@docusaurus/core", "docusaurus"),
            ("vitepress", "vitepress"),
            ("@angular/core", "angular"),
            ("vite", "plain"),
        ):
            if dep in deps:
                return stack
    return "plain"


def key_dir_for(root: Path, stack: str) -> Path:
    for candidate in STACK_KEY_DIRS.get(stack, STACK_KEY_DIRS["plain"]):
        path = (root / candidate).resolve()
        if path.is_dir():
            return path
    fallback = (root / STACK_KEY_DIRS.get(stack, ("public",))[0]).resolve()
    return fallback


def find_existing_key_files(root: Path) -> list[Path]:
    """Find files that look like an IndexNow key file anywhere in the repo."""
    found: list[Path] = []
    skip = {"node_modules", ".git", ".next", "dist", "build", ".cache", "vendor"}
    for path in root.rglob("*.txt"):
        if any(part in skip for part in path.parts):
            continue
        if not KEY_FILE_RE.match(path.name):
            continue
        try:
            body = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            continue
        if KEY_RE.match(body):
            found.append(path)
    return sorted(found)


def cmd_keygen(_args: argparse.Namespace) -> int:
    print(secrets.token_hex(16))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    stack = detect_stack(root)
    key_dir = key_dir_for(root, stack)
    existing = find_existing_key_files(root)
    plan = {
        "root": str(root),
        "stack": stack,
        "key_file_dir": str(key_dir),
        "key_file_dir_exists": key_dir.is_dir(),
        "existing_key_files": [str(p) for p in existing],
        "sitemap_in_key_dir": (key_dir / "sitemap.xml").is_file(),
        "robots_in_key_dir": (key_dir / "robots.txt").is_file(),
        "static_sitemap": sorted(
            str(p.relative_to(root)) for p in root.rglob("sitemap.xml") if "node_modules" not in p.parts
        ),
        "static_robots": sorted(
            str(p.relative_to(root)) for p in root.rglob("robots.txt") if "node_modules" not in p.parts
        ),
        "env_indexnow_key": bool(os.environ.get("INDEXNOW_KEY")),
    }
    if args.json:
        print(json.dumps(plan, indent=2))
        return 0

    print(f"stack:            {plan['stack']}")
    print(f"site-root dir:    {plan['key_file_dir']}")
    if not plan["key_file_dir_exists"]:
        print("                  (does not exist yet — create it, or pass --out)")
    if existing:
        print("existing key file(s):")
        for path in existing:
            print(f"  - {path}")
    else:
        print("existing key file(s): none")
    print(f"sitemap.xml:      {', '.join(plan['static_sitemap']) or 'none found'}")
    print(f"robots.txt:       {', '.join(plan['static_robots']) or 'none found'}")
    print(f"INDEXNOW_KEY env: {'set' if plan['env_indexnow_key'] else 'not set'}")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    key = (args.key or "").strip()
    if not key:
        key = secrets.token_hex(16)
    if not KEY_RE.match(key):
        print(
            f"invalid key {key!r}: use 8-128 characters from a-z, A-Z, 0-9 and '-'",
            file=sys.stderr,
        )
        return 1

    stack = detect_stack(root)
    out_dir = Path(args.out).resolve() if args.out else key_dir_for(root, stack)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{key}.txt"

    if target.exists() and target.read_text(encoding="utf-8").strip() == key and not args.force:
        print(f"key file already present: {target}")
    else:
        target.write_text(key, encoding="utf-8")
        print(f"wrote {target}")

    host = (args.host or "").rstrip("/")
    print(f"served at:        {host}/{key}.txt" if host else f"served at:        <site-root>/{key}.txt")
    print(f"keyLocation:      {host}/{key}.txt" if host else "keyLocation:      <site-root>/<key>.txt")
    return 0


def http_get(url: str, timeout: float = 15.0) -> tuple[int, str, str, str]:
    """Return (status, content_type, body, final_url)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            return (
                response.status,
                response.headers.get("Content-Type", ""),
                body,
                response.geturl(),
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        return exc.code, exc.headers.get("Content-Type", ""), body, url
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return 0, "", f"{exc}", url


def cmd_audit(args: argparse.Namespace) -> int:
    host = args.host.rstrip("/")
    key = (args.key or "").strip()
    key_url = args.key_location.rstrip("/") if args.key_location else f"{host}/{key}.txt"

    status, content_type, body, final_url = http_get(key_url)
    content = body.strip()
    problems: list[str] = []

    if status == 0:
        problems.append(f"key file unreachable: {body}")
    elif status != 200:
        problems.append(f"key file returned HTTP {status}")
    if final_url.rstrip("/") != key_url.rstrip("/") and status == 200:
        problems.append(f"key file redirects to {final_url} (must be served directly)")
    if content_type and "text/plain" not in content_type.lower():
        problems.append(f"key file content-type is {content_type!r} (want text/plain)")
    if content != key:
        problems.append(f"key file body is {content!r}, expected {key!r}")

    sitemap_status, _, _, _ = http_get(f"{host}/sitemap.xml")
    robots_status, _, robots_body, _ = http_get(f"{host}/robots.txt")
    sitemap_directive = "Sitemap:" in robots_body

    report = {
        "key_url": key_url,
        "key_status": status,
        "key_content_type": content_type,
        "key_matches": content == key,
        "redirected": final_url.rstrip("/") != key_url.rstrip("/"),
        "sitemap_status": sitemap_status,
        "robots_status": robots_status,
        "robots_has_sitemap_directive": sitemap_directive,
        "problems": problems,
    }
    if args.json:
        print(json.dumps(report, indent=2))
        return 1 if problems else 0

    print(f"key file:         {key_url}")
    print(f"  status:         {status}")
    print(f"  content-type:   {content_type or '(none)'}")
    print(f"  body matches:   {'yes' if content == key else 'NO'}")
    print(f"sitemap.xml:      HTTP {sitemap_status}")
    print(f"robots.txt:       HTTP {robots_status} (Sitemap directive: {'yes' if sitemap_directive else 'no'})")
    if problems:
        print("\nproblems:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nOK: key file is reachable and valid.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("keygen", help="print a new random IndexNow key").set_defaults(func=cmd_keygen)

    plan = sub.add_parser("plan", help="detect stack, key-file dir, sitemap and robots")
    plan.add_argument("--root", default=".", help="repo root (default: .)")
    plan.add_argument("--json", action="store_true", help="machine-readable output")
    plan.set_defaults(func=cmd_plan)

    install = sub.add_parser("install", help="write the key file into the site-root directory")
    install.add_argument("--root", default=".", help="repo root (default: .)")
    install.add_argument("--key", help="key to install (default: generate a new one)")
    install.add_argument("--out", help="target directory (default: detected site-root dir)")
    install.add_argument("--host", help="public site root, e.g. https://example.com")
    install.add_argument("--force", action="store_true", help="overwrite an existing key file")
    install.set_defaults(func=cmd_install)

    audit = sub.add_parser("audit", help="check the live key file, sitemap and robots")
    audit.add_argument("--host", required=True, help="public site root, e.g. https://example.com")
    audit.add_argument("--key", required=True, help="the IndexNow key")
    audit.add_argument("--key-location", help="full URL of the key file (default: <host>/<key>.txt)")
    audit.add_argument("--json", action="store_true", help="machine-readable output")
    audit.set_defaults(func=cmd_audit)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
