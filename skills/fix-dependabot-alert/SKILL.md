---
name: fix-dependabot-alert
description: Take over a GitHub Dependabot security alert and remediate it, then commit and push the fix on a new branch and open a PR. Use whenever the user provides a Dependabot alert URL (github.com/<owner>/<repo>/security/dependabot/<number>) and asks to fix it, resolve it, or "handle this alert". Covers direct bumps, transitive dependencies requiring resolutions/overrides, and cases where no patched version is installable yet.
argument-hint: "<github-dependabot-alert-url>"
disable-model-invocation: false
---

# Fix Dependabot Security Alert

Goal: given a Dependabot alert URL ($ARGUMENTS), eliminate the vulnerable version from the dependency tree (or apply the documented mitigation when a fix is not yet installable), verify nothing breaks, then commit, push to a new branch, and open a PR. Do not merge the PR. Do not dismiss the alert unless explicitly instructed.

## 1. Understand the alert

1. Parse owner, repo, and alert number from the URL: `https://github.com/<owner>/<repo>/security/dependabot/<number>`.
2. Fetch the alert details:
   ```bash
   gh api repos/<owner>/<repo>/dependabot/alerts/<number>
   ```
   Extract: the vulnerable package and ecosystem, affected version range, first patched version, severity, CVE/GHSA IDs, the manifest file (e.g. `yarn.lock`), and whether the dependency scope is `runtime` or `development`.
3. Read the advisory itself for context and workarounds:
   ```bash
   gh api /advisories/<ghsa-id>
   ```
4. Classify the situation, because it determines the whole strategy:
   - **Direct dependency, patched version exists**: simple bump in `package.json` + lockfile.
   - **Transitive dependency, patched version exists**: the parent may not accept it yet. You will need a resolution/override, or a parent bump that pulls the fixed version.
   - **No installable patched version** (Dependabot says it "cannot update X to a non-vulnerable version"): check whether the fixed version was released since the alert; if truly not installable, fall back to the advisory's documented workaround or assess exposure.

## 2. Check out the repo and create a working branch

If not already inside a clone of the repo, clone it first. Then:

```bash
git checkout <default-branch> && git pull
git checkout -b fix/dependabot-<number>-<package>
```

Detect the package manager from the lockfile present (`pnpm-lock.yaml`, `yarn.lock`, `package-lock.json`) and use only that one for every install and lockfile operation.

## 3. Map the dependency path

Find out exactly how the vulnerable package enters the tree:

```bash
# yarn classic
yarn why <package>
# yarn berry
yarn why <package> -R
# npm
npm ls <package> --all
# pnpm
pnpm why <package>
```

Note every parent chain. A vulnerable package can be introduced by several parents at several versions; all paths must end up on a patched version (or be removed).

## 4. Choose the remediation, in order of preference

1. **Bump the direct dependency** to a version at or above the first patched version, respecting semver in `package.json`. Prefer the latest stable within the same major; only cross a major if required to reach the patch, and treat that as a migration (read release notes first).
2. **Bump the parent(s)** of a transitive dependency if a newer parent release pulls in the fixed version. Check the parent's changelog or its `package.json` on the registry to confirm before bumping.
3. **Force the transitive version** when parents lag behind:
   - yarn (classic and berry): `"resolutions": { "<package>": ">=<patched>" }` in `package.json`
   - npm: `"overrides": { "<package>": ">=<patched>" }`
   - pnpm: `"pnpm": { "overrides": { "<package>": ">=<patched>" } }`
   Verify afterward that the forced version is actually compatible with its parents (install must succeed cleanly and the affected functionality must still work). If the parent hard-pins an incompatible range and breaks, do not ship the override.
4. **Remove or replace the parent** if it is unmaintained and the only path to the vulnerable package, and a maintained alternative exists. Only do this when the change is small and clearly safe; otherwise report it as a recommendation instead.
5. **Apply the advisory's workaround** when no patched version is installable (e.g. blocking specific codepaths or input types as documented in the advisory). Put the mitigation where the package is actually used, add a `TODO` comment referencing the alert number and the version that will make it removable.
6. **Assess and report only** as a last resort. If the dependency is dev-only or the vulnerable codepath is unreachable in this project (e.g. it never processes untrusted input through the affected API), and none of the above are practical, explain the exposure honestly in the report. Never silently dismiss.

## 5. Apply, install, and verify the tree

1. Make the change, then reinstall cleanly: `rm -rf node_modules && <pm> install`.
2. Confirm the vulnerable version is gone from the lockfile:
   ```bash
   yarn why <package>   # or the pm equivalent
   grep -n "<package>@" <lockfile> | head -50
   ```
   Every resolved version must be >= the first patched version.
3. Run the audit tool as a second check (`yarn audit`, `npm audit`, `pnpm audit`) and confirm this advisory no longer appears. Ignore unrelated advisories; do not scope-creep into fixing every alert unless asked.

## 6. Make sure nothing broke

Read `.github/workflows/*.yml` for the exact commands CI runs (install, build, lint, typecheck, test) and run them locally in the same order with the same package manager. Fix any breakage caused by the bump, keeping changes minimal and scoped. Do not refactor unrelated code and do not delete tests to make them pass. If the remediation is truly unworkable (e.g. the override breaks the parent at runtime), revert to the next option in step 4.

## 7. Commit, push, and open a PR

1. Commit with a conventional message referencing the alert and CVEs, e.g.:
   ```
   fix(deps): force sharp >=0.35.0 to resolve GHSA-xxxx (CVE-2026-33327 et al.)

   - add resolutions entry for sharp, introduced transitively via netlify-cli
   - regenerate lockfile
   - fixes Dependabot alert #218
   ```
2. Push and open the PR against the default branch:
   ```bash
   git push -u origin <branch>
   gh pr create --repo <owner>/<repo> --title "..." --body "..."
   ```
   In the PR body: link the alert URL, list the CVE/GHSA IDs, state the remediation chosen and why, and note any follow-up (e.g. "remove the resolutions entry once netlify-cli ships sharp >=0.35.0").

## 8. Verify CI and the alert

1. Watch checks: `gh pr checks <pr-number> --repo <owner>/<repo> --watch`. If a check fails remotely but passed locally, pull the logs (`gh run view <run-id> --log-failed`), diagnose, fix, push again.
2. Dependabot re-scans on push. After CI is green, re-check the alert state:
   ```bash
   gh api repos/<owner>/<repo>/dependabot/alerts/<number> --jq .state
   ```
   The alert auto-resolves once the fixed lockfile lands on the default branch, so it may still show `open` until the PR merges; say so in the report rather than treating it as a failure.

## 9. Report

End with a short summary: the vulnerability and its path into the tree, the remediation chosen (and options rejected, if relevant), the commit(s) and PR link, CI status, and what will close the alert. If the fix is a temporary override or workaround, state clearly when and how it should be removed.
