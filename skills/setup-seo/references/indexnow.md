# IndexNow protocol reference

Canonical spec: https://www.indexnow.org/documentation · FAQ: https://www.indexnow.org/faq · participants: https://www.indexnow.org/searchengines.json

Read this before changing the key file, the submit script, or the deploy hook.

## What IndexNow is

An open protocol (Microsoft, CC BY-SA) that lets a site tell participating search engines "these URLs changed — come look now". It shortens the crawl delay after a deploy. It does **not** guarantee indexing, does not replace a sitemap, and does not replace `robots.txt` rules.

## Key

- Format: 8–128 characters from `a-z`, `A-Z`, `0-9`, and `-`. Hexadecimal is the common choice.
- Generate with `secrets.token_hex(16)` (32 hex chars) — `python3 -I scripts/indexnow_setup.py keygen`.
- The key is **not a secret in the usual sense**: it is published in the key file on purpose. What must stay secret are the API credentials used for Google/Bing webmaster APIs (see [engine-channels.md](engine-channels.md)).
- One key per host is the norm. Keep the same key across environments only if the key file is served from the same host; production and preview hosts usually need separate files.
- Changing the key invalidates the old key file. Engines re-validate the new one on the next submission; a stale key file left at the old URL does not help.

## Key file

- One UTF-8 plain-text file named `<key>.txt` whose entire content is the key. No HTML, no JSON, no trailing markup. A trailing newline is tolerated by the engines, but a file with extra text is not.
- Must be served over **HTTPS** from the **same host** as the submitted URLs.
- Should be served as `text/plain`. A `Content-Type` of `text/html` (a common accident when the host rewrites unknown extensions, or when a catch-all SPA route serves `index.html`) still usually works, but it is a smell — check it.
- Must return **HTTP 200 directly**. A 301/302 redirect to a login page, a trailing slash redirect, a CDN "not found" page, or a bot-protection challenge means the engine cannot read the key → submissions get rejected with HTTP 403.
- Must not be behind auth, geo-blocking, or a WAF rule that blocks non-browser user agents.
- **Location**: root of the site is the recommended option (`https://example.com/<key>.txt`). A key file in a subdirectory is legal but requires `keyLocation` on every submission, and the key file's directory then limits which URLs the key can validate — a key at `/catalog/<key>.txt` can validate `/catalog/**` but not `/help/**`. Use the root.
- Serve it with a short cache lifetime (`Cache-Control: no-cache` or `max-age=300`). A CDN caching a 404 for the key path for hours is a classic cause of "it worked locally, 403 in production".
- Add the key file to `.gitignore` only if the project treats it as secret. It is public by design, so committing it is fine and often simpler — but never commit a real API key for Google or Bing in its place.

## Endpoint

Use the shared endpoint; it forwards to every participant:

```
POST https://api.indexnow.org/indexnow
Content-Type: application/json; charset=utf-8

{
  "host": "example.com",
  "key": "<key>",
  "keyLocation": "https://example.com/<key>.txt",
  "urlList": ["https://example.com/", "https://example.com/pricing"]
}
```

- `keyLocation` is optional only when the key file is at the root of `host`.
- `host` is the hostname only (no scheme, no path) and must match the host of every URL in `urlList`.
- Up to **10,000 URLs per request**; split larger sets into batches.
- A single URL can also be sent as `GET https://api.indexnow.org/indexnow?url=<url>&key=<key>&keyLocation=<url>` with the URL percent-encoded (RFC 3986).
- Per-engine endpoints exist (each participant publishes an `indexnow/meta.json`): Bing `https://www.bing.com/indexnow/`, Yandex `https://www.yandex.com/indexnow/`, Seznam `https://search.seznam.cz/indexnow/`, Naver `https://searchadvisor.naver.com/indexnow/`, Yep `https://indexnow.yep.com/indexnow/`, Internet Archive `https://web-static.archive.org/indexnow/`, Amazonbot `https://indexnow.amazonbot.amazon/indexnow/`. Use them only for debugging a specific engine — the shared endpoint covers all of them.

## Response codes

| Code | Meaning | What to do |
|------|---------|------------|
| 200 | Accepted | Nothing; check the engine later for indexing |
| 202 | Accepted, key validation pending | The key file was not yet readable; the engine retries |
| 400 | Bad request format | Fix the JSON body / endpoint / encoding |
| 403 | Key missing, invalid, or not found at `keyLocation` | The key file is unreachable, redirects, or its content does not match the key — fix the file first |
| 422 | URLs do not belong to `host`, or key violates the schema | Fix `host`, the key format, or the URL list |
| 429 | Too many requests (treated as spam) | Slow down; submit changed URLs only, not the whole site every build |

## Participants (as listed at https://www.indexnow.org/searchengines.json)

`bing`, `yandex`, `seznam`, `naver`, `yep`, `internetarchive`, `amazonbot`.

Submitted URLs are **shared** across all participants, so one submission notifies every one of them. Google is **not** a participant — it evaluated the protocol in 2021 and never adopted it. Covering Google needs its own channels; see [engine-channels.md](engine-channels.md).

Bing's index feeds Microsoft Copilot, DuckDuckGo's results, and other downstream consumers. Amazonbot participation is why AI shopping and Amazon-side crawlers see new pages quickly.

## What to submit

- Submit URLs whose **content changed**: added, updated, or removed pages.
- Do **not** resubmit the whole site on every build — that is how you get rate-limited (429) and how you waste crawl quota.
- Include deleted URLs so engines drop them. URL removals still need to be within the same host and returned 404/410.
- Keep the list to real, public, indexable URLs. Do not submit URLs behind auth, preview deployments, or `noindex` pages.

## Rotation

1. Generate a new key.
2. Replace the key file (`<new-key>.txt`) and remove the old one — an old key file still on disk is dead weight and a small information leak.
3. Update `key`/`keyLocation` in the deploy configuration and secrets.
4. Submit once with the new key so engines re-validate.

## Cloud and CDN notes

- Cloudflare: "Crawler Hints" must be enabled for the zone, otherwise the key file may be challenged or rewritten.
- Netlify/Vercel/Cloudflare Pages: files placed in the framework's `public/`/`static/` directory are served as-is; confirm the deployed URL returns the raw key.
- GitHub Pages: `public/` (or `docs/`) is copied verbatim; `.nojekyll` must exist for files starting with `_`.
- Behind a reverse proxy, make sure the key path is not rewritten by a catch-all SPA fallback.
- Behind a CDN, make sure the key path is not cached negatively and that a missing file returns 404, not 200 with an HTML body.

## Verifying by hand

```bash
curl -sI https://example.com/<key>.txt            # 200, text/plain, no redirect
curl -s  https://example.com/<key>.txt | cmp - <(printf '%s' "<key>") && echo key-ok
```

Or run the bundled auditor, which does both plus the sitemap/robots checks:

```bash
python3 -I scripts/indexnow_setup.py audit --host https://example.com --key <key>
```

## Sources

- https://www.indexnow.org/documentation
- https://www.indexnow.org/faq
- https://www.indexnow.org/searchengines.json
- https://www.bing.com/indexnow/getstarted
