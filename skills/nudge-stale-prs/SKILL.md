---
name: nudge-stale-prs
description: >-
  List every GitHub repo the authenticated user has write access to — including
  personal repos, every repo in organizations they own, and collaborator repos
  they can push to — find open pull requests older than 2 days, and tag the
  user in a comment asking them to review and merge. Use whenever the user
  wants a reminder on forgotten PRs that do not show in GitHub notifications
  (including PRs they authored), to ping stale pull requests across their
  fleet, or to fan out a review/merge nudge. Also triggers on /nudge-stale-prs
  with optional age, include-bots, and parallel|sequential.
argument-hint: "[days] [include-bots] [parallel|sequential]"
disable-model-invocation: false
---

# Nudge Stale PRs

Goal: find **open PRs older than 2 days** across **every repo the user can write to**, and **comment `@<user>` requesting they review and merge**. This is the notification-gap twin of `sweep-all-dependency-prs`: that skill lands bot PRs; this one surfaces human PRs that GitHub never notified them about — especially **PRs they authored**. Do not merge. Do not approve. Do not request reviewers via the API. The comment *is* the reminder.

## 0. Mode and filters

Parse `$ARGUMENTS` / the user message for:

- **Age floor** (optional): an integer number of days (`2`, `3`, `7`). Default: **2**. A PR is in scope when `createdAt` is **strictly older** than that many 24-hour periods (use UTC). "Over 2 days old" means created before `now - 2 days`, not last-updated.
- **Bots:** skip Dependabot/Renovate PRs unless the user said `include-bots` / "include bots" / "including dependabot". Bot PRs belong to `sweep-all-dependency-prs` by default — do not turn this skill into a bot ping storm.
- **Mode:** `parallel` (default, across **repos**) or `sequential`. Comments on PRs **in the same repo** are always sequential.
- **Scope:** if the user names an org, a subset ("only my public repos", "skip work orgs", "this repo"), an `owner/repo`, or an allow/deny list, honor it as a filter. Default is the full write-access union.

If `gh` is not authenticated, stop and tell the user to run `gh auth login` (and `gh auth refresh -s read:org` if org listing 403s). Never ask them to paste a repo list.

Resolve the authenticated login once and reuse it for every `@mention`:

```bash
gh api user --jq .login
```

## 1. List repos they can write to

Start from the **same three-source union as `sweep-all-dependency-prs`** (read that skill's step 1), with **one required delta**: source C includes **write** (`permissions.push`), not only admin/maintain. `GET /user/repos` alone still misses org repos.

- **A. Personal repos:** `gh repo list <user> --limit 1000 --no-archived --source --json nameWithOwner`
- **B. Every repo in orgs they own:** memberships from `/user/memberships/orgs` filtered to `state == "active"` and `role == "admin"`, then `gh repo list <org> --limit 1000 --no-archived --source` per owned org. A 403 means the token lacks `read:org` — stop and say so; an empty 200 just means no orgs.
- **C. Other writable repos** (collaborator / org member, including orgs they do not own):

```bash
gh api --paginate \
  "/user/repos?affiliation=collaborator,organization_member&per_page=100" \
  --jq '.[] | select(.archived == false and .disabled != true and .fork == false) | select(.permissions.admin == true or .permissions.maintain == true or .permissions.push == true) | .full_name'
```

Union by `full_name`, paginate every call to completion, skip forks and archived/disabled repos unless asked to include them. In the final report, list the owned orgs and repo count per org so a missing organization is obvious.

## 2. Probe open PRs in parallel

For every remaining repo, in parallel batches of ~15 so rate limits survive:

```bash
gh pr list --repo <owner>/<repo> --state open --limit 100 \
  --json number,title,url,author,createdAt,isDraft,headRefName,reviewRequests
```

If a call returns exactly 100, re-run with a higher `--limit`. A failing `gh pr list` is a skip for that repo, not a halt for the fleet.

A PR is a **candidate** when all of these hold:

| Check | Keep when |
|-------|-----------|
| Open, not draft | `isDraft == false` |
| Older than the age floor | `createdAt` < `now − N days` (UTC) |
| Not a bot (default) | author login does **not** contain `dependabot` or `renovate`, and `headRefName` does **not** start with `dependabot/` or `renovate/` |
| Not already nudged | issue comments do **not** contain the marker `<!-- skillable-nudge-stale-prs -->` |

Drafts are out unless the user asked to include them. Age is **created**, not last-updated: a 10-day-old PR touched yesterday is still stale. Include PRs the user authored — that is the main notification miss. Include PRs already assigned or review-requested; GitHub may still not have notified them.

**Already-nudged check** (only for candidates that passed the other filters), one call per PR:

```bash
gh api --paginate "repos/<owner>/<repo>/issues/<number>/comments?per_page=100" \
  --jq '.[].body'
```

Skip the PR if any comment body contains `<!-- skillable-nudge-stale-prs -->`. Do not re-comment unless the user explicitly said to re-nudge / ping again. Review threads do not count — only issue comments on the PR.

Bucket each **repo**:

| Bucket | When | Next step |
|--------|------|-----------|
| **No open PRs** | empty list | Skip |
| **None stale** | open PRs exist but none pass the candidate checks | Skip. Count drafts / too-new / bots / already-nudged in the report |
| **Has stale PRs** | at least one candidate | Comment on each candidate |

Do not approve, merge, rebase, or request reviewers at this layer.

## 3. Comment — tag the user to review/merge

Post **one issue comment per candidate PR**. Use this body **verbatim** (substitute `<login>`, `<N>`, and `<title>` only):

```text
<!-- skillable-nudge-stale-prs -->
@<login> this PR is over <N> days old and may not have shown up in your GitHub notifications. Please review/merge **<title>** when you can.
```

`<N>` is the whole number of days since `createdAt` (floor), not the age-floor setting. Example: floor is 2, PR created 5.8 days ago → `over 5 days old`.

```bash
gh api "repos/<owner>/<repo>/issues/<number>/comments" \
  -f body="$(cat <<EOF
<!-- skillable-nudge-stale-prs -->
@${LOGIN} this PR is over ${DAYS_OPEN} days old and may not have shown up in your GitHub notifications. Please review/merge **${TITLE}** when you can.
EOF
)"
```

Rules:

- **Do not merge. Do not approve. Do not close. Do not dismiss reviews.** Comment only.
- Do not `@`-mention anyone except the authenticated user. Do not ping authors, reviewers, or CODEOWNERS.
- You cannot request yourself as a reviewer on your own PR — that is why this is a comment, not `gh pr edit --add-reviewer`.
- Comments in the **same repo** are sequential. Across repos: parallel with a concurrency cap of ~4–6; queue the rest. If subagents are unavailable, sequential. All children share one token: a `secondary rate limit` 403 means sleep ~60 s and retry — that is throttling, not a failure. If it persists, drop concurrency.
- A 403/404 on one comment is a skip-with-error for that PR, not a halt for the fleet.
- Never comment twice on the same PR in one run. Re-read the marker if two workers might touch the same repo.
- Do not clone repositories. This skill is API-only.

## 4. Report

Organize **per repo that had a candidate or a comment**. Untouched repos are counts only.

```markdown
# Stale PR nudge — write-access repos

**Mode:** parallel | sequential
**Age floor:** 2 days
**Bots:** skipped | included
**User tagged:** @login
**Owned orgs:** org1 (n repos), org2 (n repos)
**Repos scanned:** N (personal: P, from owned orgs: O, other writable: C)
**PRs nudged:** X — already nudged: Y, skipped drafts/too-new/bots: Z

## Per-repo results

### owner/repo1 — 2 nudged, 1 already nudged
| PR | Age | Author | Result |
|----|-----|--------|--------|
| [#12 fix login](https://github.com/owner/repo1/pull/12) | 5d | @you | Commented |
| [#13 add docs](https://github.com/owner/repo1/pull/13) | 11d | @teammate | Commented |
| [#14 tweak ci](https://github.com/owner/repo1/pull/14) | 4d | @you | Already nudged |

## Repos probed but not nudged
- no open PRs: count
- open but none stale: count
- probe/comment failed: owner/repo#n — the error
```

Rules:

- Every candidate appears as a row with its URL, title, age in days, author, and outcome (`Commented` or `Already nudged` or `Failed`).
- Mark rows where the author is the authenticated user — those are the notification-gap hits.
- If the write-access list looks wrong (missing an org, or an org they do not want), say how it was filtered so they can rerun with a narrower scope.
