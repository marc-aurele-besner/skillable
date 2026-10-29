# Brand extraction: where to look

Read the files that exist; skip the rest. Prefer source of truth (tokens, config) over compiled output. The goal is only what a logo needs: palette, display type, shape language, and existing marks.

## Palette and themes

| Stack | Look in |
| --- | --- |
| Tailwind v4 | `@theme { … }` in the global CSS (`app/globals.css`, `src/index.css`, `src/styles/*.css`) |
| Tailwind v3 | `tailwind.config.{js,ts,cjs,mjs}` → `theme.extend.colors`, `darkMode` |
| shadcn/ui | `components.json`, then `:root` and `.dark` variable blocks in the global CSS |
| CSS variables | `:root`, `.dark`, `[data-theme="…"]`, `@media (prefers-color-scheme: dark)` |
| Design tokens | `tokens.json`, `*.tokens.json`, `style-dictionary` config |
| MUI / Chakra / Mantine | `createTheme(...)`, `extendTheme(...)`, `createSystem(...)` palette blocks |
| Sass / Less | `_variables.scss`, `_tokens.scss`, `variables.less` |

Record the brand color, an accent, and the ink and ground values for **each** theme the app supports. Keep the project's token names (`--primary`, `brand-500`, `$accent`) so the artifact can cite them.

## Display type

- `next/font` imports in the root layout, `@font-face` rules, `fonts.googleapis.com` links in `index.html` or the document head.
- The `fontFamily` for headings (not body) is the wordmark's family. Note its weight, letter spacing, and case style (for example, a heading that is always uppercase).

```bash
rg -n -g '!node_modules' -e 'next/font' -e '@font-face' -e 'fonts.googleapis' -e 'fontFamily' .
```

## Shape language

- Radius tokens: `--radius`, `rounded-*` in Tailwind config, `borderRadius` in theme objects.
- Icon stroke width in the icon set, if the project uses one (`lucide-react` defaults to 2px on 24px, for example).
- Whether the UI reads rounded, sharp, or soft. This decides the corner treatment of geometric marks.

## Existing marks

Look for brand assets that already exist. These are the strongest signal for what the logo should feel like.

```bash
rg --files -g '!node_modules' -g '*logo*' -g '*favicon*' -g '*icon*' -g '*apple-touch*' -g '*manifest*'
```

- `public/`, `static/`, `assets/`, `src/assets/`, `app/` icon files (`icon.svg`, `apple-icon.png`, `favicon.ico`).
- `manifest.json` or `site.webmanifest` → `theme_color`, `background_color`, icon sizes.
- Inline SVG logos in the header or footer component (`Logo.tsx`, `Logo.vue`, `Brand.svelte`).

If a current mark exists, note its colors and construction. Show it once as a "Current" reference, and explain how each direction relates to it: evolve it, contrast with it, or replace it.

## Voice and vocabulary

- The README's first paragraph and the `package.json` `description`.
- Page titles and hero copy. Keep the wordmark spelled exactly as the brand writes it, including case and any internal capital letters.

## When there is no project look

No UI, no tokens, no assets: derive a neutral system from the idea. Use one ink (near-black), one ground (off-white), and one accent that suits the keywords. Use a common sans for the wordmark, and say in the report that the palette and type are assumed.
