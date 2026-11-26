---
name: extract-design-system
description: >-
  Read a project's design language from source, tokens, light/dark themes,
  typography, spacing, layout shell, breakpoints, component idioms, icons,
  motion, and copy tone, and publish it once as a living design-system
  artifact (a browsable token and component gallery in every theme), plus a
  short drift report of hard-coded values that bypass the tokens. Other skills
  such as wireframe-feature can then reuse the published system instead of
  re-extracting it. Use whenever the user wants to document,
  extract, audit, or visualize their app's design system, build a style guide or
  component gallery from the codebase, or prepare a reusable design reference
  for wireframes, decks, or landing pages. Also triggers on
  /extract-design-system with an optional focus.
argument-hint: "[focus=tokens|components|all]"
---

# Extract Design System

Goal: turn the design language that is scattered across a codebase into one page anyone can open, every token with its value per theme, every component idiom rendered live, and the rules that make the app look like itself. Extract once, reuse everywhere: wireframes, decks, landing pages, and onboarding all read from the same published system.

## When to use

- "Document / extract / visualize our design system"
- "Build a style guide or component gallery from the code"
- "Which colors and spacing do we actually use? Where do we bypass the tokens?"
- Before a run of `wireframe-feature`, so every wireframe starts from the same reference
- `/extract-design-system [focus=tokens|components|all]`
- Not for designing a *new* visual identity (use frontend-design) or changing the project's styles.

## Inputs

| Input | Default | Notes |
| --- | --- | --- |
| Focus | `all` | `tokens` = foundations only; `components` = foundations + gallery; `all` adds layout shell, patterns, and drift report. |
| Project | current repo | Monorepo: ask which app if several have their own UI, or pick the one with the most UI code and say so. |

Do not run a questionnaire. Note assumptions in the report.

## 1. Inventory in parallel

Read the sources of truth, not compiled CSS. [references/design-extraction.md](references/design-extraction.md) lists where to look per stack.

When the agent can run subagents (e.g. Claude Code's Agent tool), split the reading into parallel read-only passes and merge the results, each returns a structured note, not file dumps:

1. **Foundations**, color tokens per theme and the theme-switching mechanism, typography (families, sources, scale, weights, line heights), spacing scale, radii, shadows, borders, z-layers, breakpoints, motion (durations, easings).
2. **Components**, the UI kit directory (`components/ui`, `packages/ui`…): each component's variants, sizes, and states; the icon set; empty, loading, error, and toast idioms.
3. **Shell and patterns**, root layout, navigation (real labels and order), page header, content width, responsive behavior per breakpoint, forms, tables vs. cards, dialogs and drawers.
4. **Voice**, copy tone from real UI strings (buttons, empty states, errors): sentence vs. title case, person, terminology for core entities.

Without subagents, do the same passes one after another.

## 2. Normalize

Build one model of the system, keeping the **project's own names**:

- Tokens as `name → value per theme`, grouped (color / type / space / radius / shadow / motion / breakpoint). Resolve aliases (`--primary: var(--blue-600)`) but show the chain.
- Semantic vs. primitive tokens: mark which ones components actually reference.
- Components as `name → variants × sizes × states`, with the source path of each.
- A short **rules** list stated as do/don't, derived from the code ("Primary buttons are always full-width on mobile", "Destructive actions confirm in a dialog, never inline").

If the project has only one theme, document only that one. If it has no real token layer (raw hex in components), say so and present the de-facto palette sorted by usage count.

## 3. Detect drift

Search for values that bypass the system and count them per file:

```bash
# Hard-coded colors in components and styles (adjust globs per stack)
rg -n -g '!node_modules' -g '!*.svg' -g '!**/tokens*' -e '#[0-9a-fA-F]{3,8}\b' -e 'rgba?\(' -e 'hsla?\(' src app components packages 2>/dev/null
# Arbitrary Tailwind values
rg -n -g '!node_modules' -e '\[(#|[0-9]+px)' src app components 2>/dev/null
```

Report the top offenders (file, count, nearest token) and near-duplicate tokens (two grays within a few ΔE, spacing values off the scale). Do **not** fix them in this skill, list them so the user can decide.

## 4. Build the design-system page

One self-contained HTML page (no build step, no network calls except fonts and pinned CDN libraries):

- **Tokens on `:root`** with the project's names, second theme under the project's own mechanism (`.dark`, `[data-theme="dark"]`…) and `prefers-color-scheme` by default, plus a visible **theme toggle**.
- **Foundations**: color swatches (name, value per theme, contrast ratio against its usual background, and a pass/fail flag at WCAG AA), type scale specimens, spacing and radius rulers, shadow tiles, motion demos, breakpoint table.
- **Components**: each component rendered live in every variant, size, and state (hover/focus/disabled/loading/error), with its source path and usage notes. Recreate them in plain HTML/CSS with the extracted tokens; they must look like the real ones.
- **Shell and patterns**: the layout shell at mobile and desktop widths, form, table/list, dialog, empty/loading/error patterns, with the real nav labels.
- **Voice**: tone rules and before/after copy examples.
- **Drift**: the findings from step 3.
- A sticky in-page nav and a search box that filters tokens and components.
- Responsive: no horizontal scroll at 375 px.

## 5. Publish and record

- **Artifact-capable agent** (e.g. Claude Code with an artifact tool): if the agent offers a **Design System** artifact type, create the system from that type and fill it with the extracted foundations and components; otherwise publish the page from step 4 as an artifact titled `<Project> Design System`. Republish to the same URL on later runs so links stay stable.
- **Otherwise:** write `design-system-<project>.html` outside the tracked tree (a scratch/temp directory) and open it locally.
- **Record the location** so other skills find it: offer to add one line to the project's agent instructions file (`CLAUDE.md`, `AGENTS.md`, or `.cursor/rules`), e.g. `Design system: <url> (generated by extract-design-system on <date>)`. Only write it when the user agrees, and commit it only if they ask.

## 6. Report

```markdown
**<Project> design system** · themes: <list> · <N> tokens · <M> components · <link>

**Foundations:** <one line each: palette, type, spacing, radius, motion, breakpoints>
**Theme mechanism:** <e.g. next-themes, class="dark" on <html>>
**Drift:** <K> hard-coded values in <F> files, top 3: <file (count) → nearest token>
**Contrast:** <pairs failing WCAG AA, or "all pass">
**Assumptions:** <bullets>
**Reuse:** wireframe-feature reads this system when it is recorded in <file>.
```

## 7. Refresh

On a later run, diff against the published version: list added, removed, and changed tokens and components, then republish in place. Never create a second artifact for the same project unless asked.

## Quality bar before reporting

- [ ] Every token shown with the project's own name and its value in every theme
- [ ] Theme toggle switches every surface; no hard-coded colors in the page itself
- [ ] Components rendered live in all their variants and states, each with a source path
- [ ] Drift findings cite files and counts; nothing in the project was modified
- [ ] No secrets, internal URLs, or real user data in the page
