---
name: upgrade-node-across-org
description: >-
  List every GitHub repo the authenticated user owns or controls — including
  every repo in organizations they own — find repos that pin Node.js, and for
  each eligible repo run upgrade-node-version on an isolated branch. Use
  whenever the user wants to bump Node across an org, upgrade Node in every
  repo they own, or roll out a new Node LTS fleet-wide. Also triggers on
  /upgrade-node-across-org with an optional target version and
  parallel|sequential.
argument-hint: "[target-node-version] [parallel|sequential]"
disable-model-invocation: false
---

# Upgrade Node Across Org

Goal: list **every repo the user owns or controls**, including **every repo in organizations they own**, cheaply probe which of them pin Node.js, and for each eligible repo **call `upgrade-node-version`** in an isolated clone. Do not reimplement pin inventory, Docker/CI edits, or the local fix loop here — read and follow `upgrade-node-version` per repo. That child opens a PR and does not merge; this parent must not merge those PRs either unless the user explicitly asks.

Do not take over when the user is clearly inside one repo and talking about that repo only — that is `upgrade-node-version`'s job — unless they also said "all repos" / "the org". Dependency-PR sweeps belong to `sweep-all-dependency-prs`, not here.

## 0. Target, mode, scope

Parse `$ARGUMENTS` / the user message for:

- **Target version:** a major or full version (`22`, `24.1.0`). If omitted, resolve the **current Node LTS once, here in the parent** (web search or https://nodejs.org/en/about/previous-releases — do not assume from memory), and pass that same resolved target into every child. Never let each child resolve LTS on its own: two children searching the web minutes apart can split the fleet 22 vs 24. Stay on even-numbered LTS majors unless the user explicitly asked for the odd-numbered Current line.
- **Mode:** `parallel` (default) or `sequential`. That mode is how **repos** are dispatched; each child still follows its own rules inside its repo.
- **Scope:** same filters as `sweep-all-dependency-prs` — if the user names an org, a subset ("only my public repos", "skip work orgs"), or an allow/deny list, honor it as a filter on the union.

If `gh` is not authenticated, stop and tell the user to run `gh auth login` (and `gh auth refresh -s read:org` if org listing 403s). Never ask them to paste a repo list.

## 1. List repos they own or control

Use the **same three-source union as `sweep-all-dependency-prs`** — read that skill's step 1 and follow it exactly:

- **A. Personal repos:** `gh repo list <user> --limit 1000 --no-archived --source --json nameWithOwner`
- **B. Every repo in orgs they own:** memberships from `/user/memberships/orgs` filtered to `state == "active"` and `role == "admin"`, then `gh repo list <org> --limit 1000 --no-archived --source` per owned org. A 403 means the token lacks `read:org` — stop and say so; an empty 200 just means no orgs.
- **C. Other controlled repos:** `/user/repos?affiliation=collaborator,organization_member` filtered to `permissions.admin` or `permissions.maintain`.

Union by `full_name`, paginate every call to completion, skip forks and archived/disabled repos unless asked to include them. In the final report, list the owned orgs and repo count per org so a missing organization is obvious.

## 2. Probe which repos are Node repos — cheaply, before cloning anything

Do **not** clone 200 repos to find the 12 that use Node. Probe via the GitHub API in parallel batches (~15 at a time so rate limits survive), e.g.:

```bash
gh api repos/<owner>/<repo>/contents/package.json --jq .name          # exists?
gh api repos/<owner>/<repo>/contents/.nvmrc --jq .content | base64 -d # current pin
```

A 404 from a contents call is normal — it just means the file is absent. A probe failure (network, permissions, empty repo) is a skip-with-error for that repo, not a halt for the fleet.

**Node signals** (any one puts the repo in scope):

- `package.json` at the repo root (or obvious workspace roots)
- `.nvmrc`, `.node-version`, or `.tool-versions` containing `node` / `nodejs`
- `package.json` `engines.node`
- `.github/workflows/*` mentioning `node-version` or `actions/setup-node`
- Dockerfile `FROM node:` (search file contents if cheap; otherwise the child catches it)

**Bucket every repo:**

| Bucket | When | Next step |
|--------|------|-----------|
| **Not Node** | no signals | Skip |
| **Already on target** | *all* visible pins (`engines.node`, `.nvmrc`, etc.) match the target major | Skip; count as up to date |
| **Engines forbid target** | declared `engines.node` range (or a documented policy file) cannot satisfy the target, e.g. `">=18 <20"` vs target 22 | Skip the child; report as blocked |
| **Eligible** | Node repo, at least one visible pin behind target, engines allow it | Call `upgrade-node-version` |

Rules for the edge cases:

- If some pins are visibly behind but others are invisible without a clone (CI matrices, Dockerfiles), the repo is **Eligible** — only skip as "already on target" when *every* visible pin matches and nothing suggests CI/Docker disagree.
- Do not fight an engine range. A repo whose `engines.node` excludes the target goes in **Blocked: engines pin** unless the user explicitly said to ignore engines.
- If the user named an allow/deny list, apply it before probing.

## 3. Dispatch `upgrade-node-version` per eligible repo

Read and follow **`upgrade-node-version`** for each eligible repo, passing the resolved target version. The child inventories every pin, bumps them together, reinstalls with that repo's package manager, runs that repo's CI commands, and opens a `chore/upgrade-node-<major>` PR.

- **One isolated clone/worktree per repo.** Never share the current workspace across children, and never let two children share a directory.
- **Parallel (default):** one agent per eligible repo, capped at ~4–6 concurrent; queue the rest. If subagents are unavailable, fall back to sequential.
- **Sequential:** finish repo N (including its report) before starting N+1.
- All children share one token. A `secondary rate limit` 403 means sleep ~60 s and retry — that is throttling, not a repo failure. If it keeps happening, drop concurrency.
- If a child stops on a blocker (native addon with no build for the new Node, incompatible dependency, missing CI secret), leave its PR unmerged — or unopened, if it never got that far — record the blocker, and continue the fleet.
- Do not merge. Do not force-push. Do not drop Node majors from a test matrix beyond what `upgrade-node-version` itself says to do — follow the child.

Every child must return its **full report** (step 9 of `upgrade-node-version`: old → new, files that pinned Node, what broke, PR URL, CI status). The parent keeps all of them — they are the raw material for the per-repo sections below.

## 4. Report

Organize per **eligible or blocked** repo — not a dump of every non-Node repo probed.

```markdown
# Node upgrade — all controlled repos

**Target:** 22.x (resolved from current LTS | from args)
**Mode:** parallel | sequential
**Owned orgs:** org1 (n repos), org2 (n repos)
**Repos scanned:** N — Node: J, eligible: M, PRs opened: X, blocked: Y, already on target: Z

## Per-repo results

### owner/repo1 — PR opened
| Field | Value |
|-------|--------|
| Old | 18 (`.nvmrc`, Actions 18, `engines >=18`) |
| New | 22 |
| PR | [#88](https://github.com/owner/repo1/pull/88) |
| Breakage | eslint parser, `@types/node` |
| CI | green / red / pending |

### owner/lib — blocked
- engines.node `>=16 <20`; target 22 excluded. Did not open a PR.

## Probed but not upgraded
- not a Node repo: count
- already on target: owner/repo (list if few)
- probe/child failed: owner/repo — error
```

If the controlled-repo list looks wrong (missing an org, or an org they do not want), say how it was filtered so the user can rerun with a narrower scope.
