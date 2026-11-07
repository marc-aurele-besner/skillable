#!/usr/bin/env python3
"""Audit hreflang correctness across a set of HTML files.

Read-only and stdlib-only. Point it at a folder of built HTML (dist/, out/,
public/, build/, .output/public/, _site/, or a folder of pages saved with
curl):

    python3 -I audit_i18n.py dist
    python3 -I audit_i18n.py dist --json
    python3 -I audit_i18n.py dist --base-url https://example.com

Checks, per page:
  - self-reference: the page declares an alternate for its own <html lang>
  - reciprocity:   every alternate is declared back by the target page
  - x-default:     the page declares an x-default alternate
  - targets exist: every hreflang href resolves to a file in the folder
  - noindex:       no alternate points at a noindex page
  - canonical:     a page with alternates canonicalises to its own URL

Exit code is 0 even when issues are found; it reports, it does not judge.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

SKIP_DIRS = {"node_modules", ".git", "_next", "assets", "static", "_astro"}


class PageParser(HTMLParser):
    """Collect the bits of a page that hreflang correctness depends on."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang: str | None = None
        self.canonical: str | None = None
        self.alternates: list[dict[str, str]] = []
        self.robots: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html":
            self.lang = (a.get("lang") or "").strip() or None
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or a.get("http-equiv") or "").lower()
            content = a.get("content", "")
            if key == "robots":
                self.robots.append(content.lower())
            elif key == "googlebot":
                self.robots.append(content.lower())
        elif tag == "link":
            rels = a.get("rel", "").lower().split()
            href = a.get("href", "").strip()
            if "canonical" in rels and href and self.canonical is None:
                self.canonical = href
            if "alternate" in rels and href:
                lang = a.get("hreflang", "").strip()
                if lang:
                    self.alternates.append({"hreflang": lang, "href": href})

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join("".join(self.title_parts).split())

    @property
    def noindex(self) -> bool:
        return any("noindex" in rule for rule in self.robots)


def page_path(root: Path, page: Path) -> str:
    """Return the URL path a built HTML file is served at."""
    rel = page.relative_to(root).as_posix()
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    return "/" + rel


def index_pages(root: Path) -> dict[str, Path]:
    """Map a normalized URL path to the file that serves it."""
    index: dict[str, Path] = {}
    for page in sorted(root.rglob("*.html")):
        if any(part in SKIP_DIRS for part in page.relative_to(root).parts):
            continue
        index[normalize(page_path(root, page))] = page
    return index


def resolve_target(href: str, page_url: str, base_netloc: str | None) -> tuple[str | None, bool]:
    """Resolve an href to a local URL path.

    Returns (path, external). path is None when the target cannot be checked
    because it lives on another host.
    """
    absolute = urljoin(page_url, href)
    parsed = urlparse(absolute)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return None, True
    if parsed.netloc and base_netloc and parsed.netloc.lower() != base_netloc.lower():
        return None, True
    return unquote(parsed.path or "/"), False


def normalize(path: str) -> str:
    """Normalize a URL path to the form used to match built files.

    "/fr/index.html", "/fr/index.html/", "/fr" and "/fr/" all become "/fr/".
    """
    path = path or "/"
    if not path.startswith("/"):
        path = "/" + path
    if path.endswith("/index.html"):
        path = path[: -len("index.html")]
    elif path.endswith(".html"):
        path = path[: -len(".html")] + "/"
    if not path.endswith("/"):
        path = path + "/"
    return path


def base_language(tag: str) -> str:
    """Return the base language of a language tag ("en-US" -> "en")."""
    return tag.strip().lower().replace("_", "-").split("-", 1)[0]


def audit_page(
    root: Path,
    page: Path,
    index: dict[str, Path],
    base_netloc: str | None,
) -> dict:
    parser = PageParser()
    parser.feed(page.read_text(encoding="utf-8", errors="replace"))
    own_path = page_path(root, page)
    issues: list[str] = []

    if not parser.lang:
        issues.append("missing-html-lang")

    resolved: list[dict[str, str | None]] = []
    for alt in parser.alternates:
        target_path, external = resolve_target(alt["href"], own_path, base_netloc)
        resolved.append(
            {
                "hreflang": alt["hreflang"],
                "href": alt["href"],
                "path": target_path,
                "external": external,
            }
        )

    # A page with no alternates at all is a single-language site: nothing to check.
    if resolved:
        if parser.noindex:
            issues.append("noindex-page-has-alternates")

        # x-default
        if not any(r["hreflang"].lower() == "x-default" for r in resolved):
            issues.append("missing-x-default")

        # self-reference: an alternate with a language (not x-default) that
        # points back at this page
        self_pointing = [
            r
            for r in resolved
            if r["hreflang"].lower() != "x-default"
            and r["path"] is not None
            and normalize(r["path"]) == normalize(own_path)
        ]
        if not self_pointing:
            issues.append("missing-self-reference")
        elif parser.lang:
            # the language of the self-reference should match <html lang>
            # (compare the base language, so "en" and "en-US" agree)
            if not any(
                base_language(r["hreflang"]) == base_language(parser.lang)
                for r in self_pointing
            ):
                issues.append("self-reference-lang-mismatch")

    # targets must exist
    for r in resolved:
        if r["external"] or r["path"] is None:
            continue
        if normalize(r["path"]) not in index:
            issues.append(f"missing-target: {r['hreflang']} -> {r['href']}")

    # canonical must point at the page itself when alternates are declared
    if resolved and parser.canonical:
        canon_path, canon_external = resolve_target(parser.canonical, own_path, base_netloc)
        if not canon_external and canon_path is not None:
            if normalize(canon_path) != normalize(own_path):
                issues.append("canonical-not-self")

    return {
        "file": page.relative_to(root).as_posix(),
        "url": own_path,
        "lang": parser.lang,
        "title": parser.title,
        "canonical": parser.canonical,
        "noindex": parser.noindex,
        "alternates": resolved,
        "issues": issues,
    }


def audit(root: Path, base_netloc: str | None) -> dict:
    index = index_pages(root)
    pages = [audit_page(root, page, index, base_netloc) for page in sorted(index.values())]

    by_path = {normalize(p["url"]): p for p in pages}

    # Reciprocity: if page A declares "this URL is the <L> version of B",
    # then B must declare an alternate pointing back at A.
    # x-default is exempt: it is a catch-all entry, not a version claim.
    for page in pages:
        for r in page["alternates"]:
            if r["external"] or r["path"] is None:
                continue
            if r["hreflang"].lower() == "x-default":
                continue
            target_path = normalize(r["path"])
            target = by_path.get(target_path)
            if target is None:
                continue
            if target["noindex"] and target_path != normalize(page["url"]):
                page["issues"].append(f"alternate-to-noindex: {r['hreflang']} -> {r['href']}")
            back = None
            for candidate in target["alternates"]:
                if candidate["path"] is None:
                    continue
                if normalize(candidate["path"]) == normalize(page["url"]):
                    back = candidate
                    break
            if back is None:
                page["issues"].append(f"non-reciprocal: {r['hreflang']} -> {r['href']}")

    counts: dict[str, int] = defaultdict(int)
    for page in pages:
        for issue in page["issues"]:
            counts[issue.split(":", 1)[0].strip()] += 1

    with_alternates = sum(1 for p in pages if p["alternates"])
    return {
        "root": str(root),
        "base_url": base_netloc,
        "pages": len(pages),
        "pages_with_alternates": with_alternates,
        "issue_counts": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "page_details": pages,
    }


def print_markdown(report: dict) -> None:
    print(f"# i18n / hreflang audit — {report['root']}\n")
    print(
        f"Pages: {report['pages']}  "
        f"Pages with hreflang alternates: {report['pages_with_alternates']}  "
        f"Base URL: {report['base_url'] or '(none — same-host links assumed)'}\n"
    )
    print("## Issue counts (pages affected)\n")
    print("| Issue | Pages |\n|-------|-------|")
    if report["issue_counts"]:
        for code, count in report["issue_counts"].items():
            print(f"| {code} | {count} |")
    else:
        print("| none | 0 |")
    print("\n## Pages\n")
    for page in report["page_details"]:
        detail = (
            f"- `{page['file']}` (lang={page['lang'] or 'none'}"
            + (", noindex" if page["noindex"] else "")
            + ")"
        )
        if page["issues"]:
            print(detail + " — " + "; ".join(page["issues"]))
        else:
            print(detail + " — ok")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("root", type=Path, help="Folder of built HTML")
    ap.add_argument("--base-url", default="", help="Production origin, e.g. https://example.com")
    ap.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    args = ap.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    base_netloc = ""
    if args.base_url:
        parsed = urlparse(args.base_url if "//" in args.base_url else "//" + args.base_url)
        base_netloc = parsed.netloc
        if not base_netloc:
            print("error: --base-url must be an origin like https://example.com", file=sys.stderr)
            return 2
    report = audit(root, base_netloc or None)
    if args.json:
        json.dump(report, sys.stdout, indent=2)
        print()
    else:
        print_markdown(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
