# Advisory sources, audit commands, and severity-vs-reachability

Reference for the `audit-vulnerabilities` skill. Read the section for the ecosystem in play; the goal is to pick the right source, understand what it covers, and reason about real exposure instead of the raw score.

## Source priority

Use the ecosystem's own auditor first — it understands that ecosystem's resolution semantics, which OSV and GitHub Advisory Database do not.

| Priority | Source | Covers | Needs network | Needs a key |
|----------|--------|--------|---------------|-------------|
| 1 | Ecosystem auditor (`npm audit`, `pnpm audit`, `yarn npm audit`, `pip-audit`, `cargo audit`, `govulncheck`) | That ecosystem's full published advisory set, matched against the resolved lockfile | Yes | No |
| 2 | OSV.dev / `osv-scanner` | Cross-ecosystem database (npm, PyPI, crates.io, Go, RubyGems, Packagist, Maven, NuGet, and more); covers unmaintained ecosystems GitHub advisories miss | Yes | No |
| 3 | GitHub Advisory Database (GHSA) | Curated advisories for npm, PyPI, RubyGems, Maven, NuGet, Go, Rust, and more | Yes | No (public API) |
| 4 | Ecosystem registry advisories endpoint | Fallback when the local auditor is unavailable | Yes | No |

If a source needs network access or an API key and it is unavailable, **say so explicitly**. A source that failed is not a source that found nothing. Never report "no vulnerabilities" when a source did not run.

## Per-ecosystem commands

### JavaScript / TypeScript (npm, pnpm, yarn)

Detect the package manager from the lockfile and use only that one. Never mix them.

```bash
npm audit --json                 # npm >= 7 auditReportVersion 2
npm audit --omit=dev --json      # production dependencies only
npm ls <package> --all           # full dependency path to a package
npm explain <package>            # npm >= 8: why is this here
npm view <package> versions      # published versions
npm view <package>@<version> dependencies

pnpm audit --json
pnpm audit --prod --json
pnpm why <package>
pnpm list <package> --depth Infinity

yarn npm audit --json            # Yarn 2+ (berry)
yarn npm audit --environment production --json
yarn why <package>
yarn list --pattern <package>
```

Yarn classic (`yarn audit --json`) emits NDJSON `auditAdvisory` records; Yarn berry (`yarn npm audit --json`) emits the same shape. The bundled collector handles both.

### Python (pip, pipenv, poetry, uv)

```bash
pip-audit --format json
pip-audit --format json --desc            # include descriptions
pip-audit --format json --local            # skip well-known remote packages
pip-audit --requirement requirements.txt --format json
pip-audit --locked .                       # audit an already-locked environment

poetry show --tree                        # dependency tree
uv pip list
```

`pip-audit` reports the advisory id and the fixed versions but often no severity — a `PYSEC-…` id maps to a GitHub advisory that does. Resolve severity from OSV or GHSA when `pip-audit` reports `unknown`.

### Rust (cargo)

```bash
cargo audit --json
cargo audit --json --deny warnings       # fail on warnings
cargo tree -i <package>                  # inverse tree: who depends on this
cargo tree -p <package>
```

`cargo audit` requires the RustSec advisory database (`cargo install cargo-audit`; the database is fetched and cached automatically). It exits non-zero when it finds advisories — that is a finding, not a crash.

### Go

```bash
govulncheck -json ./...                  # call-graph-aware; best reachability signal Go offers
govulncheck ./...
govulncheck -mode=binary ./...
```

`govulncheck` is the only source in this list that performs real static reachability analysis: it reports findings only for symbols reachable from the program's entry points. Treat a `govulncheck` finding as proven-reachable and other tools' findings as unproven until you check.

### Cross-ecosystem

```bash
osv-scanner --format json --lockfile=package-lock.json
osv-scanner --format json -r .            # scan a directory recursively
osv-scanner --format json --lockfile=pnpm-lock.yaml
```

`osv-scanner` is the fallback for ecosystems with no local auditor, and the cross-check for ecosystems that do.

### GitHub Advisory Database directly

```bash
gh api /advisories?ecosystem=npm\&severity=high
gh api /advisories/GHSA-xxxx-xxxx-xxxx
gh api repos/<owner>/<repo>/dependabot/alerts --paginate
```

The Dependabot alerts endpoint is useful for cross-checking a repo's own alerts, but it only lists what GitHub's bots already found — it is not a full-tree audit. See `fix-dependabot-alert` for working a single alert.

## What each database covers (and does not)

- **GitHub Advisory Database** — community-curated advisories for npm, PyPI, RubyGems, Maven, NuGet, Go, Rust, Erlang, Swift, and more. Does not cover every CVE in an ecosystem: packages outside GitHub's index are absent, and a dependency with no GHSA entry is invisible here.
- **OSV.dev** — aggregates many upstream databases (GitHub, PyPA, RustSec, Go, RubyGems, Packagist, Debian, and others) behind one schema. Better coverage of less common ecosystems, and it records version ranges and ecosystem-specific data precisely.
- **RustSec** — the Rust ecosystem's own database, with a maintained `informational` category that does not map cleanly onto CVSS severity. `cargo audit` reports it; treat `unmaintained` advisories as maintenance risk, not exploitability.
- **PyPA Advisory Database** — `pip-audit` reads it. Coverage is good for popular packages and thin for long-tail ones.
- **Go vulnerability database** — `GO-…` ids published by the Go security team, mirrored into OSV. `govulncheck` uses it with call-graph analysis.

## Severity vs. exploitability vs. reachability

These are three different questions. The advisory score answers only the first.

**Severity** — the intrinsic impact if the flaw is exploited: critical, high, medium, low. Sources express this differently (CVSS base score, CVSS vector, a proprietary label). The bundled collector normalizes them and computes a CVSS v3.x base score from a vector string when the source only exposes a vector.

**Exploitability** — how practically the flaw can be reached: is there a public exploit, is it in a commonly exploited list (CISA KEV), does the flaw need unusual preconditions? An advisory with no exploit in the wild and a narrow precondition is materially less urgent than its score suggests. The GitHub advisory API exposes `cvss`, `cwes`, and sometimes an exploit reference; CISA KEV is a public JSON catalog worth checking for high-value targets.

**Reachability** — whether this project can reach the vulnerable code at all. This is the question that decides the tier, and it is entirely project-specific:

- Is the package a **direct** dependency, or pulled in transitively? A transitive vuln in a build tool does not ship.
- Is it **production**, **dev**, or **build-only**? A vulnerable package used only by the test runner never processes production input.
- Does this project **call** the vulnerable function, or use the vulnerable configuration? Many advisories affect one specific API (`tar`'s extraction of archives with symlinks, `minimist`'s handling of `__proto__` keys, a parser's handling of a specific MIME type). If the project never touches that API, the flaw is not reachable.
- Does the vulnerable path **handle untrusted input**? A flaw in a code path that only ever sees values the project itself generated is a much smaller problem than one reachable from user input.

Practical checks:

```bash
# what pulls this in, and how deep
npm ls <package> --all
pnpm why <package>
cargo tree -i <package>

# is the vulnerable API actually used here
rg -n "createGunzip|extract" src/
rg -n "minimist" src/ --type js
```

`rg` is preferred; fall back to `grep -rn` if `rg` is not installed.

## Fix syntax per ecosystem

Always prefer a real upgrade. Reach for an override only when no parent accepts the fixed version yet.

### npm

```json
{
  "overrides": {
    "minimist": "1.2.8",
    "some-parent": {
      "vulnerable-child": "2.0.1"
    }
  }
}
```

### pnpm

```json
{
  "pnpm": {
    "overrides": {
      "minimist": "1.2.8"
    }
  }
}
```

### Yarn

Classic (Yarn 1):

```json
{
  "resolutions": {
    "minimist": "1.2.8"
  }
}
```

Berry (Yarn 2+):

```yaml
resolutions:
  minimist@1.2.8:
```

### Cargo

```toml
[patch.crates-io]
smallvec = "0.6.14"
```

Or pin the parent that carries the vulnerable transitive. `[patch]` changes where the source comes from, so verify the patched version's API is compatible.

### Python

Preferred: bump the direct requirement and regenerate the lockfile.

```bash
# pip-tools
pip-compile --upgrade-package <package> requirements.in
# poetry
poetry update <package>
# uv
uv lock --upgrade-package <package>
```

A constraint file pins a transitive when the parent cannot move:

```text
# constraints.txt
minimist==1.2.8
```

### Go

Bump the module requirement in `go.mod` and run `go mod tidy`. `go get <module>@<fixed>` when the fix is in a transitive.

```bash
go get golang.org/x/net@v0.23.0
go mod tidy
```

### Ruby

```bash
bundle update <gem>
```

### PHP

```bash
composer update <vendor>/<package>
```

## How to explain a fix in a PR body

A good PR body answers four questions without making the reader open the diff:

1. **What was vulnerable and why it matters here** — the advisory id, the package, and the one sentence on real exposure ("this package parses attacker-supplied archives in the import path", not "critical severity").
2. **What changed** — the manifest and lockfile diff, in plain words.
3. **Why this remediation** — why the direct bump, and not the override. Mention the alternatives you rejected and why.
4. **What is left** — the residual risk you did not fix, with the tracking issue, and any major-version migration deferred.

Template:

```markdown
## What

Fixes <GHSA-xxxx-xxxx-xxxx> (<CVE-2024-…>) in `<package>`.

The vulnerable `<package>@<version>` was reached through `<parent>` and used by
`<path in this repo>` to <what it does>. <Why it is or is not reachable by
untrusted input.>

## Changes

- `<package>` bumped `<old>` -> `<new>` in `package.json`
- lockfile regenerated

## Why this remediation

<Direct bump vs. override vs. parent bump, and what was rejected.>

## Verification

- `<npm audit --json>`: this advisory no longer reported
- `<test command>`: passing

## Residual risk

- <Advisory not fixed / no patched version>, tracked in #<issue>.
- <Major-version migration deferred>, see #<issue>.
```

Never state a fix without naming how it was verified.
