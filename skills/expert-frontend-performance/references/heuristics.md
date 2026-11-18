# Frontend performance heuristics

Load this before writing findings. Every entry is **signal → why it costs → how to confirm → fix**. A signal is only a candidate. It becomes a finding once the confirm step holds in this codebase.

Contents:
1. Bundle size and code splitting
2. Dependencies: heavy, duplicate, unused
3. Render and re-render cost
4. Hydration, SSR, and streaming
5. Data fetching and waterfalls
6. Caching headers and compression
7. Fonts
8. Images and media
9. Third-party scripts
10. Memory leaks
11. CSS and layout
12. What not to report

---

## 1. Bundle size and code splitting

Rules of thumb for compressed JS on the critical path of one route. Use the project's own budget instead if it has one.
- Content or marketing page: under ~100 KB is good, over ~300 KB is a problem.
- App shell or dashboard: under ~250 KB is good, over ~500 KB is a problem.
- Main-thread cost (parse, compile, execute) follows **uncompressed** size, not gzip size. On a mid-range Android phone, 1 MB of uncompressed JS can cost on the order of a second. Transfer cost follows compressed size. Report both.

| Signal | Why it costs | Confirm | Fix |
|--------|--------------|---------|-----|
| One huge entry chunk, few or no dynamic imports | Every route pays for every feature | Analyzer: the entry or `main`/`index` chunk holds route-specific modules | Split per route (most frameworks already do), `import()` heavy features, lazy components |
| A heavy library in the entry chunk but used on one screen (editor, charts, maps, PDF, 3D, xlsx) | Parsed on every page load | Analyzer: module appears in the shared/entry chunk; grep: imported statically from a shared file | `React.lazy` / `defineAsyncComponent` / `{#await import()}` / `next/dynamic` / Astro island with `client:visible` |
| Barrel file (`index.ts` re-exporting a whole folder) imported from many places | Bundlers that cannot prove no side effects keep everything; dev servers load every module | Analyzer shows unused siblings of the imported module; `sideEffects` missing in the package | Import from the leaf path; add `"sideEffects": false` (or a list) to internal packages; Next `optimizePackageImports` |
| `import * as X from 'big-lib'` or a default import of a CJS library | Defeats tree-shaking | Analyzer shows the whole library | Named ESM imports, an `-es` build, or per-path imports |
| Polyfills for browsers the project does not support | Dead bytes on modern browsers | `browserslist` / build target vs. `core-js` entries in the bundle | Raise the target to what analytics shows; use `useBuiltIns: 'usage'` or drop polyfills |
| Over-splitting: hundreds of tiny chunks, or `manualChunks` that put one lib per chunk | Request overhead and waterfalls of chunk-loads-chunk, even on HTTP/2 | Network panel: long chains of small JS requests before interactive | Coarser vendor groups; let the framework default decide |
| Route chunk imports server-only code (SDK with Node polyfills, DB client, `crypto` shims) | Large polyfills shipped to the browser | Analyzer shows `buffer`, `stream`, `util`, `crypto-browserify` | Keep it on the server (`server-only`, `.server.ts`, server actions/loaders) |
| Locale or data files bundled (moment locales, i18n catalogs for all languages, big JSON) | Bytes for content the user never sees | Analyzer: `locale/*.js`, large `.json` modules | Load the active locale with `import()`; fetch data at runtime |
| Source of an "admin" or "debug" area in the public bundle | Bytes and attack surface | Analyzer or grep on the entry chunk | Separate route chunk or separate app |
| `chunkSizeWarningLimit` raised, or webpack `performance.hints: false` | The warning was hiding a real regression | Config diff/blame | Restore the warning, fix the chunk |

## 2. Dependencies: heavy, duplicate, unused

| Signal | Confirm | Fix |
|--------|---------|-----|
| Two libraries for one job (moment + dayjs, axios + ky, two chart libs, two icon sets, two CSS-in-JS runtimes) | Both are imported in client code, not one only in a script or test | Pick one and migrate. If a migration is large, report it as Medium with the cost measured |
| Same package at several versions in the bundle | `npm ls <pkg>`, `pnpm why <pkg>`, `yarn why <pkg>`; the analyzer shows two copies | Dedupe (`npm dedupe`, `pnpm dedupe`), align ranges, `overrides`/`resolutions`. Hand off to `dedupe-and-prune-deps` |
| Two copies of React, Vue, or a context provider | Hooks errors, broken context, double size | Same as above, or `resolve.dedupe` in Vite |
| Dependency in `dependencies` never imported | `knip`, `depcheck`, or grep for the package name | Remove it. It costs install time, not bundle size, unless something imports it |
| A tiny utility replaced by a large package (`is-number`, `left-pad`-style, `uuid` when `crypto.randomUUID` exists) | Check the browser target supports the native API | Use the platform API |

Heavy packages and their lighter options are listed in `scripts/perf_scan.py` (`HEAVY_DEPS`). Judge each one by where it is imported. A heavy library behind a lazy route boundary is usually fine.

## 3. Render and re-render cost

React (and Preact):
- **Context with a fresh value each render** (`value={{ user, setUser }}`) re-renders every consumer. Confirm: the provider sits high in the tree and the object literal is not memoized. Fix: `useMemo` on the value, split contexts, or a selector store (Zustand, Jotai, `use-context-selector`).
- **State lifted too high**: a keystroke in one input re-renders a whole page. Confirm with the React DevTools Profiler ("Highlight updates") or by reading where `useState` lives. Fix: move the state down, or pass children as props so they keep their identity.
- **Unstable props into `memo` components** (inline objects, arrays, arrow functions) cancel the memo. Only report it when the child is expensive, or is a long list.
- **Long lists without virtualization**: hundreds or thousands of rows rendered at once. Fix: `@tanstack/react-virtual`, `react-window`, `vue-virtual-scroller`, `content-visibility: auto` for static content.
- **Expensive work in render** (sorting, filtering, parsing, `new Intl.*Format` per item) with no memoization, inside a component that re-renders often.
- **`key={index}` on lists that reorder** causes remounts and lost state. That is a correctness issue first, and a cost second.
- **Effects that set state on every render** (`useEffect` with no deps, or a dep that changes identity every render) cause render loops or double renders.
- **Derived state copied into state** via `useEffect(() => setX(f(y)), [y])`: an extra render each time. Compute it during render instead.
- **INP**: heavy synchronous work in event handlers. Fix: `startTransition`, `useDeferredValue`, yield with `scheduler.yield()` or `setTimeout`, or move the work to a Web Worker.
- **React Compiler**: when `babel-plugin-react-compiler` (or the Next/Vite option) is on, do not report missing `useMemo`/`useCallback`. Check for code the compiler bails out on instead (`"use no memo"`, rule-of-hooks violations, mutations during render).

Vue:
- `reactive()` or `ref()` around large immutable data (API payloads, GeoJSON, big tables) makes every nested object a deep proxy. Fix: `shallowRef`, `markRaw`, `Object.freeze`.
- A `computed` that returns a new object or array every time defeats caching downstream. Vue 3.4+ only re-triggers when the value changes, so return stable values.
- Methods called from the template (`{{ format(x) }}`) run on every render. Use a `computed`.
- `v-if` and `v-for` on the same element; `v-show` vs `v-if` chosen wrong for things that toggle often vs. rarely.
- Deep watchers (`watch(x, fn, { deep: true })`) on large objects.
- `v-memo` and `v-once` exist for hot lists; recommend them only with evidence.

Svelte:
- Svelte 5: `$effect` used to derive state (use `$derived`); `$state` on large data that never changes (use `$state.raw`); effects that write state they read (loops).
- Svelte 4: reactive statements (`$:`) that depend on whole objects re-run on any change; store subscriptions in components that are never destroyed.
- `{#each}` without a key on lists that reorder.

Angular:
- Default change detection on large trees; recommend `OnPush` or signals, and zoneless mode where the version supports it.
- Functions called from templates; `trackBy` (or `@for ... track`) missing on large lists.

Solid and Qwik: the compiler already handles fine-grained updates. Report destructured props (which lose reactivity in Solid) only when they cause a real bug or real cost.

## 4. Hydration, SSR, and streaming

- **Everything is a client component.** Next App Router: `"use client"` on a root `layout` or a high-level `page` sends the whole subtree, and its dependencies, to the browser. Confirm: the file is a layout or page, and its children do not need interactivity. Fix: push `"use client"` down to the interactive leaves, and pass server components as `children`.
- **Hydration mismatch** (`Date.now()`, `Math.random()`, `window` checks, or locale formatting in render). React then client-renders the whole boundary again. Confirm: console warnings in dev, or code that branches on `typeof window` in render. Fix: render stable markup and patch in an effect, use `suppressHydrationWarning` only on the leaf, or use `<ClientOnly>` / `client:only`.
- **Big serialized payloads**: `__NEXT_DATA__`, the RSC payload, `window.__NUXT__`, SvelteKit `data`, Astro island props. Passing whole API objects to the client duplicates them in HTML and JS. Confirm: view the source and measure the inline script. Fix: select only the fields the UI needs.
- **Island directives**: Astro `client:load` on below-the-fold components. Prefer `client:visible` or `client:idle`, and no directive at all for static content. In Nuxt, use `<LazyX>` with `hydrate-on-visible` / `hydrate-never` (Nuxt 3.16+ lazy hydration). In Angular, use `@defer` and incremental hydration.
- **SPA where SSR or SSG was possible**: content that rarely changes is rendered only on the client, so LCP waits for the JS. Confirm: `ssr: false`, `output: 'export'` with client fetch, or a blank `<div id="root">` in the HTML. Report it as High when it is the landing or content path.
- **Blocking data before the shell**: a slow loader blocks the whole response. Fix: stream with Suspense boundaries (`loading.tsx`, React Router `defer`/`Await`, SvelteKit streamed promises, Nuxt `lazy: true`), and keep fast data in the shell.
- **Dynamic rendering forced by accident**: Next calls to `cookies()`, `headers()`, or `searchParams` in a shared layout make every route dynamic. Confirm with the build output route table (`ƒ` vs `○`).

## 5. Data fetching and waterfalls

- **Client fetch in an effect after hydration**: HTML → JS → hydrate → fetch → render. That is at least one extra round trip on the critical path. Fix: fetch on the server (loader, server component, `useFetch`/`useAsyncData`, `+page.server.ts`) or start the request early (route loader, `preload`).
- **Sequential awaits that are independent**: `const a = await getA(); const b = await getB();`. Fix: `Promise.all`, or start both promises first and await later.
- **Parent-child waterfall**: a parent fetches, then renders a child that fetches. Confirm in the network panel (staggered requests) or by reading the tree. Fix: hoist the fetches into a loader, or prefetch in parallel.
- **Chunk → data waterfall**: a lazy route chunk loads, and only then starts its data fetch. Fix: route loaders that run in parallel with the chunk (React Router / TanStack Router loaders, SvelteKit `load`).
- **Duplicate requests**: the same endpoint is called by several components, or by both SSR and the client. Nuxt: `$fetch` in `setup` runs on server and client, so use `useFetch`. Next: a `fetch` not deduped outside React's render, or `cache()` missing for non-fetch data.
- **Over-fetching**: list endpoints returning full objects, no pagination, GraphQL queries asking for unused fields.
- **No caching layer for repeated client reads**: refetching on every mount. Fix: TanStack Query or SWR with a sensible `staleTime`.
- **Next.js 15+ caching defaults**: `fetch` is not cached by default. Code written for 14 may now hit the origin on every request. Check `cache: 'force-cache'`, `next.revalidate`, `"use cache"` / Cache Components on 16+.
- **No prefetch on likely navigations**: framework `<Link>` prefetch disabled globally, or plain `<a>` used for internal links in an SPA.
- **Missing `preconnect` to a critical third-party origin** (API, image CDN) used on first paint. Do not stack more than 2–3 preconnects.

## 6. Caching headers and compression

Check config (`vercel.json`, `netlify.toml`, `_headers`, `next.config` `headers()`, `nginx.conf`, CDN rules) and, where the site is reachable, `curl -sI <url>`.

| Resource | Want | Red flag |
|----------|------|----------|
| Hashed static assets (`/assets/index-3f2a.js`, `/_next/static/`) | `Cache-Control: public, max-age=31536000, immutable` | Short `max-age`, `no-cache`, or no header (heuristic caching) |
| HTML documents | `no-cache` or a short `max-age` with `stale-while-revalidate`, or `s-maxage` at the CDN | `immutable` or a long `max-age` on HTML: users get stuck on an old build that points at deleted chunks |
| Un-hashed assets (`/logo.png`, `/fonts/inter.woff2`) | Moderate `max-age` plus `ETag`/`Last-Modified`, or add hashes | `immutable` on a file whose content changes under the same name |
| API GET responses that are shareable | `s-maxage` plus `stale-while-revalidate` at the edge | `private, no-store` on public data, or `Set-Cookie` on a cacheable response (most CDNs then bypass the cache) |
| Text responses | `content-encoding: br` or `gzip` (or `zstd`) | Uncompressed JS, CSS, HTML, JSON, or SVG |
| `Vary` | Only the headers that really vary the response | `Vary: User-Agent` or `Vary: Cookie` that fragments the CDN cache |

Also check: a service worker that caches HTML cache-first without an update path (a stale app forever); `?v=` cache busting on files the bundler already hashes; source maps served publicly when the project did not choose that.

## 7. Fonts

- Remote CSS `@import` or a `<link>` to Google Fonts: a render-blocking chain of DNS → CSS → font. Fix: self-host (`next/font`, `@nuxt/fonts`, `@fontsource/*`, the Astro fonts API) or at least `preconnect`.
- Missing `font-display` (or `block`/`auto`) hides text (FOIT). Use `swap` for body text, `optional` when layout stability matters more than the brand font.
- Layout shift on font swap. Fix: fallback metrics (`size-adjust`, `ascent-override`; `next/font` and `@nuxt/fonts` do this automatically).
- Too many weights or styles, or whole-Unicode files. Fix: a variable font, `unicode-range` subsets, and only the weights the CSS uses (grep `font-weight`).
- Preload: only the one or two fonts used above the fold, as `woff2`, with `crossorigin`. Preloading every weight competes with the LCP image.
- Icon fonts (Font Awesome webfont, Material Icons font) for a handful of icons: switch to inline SVG or per-icon imports.

## 8. Images and media

Report image problems briefly, then hand fixes to `optimize-images`.
- The LCP image has `loading="lazy"`, has no `fetchpriority="high"`, or is a CSS background discovered late.
- No `width`/`height` or `aspect-ratio` (CLS); no `srcset`/`sizes` (oversized on mobile); no AVIF/WebP.
- The framework image component is bypassed (`<img>` in Next or Nuxt where `next/image` / `<NuxtImg>` is set up).
- Autoplaying background video on mobile, a GIF used as video (use `<video muted autoplay loop playsinline>`), a heavy video without `preload="none"` or a poster.
- Embedded iframes (YouTube, maps) above the fold: use a facade (a click-to-load placeholder).

## 9. Third-party scripts

- Synchronous `<script src>` to another origin in `<head>`: parser-blocking. Use `async`/`defer`, or the framework loader (`next/script` with `afterInteractive`/`lazyOnload`, `useScript` in Nuxt, Partytown for analytics-type tags).
- A tag manager loading more tags than the code shows: the code review cannot see them. Note it as "Not verified" and recommend auditing the container.
- Chat widgets, A/B testing, session replay, and heatmaps on every page: often the largest INP cost. Load on interaction, or after idle, or only on the pages that need them.
- A/B testing scripts that hide the page (anti-flicker snippets with `opacity: 0` for up to several seconds) directly delay LCP. Report as High when present on landing pages.
- Duplicate analytics (GA plus GTM-loaded GA, two pixels for one vendor).
- Social embeds and share buttons that load SDKs on page load.

## 10. Memory leaks

Leaks matter most for SPAs and long-lived dashboards. Look for anything that registers with a long-lived object (window, document, a global store, a socket, a timer) without a matching cleanup in the component lifecycle.

| Leak source | Cleanup |
|-------------|---------|
| `addEventListener` on `window`/`document`/`body` in a component | `removeEventListener` with the **same** function reference (not a new arrow) in the effect cleanup, `onUnmounted`, `onDestroy`, or an `AbortController` signal |
| `setInterval`, a recursive `setTimeout`, `requestAnimationFrame` loops | `clearInterval` / `clearTimeout` / `cancelAnimationFrame` in cleanup |
| `ResizeObserver`, `IntersectionObserver`, `MutationObserver` | `disconnect()` |
| WebSocket, EventSource, BroadcastChannel, RxJS or store subscriptions | `close()` / `unsubscribe()` in cleanup; Angular `takeUntilDestroyed` |
| `fetch` that sets state after unmount | `AbortController` aborted in cleanup |
| Module-level caches or Maps keyed by objects or ids with no eviction | LRU with a cap, or `WeakMap`/`WeakRef` |
| Chart, map, or editor instances (Chart.js, Mapbox, Leaflet, Monaco) | `.destroy()` / `.remove()` / `.dispose()` on unmount |
| Detached DOM kept alive by closures or refs stored globally | Null out references; avoid storing nodes in global stores |
| Server-side: module-level state in SSR that grows per request | Request-scoped state; never cache per-user data at module level |

Confirm a leak with the three-snapshot technique (see `measuring.md`) when the app runs. From source alone, rate it medium confidence unless the missing cleanup is plain to read.

## 11. CSS and layout

- One global CSS bundle for the whole site, mostly unused on any given page. Confirm with the Coverage panel. Fix: CSS modules, per-route CSS, critical-CSS inlining where the framework supports it.
- Tailwind `content`/`@source` globs that miss files (purge drops classes) or include `node_modules` (huge CSS).
- Layout thrashing: alternating reads (`offsetHeight`, `getBoundingClientRect`) and writes (`style.*`) in a loop or a scroll handler. Batch reads, then writes, or use `requestAnimationFrame`.
- Scroll, resize, and pointer handlers without `{ passive: true }`, throttling, or `requestAnimationFrame`; scroll-linked effects that could be `IntersectionObserver` or CSS scroll-driven animations.
- Animating `top`/`left`/`width`/`height`/`box-shadow` instead of `transform`/`opacity`; `will-change` sprayed on many elements.
- Huge DOM (more than ~1 500 nodes, or depth over ~32) on a key page: suggest virtualization or `content-visibility: auto`.

## 12. What not to report

- A cost the framework already removes: per-route splitting in Next, Nuxt, SvelteKit, Astro, React Router framework mode, and Angular lazy routes; Vite `modulepreload`; automatic font optimization in `next/font`; Astro shipping zero JS by default; Svelte and Solid compiled reactivity.
- Missing `useMemo`/`useCallback` on cheap values or cheap children, or anything when React Compiler is on.
- Micro-optimizations with no measurable effect (`for` vs `forEach`, `===` vs `==`, string concat vs template) outside a proven hot loop.
- Dev-mode numbers: bundle sizes from `vite dev` or `next dev`, double effects from React StrictMode, Vue devtools overhead.
- Heavy libraries that live only behind a lazy boundary the user rarely visits, unless that boundary is the main flow.
- Lighthouse score deltas under ~5 points from a single run (variance).
- Size differences under ~5 KB compressed, unless they are on a page with a strict budget.
- Generic advice not tied to a file, line, chunk, or URL ("consider using a CDN").
