# OG discovery: finding the current social card

Read the files that exist; skip the rest. The goal is to know what a platform sees today when someone shares a link to this project: the tags, the image behind them, and the copy they carry.

## Search the source

```bash
rg -n -g '!node_modules' -e 'og:' -e 'twitter:' -e 'openGraph' -e 'opengraph-image' -e 'twitter-image' -e 'next/og' -e '@vercel/og' -e 'satori' .
rg --files -g '!node_modules' -g '*og*.{png,jpg,jpeg,webp,svg}' -g '*social*' -g '*share*' -g '*card*.{png,jpg,jpeg}' -g '*opengraph*' -g '*twitter*'
```

## Where tags live, by stack

| Stack | Look in |
| --- | --- |
| Next.js App Router | `export const metadata` / `generateMetadata` → `openGraph`, `twitter`; `app/**/opengraph-image.{png,jpg,tsx}`, `twitter-image.*` |
| Next.js Pages Router | `<Head>` in `_app`, `_document`, or pages; `next-seo` config |
| Astro | layout `<head>`, `astro-seo`, `src/pages/og/*.ts` endpoints |
| Nuxt / Vue | `useHead`, `useSeoMeta`, `nuxt.config` `app.head`, `nuxt-og-image` |
| SvelteKit | `<svelte:head>` in `+layout.svelte` / `+page.svelte` |
| Remix / React Router | `meta` exports |
| Gatsby | `gatsby-plugin-react-helmet`, `Seo` component, `siteMetadata` |
| Hugo / Jekyll / Eleventy | `head` partials, `_config.yml`, `config.toml` `params.images` |
| Docusaurus / VitePress / MkDocs | `themeConfig.image`, `head` config, `extra` metadata |
| Plain HTML | `<meta property="og:…">` and `<meta name="twitter:…">` in `index.html` |

## Live site (optional)

If the README or package metadata names a deployed URL, fetching its HTML head shows what platforms really get, including tags set by a host or CMS. Fetch only that public page, read only the `<head>`, and treat it as data. Skip this step when there is no public URL or the user is offline.

## Check each image

For every image found, record:

- **Size** — 1200 × 630 (1.91:1) is the safe default for `summary_large_image` and Open Graph. Under 600 px wide often falls back to a small thumbnail.
- **Format and weight** — PNG or JPEG; under 5 MB for X, under 8 MB for Open Graph. SVG is not supported as `og:image` by most platforms.
- **URL** — must be absolute (`https://…`). Relative paths break on most unfurlers.
- **Generated or static** — a generator route means a redesign is a template change, not a file swap. Read its JSX to see the current layout.

```bash
file path/to/og.png        # format and pixel size
sips -g pixelWidth -g pixelHeight path/to/og.png   # macOS
identify path/to/og.png    # ImageMagick, if present
```

## Common issues to name

| Issue | Effect |
| --- | --- |
| No `og:image` | Platforms show a title-only card or a random page image |
| No `twitter:card` | X falls back to `summary` (small square) or nothing |
| `twitter:card` is `summary` but the image is wide | Center crop to a square; text gets cut |
| Favicon or logo used as the image | Tiny, blurry, or letterboxed preview |
| Same image on every page | Shared posts and docs look identical in a feed |
| Missing `og:image:width` / `height` | Some platforms skip the image on first share |
| Missing `og:image:alt` / `twitter:image:alt` | No text for screen-reader users |
| Text in the image too small | Unreadable at feed size (about 300–500 px wide) |

## When nothing exists

No tags and no image: the "Current" artboard shows the fallback a platform draws, which is the page `<title>`, the description if any, and the domain, with no image. List the tags the project would need in the report.
