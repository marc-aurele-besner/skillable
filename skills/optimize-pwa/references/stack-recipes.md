# Stack recipes

Where the manifest, icons, and service worker live in each stack. Prefer what the project already uses, and check the installed version before choosing an API (`npm ls <pkg>` or the lockfile), since these change between majors.

## Vite (React, Vue, Svelte, Solid, Preact, Lit)

- **Plugin:** `vite-plugin-pwa`. `VitePWA({ registerType: 'prompt', manifest: {...}, workbox: { globPatterns: ['**/*.{js,css,html,svg,png,woff2}'], navigateFallback: '/index.html', navigateFallbackDenylist: [/^\/api\//] } })`.
- **Update prompt:** `virtual:pwa-register/react` (or `/vue`, `/svelte`, `/solid`, `/preact`) → `useRegisterSW()` gives `needRefresh` and `updateServiceWorker(true)`. Add `vite-plugin-pwa/client` (or the framework variant) to `tsconfig` `types`.
- **Icons:** `@vite-pwa/assets-generator` with `pwa-assets.config.ts` (`preset: minimal2023Preset`) from one SVG; `pwaAssets: { config: true }` in the plugin injects the head links.
- **Dev:** SW is off in dev by default; test with `vite build && vite preview`.

## Next.js (App Router)

- **Manifest:** `app/manifest.ts` returning `MetadataRoute.Manifest` (served at `/manifest.webmanifest`, link added automatically).
- **Viewport and theme color:** `export const viewport: Viewport = { width: 'device-width', initialScale: 1, viewportFit: 'cover', themeColor: [{ media: '(prefers-color-scheme: light)', color: '#fff' }, { media: '(prefers-color-scheme: dark)', color: '#000' }] }` in the root layout. Do not put these in `metadata` (deprecated there since Next 14).
- **Icons:** `app/icon.png`, `app/apple-icon.png` file conventions; manifest icons as files in `public/`.
- **Service worker:** `@serwist/next` (successor of `next-pwa`, which is unmaintained). `withSerwistInit({ swSrc: 'app/sw.ts', swDest: 'public/sw.js', disable: process.env.NODE_ENV === 'development' })`. In `app/sw.ts` use `defaultCache` from `@serwist/next/worker` and `fallbacks: { entries: [{ url: '/~offline', matcher: ({ request }) => request.destination === 'document' }] }`. Serwist needs webpack; with Turbopack builds, check the Serwist docs for the current setup or hand-write `public/sw.js`.
- **Headers:** `next.config` `headers()` for `/sw.js` → `Cache-Control: no-cache, no-store, must-revalidate`, `Content-Type: application/javascript; charset=utf-8`.

## Next.js (Pages Router)

Manifest as `public/manifest.webmanifest` linked in `_document`; viewport meta in `_app` via `next/head` (not `_document`). Same Serwist setup.

## Nuxt

`@vite-pwa/nuxt` module: `pwa: { registerType: 'prompt', manifest: {...}, workbox: { navigateFallback: '/' } }` in `nuxt.config`; `<NuxtPwaManifest />` in `app.vue`; `$pwa.needRefresh` / `$pwa.updateServiceWorker()` for the update toast. Viewport and theme color in `app.head`.

## SvelteKit

- Built-in: `src/service-worker.ts` is bundled and registered automatically; use `$service-worker` (`build`, `files`, `version`) to precache. Manifest in `static/manifest.webmanifest`, links in `src/app.html`.
- Or `@vite-pwa/sveltekit` with `SvelteKitPWA({...})` if the project prefers plugin-managed Workbox.

## Astro

`@vite-pwa/astro` integration; `pwaInfo` from `virtual:pwa-info` in the base layout to inject the manifest link; the register script from `virtual:pwa-register`. For a mostly static content site, ask before adding offline support.

## Angular

`ng add @angular/pwa` creates `manifest.webmanifest`, `ngsw-config.json`, icons, and wires `provideServiceWorker('ngsw-worker.js', { enabled: !isDevMode(), registrationStrategy: 'registerWhenStable:30000' })`. Update prompt: `SwUpdate.versionUpdates` filtered on `VERSION_READY`, then `activateUpdate()` and reload. Data caching through `dataGroups` in `ngsw-config.json` with `strategy: "freshness"` for APIs.

## Remix / React Router v7

No built-in SW. Manifest as a resource route `app/routes/manifest[.]webmanifest.ts` or a `public/` file; links in `root.tsx` `links`. SW: `vite-plugin-pwa` works with the Vite build (set `navigateFallback: null` for SSR and let navigations go network-first with an offline page), or a hand-written `public/sw.js`.

## Gatsby

`gatsby-plugin-manifest` (icons generated from one source; put it before `gatsby-plugin-offline` in the plugin list). `gatsby-plugin-offline` caches aggressively; if the app has frequent deploys, prefer `gatsby-plugin-remove-serviceworker` plus a lean hand-written SW, and ask first.

## Ionic / Capacitor / Quasar

Ionic and Quasar ship a PWA mode (`quasar mode add pwa`, Ionic via `@angular/pwa` or `vite-plugin-pwa`). Mobile UX is usually good already; focus on manifest, icons, and SW config.

## CRA (Create React App)

`cra-template-pwa` uses Workbox `InjectManifest` with `src/service-worker.js`; `serviceWorkerRegistration.register()` in `index.js`. CRA is unmaintained; do not migrate in this PR, list it as a follow-up.

## Plain HTML / static site generators

- Manifest `manifest.webmanifest` at the web root, linked in every page head (one shared head partial in Hugo, Jekyll, Eleventy).
- SW: hand-written `sw.js` at the root (see service-worker.md), or `workbox-cli` (`workbox generateSW`/`injectManifest`) as a postbuild step if Node is already in the toolchain.
- Register with a small inline script guarded by `'serviceWorker' in navigator`.

## Server frameworks (Django, Rails, Laravel, Phoenix)

The SW must be served from the path whose scope it controls (root for the whole app), so add a route or static mapping for `/sw.js` and `/manifest.webmanifest` rather than serving them from `/static/`. Rails 8 generates `app/views/pwa/manifest.json.erb` and `service-worker.js` with commented routes in `config/routes.rb`; enable those. Otherwise use the `Service-Worker-Allowed` header when the file cannot live at the root.
