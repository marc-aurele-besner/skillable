---
name: wireframe-redesign
description: >-
  Redesign an entire existing website or app as one clickable, multi-variant
  prototype published in a single artifact. Inventories every route, page,
  feature, role, and state of the current product, embeds its real content as
  sample data, then rebuilds the whole site in several distinct redesign
  directions that all share one hash router, so any page can be opened in any
  variant. A floating prototype toolbar switches variant, theme, signed-in role,
  and forced state (loading, empty, error), jumps to any page from a sitemap,
  and opens a side-by-side compare of the same page across variants. Use
  whenever the user wants to redesign, reskin, or rethink a whole site or app,
  explore several redesign directions for an existing product, or see every
  page and feature of their site reimagined before committing to a redesign.
  Also triggers on /wireframe-redesign with an optional site URL or path,
  variant count, and direction hints.
argument-hint: "[site-url-or-path] [variants=4] [direction hints]"
---

# Wireframe Redesign

Goal: show what the **whole** product could become — not one feature, every page — in several competing directions the user can click through, switch between on any page, and compare side by side. The redesign keeps every feature the product has today; only the presentation, information architecture, and interaction model change. Like `wireframe-feature`, the output is throwaway exploration: one artifact, never commits to the project.

## When to use

- "Redesign our site / app", "give me a few redesign directions for <product>"
- "What could <site> look like if we rebuilt it? Keep every page and feature."
- "Reimagine the whole dashboard, not just one screen"
- `/wireframe-redesign [url-or-path] [variants=N] [hints]`
- Not for a single new feature (use `wireframe-feature`), a token/style audit (use `extract-design-system`), or shipping production UI.

## Inputs

| Input | Default | Notes |
| --- | --- | --- |
| Target | current project | A repo path, or a public URL when there is no source. With source, read the code; a URL alone means crawling (see the inventory reference). |
| Variants | 4 | First pass. Clamp 2–5. Fewer than 2 is not a choice between directions. |
| Direction hints | none | "more editorial", "app-like", "keep the brand color"… Shape the variants; do not collapse them into one. |
| Scope | entire product | Every public, auth, signed-in, and admin page. Narrow only if the user explicitly says so. |

Do not run a questionnaire. Assume, then list assumptions in the report.

## 1. Inventory the product — every page, every feature

This is what separates a redesign prototype from a mood board: nothing the product does today may disappear. Build the inventory before designing anything; [references/site-inventory.md](references/site-inventory.md) says where to look per stack and how to crawl a URL.

Write a working **coverage matrix** with one row per route:

| Route | Page | Features on it | Roles that see it | States |
| --- | --- | --- | --- | --- |
| `/emoji/:slug` | Emoji detail | TL;DR, context meanings, platform renders, warnings, related, copy, share, favorite | all | loading, 404 |

Cover, at minimum:

1. **Routes** — every static and dynamic route (with one or two real slugs each), redirects, 404, and pages only reachable by link (reset password, shared result pages, legal).
2. **Features per page** — search and autocomplete, filters and sort, pagination, forms and their validation rules, uploads, copy/share, favorites, quotas and paywalls, streaming or async results, notifications, keyboard shortcuts.
3. **Roles and gates** — guest, signed-in tiers (free, pro…), admin; what each sees or is blocked from; usage limits.
4. **Global chrome** — header, nav labels and order, footer columns, mobile nav, theme switch, banners, cookie notice, sponsored slots.
5. **States** — loading, empty, error, success, rate-limited, permission-denied, long content.
6. **Content model** — entity types, fields, counts, and where the real content lives (seed files, JSON, MDX, CMS exports, DB fixtures).

The matrix becomes the prototype's **sitemap** (step 4) and the coverage check (step 6). If a route cannot be reproduced faithfully (a third-party checkout, an OAuth provider), keep the page and stub the hand-off with a clearly marked placeholder.

## 2. Capture the current design language and real content

- **Design language** — tokens and their names, themes and the switch mechanism, fonts, breakpoints, layout shell, component idioms, icon set, copy tone. If a published design system exists (e.g. from `extract-design-system`), start from it. The redesign may propose new values, but keeps the project's **token names** so the winning direction maps back onto the codebase. Comment proposed values as `/* proposed */` when they differ.
- **Real content** — export the product's actual content into one plain data object (`window.<APP>_DATA = {…}`) embedded in the page: entity lists with the fields pages need, real counts, a few full records for detail pages. Trim long lists to a representative slice but keep the true totals for counters. No customer data, no secrets, no network calls. Keep the whole artifact well under the 16 MB limit (aim for ≤ 3 MB).

## 3. Diverge: distinct redesign directions

Each variant is a whole-product concept, not a palette swap. Vary what matters for this product, for example:

- **Shell and IA** — marketing top nav vs. app shell with sidebar and ⌘K palette vs. editorial masthead; what is first-class in the nav.
- **Primary job on the home page** — search-first, tool-first, content-first, dashboard-first.
- **Content presentation** — dense grids vs. cards vs. long-form editorial; quick-view drawers vs. full pages.
- **Interaction model** — omnibox, wizard, inline editing, command palette, bottom tab bar on mobile.
- **Visual voice** — type pairing, radius, density, motion — within the token names.

Name each variant `<Letter> · <Name>` ("A · Omnibox", "B · Decoder studio", "C · Editorial", "D · Bento app") with a one-sentence **thesis**. Every variant implements **every** route and feature from the matrix; a variant may reorganize where a feature lives, but never drop it.

## 4. Build one prototype that holds every variant

One self-contained HTML file, vanilla JS and CSS (or a pinned CDN library the project already uses), no build step. The full harness pattern — router, state, render loop, toolbar, compare — is in [references/prototype-harness.md](references/prototype-harness.md). Requirements:

**Routing and variants**
- Hash routes `#/<variant>/<path>?<query>` mirror the real URL paths, so `#/c/emoji/skull` is the emoji page in variant C and switching variant keeps the current page and query.
- One shared **route table** and data layer; each variant supplies its own shell (`shellTop`, `shellApp`…) and, where its concept differs, its own page templates (`homeA`, `homeB`…). Share components otherwise and skin them with `body[data-v="<letter>"]` overrides on the same tokens.
- Every route from the matrix resolves in every variant; unknown paths render the variant's 404.

**Prototype toolbar** (floating, collapsible, visually outside the product)
- **Variant** buttons A–N plus the active variant's thesis.
- **Theme**: light / dark / system, applied via the project's mechanism and `prefers-color-scheme`.
- **User**: guest / each signed-in tier / admin, so gated pages and quotas are reachable without filling forms.
- **State**: live / loading / error / empty, forced across every page that loads data.
- **Simulate**: "next request fails", reset quota, reset all.
- **Page**: a jump-to select listing the whole sitemap (one entry per route in the matrix).
- **Compare**: side-by-side frames of the **current page** in every variant (iframes of `#/<v>/<path>?embed=1`, scaled, each fully interactive; one column on mobile). `embed=1` hides the toolbar.
- Minimized by default to one line naming the variant, so it never hides the design.

**Behaves like the product**
- Navigation, search with suggestions, filters and sort synced to the query string, forms with validation, disabled submit while saving, inline errors, success states, auth flows that set the role, dashboards that reflect actions taken (history, favorites, usage), admin create/edit with optimistic save.
- Simulated latency (300–1200 ms) with skeletons or spinners; streaming where the product streams.
- Modals, drawers, menus, palette, toasts; Esc closes, Enter submits, arrows move through lists, focus moves sensibly.
- Prototype state (theme, variant, role, history) persists in `localStorage` inside try/catch and renders correctly without it.

**Responsive and honest**
- Reproduce or deliberately redesign responsive behavior at ~375, ~768, and ≥1280 px: no horizontal scroll, touch targets ≥ 40 px, mobile nav per variant (drawer, tab bar…).
- Mark anything invented by the redesign (a new metric, a feature the product lacks) with a dotted underline and a `title` tooltip, so it is not mistaken for an existing capability.

## 5. Publish — one artifact

- Publish the single page as **one** artifact titled `<Product> redesign`, with the variant names in the description. A design canvas is the wrong shape for a whole site; use the single-page harness.
- No artifact tool: write `redesign-<product>.html` outside the project's tracked tree (scratch or temp directory) and open it locally.
- Never commit the prototype, create branches, or open PRs in the target project unless the user explicitly asks.

## 6. Verify coverage before reporting

- Walk the coverage matrix: every route opens in every variant (use the page jump or a headless browser loop over `#/<v>/<route>` when available — see the harness reference), with no console errors and no 404 fallthrough.
- Every feature in the matrix is reachable in each variant; every forced state renders on data pages; every role changes what it should.
- Theme switch repaints every surface; nothing hard-coded survives in either theme.
- Compare view loads all variants for a deep page (a detail page, not just home).

Fix gaps before reporting. If something is intentionally stubbed, list it.

## 7. Report the first pass

```markdown
**<Product> redesign** · <N> variants · <R> routes × <N> variants · themes: light + dark

**Open:** <artifact URL or file path>

| Variant | Thesis | Best for | Trade-off |
| --- | --- | --- | --- |
| A · Omnibox | … | … | … |

**Coverage:** <R> routes, <F> features, roles <list> — all in every variant. Stubbed: <list or "none">.
**Try:** <2–3 pages where the variants differ most, e.g. home, a detail page, the paywall> — open **Compare** on each.
**Assumptions:** <bullets>
**Pick one, mix ("C's typography with D's shell"), or ask for another round.**
```

## 8. Iterate in the same artifact

Every iteration republishes the **same** artifact so the link and the history of ideas stay put.

- **"Go with C" / "refine C"** → improve C in place across every page; leave the others untouched.
- **"Mix A and D"** → add a new variant letter (e.g. "E · D's shell + A's omnibox") naming what it took from each, with full route coverage.
- **"More ideas"** → new letters whose theses explicitly avoid the concepts already shown.
- **Page or feature feedback** → apply it to the chosen variant, list what changed in a line or two.
- **Handoff** when the user is happy: per route, the screens and states, which existing components each part maps to, new components and token changes needed, features moved between pages, and open questions — so implementation can start from it (e.g. via `spike-variants`). To keep the prototype in the repo as a standalone vanilla site under `.wireframe/`, use `save-wireframe`.

## Quality bar

- [ ] Coverage matrix built from the source (or a crawl) and every route appears in the page jump
- [ ] Every route and feature works in every variant; nothing from today's product is missing
- [ ] Real content embedded; no lorem ipsum, network calls, secrets, or customer data
- [ ] Variants differ in concept (shell, IA, primary job), not just color
- [ ] Toolbar switches variant (keeping the page), theme, role, and forced state; compare shows the current page in all variants
- [ ] Works at mobile, tablet, and desktop widths in light and dark
- [ ] Inventions marked; one artifact, under the size limit
