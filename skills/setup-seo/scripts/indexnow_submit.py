#!/usr/bin/env python3
"""Submit URLs to IndexNow (shared endpoint, all participating engines).

Stdlib-only. Verifies the key file is live, then submits the URLs you give it.

    python3 -I indexnow_submit.py --host https://example.com --key <key> \
        --url https://example.com/ --url https://example.com/pricing
    python3 -I indexnow_submit.py --host https://example.com --key <key> \
        --sitemap https://example.com/sitemap.xml --dry-run

--url may be repeated. --sitemap accepts a URL or a local sitemap.xml file and
adds every <loc> that belongs to --host. Requests are sent as one POST per
batch of up to 10000 URLs to https://api.indexnow.org/indexnow, which forwards
them to every participating engine (Bing, Yandex, Seznam, Naver, Yep, Amazonbot,
Internet Archive).

Exit code is 0 when every batch was accepted (HTTP 200 or 202), 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree

DEFAULT_ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_URLS_PER_REQUEST = 10000
USER_AGENT = "setup-seo-skill/1.0 (+https://github.com/marc-aurele-besner/skillable)"


def http_request(url: str, data: bytes | None, headers: dict[str, str], timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(4096).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(4096).decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return 0, str(exc)


def fetch_text(url: str, timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(4_000_000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(4096).decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return 0, str(exc)


def urls_from_sitemap(source: str, host: str, timeout: float) -> tuple[list[str], str]:
    """Return (urls, note). Accepts an http(s) URL or a local path."""
    if source.startswith(("http://", "https://")):
        status, body = fetch_text(source, timeout)
        if status != 200:
            return [], f"could not read sitemap {source} (HTTP {status})"
    else:
        path = Path(source)
        if not path.is_file():
            return [], f"sitemap file not found: {source}"
        body = path.read_text(encoding="utf-8", errors="replace")

    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        return [], f"could not parse {source} as XML: {exc}"

    urls: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "loc":
            continue
        loc = (element.text or "").strip()
        if loc and urllib.parse.urlparse(loc).hostname == urllib.parse.urlparse(host).hostname:
            urls.append(loc)
    note = f"{len(urls)} of {source}'s URLs match {host}"
    return urls, note


def verify_key_file(key_location: str, key: str, timeout: float) -> str | None:
    status, body = fetch_text(key_location, timeout)
    if status != 200:
        return f"key file {key_location} returned HTTP {status}"
    if body.strip() != key:
        return f"key file {key_location} does not contain the key"
    return None


def chunked(items: list[str], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--host", required=True, help="host of the submitted URLs, e.g. https://example.com")
    parser.add_argument("--key", required=True, help="IndexNow key")
    parser.add_argument("--key-location", help="URL of the key file (default: <host>/<key>.txt)")
    parser.add_argument("--url", action="append", default=[], help="URL to submit (repeatable)")
    parser.add_argument("--sitemap", action="append", default=[], help="sitemap URL or file to read URLs from")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help=f"IndexNow endpoint (default: {DEFAULT_ENDPOINT})")
    parser.add_argument("--dry-run", action="store_true", help="print the request without sending it")
    parser.add_argument("--skip-verify", action="store_true", help="do not check the key file first")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds (default: 20)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    host = args.host.rstrip("/")
    key = args.key.strip()
    key_location = args.key_location.rstrip("/") if args.key_location else f"{host}/{key}.txt"

    urls: list[str] = []
    notes: list[str] = []
    for source in args.sitemap:
        found, note = urls_from_sitemap(source, host, args.timeout)
        urls.extend(found)
        notes.append(note)
    urls.extend(args.url)

    # De-duplicate while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            ordered.append(url)

    if not ordered:
        print("nothing to submit: pass --url or --sitemap", file=sys.stderr)
        for note in notes:
            print(f"  - {note}", file=sys.stderr)
        return 1

    hostname = urllib.parse.urlparse(host).hostname or ""
    foreign = [url for url in ordered if urllib.parse.urlparse(url).hostname != hostname]
    if foreign:
        print(f"refusing to submit URLs outside {hostname}:", file=sys.stderr)
        for url in foreign[:10]:
            print(f"  - {url}", file=sys.stderr)
        return 1

    if not args.skip_verify and not args.dry_run:
        problem = verify_key_file(key_location, key, args.timeout)
        if problem:
            print(f"key verification failed: {problem}", file=sys.stderr)
            print("fix the key file first; the engine will reject the batch otherwise (HTTP 403).", file=sys.stderr)
            return 1

    results: list[dict] = []
    failed = False
    for batch in chunked(ordered, MAX_URLS_PER_REQUEST):
        payload = {
            "host": hostname,
            "key": key,
            "keyLocation": key_location,
            "urlList": batch,
        }
        body = json.dumps(payload).encode("utf-8")
        if args.dry_run:
            print(f"POST {args.endpoint}")
            print(json.dumps({**payload, "urlList": batch[:5] + (["…"] if len(batch) > 5 else [])}, indent=2))
            print(f"({len(batch)} URL(s) in this batch)")
            results.append({"status": "dry-run", "urls": len(batch)})
            continue

        status, text = http_request(
            args.endpoint,
            body,
            {"Content-Type": "application/json; charset=utf-8", "User-Agent": USER_AGENT},
            args.timeout,
        )
        results.append({"status": status, "urls": len(batch), "response": text.strip()[:500]})
        if status not in (200, 202):
            failed = True

    if args.json:
        print(json.dumps({"submitted": len(ordered), "results": results}, indent=2))
    else:
        for result in results:
            if result["status"] == "dry-run":
                print(f"dry-run: {result['urls']} URL(s)")
            else:
                print(f"HTTP {result['status']}: {result['urls']} URL(s) — {result['response'] or '(empty body)'}")
        if not failed and not args.dry_run:
            print("\nAccepted. HTTP 200 means the engine received the URLs; HTTP 202 means key validation is pending.")
            print("Receipt is not an indexing guarantee — check Bing Webmaster Tools for actual indexing.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
