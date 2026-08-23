---
name: fix-dependabot-pr
description: Take over a Dependabot dependency update PR and make it pass all CI checks, then commit and push the fixes to the PR branch. Use whenever the user provides a GitHub PR URL for a Dependabot version bump or security update PR (branch names like dependabot/npm_and_yarn/...) and asks to fix it, make CI pass, or "handle this PR". Also use for major version migrations triggered by Dependabot PRs (breaking config changes, API renames, lockfile issues) and for grouped Dependabot update PRs.
argument-hint: "<github-pr-url>"
disable-model-invocation: false
---

# Fix Dependabot Dependency PR

Goal: given a PR URL ($ARGUMENTS), get every CI check green on that PR by making whatever code, config, and lockfile changes the dependency update requires, then commit and push to the PR branch. Do not merge the PR.

## 1. Understand the PR

1. Parse owner, repo, and PR number from the URL: `https://github.com/<owner>/<repo>/pull/<number>`.
2. Gather context:
   ```bash
   gh pr view <number> --repo <owner>/<repo> --json title,body,headRefName,baseRefName,files,statusCheckRollup
   gh pr checks <number> --repo <owner>/<repo>
   ```
3. From the PR title and body, identify the package(s) and the version change (e.g. `Bump next from 14.2.3 to 15.0.4`). Note whether it is a patch, minor, or major bump. Major bumps almost always mean breaking changes, so budget for a real migration, not just a lockfile refresh.
4. Identify the PR type, because it changes the strategy:
   - **Single version bump**: the normal case. One package, one version change.
   - **Grouped update** (title like `Bump the <group-name> group with N updates`): several packages move together. List every package and its old/new version from the PR body table before starting; a failure can come from any of them, and peer constraints between grouped packages are a common cause.
   - **Security update** (body links a GHSA/CVE or the PR came from a Dependabot alert): the bump targets a first patched version. Do not downgrade below it while fixing, and mention the advisory in the commit message and report.
5. Check for Dependabot's own comments on the PR (`gh pr view <number> --repo <owner>/<repo> --comments`). Dependabot often explains why it could not update cleanly, notes superseded PRs, or warns about conflicts.

## 2. Check out the PR branch

If not already inside a clone of the repo, clone it first. Then:

```bash
gh pr checkout <number> --repo <owner>/<repo>
git pull --rebase origin <headRefName>
```

Important Dependabot behavior: once anyone other than Dependabot pushes to the branch, Dependabot stops rebasing or force-pushing it, so your commits are safe after the first push. The flip side: never comment `@dependabot rebase` or `@dependabot recreate` after pushing your own commits, because `recreate` force-pushes a fresh branch and wipes your work. If the branch is badly out of date or conflicted with the base branch, either:
- rebase or merge the base branch into the PR branch yourself and resolve conflicts, or
- comment `@dependabot recreate` BEFORE you have pushed anything, wait for the new branch, then re-checkout.

## 3. Learn what CI actually runs

Read `.github/workflows/*.yml` to list the exact commands CI executes (install, build, lint, typecheck, test, coverage, etc.) and the Node/package manager versions it uses. These commands are the definition of done. Reproduce them locally with the same package manager the repo uses (check for `pnpm-lock.yaml`, `yarn.lock`, or `package-lock.json`).

## 4. For major bumps, read the changelog first

The Dependabot PR body embeds release notes, changelog excerpts, and commit lists. Read them first; fetch the full migration guide (web search or the linked release page) for anything major. Summarize the breaking changes that plausibly affect this repo, then fix accordingly. Common cases:

- Config file format changes (bundler configs, framework configs, ESM/CJS shifts)
- Renamed or removed APIs used in app code, scripts, tests, and config
- Peer dependency updates that must be bumped together (plugins, type packages, framework companions). Dependabot only bumps the one package (or group) it opened the PR for; it is fine and often necessary to bump related packages beyond that, as long as it is required to make the update work. In grouped PRs, check that the grouped versions are mutually compatible.
- `@types/*` packages that must move with their runtime package
- Node version requirements (update CI workflow or `engines` only if genuinely required)

## 5. Fix, verify locally, repeat

1. Install dependencies fresh: `rm -rf node_modules && <pm> install`. Dependabot edits `package.json` and the lockfile directly and sometimes leaves them inconsistent (especially in monorepos or with pnpm catalogs/workspaces); if so, regenerate the lockfile with the repo's package manager and commit it.
2. Run every CI command locally in the same order as the workflow. Fix failures one at a time: build/typecheck first, then lint, then tests.
3. Keep changes minimal and scoped to what the dependency update requires. Do not refactor unrelated code, do not change formatting outside touched files, and do not delete tests to make them pass. If a test asserts old behavior that legitimately changed in the new version, update the assertion and note it in the commit message.
4. If something is truly unfixable (e.g. an incompatible peer dependency with no compatible release), stop, explain the blocker on the PR via `gh pr comment`, and report back instead of pushing broken code. If the right outcome is to skip this version entirely, say so in the report and let the user decide whether to close the PR (closing it makes Dependabot ignore that version; `@dependabot ignore this major version` is also available, but leave those calls to the user unless instructed).

## 6. Commit and push

1. Commit with a conventional message describing the migration, e.g.:
   ```
   fix(deps): migrate app config and tests for next v15

   - update next.config for v15 async request APIs
   - bump eslint-config-next to match
   - regenerate lockfile
   ```
   Add commits on top of Dependabot's commit. Never force-push and never rewrite Dependabot's commit.
2. Push to the PR branch: `git push origin <headRefName>`.

## 7. Verify CI on the remote

Watch the checks until they finish:

```bash
gh pr checks <number> --repo <owner>/<repo> --watch
```

If a check fails remotely but passed locally, pull the failing job's logs (`gh run view <run-id> --log-failed`), diagnose (often a Node version or cache difference), fix, and push again. Repeat until all checks are green.

## 8. Report

End with a short summary: what broke, what was changed and why, the commit(s) pushed, and the final status of each CI check. For security updates, name the GHSA/CVE the bump resolves. If auto-merge is enabled on the PR (check `gh pr view --json autoMergeRequest`), mention that it will merge on its own once green and required reviews pass.
