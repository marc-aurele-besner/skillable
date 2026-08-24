---
name: align-minimum-release-age
description: >-
  Align minimum-release-age / dependency-cooldown settings between the package
  manager (pnpm, npm, Poetry) and the dependency bot (Renovate or similar) to
  the most conservative of the two, then open a PR. Works on one repo
  (owner/repo or current origin) or across every repo the user owns or
  controls. Use whenever the user asks to align minimum release date, sync
  pnpm minimumReleaseAge with Renovate, match dependency cooldown across
  tools, stop bot PRs failing because a package is too new, or do that across
  an org / all their repos. Also triggers on /align-minimum-release-age with
  an optional repo (or all) and parallel|sequential.
argument-hint: "[owner/repo-or-url|all] [parallel|sequential]"
disable-model-invocation: false
---

# Align Minimum Release Age

Goal: find the dependency-cooldown setting on both sides of a repo — the **package manager** (pnpm/npm/Poetry decide whether a version is *installable*) and the **dependency bot** (Renovate decides whether to *propose* it) — set both to the **most conservative** (longest) of the two, and open a PR. Do not merge. They do not read each other's config; when they drift, either bot PRs fail to install (`ERR_PNPM_NO_MATURE_MATCHING_VERSION`, npm `ETARGET`, Poetry solver errors) or the bot lands versions the cooldown was supposed to block.

This skill is config alignment only. Do not steal it for a generic Renovate config rewrite, a bot PR fix (`fix-renovate-pr` / `fix-dependabot-pr`), or lockfile hygiene (`dedupe-and-prune-deps`). If only one side has a cooldown, copy it to the other side (defense in depth). If **neither** side has one, skip the repo — never invent a duration unless the user supplied one.

## 0. Parse scope and mode

Parse `$ARGUMENTS` / the user message:

| Input | Scope |
|-------|-------|
| `owner/repo` or a GitHub repo URL | **Single repo** |
| omitted, and the workspace has `origin` | **Single repo** = `git remote get-url origin`. Never ask for the URL when origin is enough. |
| `all`, `every repo`, `across the org`, `all my repos` | **Fleet** — every repo they own or control |
| an org name | Fleet, restricted to that org |
| `parallel` / `sequential` | How **repos** are processed in fleet mode. Default `parallel`. Ignored for a single repo. |
| an explicit duration ("14 days") | Target value for **every** repo in the run, if longer than what a repo already has |

Honor allow/deny lists ("only public", "skip work orgs"). If `gh` is not authenticated, stop and say to run `gh auth login` (and `gh auth refresh -s read:org` if org listing 403s). Never ask the user to paste a repo list.

## 1. Resolve the repo list

**Single repo:** that one `owner/repo`. Use the current workspace if it is already a clone; otherwise clone it. Go to step 2.

**Fleet:** build the repo list with the **same three-source union as `sweep-all-dependency-prs`** — read that skill's step 1 and follow it exactly (personal repos; every repo in orgs where membership is `state == "active"` and `role == "admin"`; collaborator/member repos with admin or maintain). Union by `full_name`, paginate to completion, skip forks and archived/disabled repos. Report owned orgs and repo counts per org.

**Cheap probe before cloning** — contents-API checks in parallel batches of ~15; a 404 means absent, a probe failure is skip-with-error for that repo, never a halt for the fleet:

```bash
gh api repos/<owner>/<repo>/contents/<path> --jq .name   # 404 = absent
```

A repo is **eligible** if its default branch has any of:

- A package-manager cooldown location: `pnpm-workspace.yaml`, `.npmrc`, or `package.json` mentioning `minimumReleaseAge` / `minimum-release-age` / `min-release-age`
- A bot config: `renovate.json`, `renovate.json5`, `.renovaterc`, `.github/renovate.json`, or a `"renovate"` key in `package.json`
- Both sides *could* exist: a lockfile (`pnpm-lock.yaml`, `package-lock.json`, `poetry.lock`) **and** a Renovate config file — even if the cooldown lives only in a preset; the per-repo pass resolves `extends`

| Bucket | When | Next step |
|--------|------|-----------|
| **Not applicable** | no JS/Python lockfile or manifest and no bot config | Skip (a count in the report) |
| **Eligible** | PM cooldown and/or Renovate (or similar) present | Run steps 2–5 |

Do **not** skip a repo just because its cooldown might live only in a Renovate preset — if a Renovate config exists, it is eligible.

**Fleet dispatch:** one isolated clone/worktree and one child per repo — never share the current workspace across repos. Parallel (default): cap ~4–6 concurrent children, queue the rest; fall back to sequential if subagents are unavailable. Children share one token: on a `secondary rate limit` 403, sleep ~60 s and retry; if it persists, drop concurrency. **One PR per repo — never a mega-PR.** A child that errors must not abort the fleet; record the failure and continue.

## 2. Find the cooldown on both sides

**Package-manager side.** Detect the package manager from the lockfile, then scan its known cooldown locations. Known keys as of 2026 — verify against current docs if a repo looks off; units differ per tool and must not be assumed shared:

| Tool | Where | Key | Unit |
|------|-------|-----|------|
| pnpm ≥ 10.16 | `pnpm-workspace.yaml` (pnpm 10.x also `.npmrc` `minimum-release-age`) | `minimumReleaseAge` | **minutes** (`10080` = 7 days) |
| npm ≥ 11.10 | `.npmrc` | `min-release-age` (older: `before`, absolute date) | **days** |
| Yarn Berry ≥ 4.10 | `.yarnrc.yml` | `npmMinimalAgeGate` | **minutes** |
| Bun ≥ 1.3 | `bunfig.toml` `[install]` | `minimumReleaseAge` | **seconds** |
| Poetry ≥ 2.4 | `poetry.toml` `[solver]` / env `POETRY_SOLVER_MIN_RELEASE_AGE` | `min-release-age` | **days** |
| Yarn classic | — | unsupported | skip the PM side; still align the bot if present |

Also collect exclude lists (`minimumReleaseAgeExclude` for pnpm, `min-release-age-exclude` for Poetry, and equivalents). Never drop them — they are allow-lists, not the duration.

**Bot side.** Detect Renovate (or similar) from `renovate.json`, `renovate.json5`, `.renovaterc`, `.renovaterc.json`, `renovate-config.js`, `.github/renovate.json`, `.github/renovate.json5`, or a `"renovate"` field in `package.json`. Renovate's key is `minimumReleaseAge` — a duration string (`"7 days"`; formerly `stabilityDays`) — global or inside `packageRules`.

- **Resolve `extends` before concluding the bot has no cooldown.** Fetch each preset (`gh api` on the preset repo, or the Renovate docs for built-ins like `config:best-practices`, which sets `minimumReleaseAge`) and note which preset supplied the value.
- **Dependabot has no first-class minimum-release-age today.** If the repo is Dependabot-only, report that; only write the package-manager side, and only if a cooldown exists somewhere (or the user supplied one). Do not pretend Dependabot can be aligned.

If the repo has neither a supported package-manager cooldown nor a bot cooldown, skip it (fleet) or stop and say so (single repo).

## 3. Normalize and pick the conservative value

1. Convert every found duration to one unit (minutes) so `"7 days"`, `10080` pnpm minutes, and `7` Poetry days compare equal.
2. **Winner = max(all explicit durations)** for *this* repo: PM value vs bot value vs `packageRules` values that apply repo-wide. A rule that *shortens* the cooldown for a named package is an exclude, not a candidate.
3. Only one side set → that value wins; copy it to the other side. Never pick a fashionable default (7 days, 3 days) unless the user named a duration — a user-supplied duration applies to every repo in the run, but never shortens an existing longer cooldown.
4. Both sides already equal the winner after unit conversion → **already aligned**; do not open an empty PR.
5. Absolute dates (`before=2026-01-01`, uv `exclude-newer`): convert to a remaining duration for comparison only; write back a **duration**, not a drifting calendar date, unless the repo already standardized on the date form.

In fleet mode, each repo keeps its own winner — repo A at 7 days and repo B at 14 days stay 7 and 14. Never collapse the fleet onto one duration unless the user gave one explicitly.

## 4. Write both sides to the winner

- **Package manager:** set the cooldown in the file the repo already uses (do not invent a second source of truth). Prefer `pnpm-workspace.yaml` for pnpm workspaces when other pnpm settings live there; otherwise `.npmrc`. Write each tool's native unit — pnpm minutes, npm/Poetry days, Renovate duration string.
- **Renovate:** set `minimumReleaseAge` at the scope the repo already uses (root config vs a catch-all `packageRules` entry). If the current value comes from an extended preset and the local file does not override it, add a local `minimumReleaseAge` **only when the winner is stricter than the preset** — never weaken a preset. Say in the PR that a preset was the source.
- Keep `internalChecksFilter=strict` if present; do not remove it, and do not add it unless the local Renovate config is already being edited and current Renovate docs say it is required for the cooldown to block PR creation.
- **Excludes:** do not blindly copy `minimumReleaseAgeExclude` ↔ Renovate `packageRules` with `minimumReleaseAge: 0`. If the two exclude lists disagree, call it out in the report and PR body; never silently drop or add a security-sensitive exclude. Reconciling them is an optional follow-up, not a blocker.
- Do not change lockfiles, dependency versions, or bot schedules.

## 5. Branch, commit, PR (per repo)

```bash
git fetch origin
git checkout -b chore/align-minimum-release-age origin/<default-branch>
```

Commit conventionally (e.g. `chore: align minimumReleaseAge between pnpm and Renovate`), push, and open a PR against the default branch. Never force-push, never skip hooks, never merge. Watch CI (`gh pr checks --watch`); if it goes red for a reason this change caused, fix and push.

The PR body must state: the before values on each side (file + native unit, or preset), the winner in each tool's native unit, why that value is the more conservative one, and the files touched.

## 6. Report

**Single repo:**

```markdown
# Align minimum release age — <owner>/<repo>

**Winner:** <duration in human units, e.g. 7 days>
**Package manager:** <pnpm|npm|poetry|none> — <old> → <new> (<file>)
**Bot:** <renovate|none> — <old> → <new> (<file or preset>)
**Excludes:** in sync | differ (summarize; not changed)
**PR:** <url> | already aligned, no PR
**CI:** green / pending / red
```

**Fleet:** a section per repo that was eligible or blocked; skipped not-applicable repos are counts, not sections.

```markdown
# Align minimum release age — all controlled repos

**Mode:** parallel | sequential
**Owned orgs:** org1 (n repos), org2 (n repos)
**Repos scanned:** N — eligible: M, PRs opened: X, already aligned: Y, skipped: Z

## Per-repo results

### owner/repo1 — PR opened
| Field | Value |
|-------|-------|
| Winner | 7 days |
| PM | pnpm 3 days → 7 days (`pnpm-workspace.yaml`) |
| Bot | Renovate 7 days (preset `config:best-practices`) |
| PR | [#12](https://github.com/owner/repo1/pull/12) |
| CI | green / pending / red |

### owner/repo2 — already aligned
- both sides 14 days; no PR

### owner/repo3 — skipped
- neither side set; did not invent a duration

## Probed but not aligned
- not applicable (no PM cooldown support, no bot config): count
- probe/child failed: owner/repo — error
```

If the controlled-repo list looks wrong (missing an org, or one the user does not want), say how it was filtered so they can rerun with a narrower scope.
