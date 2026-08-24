---
name: prune-deps-across-org
description: >-
  List every GitHub repo the authenticated user owns or controls — including
  every repo in organizations they own — find repos with a JS lockfile, and
  for each eligible repo run dedupe-and-prune-deps on an isolated branch. Use
  whenever the user wants to prune unused dependencies across an org, dedupe
  lockfiles in every repo they own, or clean phantom imports fleet-wide. Also
  triggers on /prune-deps-across-org with optional parallel|sequential.
argument-hint: "[parallel|sequential]"
disable-model-invocation: false
---

# Prune Deps Across Org

Goal: list **every repo the user owns or controls**, including **every repo in organizations they own**, cheaply probe which of them are JS/TS repos, and for each eligible repo **call `dedupe-and-prune-deps`** in an isolated clone. Do not reimplement duplicate/unused/phantom analysis here — read and follow `dedupe-and-prune-deps` per repo; it holds the three waste classes, the depcheck caveats, and the safe apply order. That child opens a PR and does not merge; this parent must not merge those PRs either unless the user explicitly asks.

Do not take over when the user is clearly inside one repo and talking about that repo only — that is `dedupe-and-prune-deps`'s job — unless they also said "all repos" / "the org" / "fleet-wide". Landing bot PRs belongs to `sweep-all-dependency-prs` and security alerts to `sweep-all-dependabot-alerts`; this skill opens *hygiene* PRs.

## 0. Mode and scope

Parse `$ARGUMENTS` / the user message for:

- **Mode:** `parallel` (default) or `sequential`. That mode is how **repos** are dispatched; each child still follows its own rules inside its repo.
- **Scope:** same filters as `sweep-all-dependency-prs` — if the user names an org, a subset ("only my public repos", "skip work orgs"), or an allow/deny list, honor it as a filter on the union.

If `gh` is not authenticated, stop and tell the user to run `gh auth login` (and `gh auth refresh -s read:org` if org listing 403s). Never ask them to paste a repo list.

## 1. List repos they own or control

Use the **same three-source union as `sweep-all-dependency-prs`** — read that skill's step 1 and follow it exactly:

- **A. Personal repos:** `gh repo list <user> --limit 1000 --no-archived --source --json nameWithOwner`
- **B. Every repo in orgs they own:** memberships from `/user/memberships/orgs` filtered to `state == "active"` and `role == "admin"`, then `gh repo list <org> --limit 1000 --no-archived --source` per owned org. A 403 means the token lacks `read:org` — stop and say so; an empty 200 just means no orgs.
- **C. Other controlled repos:** `/user/repos?affiliation=collaborator,organization_member` filtered to `permissions.admin` or `permissions.maintain`.

Union by `full_name`, paginate every call to completion, skip forks and archived/disabled repos unless asked to include them. In the final report, list the owned orgs and repo count per org so a missing organization is obvious.

## 2. Probe which repos have a JS package manager — cheaply, before cloning anything

Do **not** clone 200 repos to find the 12 that are JS. Probe the default branch via the contents API in parallel batches (~15 at a time so rate limits survive); a 404 just means the file is absent:

```bash
gh api repos/<owner>/<repo>/contents/package.json --jq .name
gh api repos/<owner>/<repo>/contents/package-lock.json --jq .name
gh api repos/<owner>/<repo>/contents/yarn.lock --jq .name
gh api repos/<owner>/<repo>/contents/pnpm-lock.yaml --jq .name
```

A repo is **eligible** if it has any of `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, or a root `package.json`. A `package.json` with no lockfile is still eligible — the child can run — but the report must flag it: "no lockfile; child used `package.json` only".

**Skip:**

- No `package.json` and no JS lockfile — not a JS repo.
- `package.json` is `"private": true` **and** there is no lockfile **and** it declares no `workspaces` and no `dependencies`/`devDependencies` — an empty package with nothing to prune. (Fetch and decode the `package.json` content to check; when in doubt, keep it eligible.)
- Repos on the user's deny-list / filtered scope from step 0.

Do **not** skip a repo because it is a monorepo — the child handles `pnpm-workspace.yaml` and `workspaces` itself, walking each workspace package. A probe failure (network, permissions, empty repo) is a skip-with-error for that repo, not a halt for the fleet.

| Bucket | When | Next step |
|--------|------|-----------|
| **Not JS** | no `package.json`, no JS lockfile | Skip |
| **Eligible** | JS manifest/lockfile present | Call `dedupe-and-prune-deps` |

## 3. Dispatch `dedupe-and-prune-deps` per eligible repo

Read and follow **`dedupe-and-prune-deps`** for each eligible repo. The child detects the package manager, operates per workspace package, inventories duplicates/unused/phantoms, applies in the safe order (declare phantoms → dedupe → remove unused last), reinstalls, runs that repo's own CI commands, and opens a `chore/dedupe-and-prune-deps` PR.

- **One isolated clone/worktree per repo — and one child per repo, never one per workspace package.** Two agents in the same repo race the same lockfile and corrupt each other's work; the child already walks workspaces serially. Never share the current workspace across children.
- **Parallel (default):** one agent per eligible repo, capped at ~4–6 concurrent; queue the rest. A slot is released only when its child has finished its CI verify and opened its PR (or concluded "no changes"). If subagents are unavailable, fall back to sequential.
- **Sequential:** finish repo N (including its report) before starting N+1.
- All children share one token. A `secondary rate limit` 403 means sleep ~60 s and retry — that is throttling, not a repo failure. If it keeps happening, drop concurrency.

Parent rules on top of the child's own:

- **No empty PRs.** If the child finds nothing to change, do not open a PR; count the repo as "clean".
- **No churn-only lockfile diffs.** If the only diff is lockfile whitespace/reordering with no package added, removed, or version-aligned, treat it as a no-op — unless the child can show a collapsed duplicate (the resolved-version count for some package actually dropped).
- **Red stays recorded, not retried.** If CI fails after a removal, the child reverts that removal. If the child still returns with a red PR, leave it unmerged, record it as blocked, and do not start a second overlapping prune on that repo in the same run.
- Do not mix package managers, and no `npm audit fix` as a side effect (the child already forbids both).
- Do not merge. Do not force-push. Do not skip hooks.

Every child must return its **full report** (step 9 of `dedupe-and-prune-deps`: duplicates collapsed, unused removed, phantoms declared, reviewed-and-kept with why, lockfile delta, PR URL, CI status). The parent keeps all of them — they are the raw material for the per-repo sections below; do not paraphrase them into one-line rollups.

## 4. Report

Organize per repo that ran the child or failed; non-JS repos are a count.

```markdown
# Dedupe and prune — all controlled repos

**Mode:** parallel | sequential
**Owned orgs:** org1 (n repos), org2 (n repos)
**Repos scanned:** N — JS: J, eligible: M, PRs opened: X, clean (no-op): C, blocked/red: Y

## Per-repo results

### owner/repo1 — PR opened
| Class | Packages |
|-------|----------|
| Phantoms declared | `foo` (imported in `src/a.ts`) |
| Duplicates collapsed | `lodash` 4.17.20+4.17.21 → 4.17.21 |
| Unused removed | `left-pad` |
| Reviewed, kept | `eslint-plugin-n` (dev script / config) |
| PR | [#12](https://github.com/owner/repo1/pull/12) |
| CI | green / red / pending |
| Package manager | pnpm (workspaces: 4 packages) |

### owner/repo2 — clean
- child ran; no unused/phantoms/duplicates worth a PR

### owner/repo3 — blocked
- CI red after prune; child reverted removals / PR still red — [#44](https://github.com/owner/repo3/pull/44)

## Probed but not pruned
- not a JS repo: count
- no lockfile (child used `package.json` only): owner/repo
- probe/child failed: owner/repo — error
```

If the controlled-repo list looks wrong (missing an org, or an org they do not want), say how it was filtered so the user can rerun with a narrower scope.
