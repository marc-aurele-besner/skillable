# Comparison report: metrics and scoring

Measure every variant with the same commands, from its own worktree, after all variants are done. Record raw values first; score second.

## Hard metrics

| Metric | How | Notes |
| --- | --- | --- |
| Acceptance | Run only the shared acceptance tests | `passed/total`. Any failure caps the variant's verdict at "failed". |
| Existing suite | Full test command | Compare with the baseline: new failures are regressions; pre-existing failures are not the variant's fault. |
| Lint / typecheck / build | Project commands | `ok` or error count. |
| Diff size | `git diff --shortstat spike/<feature>...spike/<feature>-<x> -- . ':!*lock*' ':!<shared-tests>'` | Smaller is not automatically better, note it, then judge fit. |
| Files touched | `git diff --name-only …` | Flag edits outside the expected area. |
| New dependencies | Diff of the manifest(s) | Name, version, license, install size (`npm view <pkg> dist.unpackedSize`, bundlephobia-style estimate, or `cargo tree`). |
| Bundle / binary delta | Project build output, `du -b` of the artifact, or the bundler's stats | Only when the project ships a bundle or binary. |
| Bench | The user's `bench` command, 1 warm-up + 5 runs, report the median and spread | Same machine, sequentially, nothing else running. |
| Test duration | Wall time of the suite | Catches approaches that slow CI. |

## Soft metrics (orchestrator's review)

Read each variant's diff in full and rate 1–4:

- **Fit**: follows the codebase's existing patterns, naming, layering, and error handling.
- **Clarity**: a teammate could review and maintain it without the spike's context.
- **Extensibility**: how it handles the next likely requirement (name that requirement).
- **Risk**: migration, concurrency, security, or operational risk it introduces (4 = lowest risk).

Justify each rating with one sentence and a file reference.

## Verdict

- **Failed**: acceptance tests fail, or the build is broken.
- **Viable**: passes everything; trade-offs to weigh.
- **Recommended**: the viable variant with the best balance for *this* project's priorities. State the priorities you assumed (e.g. "small bundle over flexibility").

Never average soft and hard metrics into one number; show them side by side and explain the recommendation in words.

## Page layout

1. Header, feature, base commit, baseline test result, date.
2. Scorecard table, one row per variant, hard metrics then soft ratings, verdict badge.
3. Recommendation, one paragraph, plus the runner-up and when it would win.
4. Variant cards, thesis, metrics, 2–4 key diff hunks (syntax highlighted, collapsed by default), dependencies added, notes and known gaps, and `git switch spike/<feature>-<x>` / worktree path to inspect locally.
5. Acceptance criteria, the shared contract, with a pass/fail matrix per variant.

Light and dark themes, readable at phone width, no network calls beyond a pinned syntax-highlighting library.
