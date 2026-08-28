---
name: optimize-github-actions-across-org
description: >-
  List every GitHub repo the authenticated user owns or controls — including
  every repo in organizations they own — find repos with GitHub Actions
  workflows, and for each eligible repo run optimize-github-actions on an
  isolated branch. Use whenever the user wants to cut Actions minutes across
  an org, optimize CI fleet-wide, trim redundant workflows in every repo they
  own, or reduce GitHub Actions billing at account scale. Also triggers on
  /optimize-github-actions-across-org with optional parallel|sequential.
argument-hint: "[parallel|sequential]"
disable-model-invocation: false
---

# Optimize GitHub Actions Across Org

Goal: list **every repo the user owns or controls**, including **every repo in organizations they own**, cheaply probe which of them have GitHub Actions workflows, and for each eligible repo **call `optimize-github-actions`** in an isolated clone. Do not reimplement trigger/concurrency/matrix analysis here — read and follow `optimize-github-actions` (and its playbook) per repo. That child opens a PR and does not merge; this parent must not merge those PRs either unless the user explicitly asks.

Do not take over when the user is clearly inside one repo and talking about that repo only — that is `optimize-github-actions`'s job — unless they also said "all repos" / "the org" / "fleet-wide". If they pass a single `owner/repo`, run the child once and stop. Red builds belong to `fix-failing-ci`; Node pins to `upgrade-node-version`.

## 0. Mode and scope

Parse `$ARGUMENTS` / the user message for:

- **Mode:** `parallel` (default) or `sequential`. That mode is how **repos** are dispatched; each child still follows its own rules inside its repo.
- **Scope:** same filters as `sweep-all-dependency-prs` — if the user names an org, a subset ("only my public repos", "skip work orgs", "private only"), or an allow/deny list, honor it as a filter on the union.

If `gh` is not authenticated, stop and tell the user to run `gh auth login` (and `gh auth refresh -s read:org` if org listing 403s). Never ask them to paste a repo list.

## 1. List repos they own or control

Use the **same three-source union as `sweep-all-dependency-prs`** — read that skill's step 1 and follow it exactly:

- **A. Personal repos:** `gh repo list <user> --limit 1000 --no-archived --source --json nameWithOwner`
- **B. Every repo in orgs they own:** memberships from `/user/memberships/orgs` filtered to `state == "active"` and `role == "admin"`, then `gh repo list <org> --limit 1000 --no-archived --source` per owned org. A 403 means the token lacks `read:org` — stop and say so; an empty 200 just means no orgs.
- **C. Other controlled repos:** `/user/repos?affiliation=collaborator,organization_member` filtered to `permissions.admin` or `permissions.maintain`.

Union by `full_name`, paginate every call to completion, skip forks and archived/disabled repos unless asked to include them. In the final report, list the owned orgs and repo count per org so a missing organization is obvious.

## 2. Probe which repos have Actions workflows — cheaply, before cloning

Do **not** clone 200 repos to find the 12 with workflows. Probe via the API in parallel batches (~15 at a time so rate limits survive):

```bash
gh api repos/<owner>/<repo>/contents/.github/workflows --jq '.[].name'
# fallback if contents is awkward (empty dir vs 404):
gh api repos/<owner>/<repo>/actions/workflows --jq '.workflows[] | {name,path,state}'
```

A 404 from contents means no `.github/workflows` directory. An empty `workflows` list (or only `state: disabled` files) is still a probe hit — the child decides whether anything is worth a PR. A probe failure (network, permissions, empty repo) is a skip-with-error for that repo, not a halt for the fleet.

| Bucket | When | Next step |
|--------|------|-----------|
| **No Actions** | 404 / no workflow files | Skip |
| **Eligible** | at least one workflow file (enabled or disabled) | Call `optimize-github-actions` |
| **Filtered out** | deny-list / visibility / org filter from step 0 | Skip |

Do **not** skip a repo because it has "only one workflow" or because it looks already optimized — the child is what decides "already tight, no PR". Do not skip public repos; duplicate runs still waste concurrency even when standard runners are free.

## 3. Dispatch `optimize-github-actions` per eligible repo

Read and follow **`optimize-github-actions`** for each eligible repo. The child inventories workflows and usage, applies the playbook, and opens a `chore/optimize-github-actions` PR — or reports already-tight.

- **One isolated clone/worktree per repo — and one child per repo.** Never share the current workspace across children.
- **Parallel (default):** one agent per eligible repo, capped at ~4–6 concurrent; queue the rest. If subagents are unavailable, fall back to sequential.
- **Sequential:** finish repo N (including its report) before starting N+1.
- All children share one token. A `secondary rate limit` 403 means sleep ~60 s and retry — that is throttling, not a repo failure. If it keeps happening, drop concurrency.
- A child that errors must not abort the fleet; record the failure and continue.
- **No empty PRs.** If the child finds nothing to change, do not open a PR; count the repo as "already tight".
- Do not merge. Do not force-push. Do not skip hooks. Do not relax the child's security hard rules from the parent.

Every child must return its **full report** (step 5 of `optimize-github-actions`: applied findings, skipped-with-why, PR URL, usage snapshot). The parent keeps all of them — they are the raw material for the per-repo sections below; do not paraphrase them into one-line rollups.

## 4. Report

Organize per repo that ran the child or failed; repos with no workflows are a count.

```markdown
# Optimize GitHub Actions — all controlled repos

**Mode:** parallel | sequential
**Owned orgs:** org1 (n repos), org2 (n repos)
**Repos scanned:** N — with workflows: W, PRs opened: X, already tight: T, blocked/error: Y

## Per-repo results

### owner/repo1 — PR opened
| Finding | Detail |
|---------|--------|
| duplicate push+PR | `ci.yml` scoped to `main` |
| concurrency | cancel superseded PR runs |
| PR | [#12](https://github.com/owner/repo1/pull/12) |
| Skipped | kept macOS (native addon) |

### owner/repo2 — already tight
- child ran; scoped triggers, concurrency, timeouts already present

### owner/repo3 — blocked
- required-check path-filter was the only finding; child reported, no PR

## Probed but not optimized
- no Actions workflows: count
- probe/child failed: owner/repo — error
```

If the controlled-repo list looks wrong (missing an org, or an org they do not want), say how it was filtered so the user can rerun with a narrower scope.
