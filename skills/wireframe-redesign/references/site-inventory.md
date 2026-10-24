# Site inventory: finding every page and feature

Read what exists; skip the rest. The source of truth is the router and the content files, not the nav — nav menus routinely omit pages.

## Routes by stack

| Stack | Look in |
| --- | --- |
| Next.js (app router) | `app/**/page.{tsx,jsx,mdx}`, route groups `(group)`, dynamic `[slug]` / `[...slug]`, `generateStaticParams`, `not-found.tsx`, `middleware.ts` redirects and auth gates |
| Next.js (pages router) | `pages/**/*.{tsx,jsx}`, `getStaticPaths`, `_app`, `404.tsx` |
| Remix / React Router | `app/routes/**`, `routes.ts`, `createBrowserRouter([...])` |
| SvelteKit | `src/routes/**/+page.svelte`, `+layout.svelte`, `+page.server.ts` guards |
| Nuxt / Vue Router | `pages/**/*.vue`, `router/index.{ts,js}`, `middleware/` |
| Astro | `src/pages/**`, content collections in `src/content/` |
| Angular | `app.routes.ts`, `*-routing.module.ts`, `canActivate` guards |
| Rails / Django / Laravel | `config/routes.rb`, `urls.py`, `routes/web.php` |
| Static / unknown | `sitemap.xml`, `robots.txt`, `_redirects`, `vercel.json` / `netlify.toml` rewrites |

For each dynamic route, pick one or two real slugs from the content so the prototype opens real records.

## Features and gates

```bash
# Forms, validation, and actions
rg -n -g '!node_modules' -e '<form' -e 'useForm' -e 'zod' -e 'yup' -e 'action=' -e 'onSubmit' .

# Auth, roles, quotas, paywalls
rg -n -g '!node_modules' -i -e 'role' -e 'isAdmin' -e 'subscription' -e 'stripe' -e 'quota' -e 'rateLimit' -e 'paywall' -e 'getServerSession' -e 'auth(' .

# Search, filters, pagination, query-string state
rg -n -g '!node_modules' -e 'useSearchParams' -e 'searchParams' -e 'paginate' -e 'cursor' -e 'sort' .

# Async, streaming, toasts, shortcuts
rg -n -g '!node_modules' -e 'stream' -e 'EventSource' -e 'toast' -e 'useHotkeys' -e 'keydown' .
```

Also read: API route handlers (they reveal features with no obvious page), email templates (flows like reset password), and analytics events (they name the interactions the team cares about).

## Content

- Seeds and fixtures: `prisma/seed.*`, `db/seeds`, `fixtures/`, `data/*.json`, `content/**/*.{md,mdx,json}`, CMS exports.
- Types and schemas give the fields detail pages need: Prisma / Drizzle schema, `types/`, OpenAPI, GraphQL.
- Write a small Bun or Node script (outside the project tree, e.g. in a scratch directory) that loads the content and prints one compact JSON object with only the fields the prototype renders, plus real totals. Embed its output as `window.<APP>_DATA`.

## Crawling a URL (no source)

1. Fetch `/sitemap.xml` (and sitemap indexes) and `/robots.txt`; list every path.
2. Fetch the home page, then follow internal links breadth-first; group URLs by pattern (`/emoji/:slug`) and fetch two or three examples per pattern rather than every page.
3. Record nav and footer labels, forms (fields, validation messages from the HTML), and visible states. Sign-in and admin areas are not crawlable: infer them from what public pages link to, and mark them as assumed in the report.
4. Copy only public content, keep it small, and never submit forms or create accounts on the live site.
