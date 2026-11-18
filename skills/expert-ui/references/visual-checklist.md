# Visual design checklist

Load this file in step 4 of `SKILL.md`, before writing any finding. Walk only the dimensions the scope touches. Every item lists what to look for, how to confirm it, and what is **not** a finding.

The bar for every item: **name the screen, the element, and what a user sees wrong.** "Could be more modern" is not a finding.

## Contents

1. Visual hierarchy
2. Spacing and alignment rhythm
3. Typography scale
4. Color and contrast
5. Design tokens and component consistency
6. Responsive breakpoints
7. Light/dark theme parity
8. Iconography
9. Motion
10. State styling (hover, focus, disabled, loading, empty, error)
11. Framework-specific traps
12. What not to report

---

## 1. Visual hierarchy

Look for:

- **One primary action per view.** Two or more solid, brand-colored buttons competing in the same region; a destructive action styled as the primary one.
- **Squint test.** Blur the screenshot mentally (or zoom out to 25 %): the first thing the eye lands on should be the page's purpose (title, key number, primary CTA), not a decorative image, a badge, or the nav.
- **Heading levels that read as levels.** An `h2` visually larger or bolder than the `h1`; section titles the same size and weight as body text so sections blur together.
- **Weight used for meaning.** Bold, color, and size used on so many elements that nothing stands out ("everything is emphasized").
- **Density mismatch.** One card crammed and the next airy; a dense data table next to a hero-sized empty state.
- **Grouping by proximity.** Labels closer to the previous field than to their own input; card content spaced more tightly to the next card than within itself.

Confirm: screenshot at the default desktop width and at 375 px; compare sizes from computed styles (DevTools, `getComputedStyle`) rather than guessing from the image.

Not a finding: a deliberate editorial layout where a large image leads, if the CTA is still clear.

## 2. Spacing and alignment rhythm

Look for:

- **Off-scale values.** The project has a spacing scale (4/8-based, Tailwind defaults, `--space-*`) and a component uses `13px`, `7px`, `p-[13px]`. Run `scripts/ui_scan.py scan` and look at the most common `spacing_px` and `tw_arbitrary` values.
- **Inconsistent gutters.** Page padding differs between routes that share a shell; cards in a grid with unequal gaps; a section with 24 px top and 64 px bottom for no reason.
- **Broken alignment.** Text in a card not aligned with the heading above it; icon and label misaligned on the baseline (icon centered on the box, text on the baseline); form labels and inputs on different left edges; a button row whose right edge does not match the content edge.
- **Optical vs. mathematical centering.** A play icon or chevron that looks off-center inside a circular button because the glyph has asymmetric whitespace.
- **Collapsing or doubled margins.** `margin-bottom` on the last child adding extra space inside a card; stacked components each adding their own outer margin.
- **Vertical rhythm.** Line-height and block spacing that do not relate (paragraph spacing smaller than line spacing; random gaps between headings and body).

Confirm: inspect computed `margin`/`padding`/`gap`; overlay a grid or measure two edges in a screenshot. Cite the source line that sets the value.

Not a finding: a one-pixel difference that is a sub-pixel rounding artifact; spacing the project's own scale allows.

## 3. Typography scale

Look for:

- **Too many sizes.** More than ~6–8 distinct font sizes in the UI, or sizes like `15px`, `17px`, `19px` mixed with a modular scale. `ui_scan.py scan` lists `font_size_px` frequency.
- **Body size below 16 px on mobile** for reading text (labels and captions may be smaller; inputs below 16 px also zoom on iOS Safari).
- **Line length.** Paragraphs wider than ~75 characters (`max-width` missing on prose), or narrower than ~45 in a main column.
- **Line height.** Body below ~1.4 or headings above ~1.3 (loose, floating headings); tight line height on multi-line buttons.
- **Weight and family sprawl.** More than two families, or weights loaded but unused (also a perf cost); a fallback stack that shifts layout when the web font loads (`font-display`, `size-adjust`).
- **Truncation.** Titles clipped with no ellipsis or tooltip; ellipsis applied to text that is the only identifier of a row.
- **Numerals.** Tables, prices, and timers without `font-variant-numeric: tabular-nums`, so digits jitter as values change.
- **Case and tracking.** All-caps labels without extra letter-spacing; letter-spacing on lowercase body text.

Confirm: computed `font-size`, `line-height`, `font-family` on real elements; count distinct sizes from the scan or from the token file.

Not a finding: a display size used once for a hero headline, if it belongs to the scale.

## 4. Color and contrast

Look for:

- **Text contrast** below WCAG AA: 4.5:1 for body text, 3:1 for large text (≥ 24 px, or ≥ 18.66 px bold). Placeholder text, disabled-looking secondary text, text on images, and text on brand-colored buttons are the usual failures.
- **Non-text contrast** below 3:1: input borders, focus rings, icon-only buttons, chart lines, toggles in the off state.
- **Color as the only signal.** Error fields marked only by a red border; status dots without a label or icon; links in body text distinguished only by hue.
- **Palette sprawl.** Many near-identical grays or blues (`#333`, `#343434`, `#3a3a3a`) instead of a ramp; `ui_scan.py scan` shows the most common color literals.
- **Semantic misuse.** Brand color used for errors, red used for a non-destructive primary action, success green used for neutral information.
- **Text over images** without a scrim or text-shadow, so contrast depends on the photo.

Confirm: always compute ratios with `python3 -I scripts/ui_scan.py contrast <fg> <bg>`; never estimate contrast by eye. For alpha colors pass the real background behind it. Check both themes.

Not a finding: decorative text or logos (exempt from WCAG contrast); disabled controls (exempt, though worth a note if they are unreadable).

## 5. Design tokens and component consistency

Look for:

- **Hard-coded values next to tokens.** A component uses `#2563eb` while `--color-primary` holds the same value; `border-radius: 6px` while the scale defines `--radius-md: 8px`. Cite both the literal and the token it should use.
- **Parallel components.** Two button implementations (`Button.tsx` and a styled `<a>` in `Hero.tsx`) that drift in radius, height, or padding; three different card shadows.
- **Radius, border, and shadow consistency.** Mixed radii in one surface (8 px card holding 2 px inputs and pill buttons) without a deliberate system.
- **Elevation and z-index.** Raw `z-index: 9999`; modals under sticky headers; dropdowns clipped by `overflow: hidden` parents.
- **Overrides fighting the system.** `!important`, deep selectors into library components, inline styles that override token-driven classes.

Confirm: find the token source (CSS custom properties, `tailwind.config.*`, `theme.ts`, SCSS variables, a design-system package) and show that the literal duplicates or contradicts it. If `extract-design-system` produced a drift report, use it as the candidate list and verify each entry.

Not a finding: literals inside the token file itself; one-off values in third-party embeds you do not own; a value with a comment explaining why it is off-scale.

## 6. Responsive breakpoints

Look for:

- **Horizontal scroll** at 320–375 px (an element with a fixed width, a long unbroken string, a wide table without its own scroll container).
- **Breakpoint gaps.** Layout correct at 375 and 1440 but broken at 768–1024 (tablet, split-screen): nav overlapping logo, two-column cards squeezed to 200 px.
- **Touch targets** below 44×44 CSS px (24×24 is the WCAG 2.2 AA minimum, 44 is the comfortable target) on mobile, or targets closer than 8 px apart.
- **Content reflow.** Important content hidden on mobile with `display: none` rather than reflowed; sidebars that push content off-screen.
- **Images.** Stretched or squashed (`object-fit` missing), missing aspect ratio (layout shift), art direction that crops the subject on mobile.
- **Viewport units.** `100vh` hero cut off by mobile browser chrome (use `100dvh`/`svh`); content under notches (safe-area insets) in standalone mode.
- **Breakpoint inconsistency.** Components using different breakpoint values (`767px`, `768px`, `48em`) than the project's defined set.

Confirm: screenshots at 320, 375, 768, 1024, and 1440 px wide, plus 200 % zoom on desktop. Check `document.documentElement.scrollWidth > innerWidth` for overflow.

Not a finding: a layout that changes between breakpoints by design, as long as nothing overlaps, clips, or overflows.

## 7. Light/dark theme parity

Look for:

- **Missing overrides.** A component with hard-coded light colors that stays white in dark mode; shadows that vanish on dark backgrounds with no border to replace them.
- **Contrast that only passes in one theme.** Re-run the contrast check for every pair in the other theme.
- **Inverted semantics.** Elevation in dark mode should usually read lighter, not darker; brand colors that are too saturated on dark surfaces.
- **Assets.** Logos, illustrations, and screenshots without a dark variant (black logo on a near-black background); SVG icons with hard-coded `fill="#000"` instead of `currentColor`.
- **Theme switching.** Flash of the wrong theme on load (theme applied after hydration); `color-scheme` not set, so form controls and scrollbars stay light; `<meta name="theme-color">` not matching each theme.
- **Third mode.** The UI respects `prefers-color-scheme` but an explicit user toggle does not override it (or the reverse).

Confirm: render both themes (toggle, `prefers-color-scheme` emulation, or a `data-theme` attribute) and compare the same screen side by side.

Not a finding: a product that intentionally ships a single theme. Say so once and move on.

## 8. Iconography

Look for:

- **Mixed icon sets.** Outline and filled icons from different libraries in the same toolbar; different stroke widths (1.5 vs 2 px) side by side.
- **Size and alignment.** Icons not on the type's optical size (16 px icon next to 14 px text is fine; 24 px next to 12 px is not); icons not vertically centered with their label.
- **Meaning.** Icon-only buttons with ambiguous glyphs and no visible label or tooltip; the same icon meaning two things in different places.
- **Color.** Icons that do not inherit text color (`currentColor`) and so break in dark mode or hover states.
- **Accessibility of the visual.** Decorative icons not hidden from assistive tech, meaningful icon-only buttons without an accessible name (report the visual issue here; deep a11y belongs to a dedicated audit).

Confirm: list the icon imports (`lucide-react`, `@heroicons/*`, `react-icons/*`, local SVGs) and see whether more than one set is in use.

## 9. Motion

Look for:

- **Motion without purpose.** Animations that do not explain a change (where something came from, what changed, what to do next) and only delay the user.
- **Duration and easing.** UI transitions over ~400 ms for small elements; linear easing on movement; entrance and exit with the same duration (exits should be faster).
- **Reduced motion.** No `prefers-reduced-motion` handling for parallax, large slides, autoplaying carousels, or looping background video.
- **Animating layout properties** (`width`, `height`, `top`, `left`) instead of `transform`/`opacity`, causing jank and layout shift.
- **Inconsistency.** Each component with its own duration and easing instead of shared motion tokens.
- **Loading motion.** Spinners for content that would be clearer as a skeleton matching the final layout; skeletons that do not match the final layout and cause a jump.

Confirm: read the transition/animation declarations and the motion library config (`framer-motion`, `motion`, `@vueuse/motion`, GSAP); record a short screen capture if the issue is timing.

Not a finding: a brand moment (a hero animation) that respects reduced motion and does not block interaction.

## 10. State styling

Look for:

- **Focus visibility.** `outline: none` with no replacement; focus ring that fails 3:1 against the background; focus styles that differ per component.
- **Hover-only affordances.** Actions revealed only on hover (invisible on touch).
- **Disabled vs. loading vs. active.** A loading button that looks identical to a disabled one; selected tab indistinguishable from hover.
- **Empty, error, and loading states** that fall back to unstyled defaults (bare "No data", browser-default error text) while the rest of the UI is polished.
- **Validation.** Error text far from its field, or styled with a color only.

## 11. Framework-specific traps

- **Tailwind:** arbitrary values (`text-[13px]`, `bg-[#123456]`) that bypass `theme`; `dark:` variants missing on some components; `@apply` duplicating a component class; classes built by string concatenation that the JIT never sees (style silently missing).
- **CSS Modules / SCSS:** variables defined per file instead of shared; `:global` overrides into third-party components.
- **CSS-in-JS (styled-components, Emotion, Stitches, vanilla-extract):** theme object present but components read literals; theme provider missing on a portal (modals rendered unthemed).
- **Component libraries (MUI, Chakra, Mantine, shadcn/ui, Radix themes):** `sx`/`style` overrides that fight the theme; local copies of shadcn components that drifted from the shared ones.
- **Next.js / Astro / SvelteKit:** global CSS imported per page producing order-dependent styling; `next/font` declared but a different family used in CSS.
- **Native mobile / React Native:** `StyleSheet` literals instead of a theme; platform font scaling (`allowFontScaling`) not considered for layout.

## 12. What not to report

- Personal taste with no user-visible cost ("I would use a warmer gray").
- Re-designs. A finding fixes a defect in the current design language; it does not propose a new one. If the whole direction is the problem, say so once in the summary and point at `wireframe-redesign`.
- Flow and task logic (wrong step order, confusing copy, missing confirmation) — that is `expert-ux`.
- Performance metrics beyond what a visual issue causes (that is `audit-web-vitals`), SEO metadata (`optimize-seo-aeo`), and full accessibility audits beyond contrast, focus visibility, and target size.
- Rules the project's linter or stylelint config already enforces.
- Values the project's own design system sanctions, even if you would pick differently.
