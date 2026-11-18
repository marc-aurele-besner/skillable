#!/usr/bin/env python3
"""Collect frontend-performance facts from a project so a reviewer starts from evidence.

Stdlib-only and read-only: it never installs, builds, runs, or edits anything,
and it makes no network calls. It reads the project tree and prints:

  - stack: frameworks, bundler, package manager, rendering hints
  - dependencies known to be heavy, with lighter options to consider
  - overlapping dependencies (two date libraries, two chart libraries, ...)
  - built assets already on disk (dist/, build/, .next/, .output/, ...)
    ranked by gzip size, plus total JS/CSS and shipped source maps
  - source-level candidates with file:line (whole-library imports,
    client fetch in effects, unpaired listeners/timers, render-blocking
    fonts and scripts, "use client" on layouts, ...)
  - config files that may set caching headers

Everything it reports is a CANDIDATE. Each one must be verified by reading
the code before it becomes a finding.

Usage:
    python3 -I perf_scan.py [project-dir]
    python3 -I perf_scan.py [project-dir] --json
    python3 -I perf_scan.py [project-dir] --build-dir dist --top 30

Exit codes: 0 success, 1 error (bad path, unreadable package.json).
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    "node_modules", ".git", ".hg", ".svn", "dist", "build", "out", ".next",
    ".nuxt", ".output", ".svelte-kit", ".astro", ".vercel", ".netlify",
    "coverage", ".turbo", ".cache", ".parcel-cache", "storybook-static",
    "vendor", "__pycache__", ".venv", "venv", "target",
}
SOURCE_EXT = {
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte",
    ".astro", ".html", ".css", ".scss", ".sass", ".less",
}
MAX_FILE_BYTES = 1_000_000
MAX_SOURCE_FILES = 8000
MAX_HITS_PER_RULE = 40

FRAMEWORKS = [
    ("next", "Next.js"), ("nuxt", "Nuxt"), ("@sveltejs/kit", "SvelteKit"),
    ("astro", "Astro"), ("@remix-run/react", "Remix"), ("react-router", "React Router"),
    ("@tanstack/react-start", "TanStack Start"), ("gatsby", "Gatsby"),
    ("@angular/core", "Angular"), ("solid-js", "Solid"), ("@builder.io/qwik", "Qwik"),
    ("preact", "Preact"), ("vue", "Vue"), ("svelte", "Svelte"), ("react", "React"),
]
BUNDLERS = [
    ("vite", "Vite"), ("rolldown-vite", "Vite (Rolldown)"), ("webpack", "webpack"),
    ("@rspack/core", "Rspack"), ("rollup", "Rollup"), ("esbuild", "esbuild"),
    ("parcel", "Parcel"), ("@angular-devkit/build-angular", "Angular CLI"),
    ("@angular/build", "Angular CLI (esbuild)"),
]
LOCKFILES = [
    ("pnpm-lock.yaml", "pnpm"), ("bun.lock", "bun"), ("bun.lockb", "bun"),
    ("yarn.lock", "yarn"), ("package-lock.json", "npm"), ("deno.lock", "deno"),
]
HEAVY_DEPS = {
    "moment": "large and not tree-shakeable; date-fns, dayjs, or Temporal/Intl",
    "moment-timezone": "ships timezone data; Intl.DateTimeFormat with timeZone",
    "lodash": "CommonJS build defeats tree-shaking; lodash-es, per-method imports, or native",
    "underscore": "mostly native today",
    "jquery": "rarely needed alongside a component framework",
    "aws-sdk": "v2 is monolithic; @aws-sdk/client-* v3 modular clients",
    "firebase": "use the modular v9+ API, never firebase/compat",
    "core-js": "check the polyfill target; modern browserslist needs far less",
    "@babel/polyfill": "deprecated whole-world polyfill",
    "xlsx": "large; load it lazily on the export action",
    "pdfjs-dist": "large; lazy-load the viewer route",
    "monaco-editor": "very large; lazy-load, or CodeMirror 6",
    "three": "large; lazy-load the 3D view",
    "chart.js": "register only the controllers used; lazy-load charts below the fold",
    "echarts": "import from echarts/core and register parts",
    "highlight.js": "import highlight.js/lib/core plus the needed languages",
    "@fortawesome/fontawesome-free": "whole icon font; per-icon SVG imports",
    "antd": "large; check per-component imports and that the CSS is not global-all",
    "@mui/icons-material": "fine in prod with ESM named imports, slow in dev; avoid `import * as`",
    "rxjs": "fine when tree-shaken; check for `import * as Rx`",
    "d3": "import the d3-* submodules actually used",
    "mathjs": "large; mathjs/number or a factory build",
    "@tensorflow/tfjs": "very large; lazy-load on demand",
}
OVERLAP_GROUPS = {
    "dates": ["moment", "dayjs", "date-fns", "luxon", "@js-joda/core"],
    "utility belts": ["lodash", "lodash-es", "underscore", "ramda", "remeda", "es-toolkit"],
    "HTTP clients": ["axios", "ky", "superagent", "got", "node-fetch", "ofetch"],
    "charts": ["chart.js", "recharts", "echarts", "highcharts", "apexcharts", "victory", "nivo", "@nivo/core", "plotly.js"],
    "icons": ["react-icons", "@fortawesome/fontawesome-svg-core", "@mui/icons-material", "lucide-react", "@heroicons/react", "@tabler/icons-react", "@phosphor-icons/react"],
    "CSS-in-JS": ["styled-components", "@emotion/react", "@stitches/react", "goober", "jss"],
    "UI kits": ["@mui/material", "antd", "@chakra-ui/react", "@mantine/core", "react-bootstrap", "semantic-ui-react"],
    "animation": ["framer-motion", "motion", "gsap", "react-spring", "@react-spring/web", "animejs"],
    "state": ["redux", "@reduxjs/toolkit", "mobx", "zustand", "jotai", "recoil", "valtio", "xstate"],
    "data fetching": ["@tanstack/react-query", "swr", "@apollo/client", "urql", "react-query"],
}
BUILD_DIRS = [
    ".next/static", ".output/public", ".svelte-kit/output/client", "dist",
    "build", "out", "public/build", "storybook-static", "www",
]
HEADER_CONFIGS = [
    "vercel.json", "netlify.toml", "_headers", "public/_headers", "static/_headers",
    "firebase.json", "wrangler.toml", "wrangler.jsonc", "nginx.conf", "Caddyfile",
    "staticwebapp.config.json", "next.config.js", "next.config.mjs", "next.config.ts",
    "nuxt.config.ts", "nuxt.config.js", "astro.config.mjs", "astro.config.ts",
    "svelte.config.js", "vite.config.ts", "vite.config.js", "vite.config.mts",
    "webpack.config.js", "angular.json", ".browserslistrc",
]

# (rule id, regex, applies-to extensions or None for all, note)
LINE_RULES = [
    ("whole-lodash", re.compile(r"""(?:import\s+(?:_|\*\s+as\s+\w+|\w+)\s+from\s+|require\()\s*['"]lodash['"]"""), None,
     "whole lodash import; use lodash-es or per-method imports"),
    ("moment-import", re.compile(r"""from\s+['"]moment['"]|require\(\s*['"]moment['"]"""), None,
     "moment is large and pulls locales"),
    ("namespace-import-heavy", re.compile(r"""import\s+\*\s+as\s+\w+\s+from\s+['"](?:@mui/icons-material|react-icons(?:/\w+)?|lucide-react|date-fns|rxjs|d3|antd|@heroicons/react[^'"]*)['"]"""), None,
     "namespace import of a large package may defeat tree-shaking"),
    ("use-client-layout", re.compile(r"""^\s*['"]use client['"]"""), None,
     "'use client' at the top of a layout/page/template moves the whole subtree to the client bundle"),
    ("effect-fetch", re.compile(r"""\buseEffect\s*\(|\bonMounted\s*\(|\$effect\s*\(|\bonMount\s*\("""), None,
     "effect/mount hook; check for fetch inside it (client waterfall, no SSR data)"),
    ("google-fonts-css", re.compile(r"""<link\b[^>]*fonts\.googleapis\.com/css|@import\s+(?:url\(\s*)?['"]?https?://"""), None,
     "remote font/CSS @import or Google Fonts link is render-blocking and costs extra connections"),
    ("sync-third-party-script", re.compile(r"""<script\b(?![^>]*\b(?:async|defer|type\s*=\s*['"]module['"])\b)[^>]*\bsrc\s*=\s*['"]https?://"""), None,
     "third-party script without async/defer blocks parsing"),
    ("font-display-block", re.compile(r"""font-display\s*:\s*(?:block|auto)"""), None,
     "font-display block/auto hides text while the font loads"),
    ("lazy-img", re.compile(r"""<img\b[^>]*\bloading\s*=\s*['"]lazy['"]"""), None,
     "lazy image; confirm it is not the LCP/above-the-fold image"),
    ("json-clone", re.compile(r"""JSON\.parse\(\s*JSON\.stringify\("""), None,
     "deep clone via JSON; costly in hot paths (structuredClone or avoid the copy)"),
    ("sync-storage-in-render", re.compile(r"""\b(?:localStorage|sessionStorage)\.(?:getItem|setItem)\b"""), None,
     "synchronous storage access; costly in render/scroll/input handlers"),
    ("layout-thrash", re.compile(r"""\.(?:offsetHeight|offsetWidth|offsetTop|getBoundingClientRect\(\)|scrollHeight|clientHeight)\b"""), None,
     "layout read; check it is not interleaved with style writes in a loop or scroll handler"),
]
LAYOUT_FILE_RE = re.compile(r"(?:^|/)(?:app|src/app)/(?:.*/)?(?:layout|page|template)\.(?:t|j)sx?$")
PAIRS = [
    ("addEventListener", "removeEventListener", "listener added but never removed in this file"),
    ("setInterval", "clearInterval", "interval set but never cleared in this file"),
    ("new ResizeObserver", "disconnect", "observer created but never disconnected in this file"),
    ("new IntersectionObserver", "disconnect", "observer created but never disconnected in this file"),
    ("new MutationObserver", "disconnect", "observer created but never disconnected in this file"),
    (".subscribe(", "unsubscribe", "subscription without an unsubscribe in this file"),
]


def read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def load_package_json(root: Path) -> dict:
    pkg = root / "package.json"
    if not pkg.is_file():
        return {}
    try:
        return json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: cannot read {pkg}: {exc}")


def detect_stack(root: Path, pkg: dict) -> dict:
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    frameworks = [f"{label} {deps[name]}" for name, label in FRAMEWORKS if name in deps]
    bundlers = [f"{label} {deps[name]}" for name, label in BUNDLERS if name in deps]
    managers = [label for name, label in LOCKFILES if (root / name).exists()]
    hints = []
    if (root / "app").is_dir() or (root / "src/app").is_dir():
        hints.append("app/ directory present (Next.js App Router or similar)")
    if (root / "pages").is_dir() or (root / "src/pages").is_dir():
        hints.append("pages/ directory present (Next.js Pages Router, Nuxt, Astro, ...)")
    if "react-compiler" in json.dumps(pkg) or "babel-plugin-react-compiler" in deps:
        hints.append("React Compiler present: manual memoization findings are mostly moot")
    if pkg.get("sideEffects") is not None:
        hints.append(f"package.json sideEffects = {pkg.get('sideEffects')!r}")
    if pkg.get("browserslist"):
        hints.append(f"browserslist = {pkg.get('browserslist')!r}")
    return {
        "frameworks": frameworks,
        "bundlers": bundlers or ["(none declared; framework default)"],
        "package_managers": managers,
        "scripts": {k: v for k, v in pkg.get("scripts", {}).items() if k in {"build", "analyze", "dev", "start", "preview"}},
        "hints": hints,
        "runtime_dependency_count": len(pkg.get("dependencies", {})),
    }


def dependency_findings(pkg: dict) -> tuple[list[dict], list[dict]]:
    runtime = pkg.get("dependencies", {})
    alldeps = {**runtime, **pkg.get("devDependencies", {})}
    heavy = [
        {"package": name, "version": alldeps[name], "runtime": name in runtime, "note": note}
        for name, note in HEAVY_DEPS.items() if name in alldeps
    ]
    overlaps = []
    for group, names in OVERLAP_GROUPS.items():
        present = [n for n in names if n in runtime]
        if len(present) > 1:
            overlaps.append({"group": group, "packages": present})
    return heavy, overlaps


def iter_source_files(root: Path):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            path = Path(dirpath) / fn
            if path.suffix in SOURCE_EXT and not fn.endswith((".min.js", ".d.ts")):
                count += 1
                if count > MAX_SOURCE_FILES:
                    return
                yield path


def scan_sources(root: Path) -> dict:
    hits: dict[str, list[dict]] = {}
    files_scanned = 0
    dynamic_imports = 0

    def add(rule: str, rel: str, line: int, note: str, text: str = "") -> None:
        bucket = hits.setdefault(rule, [])
        if len(bucket) < MAX_HITS_PER_RULE:
            bucket.append({"file": rel, "line": line, "note": note, "text": text.strip()[:160]})

    for path in iter_source_files(root):
        text = read_text(path)
        if text is None:
            continue
        files_scanned += 1
        rel = path.relative_to(root).as_posix()
        lines = text.splitlines()
        dynamic_imports += len(re.findall(r"\bimport\(\s*['\"`]", text))
        for idx, line in enumerate(lines, start=1):
            for rule, regex, _exts, note in LINE_RULES:
                if not regex.search(line):
                    continue
                if rule == "use-client-layout" and not (idx <= 3 and LAYOUT_FILE_RE.search(rel)):
                    continue
                if rule == "layout-thrash":
                    # Only a read near a style write is a thrash candidate.
                    near = "\n".join(lines[max(0, idx - 6): idx + 5])
                    if not re.search(r"\.style\.\w+\s*=|\.style\.setProperty\(|classList\.(?:add|remove|toggle)\(", near):
                        continue
                if rule == "sync-storage-in-render":
                    # Only flag storage calls near hot handlers or render loops.
                    near = "\n".join(lines[max(0, idx - 9): idx + 8])
                    if not re.search(r"['\"](?:scroll|resize|input|mousemove|pointermove|keydown|keyup|wheel|touchmove)['\"]|\bon(?:Scroll|Input|Change|KeyDown|MouseMove|PointerMove)\b|requestAnimationFrame", near):
                        continue
                if rule == "effect-fetch":
                    window = "\n".join(lines[idx - 1: idx + 12])
                    if not re.search(r"\bfetch\(|axios\.|\$fetch\(|\.get\(\s*['\"`/]", window):
                        continue
                add(rule, rel, idx, note, line)
        for opener, closer, note in PAIRS:
            if opener in text and closer not in text:
                openers = [i for i, l in enumerate(lines, 1) if opener in l]
                if opener == ".subscribe(":
                    # `const stop = store.subscribe(...)` / `return x.subscribe(...)` keeps the
                    # unsubscribe function (Zustand, Svelte, Redux style); not a leak lead.
                    openers = [i for i in openers if not re.search(r"(?:=|\breturn)\s*[\w.$]*\.subscribe\(", lines[i - 1])]
                    if not openers:
                        continue
                first = openers[0] if openers else 1
                add("unpaired-" + opener.strip(".( ").replace("new ", "").lower(), rel, first, note, lines[first - 1])
    return {"files_scanned": files_scanned, "dynamic_imports": dynamic_imports, "candidates": hits}


def gzip_size(path: Path) -> int:
    try:
        return len(gzip.compress(path.read_bytes(), compresslevel=9))
    except OSError:
        return 0


def scan_build(root: Path, build_dir: str | None, top: int) -> dict:
    candidates = [build_dir] if build_dir else BUILD_DIRS
    found = [root / d for d in candidates if (root / d).is_dir()]
    if not found:
        return {"build_dirs": [], "note": "no build output on disk; run the project's own build to measure"}
    assets, maps = [], []
    for base in found:
        for dirpath, _dirs, filenames in os.walk(base):
            for fn in filenames:
                p = Path(dirpath) / fn
                if fn.endswith(".map"):
                    maps.append(p.relative_to(root).as_posix())
                elif p.suffix in {".js", ".mjs", ".css"}:
                    try:
                        raw = p.stat().st_size
                    except OSError:
                        continue
                    assets.append({"file": p.relative_to(root).as_posix(), "ext": p.suffix, "raw": raw})
    assets.sort(key=lambda a: a["raw"], reverse=True)
    for a in assets[: max(top, 1) * 3]:
        a["gzip"] = gzip_size(root / a["file"])
    ranked = sorted((a for a in assets if "gzip" in a), key=lambda a: a["gzip"], reverse=True)[:top]
    total_js = sum(a["raw"] for a in assets if a["ext"] in {".js", ".mjs"})
    total_css = sum(a["raw"] for a in assets if a["ext"] == ".css")
    return {
        "build_dirs": [d.relative_to(root).as_posix() for d in found],
        "asset_count": len(assets),
        "total_js_raw": total_js,
        "total_css_raw": total_css,
        "top_assets": ranked,
        "source_maps_on_disk": len(maps),
        "note": "totals are every chunk on disk, not what one route loads; use the analyzer for per-route cost",
    }


def kb(n: int) -> str:
    return f"{n / 1024:.1f} KB"


def print_report(data: dict) -> None:
    s = data["stack"]
    print("# Frontend performance scan (candidates, verify each one)\n")
    print(f"Frameworks: {', '.join(s['frameworks']) or '(none detected)'}")
    print(f"Bundler: {', '.join(s['bundlers'])}")
    print(f"Package manager: {', '.join(s['package_managers']) or '(no lockfile)'}")
    for k, v in s["scripts"].items():
        print(f"script {k}: {v}")
    for h in s["hints"]:
        print(f"hint: {h}")
    print(f"runtime dependencies: {s['runtime_dependency_count']}\n")

    if data["heavy_dependencies"]:
        print("## Heavy dependencies")
        for d in data["heavy_dependencies"]:
            where = "runtime" if d["runtime"] else "dev"
            print(f"- {d['package']} {d['version']} ({where}): {d['note']}")
        print()
    if data["overlapping_dependencies"]:
        print("## Overlapping runtime dependencies")
        for o in data["overlapping_dependencies"]:
            print(f"- {o['group']}: {', '.join(o['packages'])}")
        print()

    b = data["build"]
    print("## Build output on disk")
    if not b["build_dirs"]:
        print(f"- {b['note']}\n")
    else:
        print(f"- dirs: {', '.join(b['build_dirs'])}; {b['asset_count']} JS/CSS files; "
              f"JS {kb(b['total_js_raw'])} raw, CSS {kb(b['total_css_raw'])} raw; "
              f"{b['source_maps_on_disk']} source maps")
        for a in b["top_assets"]:
            print(f"- {a['file']}: {kb(a['raw'])} raw, {kb(a['gzip'])} gzip")
        print(f"- note: {b['note']}\n")

    src = data["source"]
    print(f"## Source candidates ({src['files_scanned']} files scanned, {src['dynamic_imports']} dynamic imports)")
    if not src["candidates"]:
        print("- none")
    for rule, items in sorted(src["candidates"].items()):
        print(f"\n### {rule} ({len(items)}{'+' if len(items) >= MAX_HITS_PER_RULE else ''})")
        print(f"_{items[0]['note']}_")
        for it in items:
            print(f"- {it['file']}:{it['line']}  {it['text']}")
    print()
    print("## Config that may set caching headers or build targets")
    for c in data["header_configs"] or ["(none found)"]:
        print(f"- {c}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("path", nargs="?", default=".", help="project directory (default: .)")
    ap.add_argument("--build-dir", help="build output directory to measure, relative to the project")
    ap.add_argument("--top", type=int, default=20, help="number of largest assets to list (default 20)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 1
    if args.build_dir and (".." in Path(args.build_dir).parts or Path(args.build_dir).is_absolute()):
        print("error: --build-dir must be a relative path inside the project", file=sys.stderr)
        return 1

    pkg = load_package_json(root)
    heavy, overlaps = dependency_findings(pkg)
    data = {
        "root": str(root),
        "stack": detect_stack(root, pkg),
        "heavy_dependencies": heavy,
        "overlapping_dependencies": overlaps,
        "build": scan_build(root, args.build_dir, args.top),
        "source": scan_sources(root),
        "header_configs": [c for c in HEADER_CONFIGS if (root / c).exists()],
    }
    if args.json:
        json.dump(data, sys.stdout, indent=2)
        print()
    else:
        print_report(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
