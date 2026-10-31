# Discoverability checklist

Each row: what to check, the tier, and the fix. Tiers are defined in `SKILL.md` step 3. Auditor codes in brackets are what `scripts/audit_site.py` reports.

## P0 — invisible

| Check | Fix |
|-------|-----|
| `noindex` on a page that should rank (meta robots or `X-Robots-Tag`) [`noindex`] | Remove it; keep `noindex` only on search results, auth, cart, thank-you, and staging pages |
| `robots.txt` has `Disallow: /` for `*` on production | Scope it to the private paths, or make it env-aware so only preview/staging deploys block |
| AI search bots blocked (`OAI-SearchBot`, `Claude-SearchBot`, `PerplexityBot`, user-triggered agents) [`ai-search-blocked`] | Ask the owner; unblock if it was accidental |
| Body is near-empty without JavaScript (SPA shell) [`thin-body`] | Prerender/SSG/SSR the route. Most AI crawlers do not run JS; Google does, but later and less reliably |
| Canonical points to another page, another domain, or `http://` [`canonical-foreign`] | Self-referencing absolute `https://` canonical on every indexable page |
| Missing pages return 200 (soft 404) | Use the framework's not-found mechanism so the status is 404 |
| Important content only behind tabs/accordions that load on click | Render it in the HTML; hiding with CSS is fine, fetching on click is not |
| Preview/staging domain indexable and duplicating production | `noindex` or robots block on non-production hosts via env |

## P1 — undescribed

| Check | Fix |
|-------|-----|
| Missing `<title>` [`no-title`] or duplicate across pages [`dup-title`] | Unique, descriptive, ≈30–60 chars, brand at the end via a template |
| Missing meta description [`no-description`] or duplicate [`dup-description`] | Unique summary, ≈70–160 chars, written as the answer to "what is this page?" |
| No canonical [`no-canonical`] or relative canonical [`canonical-relative`] | Absolute self-canonical; strip tracking params; pick one trailing-slash style |
| No `<html lang>` [`no-lang`] | Set it in the root layout; add `hreflang` alternates only if the site really has translations |
| No viewport meta [`no-viewport`] | `width=device-width, initial-scale=1` |
| No sitemap [`no-sitemap`], or it lists missing/redirected/noindex URLs [`sitemap-extra`], or misses pages [`sitemap-missing`] | Generate from the route source; canonical URLs only; real `lastmod`; skip `priority`/`changefreq` (Google ignores them) |
| `robots.txt` missing [`no-robots`] or without a `Sitemap:` line [`robots-no-sitemap`] | Add both; absolute sitemap URL |
| Missing `og:title`, `og:description`, `og:image`, `og:url`, `og:type`, `twitter:card` [`og-missing`] | Site defaults plus per-page overrides; absolute image URL; 1200 × 630; `summary_large_image` |
| No `Organization` (or `Person`) and `WebSite` JSON-LD on the home page [`no-jsonld`] | Add one block with name, url, logo, `sameAs` (only real profiles listed in the repo) |

## P2 — machine-readable

| Check | Fix |
|-------|-----|
| JSON-LD that does not parse [`jsonld-invalid`] or lacks `@context`/`@type` | Build it with `JSON.stringify` from data, never string templates |
| Page type has no matching schema | Blog → `BlogPosting`/`Article` (headline, datePublished, dateModified, author, image); app/tool → `SoftwareApplication` (name, applicationCategory, operatingSystem, offers if real); product → `Product`; docs/nested → `BreadcrumbList`; real Q&A section → `FAQPage` |
| Zero or several H1 [`h1-count`] | Exactly one H1 that matches the page topic; H2/H3 in order |
| Images without `alt` [`img-no-alt`] | Describe content; `alt=""` for decoration |
| Broken internal links [`broken-link`] | Fix the href or add the redirect |
| No `llms.txt` [`no-llms-txt`] | See `aeo-playbook.md`; most useful for docs, APIs, and product sites |
| No visible or machine-readable dates | `<time datetime>` for published/updated; `dateModified` in JSON-LD; `lastmod` in sitemap |
| Orphan pages (no internal links in) | Link from nav, hubs, or related-content blocks with descriptive anchor text |
| Favicon / apple-touch-icon / web manifest missing | Use the framework's icon convention; reuse existing brand assets |

## P3 — answerable content

| Check | Fix |
|-------|-----|
| Page opens with fluff before saying what it is | One plain sentence under the H1: what it is, who it's for, the key fact |
| Headings are slogans | Headings that match how people ask ("How does X price?", "X vs Y") where it fits the voice |
| Key facts buried in prose | Short lists, tables, definitions; numbers with units and sources |
| No author or "last updated" on articles/docs | Show them; mirror in JSON-LD |
| Brand/product named inconsistently | One canonical name across titles, schema, and copy |

## Report only

Core Web Vitals and image weight, redirect chains at the host/CDN, HTTPS/HSTS, backlinks and directory listings, Search Console and Bing Webmaster verification, IndexNow setup, analytics. Mention what the repo can influence (e.g. `width`/`height` on images, `loading="lazy"` below the fold, `fetchpriority="high"` on the hero) as optional P2 work.
