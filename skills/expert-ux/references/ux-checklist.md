# UX review checklist

Deep checklist behind step 3 of the skill. Each dimension lists what to look for, a concrete example of a real defect, where to find it in code, and the trap that makes it easy to miss. Score every candidate with the severity scale in SKILL.md, then put it through the verification gate before it becomes a finding.

## How to use this file

1. Pick the dimensions the target touches (or the one named by the focus word).
2. For each journey step, ask the questions in that dimension's table.
3. For each candidate, write: **user → task → step → what goes wrong → fix**. Missing any part means no finding.
4. Read the "do not report" list at the bottom before writing anything up.

---

## 1. Journeys and task completion

| Ask | Defect example | Where to look |
|-----|----------------|---------------|
| Can the user finish the job at all? | Invite flow sends an email, but the accept link requires an account type the invitee cannot create | Route guards, email templates, accept handlers |
| Is the success state obvious? | After "Save", the form stays on screen unchanged; users click again | Submit handlers: what renders after `200`? |
| Is the next step offered? | Project created → empty dashboard with no hint to add the first item | Post-create redirects, empty states |
| How many decisions before value? | Four setup screens before the user sees anything they came for | Onboarding routes, wizard step arrays |
| Does it survive interruption? | Closing the tab mid-checkout loses the cart; no draft for a long form | Local state vs. persisted state, `beforeunload` |
| Does it work from every entry point? | Works from the nav, breaks from an emailed deep link or a shared URL | Query-param parsing, auth redirect `next=` handling |

Trap: walking only from the home page. Real users arrive from email, search, notifications, and bookmarks.

## 2. Friction and dead ends

| Ask | Defect example |
|-----|----------------|
| Is there always a way forward and back? | Error page with no link anywhere; modal with no close |
| Does Back do what the user expects? | Multi-step form where browser Back exits the whole flow and discards input |
| Is sign-up forced before value? | Pricing calculator requires an account to see a number |
| Is information asked twice? | Shipping address re-entered as billing with no "same as shipping" |
| Are required fields really required? | Phone number required for a newsletter |
| Does an error keep the user's work? | Server validation error re-renders an empty form |
| Does a reload keep the user's place? | Filters, tabs, and pagination live only in component state, not the URL |
| Does a 404 or permission error help? | "Forbidden" with no explanation of who can grant access |

Trap: dead ends are often in error branches of the code, not in any screen you see on the happy path. Search for `catch`, `onError`, `notFound`, `redirect` and read what they render.

## 3. Information architecture and navigation

| Ask | Defect example |
|-----|----------------|
| Do labels use the user's words? | Nav item "Entities" for what users call "Customers" |
| Is the same thing named one way everywhere? | "Workspace", "Team", and "Org" used for the same object on three screens |
| Can users tell where they are? | No active state in nav, no page title, breadcrumbs missing in a deep hierarchy |
| Can users predict where something lives? | Billing under "Profile" in one place and "Settings" in another |
| Is the hierarchy as shallow as the content allows? | A setting five clicks deep that users change weekly |
| Is search there when the list is long? | 300-item dropdown with no filter |
| Do URLs reflect location? | Every screen is `/app`; nothing can be shared or bookmarked |

Where to look: the router config or file-based routes, the nav component, page `<title>`/metadata, i18n keys for nav labels.

Trap: judging the IA by the folder structure. Users see the nav and the labels, not `src/`.

## 4. Forms and validation

| Ask | Defect example |
|-----|----------------|
| Does every field have a visible label (not just a placeholder)? | Placeholder-only fields: the hint disappears on typing |
| Is the input type right? | `type="text"` for email, phone, or numbers on mobile |
| Are defaults sensible? | Country defaults to the first in the list instead of the detected one |
| When does validation fire? | Errors shown on every keystroke before the user finishes typing; or only after submit, all at once |
| Do errors say what to do? | "Invalid value" vs. "Use 8 or more characters, including a number" |
| Are errors next to the field and announced? | One banner at the top; the field with the problem is off-screen |
| Is the format forgiving? | Phone rejects spaces and dashes; card number rejects spaces |
| Is submit protected? | No disabled/pending state → double charges, duplicate records |
| Is the length right? | Optional fields mixed with required ones and no marking of which is which |
| Are constraints shown up front? | Password rules revealed only after failing them |

Where to look: the shared form component and schema (zod/yup/react-hook-form/Formik), server-side validation messages, the submit handler's pending flag.

Trap: client and server validation disagreeing: the client accepts, the server rejects with a raw message.

## 5. Loading, empty, and error states

For **every** view that fetches data, check all three. A missing one is a finding when the view is on a critical journey.

| State | Must tell the user | Defect example |
|-------|--------------------|----------------|
| Loading | Something is happening, roughly what | Blank screen for 3 s; spinner that never times out; layout jumps when data lands |
| Empty (first use) | Why it is empty and the one action to fill it | "No items" with no button |
| Empty (no results) | That the filter or search caused it, and how to clear it | Filtered list shows the first-use empty state |
| Error | What failed, whether data is safe, what to do (retry, contact) | Raw `TypeError: Cannot read properties of undefined`; "Something went wrong" with no retry |
| Partial | Which part failed while the rest works | One failing widget blanks the whole dashboard |
| Offline / slow | That the network is the cause | Infinite spinner with no offline message |
| Permission | Why they cannot see it and who can grant it | Empty list that is actually a 403 |

Where to look: `isLoading`/`isError`/`data?.length === 0` branches, Suspense boundaries, error boundaries (`error.tsx`, `ErrorBoundary`), query library defaults, skeleton components.

Trap: a global error boundary exists, so every error "is handled", but it replaces the whole page and loses the user's input. Handled is not the same as helpful.

## 6. Onboarding

| Ask | Defect example |
|-----|----------------|
| How long to first value? | Value requires connecting an integration before anything is visible; no sample data |
| Does the first screen say what to do? | New dashboard full of zeros and empty charts |
| Can setup be skipped and resumed? | Skipping the tour loses the checklist forever |
| Is progress visible? | Five-step setup with no step indicator |
| Does it adapt to the user's role or goal? | Admin setup shown to an invited member |
| Is it re-findable? | Tour cannot be replayed; help link missing from the empty states |
| Does verification block value? | Email confirmation required before the user can try anything |

Trap: reviewing onboarding with a seeded dev account. Use a fresh, empty account, or read the code path for a user with zero records.

## 7. Feedback and affordances

| Ask | Defect example |
|-----|----------------|
| Does every action acknowledge itself? | "Copy link" copies silently |
| Is feedback near the action? | Toast in the far corner for an inline edit |
| Does feedback last long enough? | Error toast that auto-dismisses in 2 s |
| Do destructive actions confirm or offer undo? | "Delete project" fires on one click with no undo |
| Is the confirmation specific? | "Are you sure?" vs. "Delete 'Q3 report' and its 12 files? This cannot be undone." |
| Do clickable things look clickable? | Cards that navigate on click but look static; text links styled like body text |
| Do disabled controls explain why? | Greyed-out "Publish" with no tooltip or hint |
| Is optimistic UI rolled back visibly on failure? | Item appears added, silently disappears on error |
| Is long work visible? | Export runs in the background with no progress and no notification when done |

Where to look: toast/notification calls, `confirm(`, dialog components, `disabled=` props, mutation `onError` handlers.

## 8. Microcopy

Load `references/microcopy.md` for the full guide. Quick checks:

- Buttons are verbs that name the outcome ("Create invoice", not "Submit" or "OK").
- Errors say what happened and what to do, never blame the user, never expose internals.
- One term per concept across the app, matching the user's vocabulary.
- Empty states and confirmations name the specific object.
- Copy matches the product's established voice.

---

## Do not report

- Visual taste: color choice, font, spacing, alignment, shadows (route to `expert-ui`).
- WCAG checkpoints as compliance: contrast ratios, ARIA roles, focus order as conformance (route to `expert-accessibility`). Report the *usability* impact only when it hurts all users.
- Code quality with no user-visible effect.
- A pattern you prefer when the app consistently uses another that works.
- Problems on screens outside the target, unless they break the journey you are walking, put those under Notes.
- Speculative issues with no reachable path.
