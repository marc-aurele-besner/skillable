# Flaky cause catalog

Per-language causes and the concrete fix for each, plus how to read the common failure signatures.

Read the section for the runner the target repo actually uses. Fix the **cause**, not the symptom.

---

## How to read the failure signature

| Signature | What it usually means | First thing to check |
|-----------|-----------------------|----------------------|
| `TimeoutError`, `test timed out after 5000ms` | The wait was too short, or the thing being waited for never became ready | Whether the test polls a readiness condition or sleeps a fixed amount; whether CI is simply slower than local |
| `expected 3 got 4` / `Expected: 3, Received: 4` | State from another test, an off-by-one on a shared counter, or a non-deterministic ordering | Whether the count depends on rows, fixtures, or iteration order |
| `EADDRINUSE: address already in use :::3000` | A fixed port is hard-coded and a previous test, service, or dev server still holds it | Bind to port `0` and read the assigned port back; kill the leftover process in teardown |
| `database is locked` / `SQLITE_BUSY` / `deadlock detected` | Two writers on the same file DB, or a transaction left open | Per-test DB file or in-memory DB; commit/rollback in teardown; a lock timeout |
| `database is locked` (MySQL/Postgres) | A migration or fixture ran concurrently with another worker | Serialize setup, or make the schema idempotent and per-worker |
| Snapshot mismatch (`toMatchSnapshot`, `__snapshots__`) | Unstable output: timestamps, ids, map ordering, durations, absolute paths | Make the value deterministic, or normalize it before snapshotting; do not update the snapshot to match the flaky output |
| `expected 200 got 404` (e2e) | The app was not ready, the port changed, or the build was not the one under test | Wait for the server health check; assert on the built artifact; fix the port handoff |
| `connection refused` / `ECONNREFUSED` | Nothing was listening: server not started, or started on another port | Start the server before the test and wait for readiness; pass the real port through |
| `connection reset by peer` / `ECONNRESET` | The server closed the connection, often because it crashed or the body was malformed | Check the server log; often a real bug in the handler surfaced intermittently |
| `ETIMEDOUT` on an outbound call | Real network, DNS, or a slow third party | Mock at the transport layer; inject the dependency |
| `429 Too Many Requests` / `rate limit exceeded` | Shared quota across parallel workers, or an unmocked real API | Stub the API; use per-worker credentials/quota; never retry blindly |
| `no such table` / `relation does not exist` | Migrations ran in a different order, or the schema was reset mid-suite | Apply migrations in a global fixture, once, before the tests that need them |
| `403` / `401` from an auth-gated route | Expired token, expired fixture certificate, or a clock that drifted | Freeze the clock; generate the fixture with a long validity; renew it |
| `element not found` / `unable to locate element` (e2e) | The wait was too short, or the element is behind a render that depends on a network call | Wait for the specific element with a timeout, not a fixed sleep |
| `TypeError: cannot read property of undefined` on an array element | Iteration order of a hash/dict changed, or an array was mutated in place | Sort before comparing; copy before mutating; assert on a keyed lookup |
| Flake only on the second run of a job | Something left over from the first run: a file, a port, a DB row, a background process | Clean the workspace between runs; use a per-run temp dir |
| Flake only on the last test of a file | Resource exhaustion: handles, memory, connections, disk | Close and release in teardown; check the open-file limit |

---

## Python — pytest

| Cause | Fix |
|-------|-----|
| Global state mutated by a test | Restore it in a fixture (`monkeypatch`, `unittest.mock.patch` as a context manager, or an explicit teardown that puts the value back) |
| Module-level cache or singleton not reset | Reset it in an autouse fixture; prefer a fixture-scoped instance over a module-level one |
| DB rows left behind | Use a transaction per test with rollback, or truncate between tests; scope the DB fixture per test |
| Fixed temp path | Use `tmp_path` (pytest fixture) or `tempfile.TemporaryDirectory()`; never a hard-coded `/tmp/foo` |
| Port collisions | Bind to port `0` and read `server.server_port` back |
| Time and sleep | Inject a clock, use `freezegun`/`time-machine` if already in the dependency set, or replace the sleep with a polling wait on a condition |
| Unseeded randomness | `random.seed(0)` in a fixture, or pass a seeded `random.Random(...)` instance into the code under test |
| Environment leakage | `monkeypatch.setenv`/`delenv`; use `monkeypatch.chdir` for cwd; set `TZ` via `monkeypatch.setenv("TZ", ...)` plus `time.tzset()` |
| Ordering | `pytest -p no:randomly` disables `pytest-randomly`; `pytest -p randomly` enables it. Read `pytest.ini`/`pyproject.toml` for configured plugins and ordering |
| xdist parallelism | Give each worker its own database/schema/port: `worker_id` from the `worker_id` fixture, or `testrun_uid` |
| Floating point comparisons | Compare with `pytest.approx` or round to a fixed precision |
| Fixture scope mismatch | A `session`-scoped fixture that leaks state into tests: narrow the scope, or make it read-only |

Quarantine idiom: `@pytest.mark.skip(reason="external outage, tracked in #1234")` or `@pytest.mark.xfail(strict=True, reason=...)`. `xfail(strict=True)` fails the run if the test unexpectedly passes — use it so a fixed flake is noticed.

---

## JavaScript / TypeScript — Jest, Vitest

| Cause | Fix |
|-------|-----|
| Module registry cache keeps a mutated module between tests | `jest.resetModules()` between tests, or `jest.isolateModules()`; in Vitest, `vi.resetModules()` |
| Timers left running | `jest.useFakeTimers()` with `jest.advanceTimersByTime(...)` and `jest.useRealTimers()` in teardown; in Vitest, `vi.useFakeTimers()` / `vi.advanceTimersByTime()` |
| Fake timers installed but never restored | Restore in `afterEach` |
| Shared mutable object at module scope | Build the object inside the factory/fixture instead of exporting a singleton |
| Port collisions in server tests | `server.listen(0)` and read `server.address().port` |
| `setTimeout` used to sequence work | Await the promise the code returns; never assert on a timer |
| Unmocked HTTP | `msw` handlers, or `jest.mock`/`vi.mock` the client module; unmock only the layer the test does not own |
| Open handles keeping the process alive | Close servers, clients, and databases in `afterAll`; Jest prints "A worker process has failed to exit gracefully" for this |
| Snapshot instability | Use property matchers / `toMatchSnapshot` with stable serializers; never re-record a flaky snapshot |
| Test concurrency | `test.concurrent` shares the process; use `--runInBand` to confirm the flake is concurrency-related |
| Randomness | Seed the RNG in `beforeEach`; use `jest.spyOn(Math, 'random')` for a single deterministic value |
| Fake clock vs. real clock drift | `jest.setSystemTime(new Date('2024-01-01T00:00:00Z'))` |

Order flags: `jest --randomize` (Jest 29+), `vitest --sequence.shuffle`, `vitest --sequence.seed <n>`. `jest --runInBand` serializes the run — use it to test whether parallelism is the trigger.

Quarantine idiom: `it.skip('reason — owner @who, tracked in #1234', () => {...})`. To make it loud, assert on the skip count in a suite-level test.

---

## Go

| Cause | Fix |
|-------|-----|
| Package-level variable mutated | Restore it in `t.Cleanup`; prefer passing state explicitly |
| Test runs in parallel against shared state | `t.Parallel()` requires isolated resources per test: separate DB, port, or temp dir keyed by `t.Name()` |
| Database left with rows | `t.Cleanup` that truncates, or a fresh container per test |
| `httptest.Server` not closed | `defer server.Close()` |
| Time-based logic | Inject `now func() time.Time`; use `clock` abstraction already in the repo |
| Randomness | `rand.New(rand.NewSource(1))` per test instead of the global `rand` |
| Port collisions | `net.Listen("tcp", "127.0.0.1:0")` and read the address back |
| Goroutine leak | `errgroup` with `context` and a timeout; assert the goroutine count settles |
| Environment variables | `t.Setenv` (which fails if the test is parallel) instead of `os.Setenv` |

Order flags: `go test -shuffle=on ./...` randomizes test order; `-shuffle=<seed>` makes it reproducible. `go test -count=10 ./pkg/...` reruns the package ten times — the built-in way to detect a flake.

Quarantine idiom: `t.Skip("external outage — owner @who, tracked in #1234")`.

---

## Rust

| Cause | Fix |
|-------|-----|
| Global state (`static mut`, `OnceLock`, `lazy_static`) | Prefer dependency injection; if a global is unavoidable, reset it in the test or use a scoped guard that restores it |
| Test order dependence | `cargo test -- --test-threads=1` to confirm; `serial_test` crate if already in use |
| Time | Inject a `Clock` trait or a `time::OffsetDateTime` value |
| Randomness | `StdRng::seed_from_u64(0)` instead of `thread_rng()` |
| Filesystem | `tempfile::TempDir` per test; never a shared `/tmp` path |
| Ports | Bind to `127.0.0.1:0` and read the local address back |
| Async timing | `tokio::time::pause()` and `tokio::time::advance()` for deterministic time |
| Test database | Use `sqlx::test` or a per-test schema if the repo already has that setup |

Order flags: `cargo test -- --test-threads=1`, `cargo nextest run --test-threads=1`, and `cargo test -- --nocapture` to see prints.

Quarantine idiom: `#[ignore = "external outage — owner @who, tracked in #1234"]` — note that ignored tests are invisible by default; pair it with a loud check (see step 5).

---

## Ruby — RSpec

| Cause | Fix |
|-------|-----|
| `before` hook mutating shared state | Use `let` for lazy, per-example values instead of `before` blocks that mutate a global |
| Class-level state (class variables, memoized class attributes) | Reset in `after`; prefer instance-level state |
| Database records left behind | `DatabaseCleaner` truncation if the repo uses it, or a transaction-wrapped example |
| Random order exposing coupling | `rspec --order random` to surface it; `config.order = :random` is often already on |
| Fixed time | `ActiveSupport::Testing::TimeHelpers#travel_to` or a `Timecop` block if already a dependency |
| Randomness | `srand(1234)` in a `before` hook, or inject the random value |
| File fixtures | `Dir.mktmpdir` per example, cleaned in `after` |
| Ports | `TCPServer.new('127.0.0.1', 0)` and read the assigned port |

Quarantine idiom: `skip "external outage — owner @who, tracked in #1234"` — keep the reason string; RSpec prints it in the summary, which is already loud.

---

## Java / Kotlin — JUnit

| Cause | Fix |
|-------|-----|
| Static state across tests | Reset in `@AfterEach`; avoid `static` mutable fields in tests |
| Spring context pollution | Use `@DirtiesContext` sparingly, or isolate with `@Transactional` rollback |
| Database state | `@Transactional` (rolled back automatically) or truncate between tests; a per-class schema if the suite is parallel |
| Time | Inject `Clock`; `Clock.fixed(...)` for determinism |
| Randomness | Seeded `Random` instance created per test |
| Ports | `ServerSocket(0)` and read the local port |
| Parallel execution | JUnit 5 parallel execution is opt-in; when enabled, give each test unique resources |
| Async / Awaitility | Use Awaitility's polling assertions instead of `Thread.sleep` |

Quarantine idiom: `@Disabled("external outage — owner @who, tracked in #1234")` — a disabled test is not reported as a failure, so pair it with a loud check.

---

## End-to-end — Playwright, Cypress

| Cause | Fix |
|-------|-----|
| Server not ready | Wait for a health check before the first assertion; `webServer` in the Playwright config does this |
| Flaky selector | Prefer role or test-id selectors over CSS/XPath; wait for the specific element with `expect(locator).toBeVisible()` instead of a fixed wait |
| Animation / transition | Disable animations in the test, or wait for the element to be stable (`toBeStable()`) |
| Fixed sleep | `page.waitForFunction`, `expect.poll`, or `cy.waitFor` on a real condition |
| Test data collisions | Unique data per test (unique email/id), created and deleted per test |
| Shared browser context | Use a fresh context per test (`browser.newContext()`), not a shared page |
| Port or base URL mismatch | Derive the base URL from the config; do not hard-code it |
| Screenshot / trace artifacts | Write to a per-test directory; compare with a tolerance, not byte equality |
| Third-party widgets | Block or stub third-party requests (`page.route`) |
| Eventual consistency | Poll for the state change with a deadline instead of asserting once |

Quarantine idiom: `test.skip(condition, 'reason')` or `test.fixme('reason')`. `test.fixme` is reported as a known failure rather than a skip — often the more honest option.

---

## Cross-language quick checklist

Run through this list before declaring a cause unknown:

1. Does the test pass alone but fail in the suite? → Order dependence.
2. Does it fail only with more workers? → Shared resource.
3. Does it fail only on one OS or one timezone? → Environment.
4. Does it fail only on a slow machine? → Timing.
5. Does the wrong value differ every time? → Randomness or ordering.
6. Does it fail only after many tests in the same file? → Resource leak.
7. Does it need the network? → Unmocked external.
8. Does it depend on "now"? → Clock injection.
9. Does it depend on a port, a file path, or a lock? → Fixed resource.
10. Did it start failing after a specific commit or dependency bump? → Bisect.
