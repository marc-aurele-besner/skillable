# Image formats, encoders, responsive recipes, and budgets

Reference for the `optimize-images` skill. Read the section you need; do not read it all.

## Format support matrix

| Format | Encoding | Browser support (2025) | Best for | Typical saving vs. JPEG |
|--------|----------|------------------------|----------|----------------------------|
| **AVIF** | lossy / lossless | Chrome, Edge, Firefox, Safari 16.4+ | photos, illustrations with gradients | 30–60% smaller than JPEG |
| **WebP** | lossy / lossless | All evergreen browsers, iOS 14+ | photos, UI screenshots, transparency | 25–40% smaller than JPEG, ~90% smaller than PNG for opaque images |
| **JPEG** | lossy | universal | legacy fallback, very old clients | baseline |
| **PNG** | lossless | universal | screenshots, text, flat graphics, transparency | baseline |
| **GIF** | lossless, 256 colours | universal | animation only | baseline |
| **SVG** | vector | universal | icons, logos, illustrations | usually 1–10 KB vs. 20–200 KB PNG |
| **JPEG XL** | lossy / lossless | Chrome and Edge behind a flag; not in Safari or Firefox | experimental only | n/a — do not ship |

Practical rule: **AVIF → WebP → original** as the `<picture>` fallback chain. Keep PNG and GIF originals in the repo; do not delete them, they are the fallback and the source.

Browser detection for a `<picture>` chain:

```html
<picture>
  <source type="image/avif" srcset="/img/hero-800.avif 800w, /img/hero-1200.avif 1200w, /img/hero-1600.avif 1600w" sizes="100vw">
  <source type="image/webp" srcset="/img/hero-800.webp 800w, /img/hero-1200.webp 1200w, /img/hero-1600.webp 1600w" sizes="100vw">
  <img src="/img/hero-1200.jpg" srcset="/img/hero-800.jpg 800w, /img/hero-1200.jpg 1200w, /img/hero-1600.jpg 1600w"
       sizes="100vw" width="1600" height="900" alt="…" fetchpriority="high" decoding="async">
</picture>
```

`type` on `<source>` is what lets the browser skip a format it cannot decode. Always give the `<img>` a real `src` fallback.

## Encoders and quality settings

Use a tool the project already has. Only add a dependency when there is none, and say so in the PR.

| Encoder | Command shape | Notes |
|---------|---------------|-------|
| `sharp` (Node) | `sharp(input).avif({ quality: 50 }).toFile(out)` | Fast, good AVIF/WebP; the usual choice in Node pipelines |
| `cwebp` / `webp` (libwebp) | `cwebp -q 75 in.png -o out.webp` | Reference WebP encoder; `-q 75` is a good photo default |
| `avifenc` | `avifenc --min 0 --max 40 in.jpg out.avif` | Slow; `--max 40` is roughly "quality 50" |
| `magick` / `convert` | `magick in.png -quality 80 out.webp` | Convenient but slow and imprecise for AVIF |
| `sips` (macOS) | `sips -s format webp in.png --out out.webp` | Built in on macOS, no install; quality control is limited |
| `imagemagick` + `libheif` | `heic` conversions | HEIC is not a web format; convert, do not ship |
| `ffmpeg` | frame extraction from video | Only for video posters; pick a keyframe, then optimise it |
| Cloudinary / imgix URL params | `?f=avif&q=60` | No local build step; the CDN does the work |

Quality targets to start from:

| Source type | AVIF | WebP | JPEG |
|-------------|------|------|------|
| Photo | 50–60 | 75–80 | 75–82 |
| Photo with text/UI | 65–70 | 82–88 | 85–90 |
| Screenshot / flat UI | 60 (lossless if smaller) | lossless or 90 | 90 |
| Illustration, few colours | 70 | 90 | 90 |
| Transparent PNG | lossless AVIF | lossless WebP | keep PNG |

Always compare the output size against the original: if the "optimised" file is bigger, keep the original.

## Responsive recipes

Concrete `srcset`/`sizes` values for common layouts:

```html
<!-- Full-bleed hero -->
<img src="/img/hero-1600.jpg"
     srcset="/img/hero-640.jpg 640w, /img/hero-960.jpg 960w, /img/hero-1280.jpg 1280w, /img/hero-1600.jpg 1600w"
     sizes="100vw" width="1600" height="900" alt="…">

<!-- Two-column card grid: full width on mobile, half on desktop -->
<img src="/img/card-800.jpg"
     srcset="/img/card-400.jpg 400w, /img/card-800.jpg 800w, /img/card-1200.jpg 1200w"
     sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 600px"
     width="1200" height="800" loading="lazy" decoding="async" alt="…">

<!-- Fixed-width avatar, never larger than 96 CSS pixels -->
<img src="/img/avatar-96.jpg" srcset="/img/avatar-48.jpg 48w, /img/avatar-96.jpg 96w"
     sizes="96px" width="96" height="96" loading="lazy" decoding="async" alt="…">

<!-- Thumbnail whose real CSS size is unknown: use a density descriptor list -->
<img src="/img/thumb.jpg" srcset="/img/thumb.jpg 1x, /img/thumb@2x.jpg 2x"
     width="300" height="200" loading="lazy" decoding="async" alt="…">
```

Rules that keep this honest:

- The `src` attribute is the fallback for browsers without `srcset`; keep it at the most common size.
- `sizes` must describe the **CSS layout width**, not the file width. When unsure, `sizes="100vw"` is safe but wasteful.
- Never list a width larger than the intrinsic size of the file — that is an upscale.
- Generate one file per width you list, from the largest original. Never upscale to fill a width.
- Widths in `srcset` are CSS pixels (`w`), density descriptors (`x`) are multipliers of the `src`.
- The `width`/`height` attributes must be the CSS size of the rendered image and must match the intrinsic ratio of the file, so the browser can reserve space.

## Framework image components

If the project has one, use it. It handles `srcset`, `sizes`, dimensions, and format conversion.

| Framework | Component | Notes |
|-----------|-----------|-------|
| Next.js (App Router) | `next/image` | Set `images.formats: ['image/avif', 'image/webp']`, `deviceSizes`, `imageSizes`; `priority` on the LCP image adds the preload; `loader` for a custom CDN |
| Next.js (Pages) | `next/image` | Same; use `priority` (not `loading="lazy"`) for the hero |
| Astro | `astro:assets` `<Image>` / `<Picture>` | `import` the file so Astro knows the dimensions; `<Picture>` gives the format fallback chain; `priority` for the LCP image; `layout="constrained"` sets `sizes` for you |
| Nuxt | `@nuxt/image` `<NuxtImg>` / `<NuxtPicture>` | Providers include Cloudinary, imgix, IPX; set `sizes` and `densities` in the module config |
| SvelteKit | `@sveltejs/enhanced-img` | Build-time sharp pipeline; import the image for automatic `srcset` and dimensions |
| Vite | `vite-plugin-image` or `@vite-pwa` assets | Rarely worth adding if the framework above is in use |
| Eleventy / Hugo | `eleventy-plugin-img`, `resources.Get` + `image` filters | Static generation; Hugo's image processing is built in |
| Remix / React Router | `next/image`-style community packages, or plain `<img>` | No first-party image component; prefer a plain `<picture>` |
| WordPress / CMS | the CMS's image service | Do not hand-optimize what the CMS re-renders; fix the CMS settings |

Do not mix hand-written `<img srcset>` with a framework component on the same page. Pick the project's component and use it everywhere.

## CDNs and edge optimizers

If the site already transforms images at the edge, the local file is the *source*, not the payload.

| Service | How it works | Double-optimizing looks like |
|---------|--------------|------------------------------|
| **Vercel / Next Image** | `/_next/image?url=…&w=…&q=…` | Shipping a pre-compressed AVIF through the Next loader — it re-encodes and the cache key changes |
| **Cloudinary** | `https://res.cloudinary.com/<cloud>/image/upload/f_avif,q_auto,w_800/<public-id>` | Pre-converting locally and also passing `f_auto` — double compression and banding |
| **imgix** | `?auto=format&fit=max&w=800&q=75` | The same; `auto=format` already negotiates AVIF/WebP |
| **Cloudflare Images** | Edge-resized variants via a custom loader or `/cdn-cgi/image/…` | Local conversion plus edge resize |
| **Netlify Image CDN** | `/.netlify/images?url=…&w=…&q=…` | Same |
| **Squoosh / custom worker** | A script that resizes on request | Same |

How to check before optimizing locally:

1. Look for a loader or a provider in the config: `next.config.js` (`images`), `nuxt.config.ts` (`image`), `astro.config.mjs` (`image`), a `cloudinary` / `imgix` URL in the markup or CSS.
2. Grep the repo for the CDN host: `rg -n "res\.cloudinary\.com|imgix\.net|cdn-cgi/image|/_next/image|/\.netlify/images"`.
3. Curl the served URL and read `Content-Type` and `Content-Length`. If the edge returns `image/avif` for a `.jpg` path, the CDN is already optimizing.

When the edge does the work, the local change is only: correct `width`/`height`, correct `sizes`, correct `loading`/`fetchpriority`, and making sure the source file uploaded is high enough quality and not pre-compressed.

## LCP-aware priority rules

The LCP image is the largest contentful element in the viewport — usually the hero. Getting it right is worth more than any other single image change.

1. **One image only.** Exactly one image per page gets `fetchpriority="high"`. Two "high" priorities cancel out.
2. **Never lazy-load it.** `loading="lazy"` on the LCP image delays the paint and can make it slower than not lazy-loading at all.
3. **Preload it** when the page is static HTML and the URL is known:

```html
<link rel="preload" as="image" href="/img/hero-1600.avif"
      type="image/avif" imagesrcset="/img/hero-800.avif 800w, /img/hero-1600.avif 1600w"
      imagesizes="100vw" fetchpriority="high">
```

4. **Everything else eager is a bug.** Above-the-fold images that are not the LCP should still be `loading="lazy"` if the browser allows it, or at least `decoding="async"`. Below-the-fold images must be lazy.
5. **`decoding="async"`** on every image except the LCP one, so decoding never blocks the main thread.
6. **CSS background images** cannot be lazy-loaded or preloaded with `fetchpriority` the same way. If the hero is a CSS background, consider moving it to an `<img>` with `object-fit: cover` so it gets the priority hints.
7. Do not set `fetchpriority="low"` on the LCP image; `"high"` and `"auto"` are the only values worth using.

## Building a byte budget file

The auditor (`scripts/audit_images.py`) reads a JSON budget file and exits 1 when a budget is exceeded:

```json
{
  "max_image_bytes": 250000,
  "max_total_bytes": 2000000,
  "max_page_bytes": {
    "index.html": 800000,
    "products/index.html": 1200000,
    "*": 1500000
  }
}
```

| Key | Meaning |
|-----|---------|
| `max_image_bytes` | Any single referenced file may not exceed this. |
| `max_total_bytes` | The sum of all distinct referenced images may not exceed this. |
| `max_page_bytes` | Per page: the image bytes referenced by that page. `*` is the fallback for pages without an explicit entry. |

How to pick the numbers:

1. Measure first: `python3 -I scripts/audit_images.py . --json > /tmp/images-before.json`, then read `totals.total_bytes` and `bytes_by_page`.
2. Set `max_image_bytes` to about 1.2× the current largest *shipped* image, and `max_total_bytes` / `max_page_bytes` to about 1.1–1.2× today's totals. CI starts green, with headroom for content that has not been optimized yet.
3. Tighten the numbers in the same PR as the optimization work, or in a follow-up PR, once the site is measurably smaller. Lowering a budget below today's real number fails CI immediately — that is the point, but do it deliberately.
4. Keep the budget file in the repo, and keep the auditor next to it so CI can run `python3 -I scripts/audit_images.py . --budget-file image-budget.json`.

Budgets are a policy decision. If the user owns the budget, ask before tightening it; if they do not, propose the numbers in the PR description.
