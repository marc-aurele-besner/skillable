---
name: fix-renovate-pr
description: Take over a Renovate (or Dependabot) dependency update PR and make it pass all CI checks, then commit and push the fixes to the PR branch. Use whenever the user provides a GitHub PR URL for an automated dependency bump and asks to fix it, make CI pass, or "handle this PR". Also use for major version migrations triggered by dependency PRs (breaking config changes, API renames, lockfile issues).
argument-hint: "<github-pr-url>"
disable-model-invocation: false
---

# Fix Renovate Dependency PR

Goal: given a PR URL ($ARGUMENTS), get every CI check green on that PR by making whatever code, config, and lockfile changes the dependency update requires, then commit and push to the PR branch. Do not merge the PR.

## 1. Understand the PR

1. Parse owner, repo, and PR number from the URL: `https://github.com/<owner>/<repo>/pull/<number>`.
2. Gather context:
   ```bash
   gh pr view <number> --repo <owner>/<repo> --json title,body,headRefName,baseRefName,files,statusCheckRollup
   gh pr checks <number> --repo <owner>/<repo>
   ```
3. From the PR body, identify the package(s) and the version change (e.g. `hardhat ^2.12.6 -> ^3.0.0`). Note whether it is a patch, minor, or major bump. Major bumps almost always mean breaking changes, so budget for a real migration, not just a lockfile refresh.

## 2. Check out the PR branch

If not already inside a clone of the repo, clone it first. Then:

```bash
gh pr checkout <number> --repo <owner>/<repo>
git pull --rebase origin <headRefName>
```

Renovate may rebase the branch at any time. Always pull latest before working, and prefer finishing the task in one session to avoid racing Renovate's rebases.

## 3. Learn what CI actually runs

Read `.github/workflows/*.yml` to list the exact commands CI executes (install, build, lint, typecheck, test, coverage, etc.) and the Node/package manager versions it uses. These commands are the definition of done. Reproduce them locally with the same package manager the repo uses (check for `pnpm-lock.yaml`, `yarn.lock`, or `package-lock.json`).

## 4. For major bumps, read the migration guide first

Before touching code, fetch the release notes or migration guide for the new major version (web search or the release notes link in the PR body). Summarize the breaking changes that plausibly affect this repo, then fix accordingly. Common cases:

- Config file format changes (e.g. Hardhat 2 to 3: config moves to ESM/TS with different shape, plugin system changes, `hardhat-toolbox` replaced by `hardhat-toolbox-viem` or `hardhat-toolbox-mocha-ethers`, test runner changes)
- Renamed or removed APIs used in scripts, tests, and config
- Peer dependency updates that must be bumped together (plugins, ethers/viem, typechain, etc.). It is fine and often necessary to update related packages beyond the one Renovate bumped, as long as it is required to make the update work
- Node version requirements (update CI workflow or `engines` only if genuinely required)

## 5. Fix, verify locally, repeat

1. Install dependencies fresh: `rm -rf node_modules && <pm> install`. If the lockfile is inconsistent with the manifest, regenerate it with the repo's package manager and commit it.
2. Run every CI command locally in the same order as the workflow. Fix failures one at a time: build/typecheck first, then lint, then tests.
3. Keep changes minimal and scoped to what the dependency update requires. Do not refactor unrelated code, do not change formatting outside touched files, and do not delete tests to make them pass. If a test asserts old behavior that legitimately changed in the new version, update the assertion and note it in the commit message.
4. If something is truly unfixable (e.g. an incompatible peer dependency with no compatible release), stop, explain the blocker on the PR via `gh pr comment`, and report back instead of pushing broken code.

## 6. Commit and push

1. Commit with a conventional message describing the migration, e.g.:
   ```
   fix(deps): migrate config and tests for hardhat v3

   - convert hardhat.config to v3 format
   - update toolbox plugins and test imports
   - regenerate lockfile
   ```
   Add commits on top of Renovate's commit. Never force-push and never rewrite Renovate's commit.
2. Push to the PR branch: `git push origin <headRefName>`.

## 7. Verify CI on the remote

Watch the checks until they finish:

```bash
gh pr checks <number> --repo <owner>/<repo> --watch
```

If a check fails remotely but passed locally, pull the failing job's logs (`gh run view <run-id> --log-failed`), diagnose (often a Node version or cache difference), fix, and push again. Repeat until all checks are green.

## 8. Report

End with a short summary: what broke, what was changed and why, the commit(s) pushed, and the final status of each CI check. If automerge is enabled on the PR (Renovate body says so), mention that it will merge on its own once green.
