---
name: wireframe-logo-design
description: >-
  Turn a logo idea into several logo directions, each a set of 8 logo concepts
  shown as a standalone mark and a horizontal lockup (mark plus wordmark), built
  from the current project's own colors, fonts, radii, and light/dark themes.
  Publishes every direction together in one Design canvas (one artboard per
  direction) or, without a canvas type, a single fallback page. Use whenever the
  user wants to design, sketch, explore, or mock up a logo, app icon, mark,
  wordmark, or lockup for their product, compare logo directions, or see a logo
  set in their app's look. Also triggers on /wireframe-logo-design with the idea
  and an optional direction count.
argument-hint: "<logo-idea> [directions=3]"
---

# Wireframe Logo Design

Goal: take a logo idea and produce comparable logo directions that look like they belong to this product. Each direction is a set of 8 logos; each logo is a mark and a lockup drawn in the project's own palette and type. Logo work here is exploration: it lives in the artifact, never as a commit in the project.

## When to use

- "Design a logo for this app", "sketch a few logo directions for X"
- "Make an app icon and wordmark that fit our theme"
- "Show me logo options in our colors and fonts"
- Refining a direction into final assets (see step 7)
- `/wireframe-logo-design <idea> [directions=N]`
- Not for shipping logo files to the repo, and not for a full brand guideline (use `extract-design-system` for the system itself).

## Inputs

| Input | Default | Notes |
| --- | --- | --- |
| Logo idea | required | From the arguments or the conversation. If absent, ask one short question. |
| Brand name | project name | From `package.json` `name`, the README title, or the app's `<title>`. |
| Directions | 3 | Clamp 1–4. Each direction always holds exactly 8 logos. |
| Current logo | auto-detected | If the project already ships a logo or app icon, show it once as a reference. |

Do not run a questionnaire. Fill gaps with sensible assumptions and list them in the report.

## 1. Read the project's look

Follow [references/brand-extraction.md](references/brand-extraction.md). If the project's agent instructions point to a published design system (from `extract-design-system`), start from it and confirm only what the logo needs. Capture into a short working note:

1. **Palette** — a brand/primary color, an accent, and the ink and ground for each theme (light and dark). Use the project's token names.
2. **Type** — the display family and weight used for headings, plus where it loads from. The wordmark uses this.
3. **Shape language** — corner radius token, stroke weight of icons, whether the UI is rounded, sharp, or soft.
4. **Existing marks** — favicon, app icon, logo files, and their colors.
5. **Voice** — the product's one-line description and tone, so the concepts fit its vocabulary.

If the project has no UI yet, derive a neutral system from its brand assets or the idea itself, and say so in the report.

## 2. Develop the idea

Write down, briefly:

- **Name** — the wordmark text, as the brand writes it.
- **What it is and who it is for** — one sentence.
- **Keywords** — 3–5 words that should be felt (e.g. "quick, precise, friendly").
- **Metaphors to draw on** — objects, letters, and symbols that come from the idea itself.
- **Clichés to avoid** — globes, rockets, lightbulbs, generic gradients, and anything a competitor already owns.

## 3. Diverge: directions and their eight logos

Pick N **directions** that differ in **form**, not just color. Good families, in order of preference:

- Monogram / letterform
- Geometric construction (circle, square, triangle, grid)
- Negative space or counter-form
- Enclosed emblem or badge
- Pictogram from a metaphor in the idea
- Abstract glyph built from strokes

Name each direction ("A · Geometric monogram") and write a one-sentence thesis.

Each direction gets **exactly 8 logos**. Within a direction, no two logos share the same construction; vary the metaphor, the enclosure, or the letterform. Every logo is numbered `A1`…`A8`, `B1`…`B8`, so the user can refer to "B5". Give each logo a short name and one-line rationale.

## 4. Build each logo: mark and lockup

Draw every logo as inline SVG using the rules in [references/logo-craft.md](references/logo-craft.md). For each of the 8 logos produce:

- **Mark** — a symbol-only SVG (`viewBox="0 0 64 64"`), shown on a light tile and on a dark tile.
- **Horizontal lockup** — the mark beside the wordmark, in the project's display font, on a light tile.

Color comes only from the project's tokens: ink on light, the light ground or accent on dark. No new hues. Keep every direction on the same palette so the comparison is about form.

If the project has an existing logo, show it once in the header of the first artboard, labelled "Current", for comparison.

## 5. Publish: every direction in one artifact

Publish all directions of a pass together in **one** artifact so they sit side by side and collect comments in one place. Never publish one artifact per direction.

- **Design canvas (preferred)** — call the artifact tool's `quickstart` with intent `design` and follow the Design type's instructions for its file format. Create one canvas titled `<Brand> logo directions`. Then:
  - one artboard per direction, titled `<letter> · <name>` (e.g. "A · Geometric monogram"), sized for a desktop page (about 1440 px wide, fluid height);
  - header strip: the direction name, the thesis, and the palette as swatches taken from the tokens;
  - a 4 × 2 grid of logo cards. Each card holds the number and name (`A1 · Stacked arc`), the light mark tile, the dark mark tile, the horizontal lockup tile, and the one-line rationale;
  - a canvas note above the first row: `Logo: <Brand> · N directions × 8`.
- **Single page (fallback)** — when no canvas type is available, publish one HTML page with a direction switcher (`#a`, `#b`, …) in the toolbar, the same card grid, and a side-by-side compare view at desktop width. Title it `<Brand> logo directions`.
- **No artifact tool** — write the same single page to a scratch directory outside the project as `wireframe-logo-<brand>.html` and open it locally (`open` / `xdg-open`).
- Never commit logo files, create branches, or open PRs unless the user asks.

## 6. Report the first pass

```markdown
**<Brand>** · <N> directions × 8 logos · themes: light + dark · palette: <token names>

**Open:** <the artifact URL or file path>

| Direction | Thesis | Best for | Trade-off |
| --- | --- | --- | --- |
| A · Geometric monogram | … | … | … |

**Strongest per direction:** A3, B5, C1 (one line each why)
**Assumptions:** <bullets — palette and font guessed, brand name, wordmark case>
**Pick a logo by number (e.g. "B5"), mix (e.g. "A3's mark with C7's type"), or ask for another round.**
```

## 7. Iterate

Every change goes into the **same** artifact so its link stays stable.

- **"Refine B5"** → add a stacked lockup, a monochrome version, a 16/32 px favicon, and a 180 px app icon on the chosen logo, as a new row titled "Iteration 2: B5 system". Do not touch the other logos.
- **"Mix A3 and C7"** → a new logo `M1` that names what it took from each, in a new row titled "Iteration 2: mix".
- **"More like B"** → 8 fresh logos in direction B that avoid constructions already shown, added as a new row.
- **Feedback on a detail** (a color, a letter, the wordmark weight) → apply it to that logo and list the change in one line.
- When the user settles on a logo, offer a short handoff: the SVG markup for the mark and lockups, the font to load, and the tokens each color maps to.

## Quality bar before reporting

- [ ] Every direction holds exactly 8 logos, each with a mark and a horizontal lockup
- [ ] Logos within a direction differ in construction, not only in size or color
- [ ] Colors and fonts come from the project's tokens; no new hues or stray fonts
- [ ] Each mark works in one color, on light and on dark, and at 16 px
- [ ] Marks are plain vector shapes: no gradients, shadows, filters, emoji, or raster images
- [ ] All directions sit in one artifact, each labelled and easy to compare
- [ ] Nothing committed, and no network access beyond the project's own font link
