# Framework and bundler playbook

Load the section for the stack detected in step 1. Each section lists how to detect it, what it already optimizes (so you do not report it), the traps that matter, and where the cost shows up. Version-specific behavior is marked. Check the installed version in the lockfile before relying on it.

## React (any setup)

- Detect: `react` and `react-dom` in `package.json`; `.jsx`/`.tsx` files.
- Already handled: nothing about re-renders, unless React Compiler is on (`babel-plugin-react-compiler`, `reactCompiler: true` in `next.config`, or `@vitejs/plugin-react` with the compiler plugin).
- Traps: context value identity, state too high, list virtualization, effect-driven fetches, `React.lazy` without a `Suspense` boundary near the use site (the whole page suspends), `useEffect` to sync derived state.
- React 19: `use()`, `preload()`/`preinit()` from `react-dom` for resource hints, and Actions. Rendering `<link rel="stylesheet">` and `<title>` in components hoists them.
- Look at: the React DevTools Profiler (commit durations, "why did this render"), and the Performance panel "Interactions" track for INP.

## Next.js

- Detect: `next` dependency, `next.config.*`, `app/` (App Router) or `pages/` (Pages Router).
- Already handled: per-route code splitting, `next/font` self-hosting with fallback metrics, `next/image` sizing and formats (when used), `<Link>` prefetch in production, `optimizePackageImports` for a built-in list of popular libraries.
- App Router traps:
  - `"use client"` high in the tree (layouts, pages, providers wrapping everything). Providers are often fine as long as they accept `children`. The cost is in client components that import heavy libraries.
  - Large props passed from server to client components are serialized into the RSC payload.
  - `cookies()`, `headers()`, `searchParams`, or `connection()` in a shared layout opt the whole segment into dynamic rendering. The build route table shows `ƒ` (dynamic) where `○`/`●` (static) was expected.
  - **15+:** `fetch` is uncached by default and GET route handlers are dynamic by default. **16+:** Cache Components / `"use cache"` and `cacheLife` are the caching model. Read the version before calling something uncached.
  - Missing `loading.tsx` or `Suspense` around slow data blocks streaming.
  - `next/dynamic` with `ssr: false` for above-the-fold content (it becomes client-only).
- Pages Router traps: `getServerSideProps` where `getStaticProps` + ISR would do; big `pageProps` in `__NEXT_DATA__`; `_app` importing heavy libraries for every page.
- `next/script`: `beforeInteractive` only for truly critical scripts; `afterInteractive` (default) or `lazyOnload` for analytics and widgets; `worker` (Partytown, experimental).
- Measure: `next build` prints a route table. Versions before 16 also print "First Load JS" per route. Next 16 removed the size columns. Use `@next/bundle-analyzer` (`ANALYZE=true next build`, webpack builds) or `next experimental-analyze` (Turbopack builds, 16.1+).

## Remix / React Router (framework mode) / TanStack Start

- Detect: `@remix-run/*`, `react-router` with `@react-router/dev`, or `@tanstack/react-start`.
- Already handled: route-level splitting, parallel loaders for nested routes, link prefetch with `prefetch="intent"`.
- Traps: client-side fetching in components instead of loaders; `clientLoader` used where a server loader would stream; awaiting every promise in a loader instead of returning it for streaming; prefetch disabled.
- Measure: Vite tooling (see Vite).

## Vue

- Detect: `vue`, `.vue` single-file components, `@vitejs/plugin-vue`.
- Already handled: template compile-time hoisting and patch flags, fine-grained reactivity.
- Traps: deep reactivity on large data (`shallowRef`, `markRaw`), methods in templates, deep watchers, `v-for` without `:key`, large global component registration (`app.component` for everything defeats splitting), all routes imported statically in `router/index` (use `() => import('./views/X.vue')`).
- Measure: Vue DevTools performance timeline (component render timings), plus the Vite analyzer.

## Nuxt

- Detect: `nuxt`, `nuxt.config.*`.
- Already handled: route splitting, auto-imports (tree-shaken), payload extraction for prerendered routes, `<NuxtLink>` prefetch.
- Traps:
  - `$fetch` called directly in `setup` runs on both server and client (a double request plus a hydration mismatch). Use `useFetch` or `useAsyncData`.
  - `useFetch` without `pick` or `transform` serializes the whole response into `window.__NUXT__`.
  - `ssr: false` globally, or `routeRules` that disable SSR on content pages.
  - Plugins without `.client`/`.server` suffixes, or with heavy imports, run on every page.
  - Nuxt 3.16+ lazy hydration: `<LazyX hydrate-on-visible>`, `hydrate-on-idle`, `hydrate-never`. Recommend them for heavy below-the-fold components.
  - `routeRules` with `swr`/`isr`/`prerender` are the caching lever. Check they exist for cacheable pages.
- Modules: `@nuxt/image`, `@nuxt/fonts`, `@nuxt/scripts` (third-party loading with triggers).
- Measure: `npx nuxi analyze` (bundle visualizer), the build output sizes.

## Svelte / SvelteKit

- Detect: `svelte`, `@sveltejs/kit`, `svelte.config.js`. Version 5 uses runes (`$state`, `$derived`, `$effect`).
- Already handled: compiled reactivity (no virtual DOM diffing), route splitting, `data-sveltekit-preload-data` (defaults to `hover` in the starter template).
- Traps:
  - Fetching in `onMount` instead of `load` (`+page.ts` or `+page.server.ts`).
  - Using global `fetch` inside `load` instead of the provided `fetch` (no dedupe, no SSR replay, credentials issues).
  - Awaiting slow promises in `load` instead of returning them for streaming.
  - Svelte 5: `$effect` for derivations (use `$derived`), `$state` on big immutable data (use `$state.raw`).
  - `export const ssr = false` or `csr = true` on pages that are pure content (`csr = false` ships no JS).
  - `prerender` not set on static pages.
- Measure: `vite build` output, plus `rollup-plugin-visualizer` in `vite.config`.

## Astro

- Detect: `astro`, `astro.config.*`, `.astro` files.
- Already handled: zero JS by default, islands, `<Image>`/`<Picture>` optimization, prefetch (when enabled), view transitions.
- Traps:
  - `client:load` on islands that are below the fold or not interactive until scrolled to. Use `client:visible`, `client:idle`, or `client:media`.
  - `client:only` on content that could be server-rendered (no HTML until JS runs).
  - A framework component used as an island for static markup (it should be a plain `.astro` component).
  - Passing large props to islands (serialized into the HTML).
  - Several UI frameworks (React plus Vue plus Svelte islands) on one page: each ships its own runtime.
  - `output: 'server'` where pages could be prerendered (`export const prerender = true`).
- Measure: `astro build` output, plus `rollup-plugin-visualizer` through `vite.plugins` in the Astro config.

## Angular

- Detect: `@angular/core`, `angular.json`.
- Already handled: lazy routes with `loadComponent`/`loadChildren`, build budgets in `angular.json`, image directive `NgOptimizedImage`.
- Traps: eager routes; `@defer` not used for heavy below-the-fold components; default change detection on big trees (use `OnPush` and signals, or zoneless mode on versions that support it); missing `track` in `@for`; SSR without hydration enabled (`provideClientHydration`); budgets raised to silence warnings.
- Measure: `ng build --stats-json`, then `npx esbuild-visualizer --metadata dist/<app>/stats.json` (esbuild builder) or `webpack-bundle-analyzer` (webpack builder).

## Solid, Qwik, Preact, Lit

- Solid: fine-grained reactivity; traps are destructured props and effects that fetch (use `createResource`).
- Qwik: resumability; traps are `useVisibleTask$` on many components (it forces eager JS) and big serialized state.
- Preact: check `preact/compat` aliasing is complete, or React may be bundled too.
- Lit: traps are big `updated()` work and missing `shouldUpdate`.

## Bundlers

### Vite (Rollup, or Rolldown in newer versions)

- `vite build` prints every chunk with its gzip size. Warnings over 500 KB come from `build.chunkSizeWarningLimit`.
- Analyzer: `rollup-plugin-visualizer` (add temporarily to `plugins`, or run it in a scratch copy of the config), or `npx vite-bundle-visualizer`.
- Traps: `manualChunks` that put every vendor in one chunk (every route pays for all of them) or one per package (waterfalls); `optimizeDeps` issues affect dev only, not production; `build.target` set lower than needed (more transpilation and polyfills); `build.sourcemap: true` with maps uploaded to the public host; `build.cssCodeSplit: false`.

### webpack

- Analyzer: `webpack-bundle-analyzer` or `webpack --profile --json > stats.json` and then Statoscope or webpack.github.io/analyse.
- Traps: `mode` not `production`; `devtool: 'eval-*'` in production; `optimization.splitChunks` overridden badly; `IgnorePlugin`/`ContextReplacementPlugin` missing for moment locales; `resolve.alias` pulling in CJS builds; `babel-loader` excluding `node_modules` so modern ESM packages stay unprocessed (fine) or including it (slow builds, not slower apps).

### Rspack, Turbopack, esbuild, Parcel

- Rspack: webpack-compatible config and analyzers (`rsdoctor` for deep analysis).
- Turbopack: the Next 16 default for builds. Use the Next analyzer described above.
- esbuild: `--metafile=meta.json`, then the esbuild bundle analyzer (`esbuild.github.io/analyze`) or `esbuild-visualizer`.
- Parcel: `--reporter @parcel/reporter-bundle-analyzer`.
