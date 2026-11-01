# Mobile UX details

Things that make a web app feel broken or native on a phone, with the CSS and HTML that fix them. Apply with the project's styling approach (tokens, Tailwind, CSS modules); the raw CSS below is the intent.

## Viewport

```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
```

- Add `viewport-fit=cover` only together with safe-area padding (below); otherwise content goes under the notch.
- Never `user-scalable=no` or `maximum-scale=1`. People with low vision need pinch-zoom.
- `interactive-widget=resizes-content` makes the on-screen keyboard shrink the layout viewport on Android Chrome. It helps chat-like apps with a bottom composer; leave it out otherwise.

## Safe areas (notch, rounded corners, home indicator)

```css
.app-header { padding-top: max(12px, env(safe-area-inset-top)); }
.bottom-nav { padding-bottom: max(8px, env(safe-area-inset-bottom)); }
.app-shell  { padding-left: env(safe-area-inset-left); padding-right: env(safe-area-inset-right); }
```

Tailwind: arbitrary values `pb-[max(0.5rem,env(safe-area-inset-bottom))]`, or a `tailwindcss-safe-area` plugin if already installed. Check landscape too: the insets move to the sides.

## Viewport height

`100vh` on mobile is the height with the browser toolbar hidden, so full-height screens get cut off or jump.

```css
.screen { min-height: 100vh; min-height: 100dvh; }   /* dvh tracks the toolbar */
.hero   { height: 100svh; }                           /* svh: stable, smallest */
```

Use `dvh` for app shells, `svh` for heroes that must not resize while scrolling. Remove old `--vh` JS hacks only when they are fully replaced.

## Touch targets

- Minimum 44×44 CSS px (Apple), 48×48 recommended (Material). WCAG 2.2 AA minimum is 24×24 with spacing.
- Grow the hit area with padding or a pseudo-element, not by scaling the icon:
  ```css
  .icon-btn { position: relative; }
  .icon-btn::after { content: ""; position: absolute; inset: -10px; }
  ```
- At least 8 px between adjacent targets, especially in lists, toolbars, and pagination.
- Put primary actions in the thumb zone (bottom half) on mobile layouts: bottom nav or a sticky bottom action bar for long forms.

## Forms and the on-screen keyboard

| Field | Markup |
|-------|--------|
| Email | `type="email" autocomplete="email" autocapitalize="off" spellcheck="false"` |
| Phone | `type="tel" autocomplete="tel"` |
| One-time code | `inputmode="numeric" autocomplete="one-time-code" pattern="\d*"` |
| Integer (quantity, PIN) | `inputmode="numeric"` (not `type="number"`, which adds spinners and accepts `e`) |
| Price, decimal | `inputmode="decimal"` |
| Search | `type="search" enterkeyhint="search"` |
| URL | `type="url" autocomplete="url"` |
| Name, address | `autocomplete="name"`, `"street-address"`, `"postal-code"`, `"country"` |
| Password | `autocomplete="current-password"` or `"new-password"` |
| Last field of a form | `enterkeyhint="done"` or `"send"` |

- Input, select, and textarea font size ≥ 16 px, or iOS Safari zooms in on focus.
- Labels above fields, not placeholders as labels.
- Keep the focused field visible: avoid fixed footers covering inputs; `scroll-margin-bottom` on inputs helps.

## Hover, focus, and taps

- Hover-only reveals (menus, tooltips, row actions) are invisible on touch. Make them open on tap and on `:focus-within`, and scope hover styling:
  ```css
  @media (hover: hover) and (pointer: fine) { .row:hover .actions { opacity: 1; } }
  ```
- `touch-action: manipulation` on custom buttons and controls removes double-tap-to-zoom delay without disabling pinch-zoom.
- If `-webkit-tap-highlight-color: transparent` is set, provide a visible `:active` state.

## Layout and overflow

- Mobile-first breakpoints; test 320, 360, 390, 414 px widths.
- Common causes of horizontal scroll: fixed `width` in px, `100vw` (includes the scrollbar), long URLs or tokens (`overflow-wrap: anywhere`), tables and `<pre>` (wrap in a container with `overflow-x: auto`), flex/grid children without `min-width: 0`, negative margins, absolutely positioned decorations.
- Media: `img, video, svg { max-width: 100%; height: auto; }` and explicit `width`/`height` or `aspect-ratio` to stop layout shift.
- Modals on mobile: full-screen or bottom sheet, `overscroll-behavior: contain`, lock body scroll without jumping (`scrollbar-gutter: stable` on desktop).

## Typography

- 16 px body baseline; line length 45–75 characters; `line-height` 1.4–1.6.
- `-webkit-text-size-adjust: 100%; text-size-adjust: 100%;` on `html` to stop iOS inflating text in landscape.
- Fluid sizes with `clamp()` for headings rather than many breakpoints.

## Standalone mode (installed app)

```css
@media (display-mode: standalone), (display-mode: fullscreen) {
  .install-banner { display: none; }
  body { overscroll-behavior-y: none; }    /* only if pull-to-refresh is unwanted */
}
```

- No browser back button in standalone on iOS: make sure every screen has an in-app way back.
- External links: open off-scope links in the browser (`target="_blank" rel="noopener"`).
- `user-select: none` only on chrome (nav, buttons), never on content.

## iOS specifics

- `apple-touch-icon` 180×180, opaque. iOS ignores manifest icons for the home screen on older versions.
- `<meta name="apple-mobile-web-app-title" content="Short name">` when `short_name` should differ from `<title>`.
- `<meta name="apple-mobile-web-app-status-bar-style" content="default">` (`black-translucent` only with safe-area padding at the top). `apple-mobile-web-app-capable` is legacy; the manifest `display` replaces it, but keeping it is harmless for old iOS.
- Startup images (`apple-touch-startup-image`) need one image per device size; P3 at most, and only with a generator already in the toolchain.
- Web push works only for installed PWAs on iOS 16.4+.
- Storage for non-installed sites may be evicted after 7 days of no use; installed PWAs are exempt. Do not rely on offline data for non-installed users.

## Motion and feedback

- `@media (prefers-reduced-motion: reduce)` disables large transitions and parallax.
- Skeletons or spinners for anything that takes > 300 ms; optimistic UI for quick actions.
- `navigator.vibrate` is Android-only and usually unwelcome; do not add it.
