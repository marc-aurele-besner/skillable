# Edge-case catalog

Load this at step 4 of the skill. Walk **only** the categories the change touches. For each case you keep, write one line, *input or state → expected behavior*, and drop it if the code already prevents it (check the validator, type, or constraint).

## 1. Empty, null, missing

- Empty string, whitespace-only string, `null` vs `undefined` vs missing key.
- Empty list / zero results: empty state renders, pagination says "0", no divide-by-zero in averages.
- First-ever use: no history, no settings row, no avatar, brand-new account.
- Optional field omitted by an old client or an older API version.
- `0`, `false`, `""` treated as "missing" by `||` or truthiness checks.

## 2. Huge and long

- Very long strings: names, titles, URLs, emails at max length; text without spaces that breaks layout.
- Large lists: 10 000+ rows (pagination, virtualization, query time, memory).
- Large files: upload at and above the limit; zero-byte file; wrong MIME type with right extension.
- Deep nesting (JSON, comment threads, folder trees); recursion limits.
- Request body or URL length limits; batch endpoints with max+1 items.

## 3. Unicode, text, and formatting

- Emoji (including multi-codepoint 👩‍👩‍👧 and skin tones), combining marks, zero-width characters.
- RTL text (Arabic, Hebrew) and mixed-direction strings.
- CJK, characters outside the BMP, case folding (`ß`, Turkish `İ`).
- Truncation that cuts a surrogate pair or a grapheme in half.
- Leading/trailing whitespace, homoglyphs in usernames, normalization (NFC vs NFD) in uniqueness checks.
- HTML/markdown/SQL-looking input rendered or stored (`<script>`, `'; --`, `{{7*7}}`).

## 4. Numbers and money

- Zero, negative, max int, very large decimals, `NaN`, `Infinity`.
- Float rounding on money; currency with 0 or 3 minor units (JPY, KWD).
- Locale decimal separator (`1,5` vs `1.5`), thousands separators in input.
- Percentages over 100, discounts larger than the price, quantity 0.

## 5. Dates, times, timezones

- User in a non-UTC zone (UTC-10, UTC+13, UTC+5:45); server vs client zone mismatch.
- DST transitions: the missing hour, the repeated hour; recurring events across DST.
- Midnight and end-of-day boundaries; "today" for a user whose date differs from the server's.
- Month ends, Feb 29, year boundaries, week-start differences (Sunday vs Monday).
- Date-only values parsed as UTC midnight then shown a day early.
- Expiry and TTL: exactly at expiry, clock skew between services, a token that expires mid-flow.

## 6. Concurrency and repetition

- Double-click / double-submit: two orders, two charges, two emails.
- Two tabs or two devices editing the same record; last-write-wins vs conflict.
- Retry and webhook redelivery: is the handler idempotent?
- Race between a create and an immediate read (replica lag, cache).
- Background job running twice or overlapping with itself; job and user editing the same row.
- Counters and quotas under parallel requests.

## 7. Network and failure

- Offline, then back online: queued actions, duplicate replay, stale UI.
- Slow network: spinners, timeouts, user navigating away mid-request.
- Partial failure: step 2 of 3 fails, is step 1 rolled back or left half-done?
- Third-party down or returning 429/500/malformed JSON.
- Request cancelled (abort, tab closed) after the server committed.
- Large response truncated; pagination cursor invalid or expired.

## 8. Permissions and roles

- Each role: anonymous, signed-in, owner, member, admin, suspended, deleted user.
- Direct object access: change the id in the URL or API body (IDOR).
- Permission revoked mid-session; role changed while a page is open.
- Multi-tenant: data from org A visible to org B through search, export, cache, or notifications.
- UI hides a button, but the API still accepts the action.

## 9. State and lifecycle

- Browser back/forward, refresh mid-flow, deep link straight into step 3.
- Stale tab after a deploy (old client, new API).
- Data created by an older version: legacy rows, null in a now-required column, old enum value.
- Upgrade and downgrade paths; migration run twice; rollback with new data written.
- Logout in another tab; session expiry during a form fill (is the input lost?).
- Feature flag on/off, and flipped mid-session.

## 10. Input from other systems

- Webhook payloads out of order, duplicated, or with unknown fields.
- CSV/Excel imports: BOM, different delimiters, quoted newlines, formulas (`=HYPERLINK`), 1M rows.
- Email addresses with `+`, subdomains, uppercase, IDN domains.
- Phone numbers and addresses from other countries.

## 11. Platform, devices, accessibility

- Narrow mobile width, zoom 200 %, landscape, small-height screens with an on-screen keyboard.
- Keyboard-only navigation, focus after a modal closes, screen-reader labels on new controls.
- Reduced motion, dark mode, high contrast.
- Safari/iOS quirks only when the change touches dates, storage, media, or input types.
- Touch vs hover-only interactions.

## 12. Internationalization

- Longer translated strings (German, Finnish) breaking layout; missing translation keys.
- Pluralization rules (0, 1, 2, few, many); gendered strings.
- Locale-formatted dates, numbers, and currencies in both display and input.
- Sorting and search with accented characters.

## What not to list

- Cases the type system, schema validator, or DB constraint already rules out (cite it if useful).
- Generic platform matrices unrelated to the change.
- Cases already covered by an existing test, mark them *covered* in the plan with the `file:line` instead.
