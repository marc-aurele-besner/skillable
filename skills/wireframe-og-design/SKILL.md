---
name: wireframe-og-design
description: >-
  Redesign a project's social media card (the og:image and twitter:image shown
  when a link is shared) as several variants built from the project's own
  colors, fonts, layout, and light/dark themes. Finds the current Open Graph and
  Twitter Card tags and images, reads the site's design and page layout, then
  draws each variant as a 1200 × 630 card and shows it inside realistic share
  previews (X, LinkedIn, Slack, Discord, iMessage) next to the current card.
  Publishes every variant together in one Design canvas (one artboard per
  variant) or, without a canvas type, a single fallback page. Use whenever the
  user wants to design, redesign, improve, mock up, or compare an og:image,
  Open Graph image, Twitter card, link preview, social card, share image, or
  unfurl for their site. Also triggers on /wireframe-og-design with an optional
  variant count and focus.
argument-hint: "[variants=3] [focus or page]"
---

# Wireframe OG Design

Goal: show the user what their links could look like when shared. Read the current social card (if any), the project's look, and its page layout, then propose N card redesigns that clearly belong to this product. Each variant is one 1200 × 630 card, seen at full size and inside the share previews where people actually meet it. The cards are exploration: they live in the artifact, never as a commit in the project.

## When to use

- "Redesign our og:image", "make a better Twitter card for this site"
- "What does our link look like on Slack / LinkedIn? Propose something better"
- "Give me 4 variants of the social share image"
- Refining a variant into a template for every page (see step 7)
- `/wireframe-og-design [variants=N] [focus]`
- Not for shipping the image or meta tags to the repo (offer a handoff instead), and not for the logo itself (use `wireframe-logo-design`).

## Inputs

| Input | Default | Notes |
| --- | --- | --- |
| Variants | 3 | From `variants=N` (also accept `variant=N` or a bare number). Clamp 1–6. |
| Focus | site-wide default card | A page or template to design for ("blog posts", `/pricing`). Changes the card's content, not the process. |
| Brand name | project name | From `package.json` `name`, the README title, or the app's `<title>`. |
| Current card | auto-detected | Every `og:image` / `twitter:image` found. Shown once as "Current". |

Do not run a questionnaire. Fill gaps with sensible assumptions and list them in the report.

## 1. Find the current social card

Follow [references/og-discovery.md](references/og-discovery.md). Capture into a short working note:

1. **Tags** — every `og:*` and `twitter:*` tag, where it is set (file and line), and whether it is static, per-page, or generated (`opengraph-image.tsx`, `next/og`, `@vercel/og`, Satori, a build script).
2. **Images** — the file or route behind each `og:image` and `twitter:image`, its real size, format, and weight. Note mismatches: wrong ratio, under 1200 px wide, over 5 MB, missing `twitter:card`, relative URLs, no `og:image:alt`.
3. **Content** — the title, description, and site name the tags carry. These are the card's real copy.
4. **Gaps** — no card at all, the favicon reused as the image, a screenshot crop, the same card on every page.

If the project ships no card, say so plainly; the "Current" slot then shows the plain fallback a platform draws (title and domain, no image).

## 2. Read the project's look and layout

If the project's agent instructions point to a published design system (from `extract-design-system`), start from it and confirm only what the card needs. Otherwise read the source of truth (Tailwind `@theme` or config, `:root` / `.dark` variables, theme objects, `next/font` or `@font-face`, logo and icon files). Capture:

- **Palette** — brand color, accent, and the ink and ground for each theme, with the project's token names.
- **Type** — the display family and weight for headings, the body family, and where they load from.
- **Shape** — the radius token and whether the UI reads sharp, rounded, or soft.
- **Logo** — the real mark and wordmark files (`logo.svg`, `icon.svg`, `Logo.tsx`), and `manifest` `theme_color`.
- **Layout signature** — how the hero is composed: alignment, column split, how much whitespace, the header with the logo, the background treatment (flat, grid, noise, image, gradient the site already uses).
- **Visual motifs** — illustrations, screenshots, code blocks, diagrams, or icons that recur on the site and could carry to the card.
- **Type scale** — the hero heading's size and weight relative to body, line height, letter spacing, case.
- **Themes** — whether the site leads in light or dark. The card picks one ground; record both so variants can differ.

If the project has no UI, derive a neutral system from its README and brand assets, and say so in the report.

## 3. Diverge: variants

Pick N **variants** that differ in **layout and concept**, not just color. Good families, in order of preference:

- Hero echo — the site's own hero, reframed at 1200 × 630
- Big type — the title alone, set large in the display font
- Product shot — a framed screenshot or UI fragment of the product
- Split — copy on one side, visual or motif on the other
- Mark-led — the logo large, with a short tagline
- Pattern / motif — the site's background or illustration system as the stage
- Code or data — a snippet, command, or number that sums up the product

Name each variant ("A · Hero echo"), write a one-sentence thesis, and number it `A`…`F` so the user can refer to "C". Keep the copy true to the project: reuse its real title and description, or a tightened version, never invented claims or metrics.

## 4. Build each card

Draw every card as HTML/CSS with inline SVG, using the rules in [references/card-craft.md](references/card-craft.md). For each variant produce:

- **Full card** — exactly 1200 × 630, shown scaled to fit with its real size labelled, plus a small safe-area overlay toggle.
- **Share previews** — the same card inside mock unfurls for X (`summary_large_image`), LinkedIn, Slack, Discord, and iMessage, using the real title, description, and domain. These show the crop and what text the platform adds around the card.
- **Small size** — the card at about 300 px wide, to check that the headline still reads in a feed.
- **Square crop** (only if `twitter:card` is `summary` or the project targets it) — the centered square the platform keeps.

Color and type come only from the project's tokens and fonts. Use the project's real logo; if none exists, use the brand name set in the display font, never an invented mark.

## 5. Publish: every variant in one artifact

Publish all variants of a pass together in **one** artifact so they sit side by side and collect comments in one place. Never publish one artifact per variant.

- **Design canvas (preferred)** — call the artifact tool's `quickstart` with intent `design` and follow the Design type's instructions for its file format. Create one canvas titled `<Brand> social cards`. Then:
  - a first artboard `Current` with the existing card (or the no-image fallback), its tags, and the issues found in step 1;
  - one artboard per variant, titled `<letter> · <name>` (e.g. "B · Big type"), about 1440 px wide, fluid height;
  - each artboard holds: the variant name and thesis, the palette and fonts used, the full card, the five share previews in a row, and the small-size check;
  - a canvas note above the first artboard: `Social card: <Brand> · N variants · 1200 × 630`.
- **Single page (fallback)** — when no canvas type is available, publish one HTML page with a variant switcher (`#current`, `#a`, `#b`, …) in the toolbar, a "Preview in" platform selector, and a compare view that shows the current card and every variant in the same platform preview. Title it `<Brand> social cards`.
- **No artifact tool** — write the same single page to a scratch directory outside the project as `wireframe-og-<brand>.html` and open it locally (`open` / `xdg-open`).
- Never commit images, change meta tags, create branches, or open PRs unless the user asks.

## 6. Report the first pass

```markdown
**<Brand>** · <N> variants · 1200 × 630 · ground: <light/dark per variant> · fonts: <family>

**Open:** <the artifact URL or file path>

**Current card:** <one line — what exists, where it is set, the top issues>

| Variant | Thesis | Best for | Trade-off |
| --- | --- | --- | --- |
| A · Hero echo | … | … | … |

**Strongest:** <letter> (one line why)
**Assumptions:** <bullets — copy tightened, theme chosen, font fallback, focus page>
**Pick a variant by letter (e.g. "C"), mix (e.g. "A's layout with D's background"), or ask for another round.**
```

## 7. Iterate

Every change goes into the **same** artifact so its link stays stable.

- **"Refine C"** → add per-page versions (home, a docs or blog page with a long title, a short title), a dark and a light ground, and an `og:image:alt` text, as a new artboard titled "Iteration 2: C system". Do not touch the other variants.
- **"Mix A and D"** → a new variant `M1` that names what it took from each.
- **"More like B"** → N fresh variants in B's family that avoid layouts already shown.
- **Feedback on a detail** (headline size, logo position, background) → apply it to that variant and list the change in one line.
- When the user settles on a variant, offer a handoff that matches step 1's setup: the meta tags to set (`og:image`, `og:image:width`, `og:image:height`, `og:image:alt`, `twitter:card`, `twitter:image`), and either a static 1200 × 630 export or a generator template for the stack in use (for example `app/opengraph-image.tsx` with `next/og`). Write it to the repo only if asked.

## Quality bar before reporting

- [ ] The current card (or its absence) is shown and its issues are named, with file references
- [ ] Every variant is exactly 1200 × 630 and differs from the others in layout or concept
- [ ] Headline reads at 300 px wide, and nothing important sits outside the safe area
- [ ] Each variant appears in all five share previews with the real title, description, and domain
- [ ] Colors, fonts, and logo come from the project; copy comes from its real tags and README
- [ ] All variants sit in one artifact, each labelled and easy to compare
- [ ] Nothing committed, and no network access beyond the project's own font and image links
