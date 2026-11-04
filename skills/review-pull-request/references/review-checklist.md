# PR review checklist

Deep checklist behind step 4 of the skill. Each dimension lists what to look for, a concrete example of a real defect, and the trap that makes it easy to miss. Score every candidate with the severity rubric in SKILL.md, then run it through the verification gate before it becomes a finding.

## How to use this file

1. Pick the dimensions the diff touches (SKILL.md step 3 decides the risk level and depth).
2. Read the changed hunks **with the file open** — the hunk alone hides the context that makes a bug real.
3. For each candidate, write the failure scenario: inputs or state → wrong outcome. No scenario, no finding.
4. Check the "do not report" list at the bottom before writing anything up.

---

## 1. Correctness

| Look for | Concrete example |
|----------|------------------|
| Boundary conditions | Off-by-one on `arr[0]` / `arr[len]`; a page size of 0; `limit` taken from user input without a floor |
| Inverted or wrong operator | `if x < y` where the intent was `>`; `||` used where `&&` was meant; `!==` on a numeric comparison |
| Wrong variable used | The value checked is not the value that was computed; a copy-pasted field from a sibling branch |
| Error path handling | The happy path returns early but the error path falls through to a null deref; `else` branch missing entirely |
| Null / undefined | A value the API can omit is dereferenced; `??` vs `||` when `0` or `""` is legitimate; optional-chained call whose result is immediately dereferenced |
| Ordering assumptions | A record is read before the transaction that creates it commits; a cache is written before the DB commit |
| Concurrency | Read-modify-write without a lock; two workers process the same queue item; a check-then-act on a counter |
| State captured too early | A closure captures a stale prop; a module-level variable is shared across requests (server code) |
| Loop variable capture | The classic `for (var i...)` / `setTimeout` / `setInterval` capture bug in JS |
| Resource cleanup | A file handle, DB connection, timer, or subscription is opened and never closed on the error path |
| Idempotency | A handler can run twice (retry, webhook redelivery) and double-charges or double-sends |
| Type coercion | `"0"` is falsy in some languages, `[]` is truthy in JS, `0 == "0"` in PHP |

### Language-specific traps

**JavaScript / TypeScript**
- **Stale closure in React**: an effect or callback that reads a prop/state value from the render it was created in, while the value has since changed. Fix is usually a dependency array or a functional `setState` update (`setCount(c => c + 1)`), not reading `count`.
- **Missing `key` in a list, or an index as `key`**: index keys make React reuse the wrong DOM node when the list reorders, which corrupts input values and animation state.
- **Missing `await`**: a promise-returning call not awaited — the code continues before the value exists, and the rejection is swallowed as an unhandled rejection. Look for a `try/catch` around a block where one call is un-awaited.
- **Unsafe `any` / `as` casts**: `as SomeType` silences the compiler. `any` in a public API surface spreads.
- **`await` inside a loop**: serializes independent network calls; usually a `Promise.all` was intended.
- **Optional chaining that hides a real error**: `a?.b?.c` returns `undefined` and the caller treats it as a value.
- **Floating-point money**: `0.1 + 0.2 !== 0.3`. Use integer minor units or a decimal type.
- **`==` vs `===`** and `null` vs `undefined` mismatch across a boundary.

**React / Next.js specifically**
- Server Component data fetched but not awaited (or a client hook used in a server component).
- `useEffect` used to derive state instead of computing during render.
- A `key` on a conditionally rendered list item that changes when the condition flips, remounting the subtree and losing local state.
- `"use client"` added to a whole file to use one hook, dragging the whole tree into the client bundle.

**Python**
- Mutable default argument (`def f(items=[])`) — the list persists across calls.
- Late-binding closure in a loop (`lambda: i` inside `for i in ...`).
- Bare `except:` swallows `KeyboardInterrupt` and `SystemExit`.
- `except Exception` around a block that also does I/O, hiding which call failed.
- `.get(key)` on a dict that should be `key` — a missing key returns `None` instead of raising.
- Context manager not used: a file/socket/DB connection closed only on the happy path.

**SQL / database**
- **String building**: `f"SELECT * FROM users WHERE id = {user_id}"` — injection. Must be a parameterized query.
- Filtering on an unindexed column in a hot query.
- `SELECT *` when a column is later dropped, or when a payload column holds PII that then leaks into a log or an API response.
- `LIMIT`/`OFFSET` on a large table without an index on the sort column — the offset scan grows with page number.
- A join that fans out rows and is then counted with `COUNT(*)` — count the distinct key instead.
- A write inside a loop instead of a bulk operation.
- Missing `ON DELETE` behavior, so deleting a parent orphans children or cascades too much.

**Go / Java / Rust / typed languages**
- An error checked but discarded (`_`), or an error wrapped without context.
- A `nil` / `None` / `Optional` returned as a success value and dereferenced by the caller.
- A goroutine / thread / task spawned with no cancellation path, leaking on shutdown.
- Integer overflow on a size calculation.
- A mutex held across an I/O call, serializing the whole path.

**Shell / CI**
- **Shell injection in CI**: `run: ${{ github.event.pull_request.title }}` interpolates untrusted text into a shell. Use an env var and quote it (`env: PR_TITLE: ${{ ... }}` then `"$PR_TITLE"`). The same applies to branch names, PR bodies, and issue titles.
- `curl … | bash`, `npm install` of an unpinned package, or an action referenced by a mutable tag instead of a SHA.
- A workflow triggered on `pull_request_target` that checks out and runs the PR's code — it runs with repository secrets.
- Secrets exposed via `echo "$TOKEN"` in a step, or written to a file inside the workspace that gets uploaded as an artifact.
- Missing concurrency group, so two runs race on the same environment.
- A step that runs `continue-on-error: true` and hides a real failure.

---

## 2. Test coverage

- Is there a test for the **new behavior**, not just the old behavior still passing?
- Does an existing test assert something the change silently altered (a changed default, a changed error message, a changed type)? A renamed field that breaks a fixture is a contract change, not a test nit.
- Are the assertions strong enough to fail on a broken implementation? `assert result is not None`, `assertTrue(response.ok)`, or `expect(result).toBeDefined()` pass on a wrong value.
- Was a test deleted, skipped, or weakened (`skip`, `xfail`, `.only`) to make the build green? That is a high-severity finding, not a nit.
- Are the edge cases covered: empty, one element, boundary, null, negative, unicode, very large?
- Do the tests assert on **behavior** or on **implementation details** (private method names, exact internal call order)? The latter breaks on every refactor.
- Are mocks so heavy that the test passes while the real wiring is broken?
- Does the test exercise the new code path end to end, or only a unit in isolation?
- Do the tests run in the project's own test command, and does CI actually run them?

---

## 3. Security

| Vector | Look for |
|--------|----------|
| Injection | SQL built by concatenation; shell commands built from user input; template rendering of untrusted HTML; `eval`/`exec` on user data; LDAP, XPath, or NoSQL operator injection |
| Authn / authz | A new route or handler with no auth check; an authorization check that only verifies the user is logged in, not that they own the resource; a check that can be bypassed with a different HTTP method or content type; an admin check that trusts a client-supplied role |
| Secrets | A key, token, password, or connection string committed in code, config, a fixture, a snapshot, a log line, or a test file; a secret passed as a query parameter (it lands in logs and referrers) |
| XSS | `dangerouslySetInnerHTML` / `innerHTML` / `v-html` on untrusted data; Markdown rendered to HTML without sanitizing; a URL built from user input rendered as `href` (`javascript:` scheme) |
| SSRF | A URL from a request body or webhook payload fetched by the server; a redirect-following fetch to an internal address |
| Path traversal | A filename from user input joined into a path without normalizing and checking the prefix; `../` reaching outside the intended directory |
| Unsafe deserialization | `pickle`, `yaml.load` without `SafeLoader`, `unserialize`, or a native format parsed into executable objects |
| File upload | No type or size check; the file stored under a user-controlled name; the file served back with its original content type so it executes |
| Crypto | `Math.random()` for a token or nonce; ECB mode; a hardcoded IV; a homemade crypto scheme; TLS verification disabled; a weak hash (MD5/SHA1) for passwords instead of bcrypt/argon2/scrypt |
| Dependencies | A new dependency from an unknown author, an unmaintained package, or a version with a known advisory; a dependency added to install an untrusted package |
| Info disclosure | A stack trace or internal error returned to the client; a debug endpoint left enabled; PII in a log line or an analytics event |
| Rate limiting / abuse | A new expensive or auth-sensitive endpoint with no throttle, captcha, or lockout |

---

## 4. Data and migrations

- **Backward compatibility**: can the previous application version read the new schema? If not, is the deploy order migration-then-code, and is there a documented step?
- **Data loss**: `DROP COLUMN`, `TRUNCATE`, a destructive `UPDATE` without a `WHERE`, a type change that truncates, a default that overwrites existing values.
- **Idempotency**: does re-running the migration corrupt data? Does it fail on a partially applied state?
- **Rollback**: is there a way back? A one-way migration with no down path needs a stated recovery plan.
- **Locking**: adding a non-null column with a default, changing a column type, or adding an index without `CONCURRENTLY` (Postgres) takes a table lock and blocks writes on a large table. Large backfills in one transaction time out.
- **Ordering**: a deploy that runs the new code before the schema exists fails at runtime; the reverse fails at query time.
- **Index**: does the migration add the index the new query needs? Is it created concurrently?
- **Foreign keys**: added after the fact on a table with existing orphans — the FK creation fails and takes the table down.
- **Zero-downtime**: a `NOT NULL` add on a big table, or an index build, blocks; use a nullable column + backfill + validation, then add the constraint.
- **Cross-version**: the ORM version in the repo must be able to express the new schema (a `migrations/` file written for a newer ORM version than the pinned one will not run).
- **Seed and test fixtures**: are they updated to the new shape, and does the test DB build from the migrations (not just the schema file)?

---

## 5. API and contract changes

- Public function signatures, exported types, and default values changed — is that a breaking change for consumers of the library?
- HTTP: status codes, response shape, field names, nullability, pagination semantics, error body format.
- GraphQL: fields removed or made non-null, enum values removed, input types changed.
- Events and webhooks: payload shape, ordering guarantees, the `type` string, and the schema version.
- CLI flags: renamed, removed, or changed default; `--flag` behavior changed under the same name.
- Config and env vars: a new required variable with no default breaks every existing deployment; a changed default changes behavior for everyone.
- Serialization: a field renamed in the DB but not in the API, or a date format changed (timezone handling).
- Versioning: is there a major version bump, a deprecation path, or a migration note for consumers?
- OpenAPI / schema files in the repo that were not regenerated.

---

## 6. Performance

- **N+1 queries**: a query inside a loop or a per-row accessor. Look for a repository call inside `map`/`for`.
- Work added to a hot path: a per-request call to a remote service, a synchronous API call inside an async handler, a regex compiled in a loop.
- Rendering: a new state update in a render path causing re-renders; a large inline object or function prop defeating memoization; a list rendered without virtualization where the data is unbounded.
- Payload size: a new field that returns a whole relation or a blob; an API that now returns everything instead of a page.
- Bundle size: a heavy dependency added to the client bundle; an import that pulls the whole library instead of a subpath.
- Queries without pagination, or a `LIMIT` that can be overridden by the client to something huge.
- Missing cache, or a cache with no invalidation on write (stale data) — both are findings.
- Memory: an unbounded in-memory buffer, a listener added per request on a long-lived object.

---

## 7. Observability and error handling

- A swallowed exception: `catch {}`, `except: pass`, a bare `catch (e) {}` — the failure is invisible.
- An error logged without context: no id, no user, no input, no stack.
- A new failure path with no log, no metric, and no user-visible message.
- An error message that leaks internals (stack trace, SQL, file path, internal id) to the user.
- A log at `info` on a path that should be `error`, or a `console.log` left where the project's convention is a logger.
- A user-facing error that says nothing actionable ("Something went wrong").
- Retry without idempotency, or a retry loop with no backoff and no cap.
- A timeout that does not exist on a new network call.
- No trace or correlation id on a request that crosses services.

---

## 8. Docs and config

- The README or docs now contradict the code (the old usage still documented, or a new flag missing).
- A new environment variable, secret, or config key that is not documented, has no default, and has no validation.
- A changed default value that is not called out in the PR body or a changelog.
- A feature flag added with no removal path, or the flag default flipped in the same PR as the implementation.
- A dependency version bump in a manifest without the lockfile updated (or vice versa).
- A changed CI workflow that silently drops a check, narrows a trigger, or makes a job non-blocking.
- A missing changelog entry, if the project keeps one.

---

## 9. Do not report these

Reporting these costs the author time and buries the real defects. Leave them out unless the user explicitly asks for style feedback.

- **Style the linter or formatter already enforces** — formatting, import order, trailing whitespace, line length, naming conventions covered by config. If the project's linter would reject it, CI will; that is not a review finding.
- **Personal preference between two equally valid approaches** — "I would have used a switch", "I prefer early returns". Only a violation of a documented project rule is a finding.
- **Speculative issues with no failure scenario** — "this might be slow with many records" without a realistic input. If you cannot write the scenario, drop it.
- **Missing tests for code that is trivially correct** — a one-line getter does not need a unit test.
- **Refactoring suggestions** — "this could be extracted into a helper", "this function is long". Only report when the length is causing a concrete defect or a documented rule is broken.
- **Alternative technologies** — "use Postgres instead of Mongo", "you could have used X". The project's stack is its own decision.
- **Re-reviewing code the PR did not change**, except where it makes the changed code wrong. Pre-existing problems go in "Report only", never as a blocking finding, and never with the PR's file:line as the anchor.
- **Unverified speculation about behavior you could not check** — put it in "Worth checking (unverified)" at most, clearly labeled.
- **Nitpicks on the PR body, commit message grammar, or title casing** — unless the repo has a documented convention.
