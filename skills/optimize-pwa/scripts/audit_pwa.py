#!/usr/bin/env python3
"""Audit a built web app for PWA installability and mobile-friendliness.

Read-only and stdlib-only. Point it at the build output folder (dist/, out/,
build/, public/, .output/public/, _site/, or a folder of pages saved with curl
plus the manifest, icons, and service worker):

    python3 -I audit_pwa.py dist
    python3 -I audit_pwa.py dist --json
    python3 -I audit_pwa.py dist --base-path /app/    # app served under a subpath

Per page: viewport (present, device-width, zoom not disabled, viewport-fit),
theme-color, manifest link, apple-touch-icon, html lang, form inputs without a
mobile keyboard hint or autocomplete, small Tailwind text on inputs, images
without dimensions.
App level: manifest JSON and fields, icon files and real PNG sizes, maskable
icon, screenshots, service worker registration and file, fetch handler,
offline fallback; CSS that misbehaves on phones (100vh without dvh/svh,
viewport-fit=cover without safe-area insets, input fonts under 16px).

Exit code is 0 even when issues are found; it reports, it does not judge.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

SKIP_DIRS = {"node_modules", ".git"}
MAX_TEXT_BYTES = 5_000_000
APP_DISPLAYS = {"standalone", "fullscreen", "minimal-ui", "window-controls-overlay"}
SW_NAMES = ("sw.js", "service-worker.js", "serviceworker.js", "ngsw-worker.js", "firebase-messaging-sw.js")

FIELD_HINTS = {
    "email": ("email", "email"),
    "e-mail": ("email", "email"),
    "phone": ("tel", "tel"),
    "mobile": ("tel", "tel"),
    "tel": ("tel", "tel"),
    "otp": ("numeric", "one-time-code"),
    "verification": ("numeric", "one-time-code"),
    "zip": ("text", "postal-code"),
    "postal": ("text", "postal-code"),
    "postcode": ("text", "postal-code"),
    "password": ("password", "current-password"),
    "firstname": ("text", "given-name"),
    "first_name": ("text", "given-name"),
    "lastname": ("text", "family-name"),
    "last_name": ("text", "family-name"),
    "fullname": ("text", "name"),
    "address": ("text", "street-address"),
    "city": ("text", "address-level2"),
    "country": ("text", "country-name"),
    "cardnumber": ("numeric", "cc-number"),
    "card_number": ("numeric", "cc-number"),
    "url": ("url", "url"),
    "website": ("url", "url"),
    "amount": ("decimal", "off"),
    "price": ("decimal", "off"),
    "quantity": ("numeric", "off"),
}
KEYBOARD_TYPES = {"email", "tel", "url", "number", "search", "password", "date", "time",
                  "datetime-local", "month", "week", "color", "file", "range", "checkbox",
                  "radio", "hidden", "submit", "button", "reset", "image"}


def read_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def png_size(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as f:
            head = f.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang: str | None = None
        self.meta: dict[str, str] = {}
        self.links: dict[str, list[str]] = defaultdict(list)
        self.inputs: list[dict[str, str]] = []
        self.imgs_no_dims = 0
        self.inline_scripts: list[str] = []
        self.styles: list[str] = []
        self.classes: list[str] = []
        self._buf: list[str] | None = None
        self._buf_kind = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if a.get("class"):
            self.classes.append(a["class"])
        if a.get("style"):
            self.styles.append(a["style"])
        if tag == "html":
            self.lang = a.get("lang") or None
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key:
                self.meta.setdefault(key, a.get("content", ""))
        elif tag == "link":
            for rel in a.get("rel", "").lower().split():
                self.links[rel].append(a.get("href", ""))
        elif tag in ("input", "textarea"):
            if tag == "textarea":
                a.setdefault("type", "textarea")
            self.inputs.append(a)
        elif tag == "img":
            style = a.get("style", "")
            if not (a.get("width") and a.get("height")) and "aspect-ratio" not in style:
                self.imgs_no_dims += 1
        elif tag == "script" and not a.get("src"):
            self._buf, self._buf_kind = [], "script"
        elif tag == "style":
            self._buf, self._buf_kind = [], "style"

    def handle_endtag(self, tag: str) -> None:
        if self._buf is not None and tag in ("script", "style"):
            text = "".join(self._buf)
            (self.inline_scripts if self._buf_kind == "script" else self.styles).append(text)
            self._buf = None

    def handle_data(self, data: str) -> None:
        if self._buf is not None:
            self._buf.append(data)


def parse_viewport(content: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in re.split(r"[,;]", content):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().lower()] = v.strip().lower()
    return out


def input_issues(inp: dict[str, str]) -> list[str]:
    itype = (inp.get("type") or "text").lower()
    if itype in {"hidden", "submit", "button", "reset", "image", "checkbox", "radio", "range", "file", "color"}:
        return []
    ident = " ".join(inp.get(k, "") for k in ("name", "id", "placeholder", "aria-label")).lower()
    ident_compact = re.sub(r"[\s-]", "", ident)
    hint = next((v for k, v in FIELD_HINTS.items() if k in ident or k in ident_compact), None)
    if not hint:
        return []
    out = []
    want_kbd, want_ac = hint
    has_kbd = itype in KEYBOARD_TYPES or inp.get("inputmode")
    if want_kbd != "text" and not has_kbd:
        out.append(f"input-no-keyboard-hint ({inp.get('name') or inp.get('id') or 'unnamed'} → {want_kbd})")
    if want_ac != "off" and not inp.get("autocomplete"):
        out.append(f"input-no-autocomplete ({inp.get('name') or inp.get('id') or 'unnamed'} → {want_ac})")
    return out


def resolve(root: Path, ref: str, from_url: str, base_path: str) -> Path | None:
    """Map a URL reference (as written in HTML/manifest) to a file under root."""
    if not ref or ref.startswith(("data:", "blob:")):
        return None
    parsed = urlparse(ref)
    if parsed.scheme in ("http", "https") or ref.startswith("//"):
        path = parsed.path
    elif ref.startswith("/"):
        path = parsed.path
    else:
        path = str(PurePosixPath(from_url).parent / parsed.path)
    path = re.sub(r"/+", "/", path)
    candidates = [path]
    if base_path and path.startswith(base_path):
        candidates.append("/" + path[len(base_path):])
    for c in candidates:
        parts = [p for p in PurePosixPath(c).parts if p not in ("/", ".")]
        while ".." in parts:
            i = parts.index("..")
            parts = parts[: max(i - 1, 0)] + parts[i + 1:]
        target = root.joinpath(*parts) if parts else root / "index.html"
        if target.is_file():
            return target
    return None


def page_url(root: Path, path: Path) -> str:
    return "/" + path.relative_to(root).as_posix()


def audit_page(root: Path, path: Path) -> tuple[dict, PageParser]:
    parser = PageParser()
    parser.feed(read_text(path))
    issues: list[str] = []
    vp = parser.meta.get("viewport")
    if vp is None:
        issues.append("no-viewport")
    else:
        v = parse_viewport(vp)
        if v.get("width") != "device-width":
            issues.append(f"viewport-not-device-width ({v.get('width', 'missing')})")
        max_scale = v.get("maximum-scale")
        try:
            low_max = max_scale is not None and float(max_scale) < 2
        except ValueError:
            low_max = False
        if v.get("user-scalable") in ("no", "0") or low_max:
            issues.append("zoom-disabled")
    if not parser.lang:
        issues.append("no-lang")
    if "theme-color" not in parser.meta:
        issues.append("no-theme-color")
    if not parser.links.get("manifest"):
        issues.append("no-manifest-link")
    if not parser.links.get("apple-touch-icon"):
        issues.append("no-apple-touch-icon")
    for inp in parser.inputs:
        issues.extend(input_issues(inp))
        cls = f" {inp.get('class', '')} "
        if re.search(r"\s(text-xs|text-sm)\s", cls) and not re.search(r"\s(text-base|text-\[16px\]|text-\[1rem\])\s", cls):
            issues.append(f"input-font-small (tailwind on {inp.get('name') or inp.get('id') or inp.get('type')})")
    if parser.imgs_no_dims:
        issues.append(f"img-no-dimensions ({parser.imgs_no_dims})")
    return {
        "file": path.relative_to(root).as_posix(),
        "viewport": vp,
        "issues": issues,
    }, parser


CSS_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
INPUT_SEL_RE = re.compile(r"(^|[\s,>+~(])(input|select|textarea)\b(?!\[type=[\"']?(checkbox|radio|range)\b)", re.I)
FONT_SIZE_RE = re.compile(r"font-size\s*:\s*([\d.]+)(px|rem|em|pt)", re.I)


def css_checks(css: str) -> dict:
    small_inputs: list[str] = []
    for sel, body in CSS_RULE_RE.findall(css):
        sel = sel.strip()
        if "::placeholder" in sel or not INPUT_SEL_RE.search(sel):
            continue
        m = FONT_SIZE_RE.search(body)
        if not m:
            continue
        size, unit = float(m.group(1)), m.group(2).lower()
        px = size * {"px": 1, "rem": 16, "em": 16, "pt": 4 / 3}[unit]
        if px < 16:
            small_inputs.append(f"{sel[:60]} {{font-size:{m.group(1)}{unit}}}")
    return {
        "vh100": len(re.findall(r"\b100vh\b", css)),
        "dvh": bool(re.search(r"\d(dvh|svh|lvh)\b", css)),
        "safe_area": "safe-area-inset" in css,
        "small_inputs": small_inputs,
    }


def audit_manifest(root: Path, mpath: Path, base_path: str) -> tuple[dict, list[str]]:
    issues: list[str] = []
    try:
        data = json.loads(read_text(mpath))
    except json.JSONDecodeError as e:
        return {"file": mpath.relative_to(root).as_posix(), "error": str(e)}, [f"manifest-invalid-json ({e.msg})"]
    if not isinstance(data, dict):
        return {"file": mpath.relative_to(root).as_posix()}, ["manifest-invalid-json (not an object)"]
    murl = page_url(root, mpath)
    for field in ("name", "short_name", "start_url", "display", "icons", "theme_color", "background_color", "id", "scope"):
        if not data.get(field):
            issues.append(f"manifest-missing-{field.replace('_', '-')}")
    if len(str(data.get("short_name", ""))) > 12:
        issues.append(f"short-name-long ({data['short_name']!r})")
    display = data.get("display")
    overrides = data.get("display_override") or []
    if display and display not in APP_DISPLAYS and not any(d in APP_DISPLAYS for d in overrides):
        issues.append(f"display-not-app ({display})")
    if data.get("prefer_related_applications") is True:
        issues.append("prefer-related-applications (blocks install prompt)")
    if not data.get("description"):
        issues.append("manifest-missing-description")
    shots = data.get("screenshots") or []
    if not shots:
        issues.append("no-screenshots")
    else:
        factors = {s.get("form_factor") for s in shots if isinstance(s, dict)}
        if "narrow" not in factors:
            issues.append("no-narrow-screenshot")

    icons_report = []
    any_sizes: set[int] = set()
    has_maskable = False
    for icon in data.get("icons") or []:
        if not isinstance(icon, dict):
            continue
        src = icon.get("src", "")
        purpose = set(str(icon.get("purpose", "any")).split())
        declared = str(icon.get("sizes", ""))
        file = resolve(root, src, murl, base_path)
        entry = {"src": src, "sizes": declared, "purpose": " ".join(sorted(purpose))}
        if purpose >= {"any", "maskable"}:
            issues.append(f"icon-any-maskable ({src})")
        if "maskable" in purpose:
            has_maskable = True
        if file is None:
            if not src.startswith(("http://", "https://", "//")):
                issues.append(f"icon-missing-file ({src})")
            icons_report.append(entry)
            continue
        real = png_size(file)
        entry["real"] = f"{real[0]}x{real[1]}" if real else file.suffix.lstrip(".")
        if real:
            if real[0] != real[1]:
                issues.append(f"icon-not-square ({src} {entry['real']})")
            dec = [d.lower() for d in declared.split()]
            if dec and "any" not in dec and f"{real[0]}x{real[1]}" not in dec:
                issues.append(f"icon-size-mismatch ({src} declared {declared}, real {entry['real']})")
            if "any" in purpose:
                any_sizes.add(real[0])
        icons_report.append(entry)
    if data.get("icons"):
        if not any(s >= 192 for s in any_sizes):
            issues.append("no-icon-192 (PNG, purpose any)")
        if not any(s >= 512 for s in any_sizes):
            issues.append("no-icon-512 (PNG, purpose any)")
        if not has_maskable:
            issues.append("no-maskable-icon")
    summary = {k: data.get(k) for k in ("name", "short_name", "id", "start_url", "scope", "display",
                                        "theme_color", "background_color", "orientation")}
    summary["file"] = mpath.relative_to(root).as_posix()
    summary["icons"] = icons_report
    summary["screenshots"] = len(shots)
    summary["shortcuts"] = len(data.get("shortcuts") or [])
    return summary, issues


def audit(root: Path, base_path: str) -> dict:
    files = [p for p in root.rglob("*") if p.is_file()
             and not any(part in SKIP_DIRS for part in p.relative_to(root).parts)]
    html = sorted(p for p in files if p.suffix.lower() in (".html", ".htm"))
    css_files = [p for p in files if p.suffix.lower() == ".css"]
    js_files = [p for p in files if p.suffix.lower() in (".js", ".mjs")]

    pages, parsers = [], []
    for p in html:
        rep, parser = audit_page(root, p)
        pages.append(rep)
        parsers.append((p, parser))

    app: list[str] = []

    # CSS: external files, inline <style>, style attributes, and Tailwind classes.
    all_css = "\n".join(read_text(p) for p in css_files)
    all_css += "\n".join(s for _, pr in parsers for s in pr.styles)
    css = css_checks(all_css)
    classes = " ".join(c for _, pr in parsers for c in pr.classes)
    tw_screen = len(re.findall(r"(?<![\w-])(min-h-screen|h-screen|max-h-screen)(?![\w-])", classes))
    tw_dvh = bool(re.search(r"(?<![\w-])(min-|max-)?h-(dvh|svh|lvh)(?![\w-])", classes))
    js_text = "\n".join(read_text(p) for p in js_files)
    inline_js = "\n".join(s for _, pr in parsers for s in pr.inline_scripts)
    any_text = all_css + classes + js_text

    if (css["vh100"] or tw_screen) and not (css["dvh"] or tw_dvh or re.search(r"\d(dvh|svh)\b", js_text)):
        app.append(f"vh-without-dvh ({css['vh100']} × 100vh in CSS, {tw_screen} × h-screen classes)")
    cover = any("viewport-fit=cover" in (pr.meta.get("viewport") or "").replace(" ", "") for _, pr in parsers)
    if cover and "safe-area-inset" not in any_text and "safe-area" not in classes:
        app.append("safe-area-unhandled (viewport-fit=cover but no env(safe-area-inset-*))")
    for rule in css["small_inputs"][:5]:
        app.append(f"input-font-small ({rule})")
    if len(css["small_inputs"]) > 5:
        app.append(f"input-font-small (+{len(css['small_inputs']) - 5} more rules)")

    # Manifest: from links, else any manifest-looking file.
    manifest_path = None
    for p, pr in parsers:
        for href in pr.links.get("manifest", []):
            found = resolve(root, href, page_url(root, p), base_path)
            if found:
                manifest_path = found
                break
            if not href.startswith(("http://", "https://", "//")):
                app.append(f"manifest-missing-file ({href} linked from {p.relative_to(root).as_posix()})")
        if manifest_path:
            break
    if manifest_path is None:
        manifest_path = next((p for p in files if p.name.endswith(".webmanifest")
                              or p.name in ("manifest.json", "site.webmanifest")), None)
    manifest = None
    if manifest_path:
        manifest, missues = audit_manifest(root, manifest_path, base_path)
        app.extend(missues)
    else:
        app.append("no-manifest")

    # Service worker.
    sw_refs = set(re.findall(r"serviceWorker\s*\.\s*register\(\s*[\"'`]([^\"'`]+)[\"'`]", js_text + "\n" + inline_js))
    sw_files = {p for p in files if p.name in SW_NAMES or re.fullmatch(r"(sw|service-worker)[.-][\w-]+\.js", p.name)}
    registered = []
    for ref in sorted(sw_refs):
        found = resolve(root, ref, "/index.html", base_path)
        if found:
            sw_files.add(found)
            registered.append(ref)
        else:
            app.append(f"sw-missing-file ({ref})")
    uses_register = "serviceWorker" in (js_text + inline_js) and ".register(" in (js_text + inline_js)
    angular_sw = (root / "ngsw-worker.js").is_file()
    sw_report = []
    offline = any(re.search(r"offline", p.stem, re.I) for p in html) or (root / "~offline").exists()
    for sw in sorted(sw_files):
        text = read_text(sw)
        has_fetch = bool(re.search(r"""addEventListener\(\s*["']fetch["']|onfetch\s*=""", text)) \
            or any(k in text for k in ("workbox", "registerRoute", "serwist", "Serwist", "ngsw"))
        if not has_fetch:
            app.append(f"sw-no-fetch-handler ({sw.relative_to(root).as_posix()})")
        if re.search(r"offline|navigateFallback|createHandlerBoundToURL|NavigationRoute|fallbacks", text):
            offline = True
        sw_report.append({"file": sw.relative_to(root).as_posix(), "fetch_handler": has_fetch, "bytes": len(text)})
    if not sw_files:
        app.append("no-service-worker")
    elif not (sw_refs or uses_register or angular_sw):
        app.append("sw-not-registered (file exists but no navigator.serviceWorker.register found)")
    if sw_files and not offline:
        app.append("no-offline-fallback")

    counts: dict[str, int] = defaultdict(int)
    for p in pages:
        for code in {issue.split(" ", 1)[0] for issue in p["issues"]}:
            counts[code] += 1

    return {
        "root": str(root),
        "pages": len(pages),
        "installable_basics": bool(manifest) and not any(
            i.startswith(("manifest-invalid", "manifest-missing-name", "manifest-missing-icons",
                          "manifest-missing-start-url", "no-icon-192", "no-icon-512", "display-not-app",
                          "icon-missing-file", "prefer-related"))
            for i in app),
        "manifest": manifest,
        "service_workers": sw_report,
        "sw_registrations": registered,
        "app_issues": app,
        "issue_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "page_details": pages,
    }


def print_markdown(r: dict) -> None:
    print(f"# PWA / mobile audit — {r['root']}\n")
    print(f"Pages: {r['pages']}  Installable basics: {'yes' if r['installable_basics'] else 'no'}")
    m = r["manifest"]
    if m:
        print(f"Manifest: `{m['file']}` — name={m.get('name')!r} short_name={m.get('short_name')!r} "
              f"display={m.get('display')} start_url={m.get('start_url')} id={m.get('id')} "
              f"screenshots={m.get('screenshots')} shortcuts={m.get('shortcuts')}")
        for icon in m.get("icons", []):
            print(f"  - icon {icon['src']} sizes={icon['sizes']} purpose={icon['purpose']} real={icon.get('real', 'missing')}")
    else:
        print("Manifest: none")
    sws = ", ".join(f"`{s['file']}`" for s in r["service_workers"]) or "none"
    print(f"Service worker: {sws}\n")
    print("## App issues\n")
    for issue in r["app_issues"] or ["none"]:
        print(f"- {issue}")
    print("\n## Issue counts (pages affected)\n")
    print("| Issue | Pages |\n|-------|-------|")
    for k, v in r["issue_counts"].items():
        print(f"| {k} | {v} |")
    print("\n## Pages\n")
    for p in r["page_details"]:
        if p["issues"]:
            print(f"- `{p['file']}` — " + "; ".join(p["issues"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="Build output folder")
    ap.add_argument("--base-path", default="", help="Subpath the app is served under, e.g. /app/")
    ap.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    args = ap.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    base_path = args.base_path
    if base_path and not base_path.startswith("/"):
        base_path = "/" + base_path
    if base_path and not base_path.endswith("/"):
        base_path += "/"
    report = audit(root, base_path)
    if args.json:
        json.dump(report, sys.stdout, indent=2)
        print()
    else:
        print_markdown(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
