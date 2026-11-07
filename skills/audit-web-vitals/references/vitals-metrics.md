# Core Web Vitals — metrics, thresholds, and how to measure them

Read this before writing a budget or reporting a number to the user. It defines each metric, the thresholds Google uses, where field data comes from, how to read a Lighthouse JSON report, and the false alarms that make agents report wins that do not exist.

## The three Core Web Vitals, plus TTFB

| Metric | Full name | What it measures | Unit | Good | Needs improvement | Poor |
|--------|-----------|------------------|------|------|-------------------|------|
| **LCP** | Largest Contentful Paint | Time until the largest visible element finishes rendering | ms | <= 2500 | 2500–4000 | > 4000 |
| **INP** | Interaction to Next Paint | Latency of the worst user interaction (click, tap, key) | ms | <= 200 | 200–500 | > 500 |
| **CLS** | Cumulative Layout Shift | How much visible content jumps around during the page's life | unitless | <= 0.1 | 0.1–0.25 | > 0.25 |
| **TTFB** | Time to First Byte | Server response time for the main document | ms | <= 800 | 800–1800 | > 1800 |

TTFB is not a Core Web Vital, but it is the leading indicator for the other three: a slow server delays LCP, delays hydration, and lengthens every interaction.

The official thresholds live at <https://web.dev/articles/vitals>. The 75th percentile (p75) of all real-user sessions is what counts — not the median, not the best run.

## How each metric is computed

**LCP** — the browser reports render times for candidate elements and takes the largest one painted before the first user interaction. The usual offenders: an oversized hero image that is not the priority resource, a slow server response, render-blocking CSS or JS in `<head>`, and web fonts that block text paint (`font-display: swap` fixes it).

**INP** (replaced FID in March 2024) — for the longest interaction in the session, the browser measures the delay between the input and the next frame painted after the handler runs. The whole interaction latency counts, not just the handler. Offenders: long tasks (each over 50 ms blocks the main thread), heavy hydration on a large DOM, expensive event handlers doing synchronous work, and third-party scripts attaching long listeners.

**CLS** — the browser sums the layout shift scores of every unexpected visible element movement during the session, weighted by impact distance. Offenders: images and iframes with no width/height, late-loading web fonts that swap to a different size, ads or announcement bars inserted above existing content, and async embeds.

**TTFB** — the delta between the navigation start and the first byte of the main document response. Offenders: uncached server responses, slow database or API queries in the render path, and missing CDN or edge caching.

## Field data vs. lab data

**Field data** is collected by real browsers in real sessions and reported at p75. It is the truth. If field data exists, it is the number that matters.

**Lab data** is produced by Lighthouse (or any synthetic runner) on a simulated device and network. It is a proxy: useful to compare a change against a baseline, useless as a claim about users.

Rules:

- Never present a Lighthouse number as a field metric, and never say a field metric improved unless field data was actually re-read after the change.
- Never compare a Lighthouse score (0–100) with a Core Web Vital threshold. They are different units; a score of 90 can still mean a failing INP.
- When field data is unavailable, say so explicitly rather than substituting lab numbers silently.

## Getting field data

### 1. Chrome UX Report API (CrUX) — best free source

CrUX aggregates real Chrome users' data. It needs a Google Cloud API key with the Chrome UX Report API enabled.

Ask the user for the key and for the environment variable name to use. Say something like:

> Field data comes from the Chrome UX Report API, which needs a Google Cloud API key with the Chrome UX Report API enabled. You can create one at <https://console.cloud.google.com/apis/credentials>. Put it in a `CRUX_API_KEY` environment variable (or paste it here and I will use it for this run only — I will not commit it or write it into the repo).

Never commit the key, never write it into a repo file, never paste it into a PR body or issue. Read it from the environment at call time.

Request shape (origin level, p75 across all page types):

```bash
curl -s "https://chromeuxreport.googleapis.com/v1/records:queryRecord?key=${CRUX_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "https://example.com",
    "formFactor": "PHONE",
    "metrics": ["largest_contentful_paint", "interaction_to_next_paint", "cumulative_layout_shift"]
  }'
```

Useful fields:

- `formFactor`: `PHONE`, `DESKTOP`, `TABLET`, or omit for the combined value.
- `metrics`: `largest_contentful_paint`, `interaction_to_next_paint`, `cumulative_layout_shift`, `first_contentful_paint`, `experimental_time_to_first_byte`.
- Response: `record.metrics.<metric>.percentiles.p75` (and `.p75` is the value to compare against the budget). A `record` key means data exists for that origin; a missing `record` means not enough traffic for CrUX to report, which is normal for small sites.
- For per-route data, POST to `https://chromeuxreport.googleapis.com/v1/records:queryRecord` with `{"url": "https://example.com/pricing"}` instead of `origin`.

TTFB is not part of the standard CrUX metric set. Use the site's own RUM, or treat it as a lab-only diagnostic from Lighthouse.

### 2. PageSpeed Insights API — field + lab in one call

No key is needed for the free tier, but the API is rate-limited; a key raises the limit.

```bash
curl -s "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=https://example.com&strategy=mobile&category=performance"
```

- `loadingExperience` holds the **field** p75 values (from CrUX) — this is the section to quote.
- `lighthouseResult` holds the **lab** run.
- When `loadingExperience.overall_category` is `SPEED_GENERIC` or below, there is not enough field data to score — report the lab numbers as lab numbers and say field data is unavailable.

### 3. The project's own RUM or analytics

If the site already collects vitals (via `web-vitals` in the codebase, an analytics provider, a `PerformanceObserver` snippet, or a tag manager), that is the best source: it is per-route, per-device, and continuous. Read the existing implementation and use it. Look for:

```bash
rg -n -g '!node_modules' -e 'web-vitals' -e 'PerformanceObserver' -e 'onLCP' -e 'onINP' -e 'onCLS' .
```

Do not add a new RUM vendor without the user's approval.

## Reading a Lighthouse JSON report

Lighthouse writes a JSON report with `--output json --output-path`. Structure:

- `audits` — an object keyed by audit id, each with `title`, `score`, `numericValue`, `numericUnit`, `displayValue`, and `details`.
- `categories.performance.score` — the 0–100 score. It is **not** a Core Web Vital.
- `finalUrl` / `requestedUrl` — the URL that was measured.

Audit id to metric mapping (this is what the bundled checker uses):

| Metric | Audit id | Where the value lives |
|--------|----------|----------------------|
| LCP | `largest-contentful-paint` | `audits["largest-contentful-paint"].numericValue` (ms) |
| INP | `interaction-to-next-paint` (older: `experimental-interaction-to-next-paint`) | `audits[...].numericValue` (ms) — often absent in lab runs |
| CLS | `cumulative-layout-shift` | `audits["cumulative-layout-shift"].numericValue` (unitless) |
| TTFB | `server-response-time` | `audits["server-response-time"].numericValue` (ms) |
| TBT | `total-blocking-time` | `audits["total-blocking-time"].numericValue` (ms) |
| FCP | `first-contentful-paint` | `audits["first-contentful-paint"].numericValue` (ms) |
| SI | `speed-index` | `audits["speed-index"].numericValue` (ms) |

A `metrics` array at the top level holds the same values under camelCase names (`largestContentfulPaint`, `cumulativeLayoutShift`, `interactionToNextPaint`, `serverResponseTime`, `totalBlockingTime`, `firstContentfulPaint`, `speedIndex`) with the field `value`.

Notes:

- `server-response-time` measures the main document response, so it is a good TTFB proxy. `server-response-time` also has a `details` breakdown per redirect and per origin when it is slow.
- Lighthouse usually does not produce INP unless the page was interacted with. If the audit is missing, treat INP as "not measured" and fall back to TBT as the lab proxy — and say that is what you did.
- `network-requests` under `audits` holds the full request list with transfer sizes — use it to find the biggest LCP asset.
- `unused-javascript`, `render-blocking-resources`, `uses-responsive-images`, `offscreen-images`, `font-display`, `third-party-summary`, `mainthread-work-breakdown`, `long-tasks`, `layout-shifts`, `cls-culprits-insight` are the diagnostic audits that tell you what to fix.

Running Lighthouse locally:

```bash
npx lighthouse https://example.com --output json --output-path "$TMPDIR/lh.json" --quiet
npx lighthouse https://example.com --preset=desktop --output json --output-path "$TMPDIR/lh-desktop.json" --quiet
```

Use the production build served locally or the deployed URL — never the dev server.

## Worked budget file example

```json
{
  "defaults": {
    "lcp": 2800,
    "inp": 250,
    "cls": 0.12,
    "ttfb": 900
  },
  "routes": {
    "/": { "lcp": 2200 },
    "/pricing": { "lcp": 2500 },
    "/blog/*": { "lcp": 3200, "cls": 0.15 },
    "/docs/*": { "lcp": 2000, "inp": 180 }
  }
}
```

How it resolves:

- `defaults` apply to every route with no specific match.
- `routes` keys are glob patterns matched against the path (`*` and `?` match any characters, including `/`); the most specific match wins, so `/blog/*` beats a catch-all.
- Route values override `defaults` per metric, not wholesale — `/` only sets LCP, the other metrics still come from `defaults`.
- Units are milliseconds for `lcp`, `inp`, `ttfb`, `tbt`, `fcp`, `si` and unitless for `cls`.
- A metric missing from the budget is not checked. A metric missing from the *report* is reported as `SKIP`, not as a pass.

## Setting the thresholds

Thresholds must be achievable from day one.

- Start from the measured baseline, not from the ideal. Set each threshold a little above today's p75 (about 5–10 percent of headroom), so the gate is green immediately and catches real regressions.
- Then tighten toward the "good" column (LCP 2500 ms, INP 200 ms, CLS 0.1, TTFB 800 ms) as the site improves, in separate steps.
- A budget that is red on the day it is added gets disabled within a week, and then the project has no gate at all.
- Record, in the PR body, the field p75 you based each threshold on. A budget without a stated baseline is arbitrary.

## Common false alarms

| False alarm | What is really happening |
|-------------|------------------------|
| "Lighthouse says 98, so the site is fast" | The score is not a Core Web Vital. Users get LCP, INP, CLS. A 98 score can hide a failing INP and a bad TTFB. |
| "We improved LCP from 4.1 s to 2.6 s" | Lab only. Field p75 may not have moved at all — or moved the other way. Say "lab" or say "field", never just "LCP improved". |
| "The dev build measured better than production" | Usually the opposite: dev has no minification, no compression, no CDN, and source maps. Always measure the production build. |
| "HTTP/3 made it faster" | One cold TLS handshake on a new connection can add more than HTTP/2 multiplexing saves. Compare the same number of requests over the same connection state. |
| "The first run was slow because of caching" | A cold cache penalizes every asset. Run at least three times, discard the first, and compare medians. State the run count in the report. |
| "Users in Europe saw worse numbers" | Geolocation changes the edge PoP, the network path, and the CDN cache hit rate. CrUX field data is geo-aggregated; lab runs are geo-local. Do not compare them. |
| "CLS improved after adding the banner" | Moving a banner usually trades CLS for something else, or the improvement came from setting image dimensions, not from the banner. Check `layout-shifts` and `cls-culprits-insight`. |
| "INP is missing, so it must be fine" | A missing audit means not measured, not good. Use TBT as the lab proxy and say so. |
| "The score dropped 6 points" | Lighthouse scores move run to run on the same build. A single run difference under about 10 points is noise. |
