# Testing patterns and anti-patterns

Per-framework examples for writing the tests described in `SKILL.md` step 4. Use the section for the project's own framework, and borrow the general sections (table-driven tests, fixtures, mocking boundaries, contract tests) from any framework.

Examples are illustrative. Copy the repo's existing conventions instead of importing these verbatim.

## Principles that hold everywhere

1. **Assert observable behavior.** Return value, raised error, emitted event, persisted record, outbound request. Not private fields, not call counts, not internal state.
2. **One behavior per test.** A test that asserts three unrelated things fails for one reason and gets fixed wrongly.
3. **Deterministic.** No network, no wall clock, no real randomness, no sleeps, no writes outside a temp dir, no order dependence.
4. **Fail for the right reason.** If the test would still pass with a deliberately broken implementation, it is not a test.
5. **Public API only.** Test the surface the rest of the code uses.

## pytest

```python
# tests/test_proration.py
import pytest
from myapp.billing.proration import prorate


@pytest.mark.parametrize(
    ("total", "days_used", "expected"),
    [
        (300.0, 15, 150.0),
        (300.0, 30, 300.0),
        (300.0, 0, 0.0),
        (0.0, 15, 0.0),
    ],
)
def test_prorate_refunds_remaining_days(total, days_used, expected):
    assert prorate(total, days_used) == pytest.approx(expected)


def test_prorate_rejects_more_days_than_the_period():
    with pytest.raises(ValueError, match="days_used"):
        prorate(300.0, 31)
```

Fixtures belong in `conftest.py` when they are shared, in the test module when they are local:

```python
# tests/conftest.py
import pytest

@pytest.fixture
def customer():
    return Customer(id="cus_1", plan=Plan.PRO)


@pytest.fixture
def frozen_now(monkeypatch):
    # freeze time instead of sleeping
    monkeypatch.setattr("myapp.billing.clock.now", lambda: datetime(2024, 1, 15, tzinfo=UTC))
```

Use `tmp_path` for anything on disk, `monkeypatch` for environment and attribute patching, `caplog` when the log record itself is the contract, `capsys` for stdout. Use `pytest.raises(..., match=...)` when the message is part of the contract; omit `match` when it is not.

Parametrize over inputs and expected outputs rather than writing N near-identical functions. For many cases, use `pytest.param(..., id="...")` so a failure names the case.

## Jest and Vitest

```ts
// src/billing/proration.test.ts
import { describe, it, expect } from 'vitest';
import { prorate } from './proration';

describe('prorate', () => {
  it.each([
    [300, 15, 150],
    [300, 30, 300],
    [300, 0, 0],
  ])('refunds %i of %i over %i days', (total, days, expected) => {
    expect(prorate(total, days)).toBe(expected);
  });

  it('rejects more days than the billing period', () => {
    expect(() => prorate(300, 31)).toThrow(/days_used/);
  });
});
```

- Assert on the value, or on the thrown error's message when the message is the contract. `expect(fn).toThrow()` without an argument only proves *something* was thrown.
- `await expect(promise).rejects.toThrow(TypeError)` for async failures; never leave a promise un-awaited.
- Use `beforeEach`/`afterEach` for per-test setup and `beforeAll`/`afterAll` for expensive one-time setup. Reset shared state in `afterEach`, not at the start of the next test.
- `vi.useFakeTimers()` / `jest.useFakeTimers()` with `setSystemTime` for clock control; `vi.setSystemTime(new Date('2024-01-15T00:00:00Z'))`.
- Match the runner's assertion library: `expect` in Vitest and Jest, `assert` in Node's built-in test runner.
- Follow the repo's config: if `globals: true` is set, omit the `import { describe, it, expect }` line.

## Go

```go
package proration

import "testing"

func TestProrate(t *testing.T) {
	tests := []struct {
		name    string
		total   float64
		days    int
		want    float64
		wantErr bool
	}{
		{name: "half a month", total: 300, days: 15, want: 150},
		{name: "full month", total: 300, days: 30, want: 300},
		{name: "no usage", total: 300, days: 0, want: 0},
		{name: "too many days", total: 300, days: 31, wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := Prorate(tt.total, tt.days)
			if tt.wantErr {
				if err == nil {
					t.Fatalf("Prorate(%v, %v) = %v, want error", tt.total, tt.days, got)
				}
				return
			}
			if err != nil {
				t.Fatalf("Prorate(%v, %v) returned unexpected error: %v", tt.total, tt.days, err)
			}
			if got != tt.want {
				t.Errorf("Prorate(%v, %v) = %v, want %v", tt.total, tt.days, got, tt.want)
			}
		})
	}
}
```

- One `_test.go` file next to the source, same package (or `<pkg>_test` for the external API).
- Table tests with `t.Run` subtests give per-case names in CI output.
- `t.TempDir()` for files, `t.Setenv()` for environment variables (it restores automatically).
- Do not call `t.Parallel()` unless the repo already does; it exposes order dependence.

## Rust

```rust
// src/billing.rs
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prorate_refunds_remaining_days() {
        assert_eq!(prorate(300.0, 15), Ok(150.0));
    }

    #[test]
    fn prorate_rejects_more_days_than_the_period() {
        assert!(matches!(prorate(300.0, 31), Err(ProrationError::InvalidDays)));
    }
}
```

- Unit tests live in a `#[cfg(test)] mod tests` block; integration tests live in `tests/` and use only the public API.
- Prefer asserting on `Result`/`Option` variants (`matches!`, `unwrap_err`) over matching on error strings.
- `tempfile::TempDir` for files — only if the crate is already a dependency.
- `cargo test -- --nocapture` when a test's output matters.

## RSpec

```ruby
# spec/billing/proration_spec.rb
RSpec.describe Billing::Proration do
  describe "#prorate" do
    subject(:prorate) { described_class.prorate(total, days_used) }

    context "with a valid number of days" do
      let(:total) { 300.0 }
      let(:days_used) { 15 }

      it { is_expected.to eq(150.0) }
    end

    context "with more days than the period" do
      let(:total) { 300.0 }
      let(:days_used) { 31 }

      it "raises an error" do
        expect { prorate }.to raise_error(Billing::Proration::InvalidDays)
      end
    end
  end
end
```

- `let` for lazy, overridable setup; `before` only when the setup must run for every example regardless of use.
- Prefer explicit `it "does X"` blocks over the one-liner `it { is_expected.to ... }` in shared examples; the one-liner saves lines but hides the behavior in CI output.
- Use the project's factory (FactoryBot, etc.) rather than hand-building objects, but prefer real objects over `build_stubbed` when the test reads attributes.
- Minitest repos use `test "..." do ... end` with `assert_equal`; follow whichever the repo already uses.

## JUnit (JUnit 5) and Kotlin

```java
// src/test/java/com/example/billing/ProrationTest.java
class ProrationTest {
    @ParameterizedTest
    @CsvSource({
        "300.0, 15, 150.0",
        "300.0, 30, 300.0",
        "300.0,  0,   0.0",
    })
    void prorateRefundsRemainingDays(double total, int days, double expected) {
        assertEquals(expected, Proration.prorate(total, days), 1e-9);
    }

    @Test
    void prorateRejectsMoreDaysThanThePeriod() {
        assertThrows(IllegalArgumentException.class, () -> Proration.prorate(300.0, 31));
    }
}
```

```kotlin
// src/test/kotlin/com/example/billing/ProrationTest.kt
class ProrationTest {
    @ParameterizedTest
    @MethodSource("validCases")
    fun `refunds remaining days`(total: Double, days: Int, expected: Double) {
        assertEquals(expected, Proration.prorate(total, days), 1e-9)
    }

    companion object {
        @JvmStatic
        fun validCases() = listOf(
            Arguments.of(300.0, 15, 150.0),
            Arguments.of(300.0, 30, 300.0),
        )
    }
}
```

- JUnit 5: `@Test`, `@ParameterizedTest` with `@CsvSource` or `@MethodSource`, `@TempDir` for files, `@BeforeEach` for setup.
- Assert the exception *type* with `assertThrows`; assert the message only when the message is the contract.
- Kotlin: `kotlin.test` assertions, `assertFailsWith` for exceptions, backtick test names for readability.

## Table-driven tests

Use one table with named cases instead of many near-identical functions.

| Situation | Pattern |
|-----------|---------|
| Same function, many inputs | pytest `parametrize`, Vitest/Jest `it.each`, Go table test, JUnit `@ParameterizedTest`, Rust loop over a `Vec` of tuples |
| Same input, many outputs | One test per output, named after the case |
| Many fields, one invariant | Build the object in a builder/helper and assert the invariant, not each field |
| Enum-like variants | Parameterize over the variants and assert the branch, not the implementation |

Keep the table next to the test that uses it. A shared table module for two tests is a premature abstraction.

## Fixtures and helpers

- **Reuse first.** If the repo has `conftest.py`, factories, `testdata/`, a `setupTest` helper, or a `TestBase` class, use it. Adding a parallel helper system is the most common way a test PR goes wrong.
- **Scope.** `conftest.py` for cross-module fixtures, module-level fixtures for the file, inline literals for one-offs.
- **Fresh state per test.** Each test gets its own database row, temp directory, or fake. Sharing mutable state across tests is the number-one source of order-dependent flakes.
- **Builders over factories when the object is big.** A builder lets each test state only the fields it cares about.
- **Keep helpers in the test tree.** A helper under `src/` is production code that ships.
- **One purpose per helper.** A helper that builds a user *and* a subscription *and* saves both is opaque; split it.

## Mocking boundaries

Mock at the boundary you do not own, never at the boundary you are testing.

**Good candidates to mock:**

- Network and third-party APIs (HTTP, email, payment gateways, cloud SDKs).
- The system clock, randomness, and the filesystem in narrow cases.
- Slow or expensive collaborators (a search index, a report generator).
- A collaborator whose only contract is "it returns this" — a repository returning a fixture.

**Never mock:**

- The unit under test, or anything inside it.
- Pure functions — a mocked pure function is a worse stub.
- The standard library (except the clock).
- The thing whose behavior the test exists to verify. If the test verifies pricing, do not mock pricing.
- Everything. If a test needs six mocks, the unit is doing too much.

**Assert on the mock only when the interaction is the contract:**

```python
def test_order_is_submitted_to_the_gateway():
    gateway = FakeGateway()
    checkout.place_order(cart, gateway=gateway)
    assert gateway.charges == [Charge(amount=2500, currency="usd")]
```

Assert the *effect* (the charge, the persisted row, the emitted event), not `gateway.submit.assert_called_once_with(...)` with the same arguments the production code already has. Asserting a call with arguments that merely restate the implementation is a tautology.

Prefer a hand-written fake over a mock framework when the fake is small and the behavior matters. A fake records real interactions and fails the assertion with a readable message.

## Contract tests

Use a contract test when two sides of an interface are owned by different teams or deployed independently: an HTTP API and its client, a message producer and consumer, a plugin and its host.

- Write the contract **once**, from the consumer's point of view, and run it against both the real provider and the fake.
- Assert on the wire format the consumer actually parses — status code, headers, body shape — not on internal calls.
- Keep the contract file small and versioned with the interface. A contract that changes with every release is not a contract.
- In Go and Rust, prefer a shared testdata file (golden file) both sides read, so the contract has exactly one source of truth.

Do not add contract tests to a project that has no consumer/producer split — they add maintenance without adding safety.

## Anti-pattern catalog

| Anti-pattern | Why it hurts | Instead |
|--------------|---------------|--------|
| Asserting on mocks (`mock.assert_called_with(...)` restating the implementation) | Passes even when the feature is broken | Assert the observable effect |
| `expect(result).toBeDefined()` / `assert result is not None` | Passes for any non-null value | Assert the exact value |
| `expect(true).toBe(true)` | Cannot fail | Delete it, or assert the real condition |
| Snapshotting whole objects, HTTP bodies, or rendered trees | Any unrelated change breaks the test; diffs become unreviewable | Assert the specific fields or DOM nodes that matter |
| Sleeps and `waitFor` polling on wall-clock time | Flaky under load, slow, and hides real races | Use fake timers, `await` the event, or a deterministic signal |
| Order-dependent tests (a test depends on the previous one) | Fails in isolation, passes locally | Fresh state per test; explicit setup |
| Testing private helpers directly | Freezes the implementation | Test through the public path |
| One test asserting many behaviors | Fails for one reason, gets "fixed" wrongly | One behavior per test |
| Duplicating setup in every test file | Setup drifts; fixes must be applied N times | Shared fixture / builder |
| Mocking the unit under test or pure functions | Tests the mock, not the code | Call the real thing |
| Asserting on log text | Logs change for refactors; the message is rarely the contract | Assert on the returned error or the emitted event |
| Asserting on internal state after the call | Couples the test to the implementation | Assert on the output and the effects |
| Testing getters, DTOs, generated code | Zero behavioral value | Delete the code or mark it ignored |
| Chasing a coverage number | Produces tests nobody defends | Cover behaviors; report the delta as a side effect |
| A test that cannot fail | The worst kind: it looks like coverage | Mutate the source and confirm the test goes red |
| Fixing the production code inside a "add tests" PR | Mixes a behavior change with a test change | Separate PR, or justify it explicitly |
