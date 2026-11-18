# WCAG 2.2 AA checklist for code and live audits

Load this before step 2 of the workflow. Each section lists the success criteria (SC) to cite, how to test them, the usual failure in code, and the common false positives to rule out before reporting. Cite SCs as `<number> <name> (<level>)`, for example `1.4.3 Contrast (Minimum) (AA)`.

Only Level A and AA criteria are failures. AAA items go under "Report only".

## Contents

1. Semantics, structure, and landmarks
2. Keyboard and focus
3. ARIA
4. Forms, errors, and authentication
5. Color and contrast
6. Images, icons, and media
7. Motion, animation, and timing
8. Dynamic content and announcements
9. Touch, pointer, and target size
10. Reflow, zoom, and text spacing
11. Consistency and help
12. Quick SC index

## 1. Semantics, structure, and landmarks

| SC | Test | Typical failure |
|----|------|-----------------|
| 1.3.1 Info and Relationships (A) | Structure visible on screen is in the markup: headings are `h1`–`h6`, lists are `ul`/`ol`, data tables use `th` with `scope`, groups of radios use `fieldset`/`legend` | Bold `div` used as heading; table built from `div` grid with no roles; label text next to input but not associated |
| 1.3.2 Meaningful Sequence (A) | DOM order matches reading order | CSS `order`, `flex-direction: row-reverse`, or absolute positioning puts content in a different visual order than the DOM |
| 2.4.1 Bypass Blocks (A) | Skip link to main, or landmarks (`main`, `nav`, `header`) present | No `main` landmark and long nav repeated on every page |
| 2.4.2 Page Titled (A) | Each route sets a unique, descriptive `<title>` | SPA keeps one static title for every route |
| 2.4.6 Headings and Labels (AA) | Headings and labels describe their content | Several sections all headed "Details" |
| 3.1.1 Language of Page (A) | `<html lang="…">` set and correct | Missing `lang`, or `lang="en"` on a French site |
| 3.1.2 Language of Parts (AA) | Passages in another language carry `lang` | Quote in German read with an English voice |
| 4.1.2 Name, Role, Value (A) | Custom controls expose role, name, and state | Clickable `div` toggle with no role or `aria-pressed` |

Buttons vs links: a link navigates (`<a href>`), a button acts (`<button>`). `<a>` without `href` is not focusable. `<a href="#" onClick>` used as a button is a 4.1.2 issue only if role or keyboard behavior is wrong; report it as Low unless it breaks Space activation in a core flow.

False positives: heading levels skipped (`h2` → `h4`) is not a WCAG failure on its own; report under Low only if it misrepresents structure. Multiple `h1` elements are allowed.

## 2. Keyboard and focus

| SC | Test | Typical failure |
|----|------|-----------------|
| 2.1.1 Keyboard (A) | Every action works with Tab, Shift+Tab, Enter, Space, arrows, Escape | `div onClick` with no key handler; hover-only menus; drag-only reorder |
| 2.1.2 No Keyboard Trap (A) | Focus can always leave a component | Embedded editor or iframe that swallows Tab; modal with no close by keyboard |
| 2.1.4 Character Key Shortcuts (A) | Single-key shortcuts can be turned off or remapped, or only work when focused | Global `keydown` on `s` fires while typing in a screen-reader browse mode |
| 2.4.3 Focus Order (A) | Order follows meaning; dialogs take focus on open and return it on close | Positive `tabindex`; focus stays behind a modal; focus lost to `body` after deleting a list row |
| 2.4.7 Focus Visible (AA) | A visible indicator on every focusable element | Global `*:focus { outline: none }` with no `:focus-visible` replacement |
| 2.4.11 Focus Not Obscured (Minimum) (AA) | Focused element not fully hidden by sticky headers, cookie banners, or chat widgets | Sticky footer covers focused links as user tabs down the page |
| 3.2.1 On Focus (A) | Focus alone does not change context | Focusing a field opens a new page or submits |
| 3.2.2 On Input (A) | Changing a setting does not change context unexpectedly | `select onChange` navigates immediately with no warning |

Code signals: `tabindex` greater than 0, `onClick` on `div`/`span`/`li`/`img` without `role` + `tabIndex` + `onKeyDown`, `outline: none`/`outline: 0`, `:focus { outline: … }` removal, `pointer-events` tricks, `onMouseEnter`-only menus, `autoFocus` jumps.

Dialog pattern that passes: native `<dialog>` opened with `showModal()`, or a library dialog. Focus goes inside on open, Tab cycles inside, Escape closes, focus returns to the trigger, background is inert (`inert` attribute or `aria-modal="true"` with focus trapping).

False positives: `tabindex="-1"` on a heading or container used as a focus target is correct. `outline: none` paired with a `:focus-visible` box-shadow or ring is fine. Libraries such as Radix, React Aria, Headless UI, and native `<dialog>` handle trapping.

## 3. ARIA

First rule: use a native element when one exists. Then check:

- **Valid roles and required states**: `role="checkbox"` needs `aria-checked`; `role="tab"` lives inside `role="tablist"` with `aria-selected` and `aria-controls`; `role="combobox"` needs `aria-expanded` and the 1.2 pattern.
- **References resolve**: every id in `aria-labelledby`, `aria-describedby`, `aria-controls` exists exactly once in the rendered DOM (watch generated ids and SSR mismatches).
- **Names on icon-only controls**: `aria-label` or visually hidden text on icon buttons and links (4.1.2, 2.4.4 Link Purpose (In Context) (A)).
- **`aria-hidden="true"` on focusable content** removes it from the tree while it stays tabbable: 4.1.2 failure. Includes `aria-hidden` on a wrapper that contains buttons.
- **`role="presentation"`/`none` on a focusable element** is ignored and confusing.
- **Label in Name, 2.5.3 (A)**: the accessible name contains the visible label text, so voice users can say what they see. `aria-label="Close dialog"` on a button that shows "Cancel" fails.
- **Overuse**: `role="button"` on a `<button>`, `aria-label` that repeats visible text, `role="link"` on `<a href>`: redundant, report as Low at most or not at all.

False positives: `aria-label` on a native `<button>` or `<a href>` is fine. `aria-hidden` on decorative SVG inside a labelled button is correct.

## 4. Forms, errors, and authentication

| SC | Test | Typical failure |
|----|------|-----------------|
| 1.3.1 Info and Relationships (A) / 4.1.2 (A) | Each field has a programmatic label (`<label for>`, wrapping label, `aria-labelledby`, `aria-label`) | Label is a sibling `div`; only `placeholder` |
| 3.3.2 Labels or Instructions (A) | Required fields and formats are stated before input | Asterisk with no explanation; date format only in placeholder |
| 1.3.5 Identify Input Purpose (AA) | Personal-data fields use `autocomplete` tokens (`email`, `name`, `tel`, `street-address`, `postal-code`, `cc-number`, `current-password`, `new-password`, `one-time-code`) | Sign-up form with no `autocomplete` |
| 3.3.1 Error Identification (A) | Error described in text, field identified | Red border only |
| 3.3.3 Error Suggestion (AA) | Error text says how to fix it | "Invalid input" |
| 3.3.4 Error Prevention (Legal, Financial, Data) (AA) | Review, confirm, or undo before a binding submit | One-click purchase with no review step |
| 3.3.7 Redundant Entry (A) | Info already entered in the same process is pre-filled or selectable | Shipping address must be retyped as billing with no "same as shipping" |
| 3.3.8 Accessible Authentication (Minimum) (AA) | No cognitive test (remembering, transcribing, puzzle) without an alternative; paste and password managers allowed | `onPaste` blocked on password or OTP; image CAPTCHA with no alternative |
| 4.1.3 Status Messages (AA) | Errors and success messages are announced | Inline error appears silently with no `aria-live`, `role="alert"`, or focus move |

Good error wiring: `aria-invalid="true"` on the field, `aria-describedby` pointing at the error text, and either focus moved to the first invalid field or an error summary at the top with links.

False positives: a visually hidden label (`sr-only` class) is a valid label. A single search field with a visible "Search" button and `aria-label` passes.

## 5. Color and contrast

| SC | Threshold |
|----|-----------|
| 1.4.3 Contrast (Minimum) (AA) | 4.5:1 for normal text; 3:1 for large text (≥ 24 px regular, or ≥ 18.66 px / 14 pt bold) |
| 1.4.11 Non-text Contrast (AA) | 3:1 for UI component boundaries needed to identify them (input borders, checkbox outlines, toggle states), focus indicators, and meaningful graphics (chart lines, icons) against adjacent colors |
| 1.4.1 Use of Color (A) | Color is not the only way to convey meaning: links in body text need a non-color cue (underline) unless they have 3:1 against surrounding text plus a cue on focus/hover; error and status states need text or icons |

Contrast ratio: `(L1 + 0.05) / (L2 + 0.05)` with L the relative luminance. For each sRGB channel `c` in 0–1: `c ≤ 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ^ 2.4`; `L = 0.2126 R + 0.7152 G + 0.0722 B`. Compute from the actual tokens, resolving CSS variables, opacity (blend the foreground over the background), and theme. Report the measured ratio and the required one, for example "#9CA3AF on #FFFFFF is 2.54:1; needs 4.5:1".

Check states: default, hover, focus, active, visited, placeholder text (counts as text), dark mode, text over images or gradients (measure against the lightest area behind the text).

Exempt: disabled controls, logos and brand text, purely decorative text, text in inactive UI. Do not report these.

## 6. Images, icons, and media

| SC | Test |
|----|------|
| 1.1.1 Non-text Content (A) | Informative images have `alt` that conveys the same information; functional images (inside links/buttons) describe the action; decorative images use `alt=""` or CSS backgrounds; inline SVG uses `role="img"` + `aria-label` or `<title>`, or `aria-hidden="true"` if decorative; icon fonts are hidden with a text alternative |
| 1.2.1 Audio-only and Video-only (Prerecorded) (A) | Transcript, or audio description for video-only |
| 1.2.2 Captions (Prerecorded) (A) | Captions on video with speech (`<track kind="captions">` or the player's captions) |
| 1.2.4 Captions (Live) (AA) | Captions for live video with audio |
| 1.2.5 Audio Description (Prerecorded) (AA) | Important visual-only info in video is described |
| 1.4.5 Images of Text (AA) | Text is real text, not an image, unless essential (logos) |

Bad alt: file names (`IMG_2041.jpg`), "image of", the same alt on every image, alt that duplicates adjacent caption text exactly (Low). A linked image with `alt=""` and no other text makes an unnamed link: 2.4.4 and 4.1.2 failure.

False positives: `alt=""` on decorative images is correct. CMS-driven alt cannot be judged from code; check the content model has an alt field and that templates use it.

## 7. Motion, animation, and timing

| SC | Test |
|----|------|
| 2.2.2 Pause, Stop, Hide (A) | Auto-moving, blinking, or scrolling content that lasts more than 5 s and runs alongside other content can be paused (carousels, marquees, auto-playing video, animated backgrounds) |
| 2.3.1 Three Flashes or Below Threshold (A) | Nothing flashes more than 3 times per second |
| 2.2.1 Timing Adjustable (A) | Session timeouts warn and can be extended (at least 20 s to respond) |
| 1.4.2 Audio Control (A) | Audio playing more than 3 s automatically can be paused or muted |

`prefers-reduced-motion`: honoring it is required by 2.3.3 Animation from Interactions, which is **AAA**. Report missing reduced-motion handling as a failure only when it also breaks an A/AA criterion (auto-playing motion with no pause control, 2.2.2) or causes a vestibular hazard in a core flow (large parallax, zooming page transitions) — then cite 2.2.2 if applicable and put the rest under "Report only" with the AAA citation. Code signal: `@keyframes`, `animation:`, `transition` on transform, Framer Motion, GSAP, Lottie, `scroll-behavior: smooth` without a `@media (prefers-reduced-motion: reduce)` block or a `useReducedMotion` check.

## 8. Dynamic content and announcements

| SC | Test |
|----|------|
| 4.1.3 Status Messages (AA) | Messages that do not take focus are announced: toasts, "Saved", "3 results", "Added to cart", upload progress, form errors |
| 2.4.3 Focus Order (A) | After content is replaced (route change, delete, infinite scroll), focus lands somewhere sensible |
| 4.1.2 Name, Role, Value (A) | Expanded/collapsed, selected, pressed, busy states update (`aria-expanded`, `aria-selected`, `aria-pressed`, `aria-busy`) |

Patterns that pass: a persistent `role="status"` (polite) or `role="alert"` (assertive, for errors only) container rendered on page load whose text content is replaced; library toast systems that use one live region. Route changes: move focus to the new `h1` (with `tabindex="-1"`) or announce the new title via a live region.

Failures: a toast component that mounts its own `aria-live` element together with the message (often not announced); loading spinners with no text alternative; `role="alert"` on every status message (noisy, Low).

## 9. Touch, pointer, and target size

| SC | Test |
|----|------|
| 2.5.8 Target Size (Minimum) (AA) | Pointer targets at least 24×24 CSS px, or a 24 px diameter circle centered on each target does not overlap another target. Exceptions: inline links in text, an equivalent larger control elsewhere, user-agent default controls, essential size |
| 2.5.1 Pointer Gestures (A) | Multipoint or path-based gestures (pinch, swipe patterns) have a single-pointer alternative |
| 2.5.2 Pointer Cancellation (A) | Actions fire on up-event (click), not down-event, or can be aborted |
| 2.5.4 Motion Actuation (A) | Shake or tilt actions have a UI alternative and can be disabled |
| 2.5.7 Dragging Movements (AA) | Drag-only actions (sortable lists, sliders, map pan, kanban) have a single-pointer alternative (buttons, menus, click-to-place) |

44×44 px is 2.5.5 (AAA). Do not report targets between 24 and 44 px as failures.

## 10. Reflow, zoom, and text spacing

| SC | Test |
|----|------|
| 1.4.4 Resize Text (AA) | 200% text zoom without loss of content or function |
| 1.4.10 Reflow (AA) | At 320 CSS px wide (1280 px at 400% zoom) no two-direction scrolling, except data tables, maps, and diagrams |
| 1.4.12 Text Spacing (AA) | Line height 1.5, paragraph spacing 2×, letter spacing 0.12×, word spacing 0.16× do not clip or overlap text |
| 1.4.13 Content on Hover or Focus (AA) | Tooltips and popovers are dismissible (Escape), hoverable, and persistent |
| 1.3.4 Orientation (AA) | Works in portrait and landscape unless essential |

Code signals: `<meta name="viewport" content="… maximum-scale=1 …">` or `user-scalable=no` (fails 1.4.4); fixed `height` on text containers with `overflow: hidden`; `px` font sizes are fine for WCAG but fixed-height boxes are not; tooltips that disappear when the pointer moves onto them.

## 11. Consistency and help

| SC | Test |
|----|------|
| 3.2.3 Consistent Navigation (AA) | Repeated navigation appears in the same order across pages |
| 3.2.4 Consistent Identification (AA) | Same function, same label and icon across pages |
| 3.2.6 Consistent Help (A) | Help mechanisms (contact, chat, FAQ link) appear in the same relative place on every page that has them |
| 2.4.4 Link Purpose (In Context) (A) | Link text plus context tells where it goes; "click here" or "read more" repeated without context fails |
| 2.4.5 Multiple Ways (AA) | More than one way to find a page (nav, search, sitemap), except steps in a process |

## 12. Quick SC index

A: 1.1.1, 1.2.1, 1.2.2, 1.2.3, 1.3.1, 1.3.2, 1.3.3, 1.4.1, 1.4.2, 2.1.1, 2.1.2, 2.1.4, 2.2.1, 2.2.2, 2.3.1, 2.4.1, 2.4.2, 2.4.3, 2.4.4, 2.5.1, 2.5.2, 2.5.3, 2.5.4, 3.1.1, 3.2.1, 3.2.2, 3.2.6, 3.3.1, 3.3.2, 3.3.7, 4.1.2.

AA: 1.2.4, 1.2.5, 1.3.4, 1.3.5, 1.4.3, 1.4.4, 1.4.5, 1.4.10, 1.4.11, 1.4.12, 1.4.13, 2.4.5, 2.4.6, 2.4.7, 2.4.11, 2.5.7, 2.5.8, 3.1.2, 3.2.3, 3.2.4, 3.3.3, 3.3.4, 3.3.8, 4.1.3.

Removed in 2.2: 4.1.1 Parsing. Do not cite it.

Common AAA criteria (never failures here): 1.4.6 Contrast (Enhanced), 2.3.3 Animation from Interactions, 2.4.12 Focus Not Obscured (Enhanced), 2.4.13 Focus Appearance, 2.5.5 Target Size (Enhanced), 3.3.9 Accessible Authentication (Enhanced).
