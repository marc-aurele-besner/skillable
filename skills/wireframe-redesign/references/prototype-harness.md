# Prototype harness: one page, every variant, every route

A proven shape for the single-file redesign prototype. Adapt names to the product; keep the structure.

## File layout

```html
<body data-v="a">
  <div id="app"></div>          <!-- product: shell + page + overlays -->
  <div id="proto" class="proto"></div>  <!-- prototype toolbar, outside the product -->
  <div id="toasts" aria-live="polite"></div>
  <script>window.APP_DATA = { /* real, trimmed content + true counts */ };</script>
  <script>/* data helpers → state → router → shells → pages → toolbar → events */</script>
</body>
```

CSS order: tokens on `:root` (project token names) → dark values under `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {…} }` and `:root[data-theme="dark"] {…}` → base and shared components → per-variant overrides with `body[data-v="b"] .card {…}` → responsive rules → toolbar and compare styles (fixed neutral colors, independent of the product theme).

## Variants

```js
var VARIANTS = {
  a: {name: 'A · Omnibox', thesis: 'One smart box does everything…'},
  b: {name: 'B · Decoder studio', thesis: 'Tool-first two-pane home…'},
  c: {name: 'C · Editorial', thesis: 'Magazine-grade masthead…'},
  d: {name: 'D · Bento app', thesis: 'App shell with sidebar and ⌘K…'}
};
```

Pages share one function per route; where a variant's concept differs, branch inside it (`R.v === 'c' ? homeC() : …`). Shells differ per variant (top nav vs. sidebar app shell vs. masthead), each with its own mobile pattern.

## State

```js
var STORE_KEY = '<product>-redesign-v1';
var S = {theme: 'system', v: 'a', user: null, force: 'live', failNext: false, proto: false /* + product state: history, favorites, usage… */};
try { Object.assign(S, JSON.parse(localStorage.getItem(STORE_KEY) || 'null') || {}); } catch (e) {}
function save() { try { localStorage.setItem(STORE_KEY, JSON.stringify(S)); } catch (e) {} }
var UI = {};   // open menus, drawers, palette, dialogs — reset on route change
var PAGE = {}; // per-page transient state — reset on route change
```

Product state is shared by all variants, so a favorite added in A shows on B's dashboard; that keeps the comparison fair.

## Router

```js
// #/<variant>/<path>?<query>
function parse() {
  var h = location.hash.replace(/^#\/?/, ''), qi = h.indexOf('?');
  var qs = qi >= 0 ? h.slice(qi + 1) : ''; if (qi >= 0) h = h.slice(0, qi);
  var parts = h.split('/').filter(Boolean).map(decodeURIComponent);
  var v = /^[a-e]$/.test(parts[0]) ? parts.shift() : S.v;
  var q = Object.fromEntries(new URLSearchParams(qs));
  return {v: v, parts: parts, q: q, embed: q.embed === '1'};
}
function L(path) { return '#/' + R.v + '/' + (path || ''); } // every in-product link goes through L()
window.addEventListener('hashchange', function () { R = parse(); /* reset UI/PAGE if path changed */ render(); });
```

`route()` is one table mirroring the real paths (`emoji/:slug`, `emoji/category/:key`, `dashboard/:tab`, `admin/emojis/:slug`…) and falls through to `page404()`. Each page returns `{title, html, bare?, after?}`; `after` wires anything that needs the DOM (streaming, focus).

## Render loop and events

- `render()` sets `body[data-v]`, applies the theme, builds `shell(page) + overlays()`, renders the toolbar (hidden when `embed`), restores focus and caret, then runs `page.after`.
- One delegated `click`, `input`, `submit`, and `keydown` listener on `document`, dispatching on `data-act`, `data-input`, and `data-form` attributes, keeps hundreds of controls manageable.
- Global keys: Esc closes the top overlay; ⌘K / Ctrl+K opens the palette where a variant has one; arrows and Enter drive suggestion lists.

## Forced states and latency

```js
function gate(okHtml, opts) {
  if (S.force === 'loading') return skeleton(opts);
  if (S.force === 'error') return errorBox();
  if (S.force === 'empty') return emptyBox(opts);
  return okHtml;
}
function fakeRequest(ms) {
  return new Promise(function (res, rej) {
    setTimeout(function () { if (S.failNext) { S.failNext = false; save(); rej(new Error('Simulated failure')); } else res(); }, ms || 600);
  });
}
```

Wrap every data-backed section in `gate()`; route every submit through `fakeRequest()`.

## Toolbar

Rows: header (`PROTOTYPE`, Compare, minimize) · variant buttons + thesis · theme · user role · state · simulate (next request fails, reset quota, reset all) · page jump `<select>` built from a `SITEMAP` array that lists every route in the coverage matrix. Minimized, it is one button: `<variant name> · switch variant, theme, user, state ▸`. Switching variant rewrites only the first hash segment, so the page and query stay.

## Compare view

```js
function compareHtml() {
  var path = R.parts.join('/');
  return '<div class="compare">' + Object.keys(VARIANTS).map(function (k) {
    return '<div class="fr"><span>' + VARIANTS[k].name + '</span><iframe src="#/' + k + '/' + path + '?embed=1"></iframe></div>';
  }).join('') + '</div>';
}
```

Grid of 2 columns on desktop (one per row on mobile); iframes at `width:200%;height:200%;transform:scale(.5)` so each frame shows a desktop-width page. Frames share `localStorage`, so role and theme match across them.

## Coverage loop (optional, when a headless browser is available)

```js
// bun or node + playwright, run from a scratch directory, not the project
for (const v of variants) for (const path of sitemap) {
  await page.goto(`file://${file}#/${v}/${path}`);
  // assert: no console errors, no 404 heading, toolbar page-jump lists `path`
}
```

Report any failures and fix them before publishing.
