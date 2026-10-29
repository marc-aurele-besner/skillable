# Logo craft: marks, lockups, and SVG rules

Rules for drawing the 8 logos in each direction so they are comparable, legible, and reusable. They apply to the artifact's inline SVG.

## Mark construction

- **Grid** — draw on a `viewBox="0 0 64 64"` grid. Keep a 4-unit safe margin, so the live area is 56 × 56.
- **Feature size** — no feature thinner than 4 units (about 1 px at 16 px). Strokes are 4–6 units in a single weight per mark.
- **Shapes** — `rect`, `circle`, `ellipse`, `line`, `polygon`, `path`. No `<image>`, no `<text>` inside the mark, no `<filter>`, no `<mask>` unless the mask is the concept.
- **Corners** — take the project's radius token as a ratio of its UI element size, then reuse that ratio for the mark's corners. Sharp UI gets sharp corners; soft UI gets rounded ones.
- **Color** — `fill="currentColor"` or `stroke="currentColor"` on the mark, with the token value set on a wrapper `color`. Two colors at most: ink and accent. Never a gradient, shadow, or opacity fade used as a color.
- **Negative space** — when the concept uses counters or cut-outs, draw them with `fill-rule="evenodd"` or a path that goes the other way. Do not use a mask.

## Variety inside a direction

Each direction's 8 logos must each use a different construction. Use a checklist as you draw:

| Construction | Example |
| --- | --- |
| Letterform | a single letter or pair, redrawn as geometry |
| Enclosure | the symbol sits inside a circle, square, or badge |
| Counter / negative space | the meaning sits in the gap |
| Module / grid | squares or dots on a small lattice |
| Metaphor | an object from the idea, reduced to 2–3 shapes |
| Abstract stroke | one continuous line or arc system |
| Split / overlap | two shapes that meet or overlap |
| Stacked units | repeated shape with step or offset |

## Legibility tests

Every mark must pass these before it appears on a card:

- **One color** — all ink, no accent, still reads.
- **Reversed** — the light version on the dark tile still reads, with no outline added to fake contrast.
- **16 px** — the mark still reads at favicon size. If it does not, simplify it.
- **Contrast** — the mark against its tile reaches at least 3:1 (non-text contrast).

## Lockups

Measured in units of `H`, the height of the mark.

- **Horizontal** — mark on the left, wordmark on the right. Gap `0.25H`. The wordmark's cap height is about `0.45H`, centered on the mark's optical middle. Left-align to the mark's edge.
- **Stacked** (added later, in iteration) — mark centered above the wordmark. Gap `0.3H`. The wordmark's width is about `2.5H`–`3H`, centered.
- **Clear space** — keep at least `0.5H` free on every side of the lockup.

The wordmark uses the project's display family and weight. Its case follows the brand's own spelling. Load the font through the project's own link. If a font is not loadable, fall back to the closest system family and name it in the report.

## Wordmark in SVG

The canvas artboard renders lockups as HTML with inline SVG for the mark, so the text stays live and uses the page's font. Use an element like:

```html
<div style="display: flex; align-items: center; gap: 0.25em; font-family: 'Inter', sans-serif; font-weight: 700; letter-spacing: -0.02em">
  <svg viewBox="0 0 64 64" width="48" height="48" role="img" aria-hidden="true" style="color: #1B1B1A">…</svg>
  <span style="font-size: 2.6rem; line-height: 1; color: #1B1B1A">Brand</span>
</div>
```

The `aria-hidden` on the mark is for a decorative lockup. A logo that stands alone on its own (the mark card) gets `role="img"` with a `<title>` child naming the logo, such as `<title>Brand, mark B5</title>`.

## Accessibility

- Name every logo: `<title>` inside the SVG, or `aria-label` on the wrapper.
- Keep the wordmark as real text, so it can be read and searched.
- Do not put information only in color. Light and dark tiles must both be readable without relying on hue.

## What not to draw

- Emoji, clip art, stock icons, or someone else's logo or trademark.
- Anything that reads as a real brand's existing mark.
- Gradient washes, glossy highlights, 3D bevels, and drop shadows.
- Text that is smaller than 12 px in the rendered output.
