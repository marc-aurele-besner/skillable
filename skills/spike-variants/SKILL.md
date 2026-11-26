---
name: spike-variants
description: >-
  Implement the same feature N different ways at once, each variant built by
  its own subagent in its own isolated git worktree from a shared acceptance
  contract, then run every variant through the project's tests, lint,
  typecheck, and optional benchmark, publish a side-by-side comparison (diff
  size, new dependencies, test results, performance, trade-offs), and turn the
  chosen variant into a clean branch and pull request while cleaning up the
  rest. The code counterpart of wireframe-feature. Use whenever the user wants
  to compare implementation approaches, prototype a feature several ways, spike
  competing designs or libraries, pick an architecture with evidence instead of
  debate, or build out a chosen wireframe. Also triggers on /spike-variants with
  the feature and an optional variant count and benchmark command.
argument-hint: "<feature> [variants=3] [bench=\"<cmd>\"]"
---

# Spike Variants

Goal: replace "which approach should we take?" debates with evidence. Build N genuinely different implementations of the same feature in parallel, hold them to the same acceptance contract, measure them the same way, and let the user pick, then ship only the winner.

## When to use

- "Try this three ways and tell me which is best"
- "Should we use a state machine, a reducer, or plain hooks for X?" / "Library A vs. library B for Y?"
- "Build variant B from the wireframes" (pairs with `wireframe-feature`)
- `/spike-variants <feature> [variants=N] [bench="<cmd>"]`
- Not for a change with one obvious implementation (just implement it) or a pure UX question (use `wireframe-feature`).

## Inputs

| Input | Default | Notes |
| --- | --- | --- |
| Feature | required | From arguments, the conversation, an issue URL, or a chosen wireframe. If absent, ask one short question. |
| Variants | 3 | Clamp 2–5. |
| Bench | none | A command that prints a number (ms, ops/s, bytes). If absent, measure what the project already can (bundle size, test duration). |
| Base | default branch | `origin/<default>` after `git fetch`. |

## 0. Preflight

1. `git fetch origin`; confirm the working tree is clean (stash nothing silently, if it is dirty, stop and ask).
2. Detect the project's commands from `package.json` scripts, `Makefile`, CI workflows, or docs: install, test, lint, typecheck, build. Run the test command once on the base to record a **baseline** (pass/fail counts, duration). If the baseline is already red, say so and record which tests fail so variants are not blamed for them.

## 1. Model the feature and the contract

Before any variant is written, define what "done" means for all of them:

- **Acceptance criteria**: 3–8 observable behaviors, including edge cases and error paths.
- **Shared acceptance tests**: when the project has a test suite, write tests for the criteria against a stable public seam (route, exported function, component props, CLI). Commit them on a base branch `spike/<feature>` from `origin/<default>`. Every variant starts from this commit and must not edit these tests. If a stable seam is impossible before choosing an approach, write the criteria as a checklist each variant must demonstrate instead.
- **Constraints**: performance budget, no new runtime dependencies (or allowed ones), compatibility targets, files that must not change.

## 2. Diverge: choose distinct approaches

Pick N approaches that differ in **architecture or strategy**, not style:

- Where state lives (server vs. client, store vs. local, DB vs. cache)
- Build vs. buy (hand-rolled vs. a library, name the library and its size)
- Data flow (push vs. pull, sync vs. queue, optimistic vs. pessimistic)
- Generality (narrow fix vs. reusable abstraction)

Name each one (`A · Server actions`, `B · Client store`, `C · Queue + worker`) with a one-sentence thesis and the trade-off it bets on. Show the list to the user only if an approach depends on a decision that is theirs to make (e.g. adding a paid service); otherwise proceed.

## 3. Build in parallel, isolated

Each variant gets its own worktree and branch `spike/<feature>-<letter>` from `spike/<feature>`.

- **Claude Code:** launch one subagent per variant **in a single message** so they run concurrently, each with `isolation: "worktree"`. Give each a self-contained brief: the feature, the acceptance criteria, the path to the shared tests, its approach and thesis, the constraints, the project's commands, and "commit on your branch; do not push; do not edit the shared acceptance tests; report back in the format below".
- **Other agents:** create worktrees with `git worktree add ../<repo>-spike-<letter> -b spike/<feature>-<letter> spike/<feature>` and build them one after another.
- Each variant must: install, implement, make the shared tests pass, keep the existing suite green, and add any tests specific to its approach. Small, honest commits.

Each subagent reports, as structured data:

```text
variant, branch, worktree path, commit sha
acceptance: passed/total; existing suite: passed/failed vs. baseline
lint: ok/errors; typecheck: ok/errors; build: ok/failed
diff: files changed, +lines/-lines (excluding lockfiles and the shared tests)
new dependencies: name@version (and install size if known)
notes: what was hard, what was skipped, known gaps
```

## 4. Measure the same way

After all variants return, re-run the checks yourself in each worktree, do not trust self-reports blindly. See [references/comparison-report.md](references/comparison-report.md) for the metric list and scoring rubric. At minimum: acceptance and suite results, lint/typecheck/build, diff size, new dependencies, bundle or binary size delta when the project builds one, the bench command (median of 5 runs) when given, and a short **code-fit** review (follows existing patterns, readability, extensibility, risk).

A variant that cannot pass its acceptance tests stays in the report as **failed**, with the reason, that is a finding, not something to hide.

## 5. Publish the comparison

- **Artifact-capable agent:** publish one comparison page as an artifact titled `<Feature> spike`: a scorecard table, per-variant cards (thesis, metrics, the key diff hunks with syntax highlighting, notes), a recommendation, and the exact command to inspect each branch locally. Republish in place on later rounds.
- **Otherwise:** write the same page outside the tracked tree and open it locally, and print the scorecard in the chat.

Then report:

```markdown
**<Feature>** · <N> variants · baseline: <tests> · <link>

| Variant | Acceptance | Suite | Diff | New deps | Bench | Fit |
| --- | --- | --- | --- | --- | --- | --- |
| A · Server actions | 8/8 | ✅ | +214/−31 |, | 42 ms | ●●●○ |

**Recommendation:** <variant> because <one sentence>; runner-up <variant> if <condition>.
**Pick one, mix (e.g. "A with C's retry logic"), or ask for another round.**
```

## 6. Converge on the choice

- **"Go with B"** → create `feat/<feature>` from a fresh `origin/<default>`, bring over the shared acceptance tests and variant B's commits (cherry-pick or squash into logical commits), re-run every check, then push and open a PR whose body summarizes the spike: approaches tried, the scorecard, and why B won. Follow the repo's branch and commit conventions.
- **"Mix A and C"** → a new variant D built in its own worktree from the same contract, then compare again.
- **"Another round"** → new approaches that avoid concepts already tried.

## 7. Clean up

After the PR is open (or the user abandons the spike): remove every spike worktree (`git worktree remove`), delete the local `spike/*` branches, and `git worktree prune`. Never push losing variants unless the user asks to keep them; if they ask, push them as draft branches and list the URLs.

## Guardrails

- Never modify the user's current working tree or branch; all work happens in worktrees.
- Variants never push, open PRs, or touch shared remotes, only the converge step does.
- Do not add dependencies the constraints forbid; flag licenses that differ from the project's.
- Keep secrets out of the comparison page; redact env values from command output.

## Quality bar before reporting

- [ ] Every variant was held to the same acceptance contract and measured by the same commands
- [ ] Variants differ in approach, not just naming or style
- [ ] Numbers in the comparison were re-run by the orchestrator, not copied from self-reports
- [ ] Failed variants are shown with reasons
- [ ] No worktrees or spike branches left behind after converging
