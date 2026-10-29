# Card craft: layout, previews, and HTML rules

Rules for drawing each social card so variants are comparable, legible at feed size, and easy to turn into a real image later. They apply to the artifact's HTML, CSS, and inline SVG.

## The canvas

- **Size** — every card is a fixed `1200 × 630` element. Scale it for display with `transform: scale()` inside a wrapper; never let it reflow. Label the real size under it.
- **Safe area** — keep text and the logo inside a `64 px` inset (live area `1072 × 502`). Some platforms round the corners or crop a few pixels; the inset survives both.
- **Center band** — anything that must survive a square crop (`summary` cards, some chat apps) sits inside the centered `630 × 630` band. Show that band in the safe-area overlay.
- **One ground** — a single background from the project's tokens (light ground, dark ground, or brand color). A texture, grid, or motif is fine only if the site already uses it.

## Typography

- **Headline** — the project's display family and weight, 56–88 px, at most 3 lines, line height 1.05–1.15. At 300 px wide it must still read; if it does not, shorten the copy before shrinking the type.
- **Supporting line** — body family, 28–36 px, at most 2 lines. Optional.
- **Meta line** — domain or site name, 22–26 px. Never smaller than 22 px on the 1200 px card.
- Load fonts through the project's own link. If a font is not loadable, fall back to the closest system family and name it in the report.

## Composition

- One focal point per card: the headline, the product shot, or the mark. Not all three at the same weight.
- Put the logo in a consistent spot across per-page versions (usually top-left or bottom-left of the safe area), at 48–72 px tall.
- Product shots and UI fragments are drawn as HTML or SVG from the project's own components and tokens, framed with the project's radius. Do not embed raster screenshots unless the project already ships one; then reference that file.
- Leave at least 25% of the card empty. Cards that fill every edge read as ads.

## Copy

- Take the title and description from the real tags, page `<title>`, or README. Tighten them to fit, and list every rewrite under assumptions.
- No invented numbers, testimonials, customers, or features.
- Keep the brand name spelled exactly as the project writes it.

## Share previews

Each preview is a static mock, drawn in neutral UI colors (not the project's tokens) so the card stands out the way it will in a real feed. Use the real title, description, and domain.

| Platform | Card shown as | Text around the card |
| --- | --- | --- |
| X `summary_large_image` | 1.91:1, rounded corners, domain overlaid bottom-left | Title only, under the image on some clients |
| LinkedIn | 1.91:1, full width of the post | Title and domain below |
| Slack | Small left bar, site name, bold title, description, image below at about 360 px wide | All three lines |
| Discord | Embed with a colored left border (`theme-color` if set), title, description, image | All three lines |
| iMessage | Large image with a gray caption bar | Title and domain |

Draw these as generic UI shapes. Do not copy a platform's logo, icons, or trademarked artwork, and label each preview by platform name in plain text.

## Accessibility

- Text in the card has at least 4.5:1 contrast against its ground; large headline text at least 3:1.
- Write an `og:image:alt` text for each variant (one sentence describing the card), and show it under the full card.
- The card's meaning must not depend on color alone.

## Ready to export

Write each card so it can be rendered to PNG later without redesign:

- Absolute pixel sizes on the card element and its children; no viewport units inside the card.
- Flexbox layout only, which generators such as Satori (`next/og`) support; avoid CSS grid, `position: sticky`, filters, and blend modes inside the card.
- Inline SVG for the logo and motifs; fonts referenced by family name.

## What not to draw

- Another company's logo, a platform's trademarked UI, stock photos, or emoji used as the main visual.
- Fake engagement (likes, view counts, follower numbers) in the previews.
- Gradient washes or glows the site does not already use.
