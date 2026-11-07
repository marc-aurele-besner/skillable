# hreflang: the rules, the pitfalls, and how to validate

`hreflang` tells search engines which URL is which language version of the same content. It is easy to emit, easy to get subtly wrong, and impossible to debug by eye — every error produces "no error", just worse rankings. Read this before writing a single tag.

The tag lives in `<head>`, one per locale:

```html
<link rel="alternate" hreflang="fr" href="https://example.com/fr/about" />
```

## The rules

1. **Every page lists every locale of that page.** If `/en/about`, `/fr/about`, and `/de/about` are the same content, all three pages list all three URLs.

2. **Self-reference is mandatory.** Each page must include an alternate pointing at *itself* with its own language. A page without a self-reference is ignored by search engines, and so is the whole cluster it belongs to.

   ```html
   <!-- on /fr/about -->
   <link rel="alternate" hreflang="fr" href="https://example.com/fr/about" />
   ```

3. **The links are reciprocal.** If `/fr/about` says `hreflang="en"` → `/en/about`, then `/en/about` must say `hreflang="fr"` → `/fr/about`. One-way links are ignored.

4. **`x-default` is required.** It is the catch-all for a locale that matches none of the listed ones. Point it at the source language's version, or at a language chooser. It appears on **every** page of the cluster, and it is the one alternate that does not need a reciprocal link.

5. **Valid language tags only.** BCP 47: `en`, `en-US`, `en-GB`, `pt-BR`, `zh-Hans`, `zh-Hant`, `sr-Latn`. Lowercase language, uppercase region, hyphen separator.

   | Wrong | Right | Why |
   |-------|-------|-----|
   | `en_US` | `en-US` | Underscore is not a BCP 47 separator |
   | `EN-us` | `en-US` | Language lowercase, region uppercase |
   | `english` | `en` | Use the ISO 639-1 code |
   | `en-UK` | `en-GB` | The UK has no ISO 3166 code; use `GB` |
   | `zh` | `zh-Hans` / `zh-Hant` | Chinese needs a script to be unambiguous |

6. **Return links are per-language.** When `/en/about` links to `/fr/about` with `hreflang="fr"`, the `/fr/about` page links back with `hreflang="en"` — the codes swap. Both pages use the *same* set of codes, each pointing at the other locale's URL.

7. **Canonical is per locale.** Each locale canonicalizes to its own URL. A single canonical pointing every locale at the source language tells search engines to index only that one, and the other locales get dropped.

   ```html
   <!-- on /fr/about -->
   <link rel="canonical" href="https://example.com/fr/about" />
   ```

8. **Never point hreflang at a `noindex` page.** A noindex target makes the cluster unusable — the alternates are ignored, and the canonical may be ignored too. If a locale is deliberately unindexed, remove it from every other page's alternate list *and* from the sitemap.

9. **`hreflang` and `canonical` are independent.** `hreflang` says "these are translations of each other"; `canonical` says "this is the one URL to index". A page can have a self-referencing canonical *and* alternates to its siblings. Do not point the canonical at the English version.

10. **Do not mix `hreflang` with `og:locale`.** They are different systems. `og:locale` is for social previews and uses underscores (`fr_FR`); `hreflang` uses hyphens (`fr`). Getting one right does not set the other.

## Correct example

`https://example.com/en/about`:

```html
<html lang="en">
<head>
<link rel="canonical" href="https://example.com/en/about" />
<link rel="alternate" hreflang="en" href="https://example.com/en/about" />
<link rel="alternate" hreflang="fr" href="https://example.com/fr/about" />
<link rel="alternate" hreflang="de" href="https://example.com/de/about" />
<link rel="alternate" hreflang="x-default" href="https://example.com/en/about" />
</head>
```

`https://example.com/fr/about`:

```html
<html lang="fr">
<head>
<link rel="canonical" href="https://example.com/fr/about" />
<link rel="alternate" hreflang="en" href="https://example.com/en/about" />
<link rel="alternate" hreflang="fr" href="https://example.com/fr/about" />
<link rel="alternate" hreflang="de" href="https://example.com/de/about" />
<link rel="alternate" hreflang="x-default" href="https://example.com/en/about" />
</head>
```

The two pages carry the same four lines with the URLs swapped. That is reciprocity.

## Incorrect examples

```html
<!-- WRONG: no self-reference on the French page -->
<html lang="fr"><head>
<link rel="alternate" hreflang="en" href="https://example.com/en/about" />
<link rel="alternate" hreflang="fr" href="https://example.com/fr/about" />
</head></html>
```
The French page lists `hreflang="fr"` → `/fr/about`, which *is* itself — that part is fine. But if the `en` page has no `hreflang="fr"` line, the link is one-way and the whole pair is ignored. Reciprocity is the property that breaks, not the self-reference.

```html
<!-- WRONG: one canonical for all locales -->
<html lang="fr"><head>
<link rel="canonical" href="https://example.com/en/about" />
</head></html>
```
The French page says "the real version is the English one". Search engines are told to index only the English URL.

```html
<!-- WRONG: no x-default -->
<link rel="alternate" hreflang="en" href="https://example.com/en/about" />
<link rel="alternate" hreflang="fr" href="https://example.com/fr/about" />
```

```html
<!-- WRONG: invalid language tag -->
<link rel="alternate" hreflang="fr_FR" href="https://example.com/fr/about" />
<link rel="alternate" hreflang="english" href="https://example.com/en/about" />
```

```html
<!-- WRONG: hreflang pointing at a noindex page -->
<link rel="alternate" hreflang="de" href="https://example.com/de/about" />
<!-- ...but /de/about has <meta name="robots" content="noindex"> -->
```

```html
<!-- WRONG: hreflang to a URL that 404s -->
<link rel="alternate" hreflang="es" href="https://example.com/es/about" />
```

## Locale-code pitfalls

**`en` vs `en-US`.** `en` means "English, any region"; `en-US` means "United States". They are different hreflang values. If you ship `en-US` and `en-GB` as separate versions, each page lists both, and `en` alone is not a substitute. If you ship one English version for everyone, use `en` and set `<html lang="en">`. Mixing them — `<html lang="en-US">` with `hreflang="en"` — is a mismatch: the self-reference language should match the page's language.

**`zh-Hans` vs `zh-Hant`.** Simplified and Traditional Chinese are different scripts and often different sites. `zh` alone is ambiguous and search engines treat it as a weaker signal. Use `zh-Hans` (Simplified) and `zh-Hant` (Traditional), and `zh-Hans-CN` / `zh-Hant-TW` when the region matters.

**`pt-BR` vs `pt-PT`.** Brazilian and European Portuguese are not interchangeable — different vocabulary, different spelling. Shipping one as "Portuguese" and calling it `pt` loses the distinction; shipping both means two versions and two full translations.

**`sr-Latn` vs `sr-Cyrl`.** Script matters for Serbian, Azerbaijani (`az-Latn` / `az-Arab`), Uzbek (`uz-Latn` / `uz-Cyrl`), and Mongolian (`mn-Mong` vs `mn`).

**Region-only is valid.** `fr`, `de`, `ja`, `ko` are all valid language tags. `de-CH` (Swiss German) is valid.

**`<html lang>` and `hreflang` use the same tag syntax.** Hyphens, same casing convention. `og:locale` is the odd one out (underscores, e.g. `fr_FR`).

**Lowercase is safe.** `zh-hans` and `zh-Hans` are both accepted; use lowercase language and uppercase region as the convention.

## Sitemap alternates

The sitemap lists every locale URL, each with its alternates via the `xhtml:link` namespace:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
  <url>
    <loc>https://example.com/en/about</loc>
    <xhtml:link rel="alternate" hreflang="en" href="https://example.com/en/about" />
    <xhtml:link rel="alternate" hreflang="fr" href="https://example.com/fr/about" />
    <xhtml:link rel="alternate" hreflang="de" href="https://example.com/de/about" />
    <xhtml:link rel="alternate" hreflang="x-default" href="https://example.com/en/about" />
  </url>
  <url>
    <loc>https://example.com/fr/about</loc>
    <xhtml:link rel="alternate" hreflang="en" href="https://example.com/en/about" />
    <xhtml:link rel="alternate" hreflang="fr" href="https://example.com/fr/about" />
    <xhtml:link rel="alternate" hreflang="de" href="https://example.com/de/about" />
    <xhtml:link rel="alternate" hreflang="x-default" href="https://example.com/en/about" />
  </url>
</urlset>
```

Each `<url>` entry carries the full alternate set. Do not list a locale URL in the sitemap that is `noindex` — remove it from the sitemap entirely.

## How to validate

### 1. The bundled auditor

```bash
python3 -I scripts/audit_i18n.py <build-output-dir>
python3 -I scripts/audit_i18n.py <build-output-dir> --base-url https://example.com --json > "$TMPDIR/i18n.json"
```

It checks, per page:

| Issue | Meaning |
|-------|---------|
| `missing-self-reference` | No alternate points at the page itself |
| `self-reference-lang-mismatch` | The self-reference language does not match `<html lang>` |
| `non-reciprocal` | The target page does not link back |
| `missing-x-default` | No `x-default` alternate on a page that has alternates |
| `missing-target` | An hreflang href resolves to no page in the build |
| `alternate-to-noindex` | An alternate points at a `noindex` page |
| `noindex-page-has-alternates` | A `noindex` page is part of a cluster |
| `canonical-not-self` | A page with alternates canonicalizes to another URL |
| `missing-html-lang` | The page has no `<html lang>` |

For SSR apps with no static build, save the rendered HTML of the key routes with `curl -s` into a folder and audit that folder.

### 2. Spot-check the live site

```bash
curl -s https://example.com/fr/about | grep -i -e 'hreflang' -e 'rel="canonical"' -e '<html'
```

Compare the set of alternates on two locale URLs by eye — they should carry the same codes with swapped URLs.

### 3. Google Search Console

The **International Targeting** report lists the languages Google has indexed for the site, and the **Hreflang** report (in Search Console's Pages section) lists every error it found: missing return link, no self-reference, page with another locale's canonical, and so on. Ask the user to check it — it is account-gated, and the agent should not log into it.

### 4. Other validators

- Google's Search Console International Targeting report (authoritative, needs the user's account).
- The `hreflang` tag tester in third-party SEO tools — handy but not authoritative; Google explicitly warns against relying on them.
- `curl` + a quick diff of the alternate sets between two locale URLs — a ten-second check that catches the reciprocity break.

## Common failures and their fix

| Symptom | Cause | Fix |
|---------|-------|-----|
| Only the source language is indexed | One canonical across locales | Canonical per locale |
| A locale page is not indexed at all | It is `noindex`, or its hreflang cluster points at a noindex page | Remove the noindex, or remove it from every alternate list |
| Google reports "no return tag" | The alternates are one-way | Make every cluster reciprocal |
| Google reports "no self-reference" | The page does not list its own URL | Add the self-reference |
| Google reports "page with another locale's canonical" | One canonical for all locales | Canonical per locale |
| French and English pages rank for each other | `hreflang` values swapped or missing | Fix the code/URL pairing |
| `og:locale` shows the wrong language | `og:locale` was set from `hreflang` | `og:locale` uses `fr_FR`; set it separately |
