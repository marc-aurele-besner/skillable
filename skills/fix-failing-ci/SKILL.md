---
name: fix-failing-ci
description: Take a red GitHub Actions run URL (or a PR URL whose checks are failing), pull the failed job logs, diagnose the failure, fix it on the branch that was built, push, and watch until CI is green. Use whenever the user pastes an Actions run URL (github.com/<owner>/<repo>/actions/runs/<id>), a failed check link, or asks to fix failing CI, a red build, or a broken workflow. Also triggers on /fix-failing-ci with a run or PR URL.
argument-hint: "<github-actions-run-url-or-pr-url>"
disable-model-invocation: false
---

# Fix Failing CI

Goal: given a failing GitHub Actions run or a PR with red checks ($ARGUMENTS), find the real cause of the failure, fix it on the branch that was built, push, and watch remote CI until it is green. Do not merge. This is the general-purpose version of the loop in the dependency-bot skills; if the input is a Dependabot alert, a Dependabot PR, or a Renovate PR, use `fix-dependabot-alert`, `fix-dependabot-pr`, or `fix-renovate-pr` instead.

## 1. Parse the input

Extract owner, repo, and either a run id or a PR number from the URL. Supported forms:

- `https://github.com/<owner>/<repo>/actions/runs/<id>`
- `https://github.com/<owner>/<repo>/actions/runs/<id>/job/<job-id>` (job id narrows which log to read first)
- `https://github.com/<owner>/<repo>/pull/<number>` when its checks are failing

If given a PR, resolve the failing run(s) from its checks:

```bash
gh pr checks <number> --repo <owner>/<repo>
gh pr view <number> --repo <owner>/<repo> --json headRefName,baseRefName,statusCheckRollup
```

## 2. Fetch the failure context

```bash
gh run view <id> --repo <owner>/<repo>
gh run view <id> --repo <owner>/<repo> --log-failed
```

Identify the failed job(s), the exact step and command that failed, and the **first real error** in the log — not the trailing noise (a wall of "npm ERR!" or a non-zero exit summary usually follows the actual cause by hundreds of lines). Then read the workflow file(s) under `.github/workflows/` for that run so the local repro matches what CI ran: OS, language/toolchain versions, package manager, cache configuration, env vars, and the order of commands.

## 3. Check out the branch that was built

Fix the branch the run built, not `main` by default:

```bash
gh run view <id> --repo <owner>/<repo> --json headBranch,headSha
```

If not already inside a clone of the repo, clone it first. Then:

```bash
git fetch origin
git checkout <headBranch>
git pull --rebase origin <headBranch>
```

For a PR, `gh pr checkout <number> --repo <owner>/<repo>` does the same. If the run was on the default branch itself, work on the default branch (and still push normally, never force-push).

## 4. Reproduce locally and fix

1. Detect the toolchain from the workflow and the repo's manifests/lockfiles (`package.json` + `pnpm-lock.yaml`/`yarn.lock`/`package-lock.json`, `Cargo.toml`, `go.mod`, `pyproject.toml`/`requirements.txt`, `Gemfile`, `pom.xml`, etc.). Use the same versions and the same package manager CI uses.
2. Run the exact command the failed step ran. Confirm it fails the same way; that failure is the definition of done.
3. Fix the actual cause, and keep the change minimal: no drive-by refactors, no formatting sweeps, and never delete or skip tests to make them pass. If a test asserts behavior that legitimately changed, update the assertion and say so in the commit message.
4. If the failure is not a code problem, say so instead of "fixing" it:
   - **Flaky test or external outage**: report it as flaky/external; only add a retry if the user asked for one.
   - **Missing secret or insufficient permissions**: identify which secret/permission the workflow needs and report it — do not commit secrets or weaken the workflow to bypass it.
   - **Infrastructure (runner out of disk, rate limits, registry down)**: report it; re-running may be the only fix, and that is the user's call.

## 5. Commit and push

Commit with a conventional message that names the failing check and the fix, e.g.:

```
fix(ci): correct tsconfig path so the typecheck job passes

- typecheck failed on renamed src/config module
- update import in src/index.ts
```

Push to the branch that was built: `git push origin <headBranch>`. Never force-push, never skip hooks (`--no-verify`), and do not merge the PR.

## 6. Watch remote CI, iterate until green

```bash
gh run watch <new-run-id> --repo <owner>/<repo>   # or: gh pr checks <number> --repo <owner>/<repo> --watch
```

If it fails again, pull the new failed logs (`gh run view <new-run-id> --log-failed`), diagnose, fix, and push again. A remote-only failure after a local pass is usually an environment difference (toolchain version, cache, OS, missing env var) — compare against the workflow file. Do not loop forever: after roughly three unsuccessful attempts, stop and report what was tried and what is still failing.

## 7. Report

End with a short summary: the failing job and step, the root cause, the files changed and why, the commit(s) pushed, the final status of each check, and anything intentionally left out of scope (flakes, missing secrets, unrelated red checks).
