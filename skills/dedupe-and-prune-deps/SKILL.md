---
name: dedupe-and-prune-deps
description: Find duplicate, unused, and phantom dependencies, remove them safely, regenerate the lockfile, and verify CI. Use whenever the user asks to dedupe, prune unused packages, clean up package.json, remove phantom or undeclared imports, or slim the dependency tree. Also triggers on /dedupe-and-prune-deps.
disable-model-invocation: false
---

# Dedupe and Prune Dependencies

Goal: make the dependency tree honest and minimal — collapse duplicate versions, declare phantom imports, remove genuinely unused packages — then reinstall, verify with the repo's own CI commands, commit, push to a new branch, and open a PR. Do not merge.

## 1. Detect the package manager and layout

1. Detect the package manager from the lockfile (`pnpm-lock.yaml`, `yarn.lock`, `package-lock.json`) and use only that one for every install, dedupe, and lockfile operation. Never mix package managers.
2. Detect workspaces/monorepo layout (`workspaces` in `package.json`, `pnpm-workspace.yaml`). Operate per-package: each workspace `package.json` gets its own unused/phantom analysis, not just the repo root.

## 2. Inventory three classes of waste

Do not skip any of the three.

**Duplicates** — the same package resolved at multiple versions:

```bash
# see which versions exist and who pulls them in
npm ls <package> --all   # or: yarn why <package> / pnpm why <package>
# find the worst offenders wholesale
npm dedupe --dry-run     # yarn dedupe --check (berry) / pnpm dedupe --check
```

Prefer collapsing to a single supported version that satisfies every declared range. If ranges conflict, prefer aligning the declared ranges over forcing with overrides/resolutions.

**Unused** — declared in `dependencies`/`devDependencies` but never referenced. Run a depcheck-style pass (`npx depcheck`, or `npx knip` where configured) **and** confirm each candidate with a grep across source, npm scripts, and config files — depcheck output alone is not evidence. Treat these as used even when no source file imports them:

- CLI tools invoked from `package.json` scripts, CI workflows, Dockerfiles, or git hooks
- Plugins loaded by name from config (ESLint, Prettier, Jest, Vite, Rollup, Babel, PostCSS, Tailwind, Next, etc.)
- `@types/*` packages for untyped dependencies still in use
- Packages required by codegen, migrations, or seed scripts
- Peer dependencies the app must provide for another dependency to work

**Phantoms** — imported or required in source but missing from the declaring package's `package.json` (they resolve only because a parent hoisted them). Find them by cross-checking each workspace's imports against its own declared dependencies (depcheck/knip report these as "missing"). Each phantom must become a direct dependency of the package that imports it, at a version compatible with what the tree already resolves — do not leave code relying on hoisting.

## 3. Create a working branch

If not already inside a clone of the repo, clone it first. Then:

```bash
git fetch origin
git checkout -b chore/dedupe-and-prune-deps origin/<default-branch>
```

## 4. Apply changes in a safe order

1. **Declare phantoms first** so the tree is honest before anything is removed.
2. **Dedupe / align versions** (`npm dedupe`, `yarn dedupe`, `pnpm dedupe`, plus range alignment in manifests). Do not cross a major version just to collapse a duplicate unless the migration is trivial and verified; otherwise keep the duplicate and note it in the report.
3. **Remove unused packages last**, one logical group per pass. Never remove a package solely "because depcheck said so" — check scripts, CI workflows, Docker, codegen, and config first. When genuinely unsure, leave it in and list it under "reviewed, kept" with the reason.

Keep changes scoped to dependency hygiene: no drive-by refactors, no formatting sweeps, and no `audit fix` across the whole tree as a side effect of this skill.

## 5. Reinstall cleanly

```bash
rm -rf node_modules && <pm> install    # plus workspace node_modules in a monorepo
```

Commit the lockfile if it changed. Note the lockfile delta (lines or resolved-package count) for the report.

## 6. Verify with the repo's own CI commands

Read `.github/workflows/*.yml` for the exact commands CI runs (install, build, lint, typecheck, test) and run them locally in the same order. These commands are the definition of done. If something breaks, revert that specific removal or dedupe rather than papering over it — a package that turned out to be used goes back in and onto the "reviewed, kept" list.

## 7. Commit, push, and open a PR

1. Commit with a conventional message, e.g.:
   ```
   chore(deps): dedupe lodash, declare phantom imports, remove unused packages

   - collapse lodash to a single 4.x resolution
   - declare dayjs in packages/api (was hoisting-only)
   - remove unused gulp toolchain from root devDependencies
   ```
   Never force-push and never skip hooks (`--no-verify`).
2. Push and open the PR against the default branch:
   ```bash
   git push -u origin chore/dedupe-and-prune-deps
   gh pr create --title "..." --body "..."
   ```
   In the PR body: what was collapsed, declared, and removed, and the packages reviewed but kept.

## 8. Watch CI, iterate until green

```bash
gh pr checks <number> --watch
```

If a check fails, pull the failing job's logs (`gh run view <run-id> --log-failed`), diagnose, fix (usually: restore a removal that CI proved was used), and push again. Do not merge the PR.

## 9. Report

End with a short summary: duplicates collapsed (package and versions before → after), unused packages removed, phantoms declared and where, packages reviewed-and-kept with why, the lockfile delta, the commit(s) and PR link, and final CI status.
