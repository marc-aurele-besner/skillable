# AEO playbook (answer-engine optimization)

AI answer engines find pages through a search index (their own or Bing's/Google's), fetch them live when a user asks, and quote the parts that answer the question. So AEO is mostly good SEO plus three things: **let the retrieval bots in, serve content without JavaScript, and write passages that stand on their own.** Be honest in the PR about what is proven: crawl access, server-rendered HTML, and structured data matter; `llms.txt` is a cheap, low-risk convention with uneven adoption.

## AI crawlers and robots.txt

Bot names change; check the vendor docs linked below before editing and prefer them over this table.

| Vendor | Search / retrieval (affects being cited) | User-triggered fetch | Training (owner's policy call) | Docs |
|--------|------------------------------------------|----------------------|--------------------------------|------|
| OpenAI | `OAI-SearchBot` | `ChatGPT-User` | `GPTBot` | https://platform.openai.com/docs/bots |
| Anthropic | `Claude-SearchBot` | `Claude-User` | `ClaudeBot` | https://support.claude.com/en/articles/8896518 |
| Perplexity | `PerplexityBot` | `Perplexity-User` | — | https://docs.perplexity.ai/guides/bots |
| Google | `Googlebot` (AI Overviews use the normal index) | — | `Google-Extended` (token, not a separate crawler) | https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers |
| Apple | `Applebot` | — | `Applebot-Extended` (token) | https://support.apple.com/en-us/119829 |
| Microsoft | `Bingbot` (feeds Copilot and ChatGPT search) | — | — | https://www.bing.com/webmasters/help/which-crawlers-does-bing-use-8c184ec0 |
| Common Crawl | — | — | `CCBot` | https://commoncrawl.org/ccbot |

Rules:

- Blocking `Googlebot` or `Bingbot` removes you from AI answers built on those indexes too. Never do it to "opt out of AI".
- A training opt-out that keeps citations: block `GPTBot`, `ClaudeBot`, `Google-Extended`, `Applebot-Extended`, `CCBot`; allow the search and user agents. Only write this if the owner asks for it.
- Keep groups explicit. A bot with its own `User-agent` group ignores the `*` group, so repeat shared `Disallow` lines in it.
- WAF/CDN bot-fight modes (Cloudflare "Block AI bots", Vercel firewall) can override `robots.txt`. If the live site returns 403 to these user agents, report it; the fix lives in the host dashboard.

Example that allows everything and points at the sitemap (the usual default):

```text
User-agent: *
Allow: /
Disallow: /api/
Disallow: /admin/

Sitemap: https://example.com/sitemap.xml
```

## Rendering

Assume AI fetchers read the raw HTML response and do not execute JavaScript. Check with `curl -s -A "OAI-SearchBot" <url>` and look for the page's main text. If it is missing, the page is invisible to them no matter how good the metadata is. Fix with SSG/SSR/prerender in the framework, not with user-agent sniffing or a separate "bot version" (cloaking).

## llms.txt

Spec: https://llmstxt.org. A Markdown file at `/llms.txt`:

```markdown
# Project Name

> One-paragraph summary: what it is, who it is for, the key facts an assistant should know.

Optional short notes (install command, licensing, current version).

## Docs

- [Getting started](https://example.com/docs/start): install and first run
- [API reference](https://example.com/docs/api): every endpoint with examples

## Optional

- [Changelog](https://example.com/changelog)
```

- Generate it at build time from the same nav/content source as the sitemap, so it never drifts. Hand-write only the summary.
- `llms-full.txt` (all docs concatenated as Markdown) and per-page `.md` mirrors help docs sites and APIs most; skip them for marketing sites.
- Docs frameworks may have a plugin (Docusaurus, VitePress, Starlight, Mintlify have community or built-in options); use it if already installed or clearly standard, otherwise a small build script.

## Structured data for answers

JSON-LD helps engines resolve entities (who made this, what it is, when it changed). Priorities: `Organization`/`Person` + `WebSite` on home; page-type schema everywhere else; `sameAs` linking official profiles (GitHub, X, LinkedIn, package registry) found in the repo; `dateModified` kept true.

Google limits some rich results (FAQ to authoritative government/health sites, HowTo removed), but the markup still describes the page. Add `FAQPage` only when the page shows those exact Q&As. Never add markup for content that is not visible.

## Writing passages that get cited

Small, factual edits the skill may apply; anything bigger goes in the report as suggestions:

- **Answer first.** The first sentence under an H1/H2 states the answer or definition. "X is a … that …".
- **Self-contained sections.** Each H2 section makes sense on its own, names the subject instead of "it", and fits in a few short paragraphs.
- **Question-shaped headings** where it suits the voice: "How much does X cost?", "X vs Y".
- **Concrete facts.** Numbers with units, versions, dates, limits, prices; cite sources for claims.
- **Comparison and spec tables** in HTML (`<table>`), not images.
- **Freshness.** Visible "Updated <date>" on docs and articles, matching `dateModified` and sitemap `lastmod`.
- **Consistent entity naming.** Same product name, tagline, and description across title, schema, README, package metadata, and social profiles.

## Outside the repo (report as follow-ups)

- Verify in Google Search Console and Bing Webmaster Tools and submit the sitemap. Bing matters for ChatGPT search and Copilot.
- IndexNow (Bing, Yandex, others) for fast re-crawl after deploys — needs a key file and a deploy hook; offer it, do not set it up silently.
- Get listed where assistants look: official docs, GitHub README, package registries, Wikipedia/Wikidata (if notable), reputable directories and comparisons.
