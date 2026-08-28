# GitHub Actions minutes playbook

Apply these plays in `optimize-github-actions`. Each play: **detect → do → don't**. Prefer the smallest YAML change that removes waste. Verify hosted-runner pricing at https://docs.github.com/en/billing/reference/actions-runner-pricing when quoting cost; included-minute drain is still roughly Linux 1×, Windows 2×, macOS 10×.

## 1. Duplicate `push` + `pull_request` on the same SHA

**Detect.** `on: [push, pull_request]` or `push:` with no `branches:` (or `branches: ['**']`) plus `pull_request:`. Every commit on a PR branch fires two runs.

**Do.** Feature-branch CI belongs on `pull_request` (and `merge_group` if the repo uses a merge queue). `push` should be the default branch and any release branches only:

```yaml
on:
  push:
    branches: [main]
  pull_request:
  merge_group:  # keep if already present or if the repo uses merge queues
```

Use the repo's real default branch name (`master`, `trunk`, …). Keep `workflow_dispatch` / `workflow_call` / `schedule` as they were unless play 9 applies.

**Don't.** Drop `push` to the default branch (post-merge CI goes away). Don't replace `pull_request` with `pull_request_target`. Don't remove `merge_group`.

## 2. Concurrency — cancel stale CI, never cancel deploys

**Detect.** No top-level `concurrency:` on a test/lint/build workflow, or `cancel-in-progress: true` on deploy/release/publish/pages.

**Do** on CI:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/<default>' }}
```

On deploy/release/publish, set a group so two deploys to the same environment cannot overlap, but `cancel-in-progress: false`.

**Don't.** Cancel in-progress deploys, production workflows, or a workflow that publishes packages/releases. Don't use a group so coarse it serializes unrelated PRs (workflow name + PR/ref is the default).

## 3. Dead and duplicate workflows

**Detect.**

- `state: disabled` in `gh api .../actions/workflows`, or `if: false` on every job.
- Two workflow files that run the same package-manager install + the same test/lint/build commands on the same events (classic: `ci.yml` and `test.yml`).
- A workflow whose `on:` can never fire (empty `paths` intersection, wrong branch name).

**Do.** Delete disabled/untriggerable files. For duplicates, keep the one whose **job names** match required checks; fold any unique step into it; delete the other.

**Don't.** Delete CodeQL / dependency-review / Scorecard / "security" workflows. Don't delete a workflow that is the required check just because another file looks similar. Don't merge two workflows that test different packages in a monorepo unless they truly share the same command on the same paths.

## 4. Matrix and OS bloat

**Detect.** `strategy.matrix` with language versions the repo does not support (`engines`, `.nvmrc`, go.mod `go`, `requires-python`), or `macos-*` / `windows-*` legs on a library with no native addons, no OS-specific tests, and no desktop/mobile product.

**Do.**

- Keep the versions they ship; drop EOL legs unless the user asked to keep them.
- Default PR matrix: Linux + current supported version. Broader OS/version matrix: default branch and/or tags/releases only (`if: github.ref == 'refs/heads/<default>'` or a dedicated workflow).
- Drop macOS/Windows when the product is Linux-only (containers, typical Node/Python libraries). Keep **one** macOS job if they ship a native addon, Electron/desktop, or iOS; keep Windows if they ship a Windows binary or have Win32 tests.

**Don't.** Collapse a matrix that matches documented support. Don't move iOS/Android builds off macOS. Don't switch `ubuntu-latest` to ARM or a 1-core slim runner as a surprise (native addons, undocumented CPU flags). Flag oversized runners (`*-4-core`, `*-8-core`, `*-16-core`, GPU) in the report; only downsize when recent runs show the job finishing with CPU/RAM to spare **and** the user did not adopt large runners for a reason in comments/docs.

## 5. Job timeouts

**Detect.** Jobs with no `timeout-minutes` (GitHub's default is 6 hours).

**Do.** Set `timeout-minutes` per job from observed duration: about 3× a healthy run, with a floor of 10 minutes for typical CI and a ceiling well under 6 hours. Hung jobs are how a flake becomes a four-figure minutes bill.

**Don't.** Set a timeout tighter than the slowest successful run in the last 100 plus slack — that flakes CI.

## 6. Caching without doubling it

**Detect.** `actions/setup-node` / `setup-python` / `setup-go` / `setup-java` without `cache:`, or **both** that built-in cache **and** a separate `actions/cache` on `node_modules` / pip / go-mod.

**Do.** Enable the setup action's built-in cache (`cache: npm` / `pnpm` / `yarn` / `pip` / `go-sum`). Remove the redundant `actions/cache` step when it keys the same lockfile. Do not cache `node_modules` directories; lockfile-keyed setup caches are the default.

**Don't.** Add a new third-party cache action. Don't cache Docker layers unless the workflow already builds images (then `cache-from`/`cache-to` on `docker/build-push-action` is in-scope). Don't share caches across untrusted fork PRs in a privileged workflow.

## 7. Path filters — non-required extra workflows only

**Detect.** A heavy extra workflow (e2e, visual regression, benchmark, docker publish) that runs on markdown/docs/issue-template-only PRs, **and** none of its job names appear in required checks / rulesets.

**Do.**

```yaml
on:
  pull_request:
    paths:
      - "src/**"
      - "package.json"
      - "pnpm-lock.yaml"
      - ".github/workflows/e2e.yml"
```

Always include the workflow file itself so workflow edits still run. For docs-only repos, invert: a tiny docs workflow, not "skip CI".

**Don't.** Put `paths` / `paths-ignore` on a workflow that reports a required check (the check never runs → PR stuck pending). Don't exclude lockfiles, workflow files, or security config from test workflows. Don't add `dorny/paths-filter` or similar; if required CI must skip expensive jobs, use a `git diff` step already in-repo **or** skip this play and report it.

## 8. Checkout depth and duplicate installs

**Detect.** `fetch-depth: 0` (or a large depth) on jobs that never run `git log` / `git diff` against main, changelogs, or coverage-of-changed-files. Several jobs in one workflow each `checkout` + install the same toolchain for a <2 minute lint/typecheck/unit step.

**Do.** Drop extra fetch-depth so the action default (shallow) applies, **unless** the job needs history (this repo's skill validator, `git describe`, changed-file linters, release-please). Combine cheap same-setup jobs into one job (lint then typecheck then unit) so `npm ci` runs once. Leave long independent suites parallel; give them the setup-action cache from play 6 so they don't each pay a cold install.

**Don't.** Shallow-clone a job that diffs against the base SHA. Don't serialize two 15-minute suites just to save a duplicate checkout.

## 9. Schedules that aren't security

**Detect.** `cron` more than daily on non-security workflows (stale comments, image rebuilds, "ci on a timer"). Hourly crons. A heavy test workflow on `schedule` **and** every push to default.

**Do.** Move non-security timers to daily or weekly (off-peak UTC). If the same tests already run on `push` to default, drop the duplicate `schedule` on that test workflow.

**Don't.** Remove or stretch CodeQL / Scorecard / dependency / vuln-scan schedules past weekly. GitHub's CodeQL starter (`push` + `pull_request` on default + weekly `schedule`) is the floor — you may **scope** `push` to the default branch (play 1), not delete the weekly backup.

## 10. Artifacts and caches (storage, not minutes)

Only while editing the file: `retention-days: 90` on CI logs/build artifacts is usually overkill; 7–14 days is enough for debugging. Don't cut retention on release artifacts. Mention cache-usage (`gh api repos/<owner>/<repo>/actions/cache/usage`) in the report if it is huge; don't flush caches as a "fix".

## Out of scope (report, don't apply)

- Migrating to self-hosted or third-party runners
- Rewriting the test suite, deleting tests, or skipping flaky tests
- Changing application code, package manager, or Node/Python/Go versions
- Enabling merge queues, OIDC, or SHA-pinning as a project (hardening is fine only as play "while you're in the file" permissions)
- `pull_request_target`, fork-PR secrets, or any trigger change that grants a fork more access
