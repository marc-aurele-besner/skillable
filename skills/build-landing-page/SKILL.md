---
name: build-landing-page
description: >-
  Scaffold, design, wire analytics, and deploy a production-grade landing page
  from a product idea, then return the live URL. Use whenever the user asks to
  build a landing page, marketing page, waitlist page, or launch page, or wants
  to go from idea to a deployed URL in one shot. Also triggers on
  /build-landing-page with the idea or product name.
argument-hint: "<product-idea>"
disable-model-invocation: false
---

# Build Landing Page

Goal: take a product idea and ship a live landing page in one run — scaffold the stack, design a distinctive page with real copy, wire working analytics, deploy to production, verify the live URL, and report it. One landing page, not a full product app.

## When to use

- "Build a landing page for …" / "I need a waitlist / launch / marketing page live today"
- `/build-landing-page <idea>`
- Not for rebuilding an existing app's authenticated UI — this is a standalone marketing page from idea to URL.

## 1. Take the idea

`$ARGUMENTS` or the user's message is the product: name, one-line pitch, audience. If the name, tagline, or CTA is missing, invent a sharp one — do not stall on a questionnaire. Ask only when the deploy target or domain is genuinely ambiguous (e.g. multiple linked Vercel projects) and cannot be inferred from the repo (`vercel.json`, `netlify.toml`, `.vercel/`, CI deploy workflows).

## 2. Stack (default, do not re-pick each run)

- **Default:** Next.js (App Router) + TypeScript + Tailwind CSS, scaffolded with `npx create-next-app@latest <slug> --typescript --tailwind --app --no-src-dir --import-alias "@/*"`.
- **Inside an existing project:** reuse that project's stack and deploy path instead of scaffolding a second framework. Detect it from the manifest/lockfile and follow the repo's package manager.
- Keep dependencies lean: the framework, Tailwind, one font pipeline (`next/font` with Google Fonts), and the analytics package. No UI kit, no CMS, no state library.

## 3. Design direction

The page must look intentional, not like a generic AI template. Concretely:

- **Type:** pick a bold display/body pairing loaded via `next/font` — never default Inter/Roboto/system-ui as the visible identity. Choose the pairing to fit the product's voice (e.g. a grotesk display over a readable serif, or a heavy slab over a neutral sans).
- **Color:** a constrained system — one dominant background, one ink, one accent tied to the product's domain. No purple-gradient-on-white hero unless the product genuinely calls for it.
- **One memorable visual idea** tied to the product: an oversized typographic hero, a diagram of what the product does, a live-looking demo panel, a texture or motif from the product's world. Build the page around it.
- **Layout rhythm:** vary section density and alignment; avoid three identical feature cards + fake testimonial row as the whole page.
- Responsive at desktop and mobile widths; check both before deploying.

## 4. Page content

- Write real copy for this specific idea — hero headline, subhead, section text, CTA labels. No lorem ipsum, no placeholder stock-photo walls.
- Sections follow the actual pitch (problem, product, proof, CTA) — not a fixed five-section template. Cut sections the idea doesn't need.
- One primary CTA (waitlist, signup, or "get started"). If it's email capture, implement a working path: a form posting to an API route that stores or forwards the address, or a documented provider integration — never a dead button.
- No auth, no dashboard, no extra routes unless the CTA requires them (an API route for the form is fine).

## 5. Analytics

Wire working analytics on first ship — no fake tracking snippets:

- **Default (Vercel host):** `@vercel/analytics` — install and render `<Analytics />` in the root layout. Works with zero config on Vercel.
- **Other hosts:** the host's first-party analytics if available, otherwise Plausible (`next-plausible` or the plain script tag) with the domain set.
- If a provider needs a key that's missing, leave a single clearly named env var (e.g. `NEXT_PUBLIC_PLAUSIBLE_DOMAIN`), document it in the report, and still deploy.

## 6. Deploy

- **Default host: Vercel**, production deploy via CLI: `vercel deploy --prod --yes` (add `--name <slug>` on first deploy if needed). If the repo already deploys elsewhere (Netlify, Cloudflare Pages), use that host's CLI instead.
- Run the production build locally first (`next build` or the repo's build script) and fix errors before deploying.
- Capture the live URL from the CLI output.
- Never commit `.env` files or secrets; never force-push.
- If the host CLI is not authenticated, stop and give the user the exact command to run (e.g. `vercel login`) — never fake or guess a URL.

## 7. Verify the live page

Open the live URL — browser tools if available, otherwise `curl -sL <url>` — and confirm:

1. The page returns 200 and the hero headline is present in the HTML.
2. The primary CTA is rendered (and the form endpoint responds if email capture).
3. The analytics snippet/runtime is actually in the served page (e.g. `/_vercel/insights` script or the Plausible script tag).

If anything is broken, fix and redeploy before reporting.

## 8. Report

End with:

- **Live URL**
- **Stack used** (framework, styling, fonts)
- **Where analytics lives** (provider, file wired in)
- **Env vars still needed**, if any
- **How to iterate** — the project directory, dev command, and redeploy command
