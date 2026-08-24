---
name: sweep-all-dependency-prs
description: >-
  List every GitHub repo the authenticated user owns or controls — including
  every repo in organizations they own — check in parallel which ones have
  open PRs, and for each of those run sweep-dependency-prs. Use whenever the
  user wants a morning GitHub sweep across all their repos and orgs, to
  process Dependabot/Renovate PRs in every repo they own, or to fan out
  sweep-dependency-prs in parallel. Also triggers on /sweep-all-dependency-prs
  with optional parallel|sequential.
argument-hint: "[parallel|sequential]"
disable-model-invocation: false
---

# Sweep All Dependency PRs

Goal: list **every repo the user owns or controls**, including **every repo in organizations they own**, verify **in parallel** which of them have open PRs, and if so **call `sweep-dependency-prs`** on that repo. Do not reimplement approve/merge/fix here — read and follow `sweep-dependency-prs` for each repo that needs it.

## 0. Mode

Parse `$ARGUMENTS` / the user message for `parallel` (default) or `sequential`. That mode is how **repos** are swept. Each child sweep still follows its own rules (including serial merges inside a repo).

If `gh` is not authenticated, stop and tell the user to run `gh auth login`. Never ask them to paste a repo list.

## 1. List repos they own or control

`GET /user/repos` does **not** reliably return every org repo, even for org owners. Build the list from **three** sources and union by `full_name`. Paginate every call to completion.

```bash
gh api user --jq .login
```

**A. Personal repos** (user namespace):

```bash
gh repo list <user> --limit 1000 --no-archived --source --json nameWithOwner
```

If the result is a full page of 1000, re-run with a higher limit or paginate `GET /users/<user>/repos`.

**B. Every repo in organizations they own.** Org owners have membership `role` `admin`. Do not infer ownership from `/user/repos`.

```bash
gh api --paginate "/user/memberships/orgs?per_page=100" \
  --jq '.[] | select(.state == "active" and .role == "admin") | .organization.login'
```

The `state == "active"` filter matters: a pending org invitation also reports a role, but its repos are not accessible yet. Distinguish the failure modes: a **403** means the token lacks `read:org` — stop and tell them to run `gh auth refresh -s read:org`; an **empty 200** just means no org memberships — continue with personal and collaborator repos. For each owned org:

```bash
gh repo list <org> --limit 1000 --no-archived --source --json nameWithOwner
# equivalent: gh api --paginate "/orgs/<org>/repos?per_page=100&type=all"
```

List **all** non-archived, non-fork repos in that org (public and private). An org owner can see them; do not filter by `permissions` here or you will drop repos `/user/repos` never returned.

**C. Other repos they control but do not own** (collaborator / member with admin or maintain, including orgs they do not own):

```bash
gh api --paginate \
  "/user/repos?affiliation=collaborator,organization_member&per_page=100" \
  --jq '.[] | select(.archived == false and .disabled != true and .fork == false) | select(.permissions.admin == true or .permissions.maintain == true) | .full_name'
```

Skip **forks** and **archived** / **disabled** repos unless the user asked to include them. If they name an org or a subset ("only my public repos", "skip work orgs"), honor that as a filter on the union.

In the final report, list the owned orgs and the repo count per org so a missing organization is obvious.

## 2. Probe open PRs in parallel

For every remaining repo, in parallel (batches of ~15 so GitHub rate limits survive):

```bash
gh pr list --repo <owner>/<repo> --state open --limit 100 \
  --json number,title,url,author,headRefName,isDraft
```

If a call returns exactly 100, re-run with a higher `--limit`. A failing `gh pr list` (no access, repo gone) is a skip for that repo, not a halt for the whole sweep.

Bucket each repo:

| Bucket | When | Next step |
|--------|------|-----------|
| **No open PRs** | empty list | Skip. Do not call `sweep-dependency-prs`. |
| **Human PRs only** | open PRs, but none match the bot filter in `sweep-dependency-prs` (author login contains `dependabot` or `renovate`, or `headRefName` starts with `dependabot/` / `renovate/`) | Skip the child sweep. Count them as out of scope. |
| **Has bot PRs** | at least one **non-draft** Dependabot/Renovate PR | Call `sweep-dependency-prs` |

Apply the same draft skip here that the child sweep applies (that is why the probe fetches `isDraft`): a repo whose only bot PRs are drafts belongs in the skip bucket, not in a no-op child sweep.

The probe exists so empty repos do not spawn a no-op sweep. Do not approve, merge, or fix at this layer.

## 3. Call `sweep-dependency-prs` per repo

Read and follow **`sweep-dependency-prs`** with that `owner/repo`. Pass through the same parallel/sequential hint if the user set one (it applies to red-PR fixes *inside* that repo).

### Parallel (default)

One isolated agent per **Has bot PRs** repo. They must not share a working tree (different repos, so separate clone directories — never the current workspace for all of them). Cap concurrency around 4–6 repos; queue the rest. Each agent’s job is: run `sweep-dependency-prs` on that repo and return its report. If subagents are unavailable, fall back to sequential.

All parallel children share one token, and GitHub's **secondary rate limit** on content-creating requests (reviews, comments, merges) is per token. If a child hits a `secondary rate limit` 403, it should sleep ~60 s and retry — that is throttling, not a repo failure. If it keeps happening, drop concurrency.

### Sequential

Run `sweep-dependency-prs` on one repo at a time. Finish repo N (including its report) before starting repo N+1.

A child sweep that errors on one repo must not abort the others — record the failure and continue.

## 4. Report

Roll child reports up; do not dump every empty repo as its own section.

```markdown
# Dependency PR sweep — all controlled repos

**Mode:** parallel | sequential
**Owned orgs:** org1 (n repos), org2 (n repos)
**Repos scanned:** N (personal: P, from owned orgs: O, other controlled: C; skipped forks: F, archived: A)
**Repos with bot PRs:** M
**Called sweep-dependency-prs:** M

## Merged
- owner/repo#n title

## Auto-merge enabled (CI still running)
- owner/repo#n title

## Fixed then merged
- owner/repo#n title — what broke

## Still open
- owner/repo#n title — conflict | still red | blocked | skipped (why)

## Repos skipped
- no open PRs: count
- human PRs only: count (and the repos, if few)
- probe/sweep failed: owner/repo — error
```

Include PR URLs. If the controlled-repo list looks wrong (missing an org, or an org they do not want), say how it was filtered so they can rerun with a narrower scope.
