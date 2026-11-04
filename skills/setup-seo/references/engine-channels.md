# Engine coverage: what each engine actually needs

IndexNow is one channel. This file lists the rest, so "maximum coverage for Google, Bing, and every IndexNow participant" is a checklist and not a vibe.

Read this before deciding what to wire into a project.

## The short version

| Engine | IndexNow | Sitemap | Push channel beyond the sitemap |
|--------|----------|---------|----------------------------------|
| **Bing** | yes (originator) | yes | Bing Webmaster Tools API (`submitUrl`, `SubmitSitemap`), `https://www.bing.com/ping?sitemap=` |
| **Yandex** | yes | yes | Yandex Webmaster API (`/api/v4/webmaster/url/submit`) |
| **Seznam** | yes | yes | Seznam webmaster portal |
| **Naver** | yes | yes | Naver Search Advisor API |
| **Yep** | yes | yes | — (IndexNow is the channel) |
| **Amazonbot** | yes | yes | Amazon product feeds (different surface) |
| **Internet Archive** | yes | yes | — |
| **Google** | **no** | yes (required) | Search Console API `sitemaps.submit`; Google Indexing API **only** for JobPosting/BroadcastEvent pages; `https://www.google.com/ping?sitemap=` (legacy, unreliable) |
| **DuckDuckGo** | no (uses Bing's index) | yes | — |
| **Apple** | no | yes | Applebot crawls on its own schedule |
| **AI answer engines** (ChatGPT search, Copilot, Perplexity, Claude) | indirectly (via Bing's index for Copilot/ChatGPT search) | yes | `robots.txt` must not block their retrieval bots (see `optimize-seo-aeo`) |

Google has never adopted IndexNow — it evaluated the protocol in 2021 and stopped there. **A site that only wires IndexNow is invisible to Google.** Sitemap + Search Console + crawlable, server-rendered pages are the Google path.

## Google

1. **Sitemap** — `https://example.com/sitemap.xml`, absolute URLs, only canonical indexable 200 URLs, real `lastmod`. Google ignores `lastmod` it cannot verify, so do not stamp every URL with the build time.
2. **`robots.txt`** — must not `Disallow: /` on production, and must include `Sitemap: https://example.com/sitemap.xml`.
3. **Search Console** — the user must verify ownership. Two options:
   - DNS TXT record (`google-site-verification=…`) — no repo change, strongest, covers both apex and www.
   - HTML meta tag `<meta name="google-site-verification" content="…">` — needs the token from the user; add it to the shared head/layout so it survives on every page.
   - A `google-site-verification.html` file at the site root also works.
   Ask the user for the token; never invent one.
4. **Sitemap submission** — the reliable route is the Search Console API `sitemaps.submit`, called with an OAuth service account. The service-account JSON key **must** live in CI secrets, never in the repo. If no credentials exist, list "submit the sitemap in Search Console" as a manual follow-up rather than adding a credential flow.
5. **Google Indexing API** — only for pages with `JobPosting` or `BroadcastEvent` (live-stream) structured data. Using it for ordinary pages is a documented policy violation and can get the domain dropped from Google results. Only wire it when the site really publishes job postings or live streams; otherwise say so explicitly in the report.
6. **Legacy ping** — `GET https://www.google.com/ping?sitemap=https://example.com/sitemap.xml` usually returns a blank 200 and is not officially supported. Use it at most as a harmless extra, never as the only submission path.

## Bing

1. **IndexNow** — covered by the shared endpoint (Bing is the originator).
2. **Bing Webmaster Tools** — the user must verify ownership with an `msvalidate.01` meta tag (or an XML file). Ask for the token; add the meta tag to the shared head.
3. **Sitemap** — `https://example.com/sitemap.xml` submitted in Bing Webmaster Tools, plus the `Sitemap:` line in `robots.txt`. Bing also honours the legacy `https://www.bing.com/ping?sitemap=…` endpoint.
4. **Bing Webmaster API** — `https://ssl.bing.com/webmaster/api.svc/json` with an API key generated in Bing Webmaster Tools. It offers `SubmitUrl` and `SubmitSitemap`. The API key is a secret → CI secrets only. Without a key, submit the sitemap manually.
5. **Bing's index is reused** by DuckDuckGo, Copilot, and part of ChatGPT search. IndexNow therefore has a reach multiplier beyond Bing itself.

## Yandex, Seznam, Naver, Yep

- All four accept IndexNow submissions through the shared endpoint — that is the whole setup.
- Each also has a webmaster portal worth verifying the domain in (Yandex Webmaster, Seznam, Naver Search Advisor). Verification tokens are per-engine (`yandex-verification` meta or file, Seznam/Naver similar) and are **the user's to obtain** — ask, never guess.
- Yandex additionally exposes a sitemap submission API (`https://yandex.com/webmaster/api/v4/webmaster/url/submit`) that needs an OAuth token — optional, list as a follow-up.

## Verification tokens in one place

Every engine's verification token is a different string and they do not interfere with each other. Collect whatever the user has and put them in the shared head/layout:

```html
<meta name="google-site-verification" content="…" />
<meta name="msvalidate.01" content="…" />
<meta name="yandex-verification" content="…" />
```

If the project has no shared head (plain HTML pages), put the tags in every `<head>`, or in a template the site already uses.

## Host and URL hygiene that gates every channel

- Pick one canonical host (apex or `www`) and 301 the other to it. Every engine indexes both otherwise, and `host` in the IndexNow body must match the URLs you submit.
- HTTPS everywhere, `http://` → `https://` redirects, no redirect chains.
- The site must return real `404` for unknown paths. A catch-all SPA fallback that returns `200` for every URL makes the sitemap, IndexNow, and every engine think every path is a duplicate.
- `www.example.com` and `example.com` are different hosts: each needs its own key file if you submit to both. Pick one.

## What to tell the user at the end

- Which engines are covered by the automation, and which need a manual account action (verification, sitemap submission, API key).
- That IndexNow receipt is not an indexing guarantee — check Bing Webmaster Tools and Google Search Console for actual index coverage.
- Which Google channels were intentionally **not** wired and why (for example: no Indexing API because the site has no job postings).
