# DX review checklist

Deep checklist behind step 3 of the skill. Each dimension lists what to check, what a real finding looks like, and the trap that makes it easy to misjudge. Score every candidate with the severity scale in SKILL.md, then run it through the verification gate before it becomes a finding.

## How to use this file

1. Pick the dimensions that the target type and focus touch (SKILL.md "Inputs and scope").
2. Check each item against evidence: a file line, a command's output, a URL.
3. For each candidate, write the adopter scenario: who does what → what goes wrong → cost. No scenario, no finding.
4. Read the "Do not report" list at the bottom before writing anything up.

---

## 1. Time-to-first-success and quickstart accuracy

| Check | Real finding looks like |
|-------|-------------------------|
| The install command installs the right thing | `npm i foo` but the package is published as `@org/foo`; `pip install foo` but the import is `foo_sdk` with no mention |
| Every snippet import exists in the public exports | README imports `createClient` from `foo`; `src/index.ts` exports only `Client` since v2 |
| Every function call matches the current signature | Snippet passes `(url, opts)`; signature is now `({ url, ...opts })` |
| The snippet is complete enough to run | Uses `await` at top level in CommonJS; needs an API key but never shows where it goes |
| Output is shown | A newcomer cannot tell whether it worked; show expected output or a success line |
| The first success is meaningful | "Hello world" that skips auth when every real use needs auth hides the hard step |
| The path is one page | Quickstart jumps to three other docs before the first result |

Trap: you already know the API. Paste the snippet into a fresh file in a scratch project and run it, or trace each identifier to its export.

TTFS reference points (judge against the ecosystem, not these alone): a library under 5 min, a CLI under 2 min to a useful command, an HTTP API under 10 min including credentials, an app repo under 15 min to a running dev server.

## 2. Setup, prerequisites, and scripts

| Check | Real finding looks like |
|-------|-------------------------|
| Runtime version is pinned and stated | No `engines`, `.nvmrc`, `.tool-versions`, `requires-python`, `rust-toolchain`; install fails on the current LTS |
| System dependencies are listed | Native build needs `libvips`, `protoc`, or Xcode CLT; the first error is a 200-line compiler log |
| Required env vars are documented with an example | Code reads `process.env.DATABASE_URL`; no `.env.example`, no README mention |
| One command gets from clone to running | `make setup` / `pnpm bootstrap` / `just dev`, or a short numbered list |
| Script names follow ecosystem norms | `npm test` works; `dev`, `build`, `lint` do what their names say; no `test2`, `test:real` |
| The package manager is unambiguous | Lockfile for pnpm but README says `npm install`; `packageManager` field missing |
| Scripts referenced in docs exist | README says `npm run seed`; no `seed` script (the inventory script flags these) |
| Setup is idempotent | Running setup twice fails or duplicates data |

Trap: a globally installed tool on your machine (a CLI, a database, Docker) makes a missing prerequisite invisible. Note every tool the path assumes.

## 3. Error messages

Probe the mistakes a newcomer makes: missing config, missing credential, wrong argument type, unknown flag, file not found, network down, wrong runtime version.

A good error states **what** failed, **why**, and **what to do**, and points at the input that caused it.

| Check | Real finding looks like |
|-------|-------------------------|
| Missing config fails early and clearly | `TypeError: Cannot read properties of undefined (reading 'token')` instead of `FOO_API_KEY is not set; see README#auth` |
| Errors name the bad input | `Invalid option` vs `Unknown option --verbos. Did you mean --verbose?` |
| Errors are typed or coded | Library throws plain `Error` strings; callers cannot branch on `err.code` |
| API errors have a stable shape | Some endpoints return `{error}`, others `{message}`, others HTML |
| Stack traces are not the UX | CLI prints a raw stack for an expected user mistake |
| Exit codes are meaningful | CLI exits 0 after an error |
| Errors do not leak secrets | Error message echoes the full token or connection string |

Trap: only probing with harmless inputs in a scratch copy. Never trigger errors against production endpoints or with real credentials.

## 4. API naming and ergonomics

| Check | Real finding looks like |
|-------|-------------------------|
| Naming is consistent | `getUser`, `fetchOrder`, `loadInvoice` for the same operation; `userId` vs `user_id` across methods |
| The common case is short | Ten lines of builder setup for the call 90% of users make |
| Defaults are safe and sensible | Retries off by default for a network SDK; TLS verify off; timeout infinite |
| Options objects over long positional lists | `send(to, from, subject, body, true, false, 3)` |
| Sync vs async is predictable | Some methods return promises, siblings take callbacks |
| Naming follows the ecosystem | Python SDK with `camelCase` methods; Go package with stutter (`foo.FooClient`) |
| CLI follows conventions | No `--help`/`-h`, no `--version`, flags inconsistent between subcommands, no machine-readable output (`--json`) where scripting is likely |
| Resources are closeable | Client opens connections with no `close()` / context manager / `Dispose` |
| Breaking surface is small | Internals exported from the root entry point and documented by accident |

Trap: taste. Report a naming issue only when it causes a concrete wrong guess (the adopter calls the wrong method, or cannot find the right one).

## 5. Typing and editor support

| Check | Real finding looks like |
|-------|-------------------------|
| Types ship with the package | No `types`/`typings` in `package.json`, no `py.typed`, no `.d.ts` in the published tarball |
| Public signatures are precise | `options: any`, return `Promise<any>`, `**kwargs` with no `TypedDict` |
| Types match runtime | Type says `string`, runtime returns `string \| null` |
| Discriminated results or errors are typed | Callers must `as`-cast to read the error code |
| Docstrings show in the editor | Public functions have no JSDoc/docstring; hover shows nothing |
| `exports` map resolves for both ESM and CJS when both are claimed | `require('foo')` fails with `ERR_PACKAGE_PATH_NOT_EXPORTED` |

Trap: types in the repo are not types in the published package. Check the tarball (`npm pack --dry-run`, the wheel contents) when you can.

## 6. Examples

| Check | Real finding looks like |
|-------|-------------------------|
| Examples run against the current version | `examples/` pins `foo@1.2` while the README documents 3.x |
| Examples are tested or built in CI | No CI step touches `examples/`; three of them no longer compile |
| Examples cover the real use cases | Only "hello world"; nothing for auth, pagination, errors, or retries |
| Examples are copy-pasteable | Depend on repo-internal paths (`../../src`) instead of the package name |
| Examples do not model bad practice | Hard-coded secrets, swallowed errors, disabled TLS |

## 7. Changelog, versioning, and migration notes

| Check | Real finding looks like |
|-------|-------------------------|
| A changelog or release notes exist and are current | Last `CHANGELOG.md` entry is two majors behind the published version |
| Breaking changes are labeled | A renamed export appears under "Changes" with no "BREAKING" mark |
| Majors have a migration guide | v3 removed `init()`; no note on what replaces it |
| Versioning matches the claim | Claims semver; a minor release removed a public method |
| Deprecations warn before removal | Method removed with no prior runtime warning or docs note |
| Tags or releases match the registry | npm has 2.4.0; GitHub releases stop at 2.1.0 |

## 8. Local dev loop

| Check | Real finding looks like |
|-------|-------------------------|
| Clean install time is reasonable for the toolchain | 6 min install due to a postinstall that downloads a browser nobody uses in dev |
| Tests can be run focused | Only a full-suite script; no documented way to run one file |
| Watch / dev mode exists where it matters | Library with a 40 s build and no watch script |
| Feedback is fast | Lint + typecheck + test take 8 min locally; CI is the only fast path |
| The loop works offline or without secrets | Unit tests hit a real API and fail without credentials |
| Hooks are not hostile | Pre-commit runs the full test suite; no documented way to skip in an emergency |

Measure, do not guess: `time <install>`, `time <test>`, a one-line change → rebuild time. Report the numbers.

---

## Do not report

- Missing governance files with no adopter impact (send to `standardize-repo-hygiene` once, under next steps).
- Style preferences the project's linter does not enforce.
- README length, badges, emoji, or tone, unless they hide the path.
- Ecosystem-normal costs (Rust compile times, a Docker pull for a service that needs a database).
- Hypothetical adopters the project does not target (e.g. "no Windows support" for a macOS-only tool that says so).
- Anything you could not tie to a location and a scenario. Put it under "Not verified" if it matters.
