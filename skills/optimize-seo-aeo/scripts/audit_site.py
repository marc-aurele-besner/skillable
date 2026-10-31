#!/usr/bin/env python3
"""Audit a built static site for SEO and AEO basics.

Read-only and stdlib-only. Point it at a folder of built HTML (dist/, out/,
public/, build/, _site/, or a folder of pages saved with curl):

    python3 -I audit_site.py dist --base-url https://example.com
    python3 -I audit_site.py dist --base-url https://example.com --json

Per page: title, meta description, canonical, html lang, viewport, H1 count,
Open Graph / Twitter tags, JSON-LD validity and types, images without alt,
noindex, near-empty body text, broken internal links.
Site level: duplicate titles/descriptions, robots.txt (Sitemap line, blocked
AI search bots), sitemap.xml coverage, llms.txt.

Exit code is 0 even when issues are found; it reports, it does not judge.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

AI_SEARCH_BOTS = (
    "OAI-SearchBot",
    "ChatGPT-User",
    "Claude-SearchBot",
    "Claude-User",
    "PerplexityBot",
    "Perplexity-User",
    "Googlebot",
    "Bingbot",
    "Applebot",
)
AI_TRAINING_BOTS = ("GPTBot", "ClaudeBot", "Google-Extended", "Applebot-Extended", "CCBot")
OG_REQUIRED = ("og:title", "og:description", "og:image", "og:url", "og:type")
THIN_BODY_WORDS = 50
SKIP_DIRS = {"node_modules", ".git", "_next", "assets", "static", "_astro"}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang: str | None = None
        self.title_parts: list[str] = []
        self.in_title = False
        self.meta: dict[str, str] = {}
        self.canonical: str | None = None
        self.h1 = 0
        self.imgs_no_alt = 0
        self.links: list[str] = []
        self.jsonld: list[str] = []
        self._in_jsonld = False
        self._jsonld_buf: list[str] = []
        self._skip_depth = 0
        self.text_words = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang") or None
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or a.get("http-equiv") or "").lower()
            if key:
                self.meta.setdefault(key, a.get("content", ""))
        elif tag == "link":
            rels = a.get("rel", "").lower().split()
            if "canonical" in rels:
                self.canonical = a.get("href", "")
        elif tag == "h1":
            self.h1 += 1
        elif tag == "img":
            if "alt" not in a:
                self.imgs_no_alt += 1
        elif tag == "a":
            href = a.get("href")
            if href:
                self.links.append(href)
        elif tag == "script":
            if a.get("type", "").lower() == "application/ld+json":
                self._in_jsonld = True
                self._jsonld_buf = []
            else:
                self._skip_depth += 1
        elif tag in ("style", "noscript", "template"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif tag == "script":
            if self._in_jsonld:
                self.jsonld.append("".join(self._jsonld_buf))
                self._in_jsonld = False
            elif self._skip_depth:
                self._skip_depth -= 1
        elif tag in ("style", "noscript", "template") and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        elif self._in_jsonld:
            self._jsonld_buf.append(data)
        elif not self._skip_depth:
            self.text_words += len(data.split())

    @property
    def title(self) -> str:
        return " ".join("".join(self.title_parts).split())


def page_url(root: Path, path: Path, base: str) -> str:
    rel = path.relative_to(root).as_posix()
    if rel == "index.html":
        rel = ""
    elif rel.endswith("/index.html"):
        rel = rel[: -len("index.html")]
    return urljoin(base, rel)


def jsonld_types(raw: str) -> tuple[list[str], str | None]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [], f"invalid JSON ({exc.msg} at line {exc.lineno})"
    items = data if isinstance(data, list) else [data]
    types: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        graph = item.get("@graph")
        nodes = graph if isinstance(graph, list) else [item]
        if "@context" not in item:
            return types, "missing @context"
        for node in nodes:
            if isinstance(node, dict):
                t = node.get("@type")
                types.extend(t if isinstance(t, list) else [t] if t else [])
    if not types:
        return types, "no @type"
    return [str(t) for t in types], None


def audit_page(root: Path, path: Path, base: str, known: set[str], real_base: bool) -> dict:
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    url = page_url(root, path, base)
    issues: list[str] = []
    m = parser.meta
    robots = (m.get("robots", "") + "," + m.get("googlebot", "")).lower()
    noindex = "noindex" in robots

    if not parser.title:
        issues.append("no-title")
    elif not 15 <= len(parser.title) <= 70:
        issues.append(f"title-length ({len(parser.title)} chars)")
    desc = m.get("description", "").strip()
    if not desc:
        issues.append("no-description")
    elif not 50 <= len(desc) <= 170:
        issues.append(f"description-length ({len(desc)} chars)")
    if parser.canonical is None:
        issues.append("no-canonical")
    elif not urlparse(parser.canonical).scheme:
        issues.append("canonical-relative")
    elif real_base and urlparse(parser.canonical).netloc != urlparse(base).netloc:
        issues.append(f"canonical-foreign ({parser.canonical})")
    elif real_base and parser.canonical.rstrip("/") != url.rstrip("/"):
        issues.append(f"canonical-other-page ({parser.canonical})")
    if not parser.lang:
        issues.append("no-lang")
    if "viewport" not in m:
        issues.append("no-viewport")
    if parser.h1 != 1:
        issues.append(f"h1-count ({parser.h1})")
    missing_og = [k for k in OG_REQUIRED if not m.get(k)]
    if "twitter:card" not in m:
        missing_og.append("twitter:card")
    if missing_og:
        issues.append("og-missing (" + ", ".join(missing_og) + ")")
    og_image = m.get("og:image", "")
    if og_image and not urlparse(og_image).scheme:
        issues.append("og-image-relative")
    if noindex:
        issues.append("noindex")
    if parser.text_words < THIN_BODY_WORDS:
        issues.append(f"thin-body ({parser.text_words} words without JS)")
    if parser.imgs_no_alt:
        issues.append(f"img-no-alt ({parser.imgs_no_alt})")

    types: list[str] = []
    for raw in parser.jsonld:
        t, err = jsonld_types(raw)
        types.extend(t)
        if err:
            issues.append(f"jsonld-invalid ({err})")
    if not parser.jsonld:
        issues.append("no-jsonld")

    broken = sorted({h for h in parser.links if is_broken_internal(h, url, base, known)})
    if broken:
        issues.append("broken-link (" + ", ".join(broken[:5]) + (" …" if len(broken) > 5 else "") + ")")

    return {
        "url": url,
        "file": path.relative_to(root).as_posix(),
        "title": parser.title,
        "description": desc,
        "noindex": noindex,
        "jsonld_types": sorted(set(types)),
        "issues": issues,
    }


def normalize(u: str) -> str:
    p = urlparse(u)
    path = p.path or "/"
    if path.endswith("/index.html"):
        path = path[: -len("index.html")]
    elif path.endswith(".html"):
        path = path[: -len(".html")]
    return path.rstrip("/") or "/"


def is_broken_internal(href: str, page: str, base: str, known: set[str]) -> bool:
    if href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return False
    target = urljoin(page, href)
    if urlparse(target).netloc != urlparse(base).netloc:
        return False
    path = urlparse(target).path
    if re.search(r"\.(png|jpe?g|gif|svg|webp|avif|ico|pdf|zip|css|js|xml|txt|json|woff2?)$", path, re.I):
        return False
    return normalize(target) not in known


def parse_robots(text: str) -> dict:
    groups: list[tuple[list[str], list[str]]] = []
    agents: list[str] = []
    rules: list[str] = []
    sitemaps: list[str] = []
    last_was_agent = False
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (s.strip() for s in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not last_was_agent and agents:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
            last_was_agent = True
        elif key in ("disallow", "allow"):
            rules.append(f"{key}:{value}")
            last_was_agent = False
        elif key == "sitemap":
            sitemaps.append(value)
    if agents:
        groups.append((agents, rules))

    def blocks_root(bot: str) -> bool:
        b = bot.lower()
        chosen = next((r for a, r in groups if b in a), None)
        if chosen is None:
            chosen = next((r for a, r in groups if "*" in a), [])
        return "disallow:/" in chosen and "allow:/" not in chosen

    return {
        "sitemaps": sitemaps,
        "blocked_search_bots": [b for b in AI_SEARCH_BOTS if blocks_root(b)],
        "blocked_training_bots": [b for b in AI_TRAINING_BOTS if blocks_root(b)],
    }


def sitemap_urls(root: Path, name: str, seen: set[str] | None = None) -> list[str]:
    seen = seen if seen is not None else set()
    path = root / name
    if name in seen or not path.is_file():
        return []
    seen.add(name)
    try:
        tree = ElementTree.parse(path)
    except ElementTree.ParseError:
        return ["<unparseable>"]
    urls: list[str] = []
    for el in tree.iter():
        if el.tag.endswith("}loc") or el.tag == "loc":
            loc = (el.text or "").strip()
            if el.text and loc.endswith(".xml"):
                urls.extend(sitemap_urls(root, urlparse(loc).path.lstrip("/"), seen))
            else:
                urls.append(loc)
    return urls


def audit_site(root: Path, base: str) -> dict:
    files = sorted(
        p for p in root.rglob("*.html")
        if not any(part in SKIP_DIRS for part in p.relative_to(root).parts)
        and p.name not in ("404.html", "500.html")
    )
    base_for_pages = base or "https://site.invalid/"
    known = {normalize(page_url(root, p, base_for_pages)) for p in files}
    pages = [audit_page(root, p, base_for_pages, known, bool(base)) for p in files]

    site: list[str] = []
    for field, code in (("title", "dup-title"), ("description", "dup-description")):
        groups: dict[str, list[str]] = defaultdict(list)
        for p in pages:
            if p[field] and not p["noindex"]:
                groups[p[field]].append(p["url"])
        for value, urls in groups.items():
            if len(urls) > 1:
                site.append(f"{code}: {len(urls)} pages share {value[:60]!r}")

    robots = None
    robots_path = root / "robots.txt"
    if robots_path.is_file():
        robots = parse_robots(robots_path.read_text(encoding="utf-8", errors="replace"))
        if not robots["sitemaps"]:
            site.append("robots-no-sitemap")
        if robots["blocked_search_bots"]:
            site.append("ai-search-blocked: " + ", ".join(robots["blocked_search_bots"]))
    else:
        site.append("no-robots (not in build output; may be served by the host)")

    sm = sitemap_urls(root, "sitemap.xml") or sitemap_urls(root, "sitemap-index.xml")
    coverage = None
    if not sm:
        site.append("no-sitemap (not in build output; may be generated at runtime)")
    elif sm == ["<unparseable>"]:
        site.append("sitemap-invalid-xml")
    else:
        listed = {normalize(u) for u in sm}
        indexable = {normalize(p["url"]) for p in pages if not p["noindex"]}
        missing = sorted(indexable - listed)
        extra = sorted(listed - known)
        coverage = f"{len(indexable & listed)}/{len(indexable)}"
        if missing:
            site.append(f"sitemap-missing: {len(missing)} indexable pages, e.g. {missing[:3]}")
        if extra:
            site.append(f"sitemap-extra: {len(extra)} URLs with no built page, e.g. {extra[:3]}")
        noindexed = sorted(listed & {normalize(p["url"]) for p in pages if p["noindex"]})
        if noindexed:
            site.append(f"sitemap-lists-noindex: {noindexed[:3]}")

    if not (root / "llms.txt").is_file():
        site.append("no-llms-txt")

    counts: dict[str, int] = defaultdict(int)
    for p in pages:
        for issue in p["issues"]:
            counts[issue.split(" ", 1)[0]] += 1

    return {
        "root": str(root),
        "base_url": base or None,
        "pages": len(pages),
        "sitemap_coverage": coverage,
        "robots": robots,
        "site_issues": site,
        "issue_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "page_details": pages,
    }


def print_markdown(r: dict) -> None:
    print(f"# SEO / AEO audit — {r['root']}\n")
    print(f"Pages: {r['pages']}  Base URL: {r['base_url'] or '(none — canonical checks limited)'}")
    print(f"Sitemap coverage: {r['sitemap_coverage'] or 'n/a'}\n")
    if r["robots"]:
        print(f"robots.txt — sitemaps: {r['robots']['sitemaps'] or 'none'}; "
              f"blocked AI search bots: {r['robots']['blocked_search_bots'] or 'none'}; "
              f"blocked AI training bots: {r['robots']['blocked_training_bots'] or 'none'}\n")
    print("## Site issues\n")
    for issue in r["site_issues"] or ["none"]:
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
    ap.add_argument("root", type=Path, help="Folder of built HTML")
    ap.add_argument("--base-url", default="", help="Production origin, e.g. https://example.com")
    ap.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    args = ap.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    base = args.base_url.rstrip("/") + "/" if args.base_url else ""
    if base and not re.match(r"^https?://[^/\s]+/$", base):
        print("error: --base-url must be an origin like https://example.com", file=sys.stderr)
        return 2
    report = audit_site(root, base)
    if args.json:
        json.dump(report, sys.stdout, indent=2)
        print()
    else:
        print_markdown(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
