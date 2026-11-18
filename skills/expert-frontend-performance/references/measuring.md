# Measuring frontend performance

Load this when a finding needs a number, or when the user asks for evidence. Measure the **production build**. Dev servers are unminified, unsplit, and instrumented, so their numbers mean nothing for users.

Ground rules:
- Never install packages into the project to measure. Use `npx`/`pnpm dlx`/`bunx` for one-off tools, or a scratch copy of the config. If a tool must be added as a dependency, ask first.
- Running the project's own `build` script is fine when dependencies are already installed and the code is trusted. Never run builds, installs, or scripts for an untrusted fork.
- Write any reports or stats files to a scratch directory, not into the repo. Delete temporary analyzer config afterwards.
- Lab runs vary. Take the median of 3–5 runs and say how many you ran.

## 1. Static facts (no build)

```bash
python3 -I scripts/perf_scan.py <project-dir>          # stack, heavy deps, overlaps, source candidates
python3 -I scripts/perf_scan.py <project-dir> --json   # same, machine-readable
```

Duplicates and unused dependencies:

```bash
npm ls <pkg> --all        # or: pnpm why <pkg> / yarn why <pkg> / bun pm ls
npx knip --dependencies   # unused deps and exports (read-only report)
npx depcheck              # older alternative
```

Library cost before it ships: `https://bundlephobia.com/package/<name>@<version>` or `https://pkg-size.dev/<name>`. Treat those as approximate; the real cost depends on which exports are imported.

## 2. Build output

Run the build once, then read what it printed and what it wrote:

| Stack | Command | What to read |
|-------|---------|--------------|
| Vite (React, Vue, Svelte, Solid) | `npm run build` | Per-chunk size and gzip size; warnings over the chunk limit |
| Next.js ≤ 15 | `next build` | Route table: size and First Load JS per route; `○` static, `●` SSG, `ƒ` dynamic |
| Next.js 16+ | `next build` | Route table (static vs dynamic only); use the analyzer for sizes |
| Nuxt | `nuxi build` | Client and server chunk sizes |
| SvelteKit | `vite build` | Client chunk sizes |
| Astro | `astro build` | Pages built, island scripts emitted |
| Angular | `ng build` | Initial vs lazy chunk table, budget warnings |

Then size the output with the scanner (`--build-dir <dir>` if it is not a default location). Remember: the total on disk is every chunk, not what one route loads.

## 3. Bundle analyzers

| Bundler | Analyzer |
|---------|----------|
| Next (webpack) | `ANALYZE=true next build` with `@next/bundle-analyzer` wired in `next.config` |
| Next (Turbopack, 16.1+) | `next experimental-analyze` |
| Vite / Rollup / Rolldown | `npx vite-bundle-visualizer`, or `rollup-plugin-visualizer` added temporarily |
| Nuxt | `npx nuxi analyze` |
| webpack | `npx webpack-bundle-analyzer stats.json` after `webpack --profile --json > stats.json` |
| Rspack | `rsdoctor` |
| esbuild / Angular (esbuild) | `--metafile`, then `npx esbuild-visualizer --metadata <meta.json>` |
| Any (from source maps) | `npx source-map-explorer 'dist/**/*.js'` (needs source maps; build them to a scratch dir if the project does not) |

Read the analyzer for: what is in the entry/shared chunk, the biggest modules overall, the same package appearing twice, CommonJS modules that did not tree-shake, and polyfills.

## 4. Lab traces (when the app runs)

Serve the production build locally (`npm run preview`, `next start`, `npx serve dist`), or use a staging/production URL the user named. Only GET the project's own pages.

Lighthouse CLI:

```bash
npx lighthouse <url> --preset=desktop --output=json --output-path=<scratch>/lh-desktop.json --quiet
npx lighthouse <url> --output=json --output-path=<scratch>/lh-mobile.json --quiet   # mobile is the default
```

Read in the JSON: `largest-contentful-paint`, `total-blocking-time`, `cumulative-layout-shift`, `server-response-time`, `render-blocking-resources`, `unused-javascript`, `unused-css-rules`, `bootup-time`, `mainthread-work-breakdown`, `third-party-summary`, `font-display`, `uses-long-cache-ttl`, `uses-text-compression`, `lcp-lazy-loaded`, `prioritize-lcp-image`, `dom-size`, `legacy-javascript`.

Chrome DevTools (manually, or through a browser-automation tool if one is available):
- **Performance panel**: record a load with CPU 4× slowdown and "Fast 4G"; look at long tasks (> 50 ms), the LCP marker and its element, layout shifts, and the Interactions track for INP. Record an interaction (typing, opening a menu) to find slow handlers.
- **Network panel**: sort by start time to see waterfalls; check `Cache-Control`, `content-encoding`, and priority columns; filter by third-party domains.
- **Coverage panel**: unused JS and CSS bytes per file on a given page.
- **Rendering drawer**: "Paint flashing", "Layout shift regions".

Framework profilers: React DevTools Profiler (enable "Record why each component rendered"), Vue DevTools performance timeline, Angular DevTools profiler.

## 5. Caching and compression

```bash
curl -sI <url>                                         # HTML document headers
curl -sI <url>/<hashed-asset-path>                     # a JS/CSS chunk from the build
curl -sI -H 'Accept-Encoding: br, gzip' <url>/<asset>  # confirm content-encoding
```

Compare preview and production: preview deployments often send different cache headers.

## 6. Memory

Three-snapshot technique in DevTools Memory panel:
1. Load the page, perform the suspected action once (warm-up), take snapshot 1.
2. Repeat the action several times (open and close the modal, navigate away and back), take snapshot 2.
3. Repeat again, take snapshot 3.
4. In snapshot 3, view "Objects allocated between snapshot 1 and 2". Anything that survives and keeps growing is a leak candidate. Check "Detached" DOM nodes and the retainers path.

Also useful: the Performance Monitor (JS heap size and DOM node count over time), the "Detached elements" panel, and `memlab` (`npx memlab run --scenario <file>`) for repeatable leak tests.

## 7. Field data

Field data (CrUX, RUM) belongs to `audit-web-vitals`. If it is already available, use it to rank findings: a source-level problem on a page with poor p75 LCP or INP outranks the same problem on a page nobody visits.
