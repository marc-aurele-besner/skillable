# Microcopy guide

Load this when the review touches wording: buttons, labels, errors, empty states, confirmations, onboarding text, notifications, or emails. Every copy finding must quote the current text, give the location, and propose the replacement text.

## Where copy lives

Check all of these, not only component markup:

- JSX/template strings and `aria-label`/`title` text that is also shown
- i18n catalogs (`locales/*.json`, `messages/*.po`, `*.ftl`) — the shipped text may differ from the source default
- Server error messages passed through to the UI (API `message` fields, validation libraries' default messages)
- Email and notification templates
- CMS or config-driven content

```bash
rg -n -g '!node_modules' -e '"Submit"' -e "'Submit'" -e '>Submit<' -e '"OK"' -e 'Something went wrong' -e 'Invalid' -e 'Error:' . | head -60
```

## Rules, with before → after

### Buttons and links

- Name the outcome with a verb: `Submit` → `Create account`; `OK` → `Delete file`.
- Keep the label consistent with the screen title and the confirmation: the "Archive" button opens "Archive project?" and the toast says "Project archived".
- Links say where they go: `Click here` → `View billing history`.

### Errors

Every error answers: **what happened, is my work safe, what do I do now.**

- `Invalid input` → `Enter a date in the future`
- `Error 500` → `We couldn't save your changes. Your draft is kept — try again in a moment.`
- `Payment failed` → `Your card was declined. Try another card or contact your bank.`
- Never blame: `You entered a wrong password` → `That password doesn't match this email`.
- Never expose internals: stack traces, SQL, error codes without meaning, `undefined`, `[object Object]`.

### Empty states

Say why it is empty and offer the one next action:

- `No data` → `No invoices yet. Create your first invoice to get paid faster.` + `Create invoice`
- No-results state: `No results` → `No projects match "acme". Clear search`.

### Confirmations of destructive actions

Name the object, the consequence, and reversibility; the confirm button repeats the verb:

- `Are you sure?` / `Yes` → `Delete "Q3 report"? Its 12 files will be removed permanently.` / `Delete report`

### Success and status

- Confirm the specific thing: `Success!` → `Invite sent to sam@example.com`.
- Pending states say what is happening: `Loading…` → `Importing 240 contacts…` when the operation is long.

### Labels, hints, placeholders

- Labels name the field; hints explain format or constraints; placeholders are examples, never the only label.
- Show constraints before the user fails them: `Password` + hint `At least 8 characters, including a number`.

### Terminology

- One term per concept across the app. List every synonym you find for the same object and recommend the one users use (check the marketing site, docs, and support content for the user's word).
- Prefer the user's vocabulary over internal or database names (`tenant`, `entity`, `record`).

### Tone

- Match the product's existing voice; do not impose a new one. Flag only inconsistency or text that is unclear, cold where reassurance matters (errors, payment, deletion), or jokey where it confuses.
- Plain language: short sentences, no jargon, no double negatives (`Don't disable notifications` → `Keep notifications on`).

## Severity for copy findings

- **High** when wording causes a wrong action or blocks a task (ambiguous destructive button, error with no way forward on a critical journey).
- **Medium** when it causes confusion or rework (inconsistent terms, generic errors on secondary flows).
- **Low** for clarity polish on secondary paths.
- Copy is rarely Critical; reserve that for text that leads users into data or money loss.
