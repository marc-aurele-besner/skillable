---
name: optimize-github-actions
description: >-
  Analyze a repository's GitHub Actions workflows and open a PR that cuts
  wasted Actions minutes — duplicate push+PR runs, missing concurrency,
  redundant workflows, bloated matrices, unnecessary macOS/Windows jobs —
  without weakening security. Use whenever the user asks to optimize GitHub
  Actions, reduce Actions minutes, cut CI cost, trim redundant workflows, or
  speed up CI billing. Also triggers on /optimize-github-actions with an
  optional owner/repo.
argument-hint: "[owner/repo-or-url]"
disable-model-invocation: false
---

# Optimize GitHub Actions

Goal: inventory a repo's GitHub Actions workflows, measure where minutes actually go, apply **performance-only** YAML changes (duplicate triggers, concurrency, redundant workflows, matrix/runner bloat, timeouts, caching), then open a PR. Do not merge.

This is not `fix-failing-ci` (red builds), not `upgrade-node-version` (runtime pins), and not a security hardening sweep. If the user said **all repos** / **the org** / **fleet-wide**, use `optimize-github-actions-across-org` instead.

If `$ARGUMENTS` / the user message is a single `owner/repo` or GitHub URL, use that. If omitted, use `git remote get-url origin`. Never ask for the URL when origin is enough. If `gh` is not authenticated, stop and say to run `gh auth login`.

## Hard rules — never trade security for minutes

Do **not** apply a change that does any of the following. If a finding would require it, report it as out of scope; do not "optimize around" it.

- Remove, skip, or `continue-on-error` security jobs: CodeQL, dependency-review, secret scanning, Scorecard, gitleaks, Trivy, `npm audit`, SAST/DAST, license scanners.
- Skip CI on Dependabot / Renovate / security-bot PRs.
- Weaken `permissions:` (no `write-all`, no adding `contents: write` / `id-token: write` / `pull-requests: write` / `packages: write` unless the workflow already needed that and you are not the one adding it). Adding a **tighter** `permissions:` block on a file you are already editing is allowed only when every job is read-only checkout + test/lint.
- Unpin actions from commit SHAs to tags/majors. Do not add third-party actions for speed (including `dorny/paths-filter`, faster-runner vendors, cache substitutes).
- Introduce `pull_request_target`, `workflow_run` on fork PRs, or checkout of untrusted code in a privileged workflow.
- Disable `persist-credentials: false`, environment protection, OIDC, or required status checks.
- Drop `merge_group` / merge-queue triggers. Do not rename a job that is a required check (branch protection / rulesets) without calling it out and keeping a job of the same name.

**Required checks vs path filters:** a workflow skipped by `on.paths` never reports, so a required check stays pending and blocks the PR. Use trigger-level `paths` / `paths-ignore` **only** on workflows that are **not** required. For required CI, keep the workflow always reporting; filter expensive jobs inside it, or skip path filters entirely.

**While-you're-in-the-file (optional, never the reason to open a PR):** if a workflow you already edit has no `permissions:` and only reads the repo, add `permissions: contents: read`.

## 1. Inventory workflows and where minutes go

Clone if needed. Then collect **files + usage + protection** before editing.

```bash
gh api repos/<owner>/<repo> --jq '{default_branch,private,visibility}'
ls -la .github/workflows/

gh api repos/<owner>/<repo>/actions/workflows \
  --jq '.workflows[] | {id,name,path,state}'

gh run list --repo <owner>/<repo> --limit 100 \
  --json databaseId,name,event,headBranch,conclusion,status,createdAt,updatedAt,workflowName

# Per-workflow billable ms (private repos). Deprecated; if it 404s, estimate from run timestamps.
gh api repos/<owner>/<repo>/actions/workflows/<id>/timing
```

Read every `.github/workflows/*.{yml,yaml}`. Note reusable callers (`workflow_call`), composite actions under `.github/actions/`, and `uses: <owner>/<repo>/.github/workflows/...`.

Required checks (404 is fine — means none / no permission):

```bash
gh api repos/<owner>/<repo>/branches/<default>/protection \
  --jq '.required_status_checks.contexts // []'
gh api repos/<owner>/<repo>/rulesets
```

Bucket recent runs by **workflow × event × runner OS**. Look for: two runs on the same SHA (`push` + `pull_request`), cancelled-but-finished jobs with no concurrency, macOS/Windows minutes, matrix legs that always skip or always fail, schedules firing more than daily, workflows with `state: disabled`.

Public repos on standard runners are not billed the private-minutes quota, but duplicate runs still burn concurrency and wall-clock. Larger runners bill even on public repos. Verify current hosted-runner rates at https://docs.github.com/en/billing/reference/actions-runner-pricing — do not hard-code dollar amounts from memory. Included-minute multipliers are still roughly Linux 1×, Windows 2×, macOS 10×.

## 2. Classify findings

Read [references/playbook.md](references/playbook.md) and match the repo against every play. Each finding is one of:

| Verdict | Meaning |
|---------|---------|
| **Apply** | Safe YAML change; do it in this PR |
| **Skip — security** | Would weaken a control; leave it, mention in the report |
| **Skip — required check** | Path-filter or job skip would strand a required status |
| **Skip — ships that platform** | macOS/Windows/matrix leg is product surface, not copy-paste |
| **Report only** | Needs a human call (downsize a large runner, merge two similar-but-not-identical workflows) |

Do not invent work. If the repo is already tight (scoped `push`, concurrency on CI, timeouts, no duplicate workflows), say so and **do not open an empty PR**.

## 3. Apply on a branch

```bash
git fetch origin
git checkout -b chore/optimize-github-actions origin/<default-branch>
```

Apply every **Apply** finding. Keep the diff to workflow YAML (and a composite action only if it is how duplicate setup is shared). No app-code refactors, no action version bumps, no runner-vendor migrations, no self-hosted cutover.

Priority (highest minutes first):

1. Duplicate `push` + `pull_request` on the same SHA
2. Concurrency with cancel-in-progress on CI (never on deploy)
3. Dead or duplicate workflows
4. Matrix / OS bloat
5. Job `timeout-minutes`
6. Language-setup caches (not a second `actions/cache` on top of `setup-node` cache)
7. Path filters on **non-required** extra workflows
8. Shallow checkout where history is unused
9. Combining cheap jobs that each repeat the same install

After edits, sanity-check YAML (`python -c "import yaml,sys,..."` or `actionlint` if the repo already has it). Do not add actionlint as a dependency.

## 4. Commit, push, PR

```
chore: cut wasted GitHub Actions minutes

- scope push to the default branch so PRs are not billed twice
- cancel superseded CI runs; leave deploys uncancelled
- drop the unused Windows matrix leg (library is Linux-only)
```

Never force-push, never skip hooks, do not merge. PR against the default branch. The body must list every finding (applied vs skipped-with-why), the files touched, required checks considered, and a rough savings story (e.g. "CI was running twice per PR commit; concurrency will cancel superseded runs").

Watch CI on the PR (`gh pr checks --watch`). If a check fails because of this change, fix it. A red PR that is red for an unrelated reason: record it, do not pile on.

## 5. Report

```markdown
# Optimize GitHub Actions — <owner>/<repo>

**Visibility:** public | private
**Workflows:** N (disabled: D)
**Required checks:** list | none
**PR:** <url> | already tight, no PR

## Applied
| Finding | Files | Why it saves minutes |
|---------|-------|----------------------|
| duplicate push+PR | `ci.yml` | same SHA ran twice |

## Skipped
| Finding | Why |
|---------|-----|
| drop macos | ships a native addon; keep one macOS job |
| path-filter `ci.yml` | job `test` is a required check |

## Usage snapshot (last ~100 runs)
- heaviest workflow / event / OS
- duplicate-run count (same SHA, push+pull_request)
```
