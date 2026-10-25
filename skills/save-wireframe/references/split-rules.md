# Split rules

How to cut a single-file wireframe into a vanilla site without changing what it does.

## Finding the pieces

| Piece | Where it is in the source | Where it goes |
| --- | --- | --- |
| Publish wrapper | A leading `<!doctype html><html><head>` with a tiny reset `<style>`, followed by a second `<!doctype html>` | Dropped |
| Font links | `<link rel="preconnect">`, `<link href="https://fonts.googleapis.com/…">` | Kept in `index.html` `<head>` |
| CSS | Every `<style>` block, in document order | `styles/NN-<section>.css` |
| Large data | A `<script>` that only assigns a big literal (`window.APP_DATA = {…}`), or a JSON `<script type="application/json">` | `data/NN-<name>.js` as `window.<NAME> = …;` (JSON scripts: read with `JSON.parse` in the same place the original did, now from the global) |
| Code | Remaining `<script>` blocks, in document order | `scripts/NN-<section>.js` |
| Inline handlers | `onclick="…"` attributes | Left as they are — they still work and moving them changes behavior |
| Body skeleton | Mount points (`#app`, `#proto`, `#toasts`) and static markup | `index.html` `<body>` |
| Inline images | `data:` URIs over ~4 KB in CSS or HTML | `assets/<name>.<ext>`, referenced relatively (from CSS: `../assets/…`) |

## Section boundaries

Cut at the source's own banner comments:

```text
/* ===== Tokens ===== */         → styles/01-tokens.css
/* ===== Base ===== */           → styles/02-base.css
/* ===== Controls ===== */       → styles/03-controls.css
/* ===== Prototype toolbar ===== */ → styles/NN-prototype.css
/* ================= DATA ================= */   → scripts/01-data-helpers.js
/* ================= ROUTER ================= */ → scripts/03-router.js
```

No banners? Cut at clear seams only — between top-level rule groups (CSS) or top-level function groups (JS) — and fall back to one `styles/main.css` and one `scripts/main.js` rather than guessing. Never cut inside a rule, an `@media` block, a function, or a statement.

Empty `<script></script>` placeholders are dropped. A file under ~20 lines merges into its neighbor.

## Why order is sacred

- CSS: later rules win at equal specificity; variant overrides (`body[data-v="c"] …`) and responsive rules depend on coming after the base.
- JS: classic scripts share one global scope and run in order; a function declared in file 5 is callable from file 3 only after file 5 has loaded — so code that runs immediately (top-level calls, `render()`) must stay after everything it uses, exactly as in the source.

## Lossless check

```bash
# from a scratch directory, with the original saved as original.html
bun -e '
const fs = require("fs");
const html = fs.readFileSync(process.argv[1], "utf8");
const dir = process.argv[2];
const pick = (re) => [...html.matchAll(re)].map(m => m[1]).join("\n");
const norm = (s) => s.replace(/\s+/g, " ").trim();
const cat = (sub) => fs.readdirSync(`${dir}/${sub}`).sort().map(f => fs.readFileSync(`${dir}/${sub}/${f}`, "utf8")).join("\n");
const css = pick(/<style[^>]*>([\s\S]*?)<\/style>/g);
const js = pick(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g);
console.log("css", norm(css) === norm(cat("styles")) ? "ok" : "MISMATCH");
console.log("js", norm(js) === norm(cat("data") + "\n" + cat("scripts")) ? "ok" : "MISMATCH");
' original.html .wireframe/<name>
```

Run it on the unwrapped document (wrapper removed). Adjust the data/scripts concatenation order to match the source if data was not first. Runtime stubs you added are excluded from the comparison.

## Load check (optional, Playwright)

```js
// bun or node, run from a scratch directory
const { chromium } = require('playwright');
const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));
page.on('console', m => m.type() === 'error' && errors.push(m.text()));
const base = 'file://' + require('path').resolve('.wireframe/<name>/index.html');
for (const hash of ['', '#/a/', '#/b/emoji', '#/c/nope/404']) {   // from wireframe.json routes and variants
  await page.goto(base + hash);
  await page.waitForTimeout(300);
}
console.log(errors.length ? errors : 'no errors');
await browser.close();
```

Repeat against `python3 -m http.server` (or `bunx serve`) to catch anything that only breaks over HTTP.
