---
name: upgrade-node-version
description: Bump the Node.js version across .nvmrc, package.json engines, GitHub Actions workflows, Dockerfiles, and any other version pins, then fix breakage from the upgrade. Use whenever the user asks to upgrade Node, bump Node, move to a new Node LTS, or update the runtime version in CI/Docker. Also triggers on /upgrade-node-version with an optional target version (e.g. 22 or 24).
argument-hint: "[target-node-version]"
disable-model-invocation: false
---

# Upgrade Node Version

Goal: given an optional target version ($ARGUMENTS), move every Node.js version pin in the repo to the same new major, fix whatever the bump breaks, then commit, push to a new branch, and open a PR. Do not merge.

## 1. Resolve the target version

1. If `$ARGUMENTS` contains a major or full version (e.g. `22`, `24.1.0`), use it.
2. Otherwise, use the **current Node LTS**. Verify what that is right now (web search or https://nodejs.org/en/about/previous-releases) — do not assume from memory. Stay on even-numbered LTS majors unless the user explicitly asked for the odd-numbered Current line.
3. Note the repo's current version(s) before touching anything, so the report can state old → new.

## 2. Inventory every Node pin

Scan the repo for all of the following before editing anything. Not all will exist — list what does:

- Version files: `.nvmrc`, `.node-version`, `.tool-versions` (asdf), `mise.toml`
- `package.json` (and every workspace `package.json`): `engines.node`, Volta pins (`volta.node`)
- `.github/workflows/*.yml`: `node-version`, `node-version-file`, matrix entries listing Node majors
- Dockerfiles and compose files: `FROM node:<tag>`, `NODE_VERSION` args/env
- Deploy platform config: Netlify (`netlify.toml`), Vercel, Cloudflare, Render, Railway, Heroku (`NODE_VERSION`, engines-based detection)
- `.devcontainer/` config, `.github/dependabot.yml` / Renovate config with a `node` manager
- Docs (`README`, `CONTRIBUTING`) that state a required Node version

A useful sweep: `grep -rn --include='*' -iE 'node[-_]?version|FROM node:|engines' .` (excluding `node_modules` and lockfiles). Every hit goes in the final report so nothing is silently left behind.

## 3. Create a working branch

If not already inside a clone of the repo, clone it first. Then:

```bash
git fetch origin
git checkout -b chore/upgrade-node-<major> origin/<default-branch>
```

## 4. Bump all pins together

1. Move every pin found in step 2 to the same new major. Use the full version in `.nvmrc`-style files where the repo already does; use the major (or `>=<major>`) in `engines.node` matching the existing style.
2. In GitHub Actions, prefer `node-version-file: .nvmrc` over a hardcoded `node-version` so CI and local cannot drift — but only introduce it if an `.nvmrc` (or equivalent) exists.
3. In workflow matrices, drop Node majors that are past end-of-life; do not keep testing an abandoned major unless the user asked to keep it.
4. In Dockerfiles, keep the same image flavor (`node:<major>-alpine` stays alpine, `-slim` stays slim). A new major can mean a newer Debian/Alpine base — watch for OS-level breakage in step 5.

## 5. Install and verify

1. Detect the package manager from the lockfile (`pnpm-lock.yaml`, `yarn.lock`, `package-lock.json`) and use only that one. Switch the local toolchain to the target Node (`nvm use`, `mise use`, etc.) before installing.
2. Reinstall cleanly: `rm -rf node_modules && <pm> install`. Commit lockfile changes the reinstall produces.
3. Read `.github/workflows/*.yml` for the exact commands CI runs (install, build, lint, typecheck, test) and run them locally in the same order. These commands are the definition of done.
4. Fix what the new Node (and its bundled npm/V8) broke. Common cases:
   - `engines`-strict installs failing until every workspace `engines.node` is updated
   - Removed or changed Node APIs (check the new major's changelog for deprecations that landed)
   - Native addons needing a rebuild or a newer release (`node-gyp`, prebuilds)
   - `@types/node` out of sync with the new runtime — bump it to the matching major
   - ESLint/TypeScript targets or parser options that cap the supported Node/ECMAScript version
   - CI cache keys derived from the Node version, and Docker base-image OS differences (missing system libs, new Debian release)
5. If a dependency has no release compatible with the new Node, stop and report the blocker rather than pinning an insecure workaround or downgrading the target silently.

## 6. Keep the change scoped

Only what the Node bump requires: version pins, lockfile, and the minimal code/config fixes from step 5. No drive-by refactors, no formatting sweeps, and never delete or skip tests to make them pass. If a test asserts behavior that legitimately changed in the new runtime, update the assertion and say so in the commit message.

## 7. Commit, push, and open a PR

1. Commit with a conventional message, e.g.:
   ```
   chore: upgrade Node 20 -> 22

   - bump .nvmrc, engines, CI workflows, and Dockerfile
   - update @types/node to 22
   - regenerate lockfile
   ```
   Never force-push and never skip hooks (`--no-verify`).
2. Push and open the PR against the default branch:
   ```bash
   git push -u origin chore/upgrade-node-<major>
   gh pr create --title "..." --body "..."
   ```
   In the PR body: old → new version, every file that pinned Node, and what the bump broke and how it was fixed.

## 8. Watch CI, iterate until green

```bash
gh pr checks <number> --watch
```

If a check fails, pull the failing job's logs (`gh run view <run-id> --log-failed`), diagnose (often a cache key, container image, or platform-specific difference that local runs miss), fix, and push again. Do not merge the PR.

## 9. Report

End with a short summary: old → new Node version, every file that pinned Node (bumped or intentionally left), what broke and what was fixed, the commit(s) and PR link, final CI status, and any blockers or follow-ups (e.g. a dependency that still caps the supported Node version).
