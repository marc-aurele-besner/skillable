# Per-stack i18n recipes

Concrete file layouts, routing, and string extraction for the stacks this skill is likely to meet. **Prefer what the project already uses.** Check the installed version first (`npm ls <pkg>`, or the lockfile) — the APIs below move between majors.

```bash
rg -n -g '!node_modules' -e 'i18n' -e 'locale' -e 'lang' package.json next.config.* astro.config.* nuxt.config.* svelte.config.* remix.config.* vite.config.* 2>/dev/null | head -40
rg --files -g '!node_modules' -g 'locales/**' -g 'messages/**' -g 'i18n/**' -g 'lang/**' | head -40
```

| Stack | Mechanism | Catalog location | Routing |
|-------|-----------|------------------|---------|
| Next.js (App Router) | built-in `[locale]` segment + middleware | `messages/<locale>.json` | `app/[locale]/…` |
| Next.js (Pages Router) | `next-i18next` or built-in i18n config | `locales/<locale>.json` | `next.config.js` `i18n.locales` |
| Astro | `astro:i18n` + a routing integration | `src/i18n/<locale>.json` | `src/pages/[locale]/…` |
| Nuxt | `@nuxtjs/i18n` | `i18n/locales/*.json` | file-based, `pages/[locale]/` or prefix strategy |
| SvelteKit | `[lang]` route param + `handle` | `src/lib/i18n/<locale>.json` | `src/routes/[lang]/…` |
| Remix / React Router | locale segment + `loader` | `app/locales/<locale>.json` | `app/routes/$locale./*` |
| Angular | `@angular/localize` | `src/locale/messages.<locale>.xlf` | built-in `$localize` |
| Vue / Vite SPA | `vue-i18n` | `src/locales/<locale>.json` | client-side, `vue-router` locale prefix |
| Rails | `I18n` | `config/locales/<locale>.yml` | `scope :locale` |
| Django | `gettext` | `locale/<lang>/LC_MESSAGES/django.po` | `LocaleMiddleware` |
| Laravel | `lang/<locale>/*.php` | `lang/` | `App::setLocale` |
| Plain HTML / Jekyll / Hugo | a catalog file + a small build step | `locales/<locale>.json` | per-locale output folders |

---

## Next.js — App Router

Next has i18n built in since v13.4 (the App Router's `[locale]` segment, `i18n` config in `next.config`, and `middleware.ts`). Use it; do not add `next-intl` unless the project already uses it.

### Layout

```text
app/
  layout.tsx            # root: passes <html lang> and <html dir> through
  [locale]/
    layout.tsx          # sets <html lang={locale} dir={dir}>
    page.tsx            # /
    about/page.tsx      # /about
  sitemap.ts
  robots.ts
middleware.ts
messages/
  en.json
  fr.json
  ar.json
```

### `next.config`

```js
// next.config.mjs
const nextConfig = {
  i18n: {
    locales: ["en", "fr", "ar"],
    defaultLocale: "en",
  },
};
export default nextConfig;
```

### Middleware — detection and redirect

Detect the locale **once**, redirect, then remember the choice. Do not rewrite every request from `Accept-Language` — the URL must be stable for crawlers and caches.

```ts
// middleware.ts
import { NextResponse, type NextRequest } from "next/server";

const LOCALES = ["en", "fr", "ar"] as const;
const DEFAULT_LOCALE = "en";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasLocale = LOCALES.some(
    (l) => pathname === `/${l}` || pathname.startsWith(`/${l}/`),
  );
  if (hasLocale) return NextResponse.next();

  // 1. an explicit choice wins
  const cookieLocale = request.cookies.get("NEXT_LOCALE")?.value;
  // 2. then Accept-Language
  const headerLocale = request.headers
    .get("accept-language")
    ?.split(",")
    .map((v) => v.split(";")[0].trim().toLowerCase())
    .find((v) => LOCALES.includes(v as (typeof LOCALES)[number]));

  const locale = cookieLocale ?? headerLocale ?? DEFAULT_LOCALE;
  const url = request.nextUrl.clone();
  url.pathname = `/${locale}${pathname === "/" ? "" : pathname}`;
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};
```

### `app/[locale]/layout.tsx` — `lang` and `dir`

```tsx
import { notFound } from "next/navigation";
import { getDictionary } from "@/i18n/dictionary";

const locales = ["en", "fr", "ar"];
const rtl = new Set(["ar", "he", "fa", "ur"]);

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!locales.includes(locale)) notFound();

  const dict = await getDictionary(locale);
  const dir = rtl.has(locale) ? "rtl" : "ltr";

  return (
    <html lang={locale} dir={dir}>
      <body>{children}</body>
    </html>
  );
}
```

### Metadata per locale

```tsx
// app/[locale]/page.tsx
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const dict = await getDictionary(locale);
  return {
    title: dict.home.title,
    description: dict.home.description,
    alternates: {
      canonical: `/${locale}`,
      languages: {
        en: "/en",
        fr: "/fr",
        ar: "/ar",
        "x-default": "/en",
      },
    },
    openGraph: {
      title: dict.home.title,
      description: dict.home.description,
      locale: "fr_FR",            // og:locale uses underscores, unlike hreflang
      alternateLocale: ["en_US", "ar_AR"],
    },
  };
}
```

### Dictionary loading

```ts
// i18n/dictionary.ts
import "server-only";

const dictionaries = {
  en: () => import("@/messages/en.json").then((m) => m.default),
  fr: () => import("@/messages/fr.json").then((m) => m.default),
  ar: () => import("@/messages/ar.json").then((m) => m.default),
};

export type Dictionary = Awaited<ReturnType<(typeof dictionaries)["en"]>>;

export async function getDictionary(locale: string): Promise<Dictionary> {
  return (dictionaries[locale as keyof typeof dictionaries] ?? dictionaries.en)();
}
```

> `getDictionary` as shown is a server helper. For client components, pass the dictionary down as props, or use `next-intl`'s provider if the project already uses it.

### Redirects from old URLs

```ts
// next.config.mjs
async redirects() {
  return [
    { source: "/about", destination: "/en/about", permanent: true },
    { source: "/fr/a-propos", destination: "/fr/about", permanent: true },
  ];
}
```

---

## Astro

Astro has `astro:i18n` helpers but **no built-in routing**. Use `@astrojs/i18n` (the community integration) or a hand-rolled `[locale]` directory.

### Layout

```text
src/
  i18n/
    index.ts          # locales, ui strings, routing helpers
    ui.ts             # { en: { home: { title: "…" } }, fr: { … } }
  pages/
    index.astro       # redirect to the default locale
    [locale]/
      index.astro
      about.astro
astro.config.mjs
```

### Routing helper

```ts
// src/i18n/index.ts
export const locales = ["en", "fr", "ar"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "en";

export function isLocale(value: string | undefined): value is Locale {
  return locales.includes(value as Locale);
}

export function t(locale: Locale, path = "/"): string {
  const suffix = path === "/" ? "" : path.startsWith("/") ? path : `/${path}`;
  return `/${locale}${suffix}`;
}
```

### Page

```astro
---
// src/pages/[locale]/index.astro
import { locales, defaultLocale, isLocale, t } from "../../i18n";
import { ui } from "../../i18n/ui";

export function getStaticPaths() {
  return locales.map((locale) => ({ params: { locale } }));
}

const { locale } = Astro.params;
if (!isLocale(locale)) return Astro.redirect(`/${defaultLocale}`);
const strings = ui[locale];
---
<html lang={locale} dir={locale === "ar" ? "rtl" : "ltr">
  <head>
    <link rel="canonical" href={t(locale)} />
    <link rel="alternate" hreflang="en" href={t("en")} />
    <link rel="alternate" hreflang="fr" href={t("fr")} />
    <link rel="alternate" hreflang="x-default" href={t(defaultLocale)} />
    <title>{strings.home.title}</title>
  </head>
  <body>
    <h1>{strings.home.heading}</h1>
  </body>
</html>
```

---

## Nuxt

`@nuxtjs/i18n` is the standard. It handles routing, the `switchLocalePath` helper, SEO (`useLocaleHead` for `hreflang`), and date/number formats.

```bash
npx nuxi module add @nuxtjs/i18n
```

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  modules: ["@nuxtjs/i18n"],
  i18n: {
    defaultLocale: "en",
    strategy: "prefix_except_default",  // or "prefix" for every locale
    locales: [
      { code: "en", language: "en-US", name: "English", file: "en.json" },
      { code: "fr", language: "fr-FR", name: "Français", file: "fr.json" },
      { code: "ar", language: "ar", name: "العربية", file: "ar.json", dir: "rtl" },
    ],
    langDir: "locales",
    bundle: { optimizeTranslationDirective: false },
  },
});
```

```vue
<!-- pages/[locale]/index.vue -->
<script setup lang="ts">
const { locale, locales, t, switchLocalePath } = useI18n();
const head = useLocaleHead({ addSeoAttributes: true });
const rtlLocales = new Set(["ar", "he", "fa", "ur"]);
const dir = computed(() => (rtlLocales.has(locale.value) ? "rtl" : "ltr"));
useHead(() => ({ htmlAttrs: { lang: locale.value, dir: dir.value }, link: head.value.link }));
</script>

<template>
  <h1>{{ t("home.heading") }}</h1>
  <NuxtLink v-for="l in locales" :key="l.code" :to="switchLocalePath(l.code)">
    {{ l.name }}
  </NuxtLink>
</template>
```

`useLocaleHead` emits the `hreflang` alternates and `x-default` automatically. Verify them anyway — the bundled auditor exists for exactly this.

---

## SvelteKit

SvelteKit has no i18n built in. The idiomatic approach is a `[lang]` route parameter plus a `handle` hook that validates it. (A route group `(lang)` groups files but adds no URL segment — use `[lang]` when the locale must be in the URL.)

### Layout

```text
src/routes/
  [lang]/
    +layout.ts        # validates lang, sets locale in the store
    +layout.server.ts # loads the catalog for the locale
    +page.ts
    about/+page.ts
  api/
  +layout.ts
src/lib/i18n/
  locales.ts
  en.json
  fr.json
  ar.json
```

### `handle` — validate the locale

```ts
// src/hooks.server.ts
import type { Handle } from "@sveltejs/kit";
import { locales, defaultLocale } from "$lib/i18n/locales";

export const handle: Handle = async ({ event, resolve }) => {
  const lang = event.params.lang;
  if (!lang || !locales.includes(lang)) {
    // redirect to the default locale, keeping the rest of the path
    return new Response(null, {
      status: 302,
      headers: { location: `/${defaultLocale}${event.url.pathname.replace(/^\/[a-z]{2}/, "")}` },
    });
  }
  event.locals.lang = lang;
  return resolve(event);
};
```

```ts
// src/app.d.ts
declare global {
  namespace App {
    interface Locals {
      lang: (typeof locales)[number];
    }
  }
}
```

### Layout — `lang` and `dir`

```svelte
<!-- src/routes/[lang]/+layout.svelte -->
<script lang="ts">
  import { rtlLocales } from "$lib/i18n/locales";
  export let data;
  $: lang = data.lang;
  $: dir = rtlLocales.includes(lang) ? "rtl" : "ltr";
</script>

<svelte:head>
  <!-- one alternate per locale, plus x-default; see references/hreflang.md -->
  <link rel="alternate" hreflang="en" href={`/en${data.path}`} />
  <link rel="alternate" hreflang="fr" href={`/fr${data.path}`} />
  <link rel="alternate" hreflang="x-default" href={`/en${data.path}`} />
</svelte:head>

<html lang={lang} dir={dir}>
  <slot />
</html>
```

The alternates must point at the *same page* in each locale. Build them from the current route's path, not from a fixed string — a layout that hardcodes `/` produces `/fr/` alternates on every page, which breaks reciprocity.

The `lang` param comes from the group directory name in the URL; make the group's segment configurable via `+layout.ts` `entries` if you need `/en/` and `/fr/` rather than a bare group.

---

## Remix / React Router

The locale is a route parameter; the loader loads the catalog and provides the locale to the app.

```text
app/
  routes/
    $locale._index.tsx
    $locale.about.tsx
    $.tsx               # catch-all: redirect to a locale
  locales/
    en.json
    fr.json
  entry.server.tsx
  root.tsx
```

```ts
// app/routes/$locale.about.tsx
import { json } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";
import { getLocale, isLocale, locales } from "~/locales";

export async function loader({ params }: { params: { locale?: string } }) {
  if (!isLocale(params.locale)) throw new Response("Not Found", { status: 404 });
  return json({
    locale: params.locale,
    strings: await getLocale(params.locale),
    alternates: Object.fromEntries(
      locales.map((l) => [l, `/${l}/about`]),
    ),
  });
}

export default function About() {
  const { locale, strings, alternates } = useLoaderData<typeof loader>();
  return (
    <>
      <head>
        <link rel="canonical" href={`/${locale}/about`} />
        {Object.entries(alternates).map(([l, href]) => (
          <link key={l} rel="alternate" hrefLang={l} href={href} />
        ))}
        <link rel="alternate" hrefLang="x-default" href="/en/about" />
      </head>
      <h1>{strings.about.title}</h1>
    </>
  );
}
```

---

## Plain HTML, Jekyll, Hugo, Eleventy

No framework routing, so build per-locale output directories and generate the tags.

```text
locales/
  en.json
  fr.json
templates/
  page.html
build.mjs             # renders every locale into build/<locale>/...
build/
  en/index.html
  fr/index.html
```

A minimal build step (Node, stdlib only):

```js
// build.mjs
import { readFile, writeFile, mkdir } from "node:fs/promises";

const locales = ["en", "fr"];
const strings = Object.fromEntries(
  await Promise.all(
    locales.map(async (l) => [l, JSON.parse(await readFile(`locales/${l}.json`, "utf8"))]),
  ),
);

for (const locale of locales) {
  const s = strings[locale];
  const html = `<!doctype html>
<html lang="${locale}"${locale === "ar" ? ' dir="rtl"' : ""}>
<head>
<meta charset="utf-8">
<title>${s.title}</title>
<link rel="canonical" href="/${locale}/">
${locales.map((l) => `<link rel="alternate" hreflang="${l}" href="/${l}/">`).join("\n")}
<link rel="alternate" hreflang="x-default" href="/en/">
</head>
<body><h1>${s.heading}</h1></body>
</html>`;
  await mkdir(`build/${locale}`, { recursive: true });
  await writeFile(`build/${locale}/index.html`, html);
}
```

Run it from the existing build script, so the deploy stays one command.

---

## Extracting strings

Use the tool the stack or the installed library expects. Do not hand-copy strings into a catalog.

| Library | Extraction command | Notes |
|---------|-------------------|-------|
| FormatJS / react-intl | `npx formatjs extract src --out-file messages/en.json` | `--id-interpolation-pattern` keeps explicit IDs; `--format` writes ICU |
| Lingui | `npx lingui extract` | Catalogs in `src/locales/*.po` or `.json`; compile with `npx lingui compile` |
| i18next / i18next-parser | `npx i18next-parser 'src/**/*.{ts,tsx}'` | Needs `i18next-parser` in devDependencies |
| vue-i18n | `npx vue-i18n-extract 'src/**/*.vue'` | Or `@intlify/vue-i18n-extract` |
| Rails | `bin/rails gettext:find` then `rails g gettext:locale fr` | `.po` files; compile at boot |
| Django | `django-admin makemessages -l fr` then `compilemessages` | `.po` in `locale/<lang>/LC_MESSAGES/` |
| Angular | `ng extract-i18n` | XLIFF `.xlf`; add `localize` to the build |
| Plain / custom | a small script that greps for the call expression | Keep it in `scripts/`, run it in `npm run` before the build |

### The missing-key check

The check must fail the build. Pick the one the project can support:

```bash
# 1. FormatJS / Lingui already fail on a missing message at compile time — verify it
npx lingui compile --strict

# 2. i18next: compare the extracted catalog against the locale catalogs
node scripts/check-missing-keys.mjs

# 3. A generic check for JSON catalogs: every key in the source must exist in every locale
node scripts/check-missing-keys.mjs locales/en.json locales/fr.json
```

A tiny generic checker:

```js
// scripts/check-missing-keys.mjs
import { readFile } from "node:fs/promises";

const [source, ...targets] = process.argv.slice(2);

function flatten(obj, prefix = "") {
  return Object.entries(obj).flatMap(([k, v]) => {
    const key = prefix ? `${prefix}.${k}` : k;
    return v && typeof v === "object" ? flatten(v, key) : [[key, v]];
  });
}

const sourceKeys = new Set(flatten(JSON.parse(await readFile(source, "utf8"))).map(([k]) => k));
let failed = false;

for (const target of targets) {
  const targetKeys = new Set(flatten(JSON.parse(await readFile(target, "utf8"))).map(([k]) => k));
  const missing = [...sourceKeys].filter((k) => !targetKeys.has(k));
  const extra = [...targetKeys].filter((k) => !sourceKeys.has(k));
  if (missing.length || extra.length) {
    failed = true;
    console.error(`${target}: ${missing.length} missing, ${extra.length} stale`);
    for (const k of missing) console.error(`  missing: ${k}`);
    for (const k of extra) console.error(`  stale:   ${k}`);
  }
}

if (failed) process.exit(1);
```

Wire it into the existing CI job (test or lint), not as a new workflow. Keep the extracted source catalog as the single source of truth: `npm run extract` regenerates it, and the checker diffs every locale against it.
