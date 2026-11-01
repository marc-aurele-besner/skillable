# PWA and mobile checklist

Score each finding with its tier from SKILL.md step 3. Auditor codes from `scripts/audit_pwa.py` are in `code` style.

## P0: broken on mobile

| Check | Fix |
|-------|-----|
| No viewport meta (`no-viewport`) | `<meta name="viewport" content="width=device-width, initial-scale=1">` |
| Viewport not `width=device-width` (`viewport-not-device-width`) | Same as above; a fixed width like `width=1024` renders a zoomed-out desktop page |
| Zoom disabled (`zoom-disabled`): `user-scalable=no` or `maximum-scale` < 2 | Remove both. It fails WCAG 1.4.4, and iOS ignores it anyway. Fix input-focus zoom with 16 px fonts instead |
| Horizontal scroll at 360 px (mobile check) | Fix the widest offender at its cause; never `overflow-x: hidden` on `body` as the only fix (it hides content and breaks `position: sticky`) |
| Manifest fails to parse (`manifest-invalid-json`) or linked file missing (`manifest-missing-file`) | Fix the file or the link |
| Icon in manifest 404s (`icon-missing-file`) | Generate or fix the path |
| SW registered but file missing (`sw-missing-file`) | Fix the path or the build output |
| SW serves navigations cache-first with no update path | Network-first for navigations; see service-worker.md |
| SW scope wider than the app on a shared origin | Serve it from the app's subpath or set `scope` |

## P1: not installable

Chromium's install criteria: served over HTTPS (or localhost), a linked manifest with `name` or `short_name`, `icons` with 192 px and 512 px, `start_url`, `display` of `standalone`, `fullscreen`, `minimal-ui` (or `window-controls-overlay`), and `prefer_related_applications` not `true`. A `fetch` handler is no longer required by Chrome, but keep one for offline support. iOS installs any page through Share → Add to Home Screen; the manifest and `apple-touch-icon` decide how it looks.

| Field / tag | Rule |
|-------------|------|
| `name` | Full app name, as in the UI |
| `short_name` | ≤ 12 characters so it is not cut off under the home-screen icon (`short-name-long`) |
| `id` | Stable identity, for example `"/"` or `"/?source=pwa"`. Set once, never change |
| `start_url` | Inside `scope`; a route that works logged out or redirects cleanly to login |
| `scope` | The app's path, usually `"/"` |
| `display` | `standalone` by default; `display_override` for `window-controls-overlay` on desktop |
| `theme_color` / `background_color` | From design tokens; `background_color` matches the first paint to avoid a flash on the splash screen |
| `icons` | PNG 192 and 512 `purpose: "any"`; a separate 512 PNG `purpose: "maskable"`. Avoid `"any maskable"` on one file (`icon-any-maskable`): it renders with too much padding or gets cropped |
| `<link rel="manifest">` | On every page (`no-manifest-link`) |
| `<meta name="theme-color">` | On every page (`no-theme-color`); add `media="(prefers-color-scheme: dark)"` variant if the app has a dark theme |
| `<link rel="apple-touch-icon">` | 180×180 PNG, opaque background (`no-apple-touch-icon`) |
| SW `Cache-Control` | `no-cache` or max-age ≤ a few minutes |

## P2: awkward on a phone

| Check | Fix |
|-------|-----|
| `viewport-fit=cover` without `env(safe-area-inset-*)` (`safe-area-unhandled`) | Pad fixed headers, footers, side rails |
| `100vh` without `dvh`/`svh` (`vh-without-dvh`) | `height: 100vh; height: 100dvh;` (fallback first) |
| Inputs with font-size < 16 px (`input-font-small`) | Raise to 16 px (1rem) to stop iOS zoom-on-focus |
| Inputs without type / inputmode (`input-no-keyboard-hint`) | `type="email"`, `type="tel"`, `inputmode="numeric"`, `inputmode="decimal"`, `type="search"`, `type="url"` |
| Inputs without autocomplete (`input-no-autocomplete`) | `email`, `name`, `tel`, `street-address`, `postal-code`, `current-password`, `new-password`, `one-time-code`, `cc-number` |
| Tap targets < 44×44 px (mobile check) | Padding or `min-height`/`min-width`; ≥ 8 px gap between neighbors |
| Body text < 16 px or tiny labels (mobile check) | 16 px body is the mobile baseline; never below 12 px |
| Hover-only interactions | Also open on click/focus; wrap hover styles in `@media (hover: hover)` |
| Images without width/height (`img-no-dimensions`) | Add dimensions or `aspect-ratio` to stop layout shift |
| No `lang` (`no-lang`) | Needed for correct hyphenation, voice-over, and translation prompts |

## P3: feels native

- Offline fallback page precached and served when a navigation fails (`no-offline-fallback`).
- "Update available" prompt when a new SW is waiting, instead of silent `skipWaiting` mid-session.
- Install button on `beforeinstallprompt`; iOS Safari "Add to Home Screen" hint, dismissible, shown once.
- `screenshots` with at least one `form_factor: "narrow"` and one `"wide"`, plus `description`, for the richer install sheet on Android and desktop (`no-screenshots`).
- `shortcuts` for the 2–4 most common entry points (long-press on the icon).
- `@media (display-mode: standalone)` styling: hide web-only install banners, show an in-app back control when navigation relies on the browser back button.
- `overscroll-behavior: contain` on modals and inner scroll areas; `overscroll-behavior-y: none` on the app shell only if pull-to-refresh is unwanted.
- `-webkit-tap-highlight-color: transparent` paired with a visible `:active` / `:focus-visible` state.
- `prefers-reduced-motion` respected for page transitions.
- Native share: `navigator.share` where the app has a share action, with a copy-link fallback.

## Report only

- Push notifications (needs a backend and VAPID keys; iOS needs the app installed, 16.4+).
- Background sync, periodic sync, share target, file handling, protocol handlers.
- Store packaging: PWABuilder, Bubblewrap / Trusted Web Activity for Play Store.
- Host configuration not in the repo: HTTPS redirect, HSTS, SW headers, CSP.
- Performance beyond quick wins (bundle splitting, image pipeline).
