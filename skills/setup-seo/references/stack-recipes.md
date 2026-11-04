# Stack recipes

Where the IndexNow key file goes, where the sitemap and robots.txt live, and where to hook the post-build ping. Prefer what the project already uses — check the installed framework version (`npm ls <pkg>` or the lockfile) before choosing an API, since these move between majors.

```bash
rg -n -g '!node_modules' -e 'sitemap' -e 'robots' -e 'publicDir' -e 'assets' -e 'postbuild' -e 'build' package.json astro.config.* nuxt.config.* next.config.* svelte.config.* gatsby-config.* vite.config.* 2>/dev/null | head -40
rg --files -g '!node_modules' -g 'sitemap*' -g 'robots*' -g 'vercel.json' -g 'netlify.toml' -g 'wrangler.toml' -g '.github/workflows/*'
```

## Where the key file goes

The key file must be served at the site root, so it must live in the directory the framework copies verbatim to the deploy root.

| Stack | Key file dir | Sitemap | robots.txt |
|-------|--------------|---------|------------|
| Next.js (App/Pages) | `public/` | `app/sitemap.ts` or `pages/sitemap.xml.ts` | `app/robots.ts` or `public/robots.txt` |
| Astro | `public/` | `@astrojs/sitemap` | `public/robots.txt` or `src/pages/robots.txt.ts` |
| Nuxt / Nitro | `public/` | `@nuxtjs/sitemap` | `@nuxtjs/robots` or `public/robots.txt` |
| SvelteKit | `static/` | `src/routes/sitemap.xml/+server.ts` | `src/routes/robots.txt/+server.ts` |
| Gatsby | `static/` | `gatsby-plugin-sitemap` | `gatsby-plugin-robots-txt` or `static/robots.txt` |
| Remix / React Router | `public/` | `app/routes/sitemap[.]xml.ts` | `app/routes/robots[.]txt.ts` |
| Vite SPA / CRA | `public/` | `vite-plugin-sitemap` or a prebuild script | `public/robots.txt` |
| VitePress | `public/` | built in (`sitemap.hostname`) | `public/robots.txt` |
| Docusaurus | `static/` | built in (`sitemap` option) | `static/robots.txt` |
| Hugo | `static/` | built in | `enableRobotsTXT` + `layouts/robots.txt` |
| Jekyll | repo root (or `static/`) | `jekyll-sitemap` | `robots.txt` at root |
| Eleventy | root (passthrough) | `sitemap.njk` | `robots.njk` |
| Angular | `src/assets/` (check `angular.json` assets) | `sitemap` builder | `src/assets/robots.txt` |
| Django / Rails / Laravel | `public/` | framework sitemap app | `public/robots.txt` |
| Plain HTML | repo root | hand-written `sitemap.xml` | `robots.txt` at root |

`python3 -I scripts/indexnow_setup.py plan --root .` prints the detected stack, the directory it picked, and any key file, `sitemap.xml`, or `robots.txt` it already found.

## Hooking the ping

Submit **changed URLs only**. Compute them from the diff, map file paths to public routes, and pass them to the submit script.

### Any stack — a build script

Add a post-build step that runs after the site is built and deployed:

```jsonc
// package.json
{
  "scripts": {
    "build": "next build && npm run sitemap",  // whatever the project already runs
    "postbuild": "node scripts/indexnow-submit.mjs"
  }
}
```

The submit script should fail soft: a failed ping must not break the deploy. Log the failure and exit 0.

### Next.js

- Key file: `public/<key>.txt`.
- Sitemap: `app/sitemap.ts` returning `MetadataRoute.Sitemap`; build it from the same data that drives `generateStaticParams`.
- Robots: `app/robots.ts` returning `MetadataRoute.Robots`, including `sitemap: `${siteUrl}/sitemap.xml``.
- Changed routes: `git diff --name-only origin/main...HEAD -- app | sed -E 's#^app(.*)/page\.(tsx|ts|jsx|js)$#\1#'` (strip the root route to `/`).

### Astro

- Key file: `public/<key>.txt`.
- Sitemap: `@astrojs/sitemap` (needs `site` in `astro.config`).
- Robots: `public/robots.txt`.
- Changed routes: map changed files under `src/pages/` to their route paths (strip the file extension, `index` → the directory).

### Nuxt / Nitro

- Key file: `public/<key>.txt`.
- Sitemap: `@nuxtjs/sitemap` or `server/routes/sitemap.xml.ts`.
- Robots: `@nuxtjs/robots` or `public/robots.txt`.
- Changed routes: pages under `pages/` (or `app/pages/` in Nuxt 4) map 1:1 to routes.

### SvelteKit

- Key file: `static/<key>.txt` (copied to the adapter output for `adapter-static`; for `adapter-node`/serverless, serve it from a `+server.ts` route instead).
- Sitemap: `src/routes/sitemap.xml/+server.ts` with `export const prerender = true`.

### Gatsby

- Key file: `static/<key>.txt`.
- Sitemap: `gatsby-plugin-sitemap` (needs `siteUrl` in `gatsby-config`).
- Changed routes: `src/pages/**` → route path.

### Vite SPA / VitePress

- Key file: `public/<key>.txt`.
- Sitemap: `vite-plugin-sitemap` (needs `site` in the config) or a small prebuild script that walks the route table.
- A SPA that ships one `index.html` for every route needs prerendering (`vite-plugin-ssg`, `vite-react-ssg`, `react-snap`) before a sitemap means anything. Say so if it does not.

### Hugo / Jekyll / Eleventy / Docusaurus

- Key file: `static/` (Hugo, Docusaurus) or the root/passthrough directory (Jekyll, Eleventy).
- Sitemap: built in — set `baseURL`/`siteUrl`/`url` so the absolute URLs are right.
- Changed routes: map changed content files to their output paths.

### Plain HTML / other

- Key file: repo root (it is served as-is).
- Sitemap: hand-written, or a tiny script that lists the HTML files.

## Where the ping runs

Pick the place that already exists in the project — do not add a CI provider that the project does not use.

| Target | Where to hook |
|--------|---------------|
| Vercel | `package.json` `postbuild`, or a Build Step in project settings |
| Netlify | `package.json` `postbuild`, or the `post` field in `netlify.toml` |
| Cloudflare Pages | `package.json` `postbuild`, or the Pages build command |
| GitHub Pages | a step after the Pages deploy job, or the Pages build |
| GitHub Actions → any host | a job step after the deploy step, using repository secrets |
| Self-hosted / Docker | the entrypoint after the container is healthy, or a cron that diffs against the last deploy |

### GitHub Actions example

```yaml
- name: Notify IndexNow
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  run: |
    python3 -I scripts/indexnow-submit.py \
      --host "${{ vars.SITE_URL }}" \
      --key "${{ secrets.INDEXNOW_KEY }}" \
      --key-location "${{ vars.SITE_URL }}/${{ secrets.INDEXNOW_KEY }}.txt" \
      --url "https://${{ vars.SITE_URL }}/new-page"
  continue-on-error: true
```

Set `SITE_URL` as a repository **variable** (public) and `INDEXNOW_KEY` as a repository **secret** (or a variable — it is published anyway, but a secret keeps it out of the workflow logs). `continue-on-error: true` keeps a failed ping from failing the deploy.

### GitHub Actions — sitemap-driven variant

When the project cannot map diffs to routes, submit the sitemap's URLs instead — once, not on every commit:

```bash
python3 -I scripts/indexnow-submit.py \
  --host "$SITE_URL" --key "$INDEXNOW_KEY" \
  --sitemap "$SITE_URL/sitemap.xml"
```

Only do this when the sitemap is small and the deploy is infrequent; it is a blunt instrument and repeated full-site submissions risk the 429 rate limit.

## Verification tokens and site-wide head tags

If the project has a shared layout/head component, the engine verification meta tags go there:

- Next.js App Router: `app/layout.tsx` → `metadata.verification = { google: "…", other: { "msvalidate.01": "…" } }`.
- Next.js Pages Router: `next/head` in `_app.tsx`.
- Astro: the head component in `src/layouts/`.
- Nuxt: `app.head` in `nuxt.config.ts`.
- SvelteKit: `<svelte:head>` in `+layout.svelte`.
- Plain HTML: every `<head>`.

If the project has no shared head, list the tokens as a manual follow-up instead of hand-editing dozens of files.
