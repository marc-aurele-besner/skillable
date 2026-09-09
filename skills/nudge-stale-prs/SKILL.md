---
name: nudge-stale-prs
description: >-
  List every GitHub repo the authenticated user has write access to — including
  personal repos, every repo in organizations they own, and collaborator repos
  they can push to — find open pull requests older than 2 days, and have the
  running agent GitHub user (cursor[bot], claude[bot], or Codex) tag the human
  in a comment asking them to review and merge. Use whenever the user wants a
  reminder on forgotten PRs that do not show in GitHub notifications (including
  PRs they authored), to ping stale pull requests across their fleet, or to fan
  out a review/merge nudge. Also triggers on /nudge-stale-prs with optional age,
  include-bots, and parallel|sequential. Never comment as the same user being
  tagged — GitHub drops self-mentions.
argument-hint: "[days] [include-bots] [parallel|sequential]"
disable-model-invocation: false
---

# Nudge Stale PRs

Goal: find **open PRs older than 2 days** across **every repo the human can write to**, and **have the running agent GitHub user** (`cursor[bot]`, `claude[bot]`, or Codex) **comment `@<human>` requesting they review and merge**. GitHub does **not** notify a user who `@`-mentions themselves, so the comment author must be a **different** login than the tagged human. Do not merge. Do not approve. The agent-authored mention *is* the reminder.

## 0. Identities — human vs agent bot

Resolve **two** logins before listing any repos. They must not be the same.

**Human to notify (`NOTIFY_LOGIN`)** — the person whose forgotten PRs this sweep is for:

```bash
gh api user --jq .login
```

If that login is already an agent bot (table below), do not tag it. Take `NOTIFY_LOGIN` from `$ARGUMENTS` (`@someone` / `--user login`), else `GITHUB_ACTOR` when that is a human, else stop and say the skill needs an explicit human GitHub login to tag.

**Agent that posts (`AGENT_BOT`)** — whichever product is executing this skill. You know which you are; also confirm via env:

| Running as | Env signals | GitHub App slug | Bot login | Mention |
|------------|-------------|-----------------|-----------|---------|
| Cursor | `CURSOR_AGENT`, `CURSOR_TRACE_ID`, `CURSOR_SANDBOX` | `cursor` | `cursor[bot]` | `@cursor` |
| Claude Code | `CLAUDECODE`, `CLAUDE_CODE` | `claude` | `claude[bot]` | `@claude` |
| Codex | `CODEX_SANDBOX`, `CODEX_THREAD_ID`, `CODEX_HOME` | `chatgpt-codex-connector` | `chatgpt-codex-connector[bot]` | `@codex` |

Normalize logins by stripping a trailing `[bot]` before comparing. If `gh api user` is already `AGENT_BOT` (Cursor Automations, Claude GitHub Action, some Cloud Agents), later comments go through `gh` directly. If `gh` is `NOTIFY_LOGIN` (typical local IDE), **do not** `POST` the nudge body with `gh` — that would be a self-mention. Delegate to the App so `AGENT_BOT` is the comment author.

If this session is not Cursor, Claude Code, or Codex, stop: the skill cannot produce a notifying mention without one of those GitHub App users.

**Hard rule:** never create an issue comment whose author login equals `NOTIFY_LOGIN` and whose body contains `@NOTIFY_LOGIN`. Skip that PR rather than post a no-op self-tag.

## 1. Mode and filters

Parse `$ARGUMENTS` / the user message for:

- **Age floor** (optional): an integer number of days (`2`, `3`, `7`). Default: **2**. A PR is in scope when `createdAt` is **strictly older** than that many 24-hour periods (use UTC). "Over 2 days old" means created before `now - 2 days`, not last-updated.
- **Bots:** skip Dependabot/Renovate PRs unless the user said `include-bots` / "include bots" / "including dependabot". Bot PRs belong to `sweep-all-dependency-prs` by default — do not turn this skill into a bot ping storm.
- **Mode:** `parallel` (default, across **repos**) or `sequential`. Comments on PRs **in the same repo** are always sequential.
- **Scope:** if the user names an org, a subset ("only my public repos", "skip work orgs", "this repo"), an `owner/repo`, or an allow/deny list, honor it as a filter. Default is the full write-access union.

If `gh` is not authenticated, stop and tell the user to run `gh auth login` (and `gh auth refresh -s read:org` if org listing 403s). Never ask them to paste a repo list.

## 2. List repos they can write to

Start from the **same three-source union as `sweep-all-dependency-prs`** (read that skill's step 1), with **one required delta**: source C includes **write** (`permissions.push`), not only admin/maintain. `GET /user/repos` alone still misses org repos. List as the **human** (their `gh` when `gh` is `NOTIFY_LOGIN`; when `gh` is already `AGENT_BOT`, list what that App can see and say so in the report).

- **A. Personal repos:** `gh repo list <user> --limit 1000 --no-archived --source --json nameWithOwner`
- **B. Every repo in orgs they own:** memberships from `/user/memberships/orgs` filtered to `state == "active"` and `role == "admin"`, then `gh repo list <org> --limit 1000 --no-archived --source` per owned org. A 403 means the token lacks `read:org` — stop and say so; an empty 200 just means no orgs.
- **C. Other writable repos** (collaborator / org member, including orgs they do not own):

```bash
gh api --paginate \
  "/user/repos?affiliation=collaborator,organization_member&per_page=100" \
  --jq '.[] | select(.archived == false and .disabled != true and .fork == false) | select(.permissions.admin == true or .permissions.maintain == true or .permissions.push == true) | .full_name'
```

Union by `full_name`, paginate every call to completion, skip forks and archived/disabled repos unless asked to include them. In the final report, list the owned orgs and repo count per org so a missing organization is obvious.

## 3. Probe open PRs in parallel

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
| Not already nudged | no issue comment body contains `<!-- skillable-nudge-stale-prs -->` (the **bot** marker — ignore the trigger marker below) |

Drafts are out unless the user asked to include them. Age is **created**, not last-updated: a 10-day-old PR touched yesterday is still stale. Include PRs the human authored — that is the main notification miss. Include PRs already assigned or review-requested; GitHub may still not have notified them.

**Already-nudged check** (only for candidates that passed the other filters), one call per PR:

```bash
gh api --paginate "repos/<owner>/<repo>/issues/<number>/comments?per_page=100" \
  --jq '.[] | {user: .user.login, body}'
```

- **Nudged:** any comment body contains `<!-- skillable-nudge-stale-prs -->` — skip (unless they said re-nudge).
- **Trigger only:** `<!-- skillable-nudge-stale-prs-trigger -->` without the bot marker — skip as "waiting on agent bot"; do not post a second trigger unless they said re-nudge.
- Review threads do not count — only issue comments on the PR.

Bucket each **repo**:

| Bucket | When | Next step |
|--------|------|-----------|
| **No open PRs** | empty list | Skip |
| **None stale** | open PRs exist but none pass the candidate checks | Skip. Count drafts / too-new / bots / already-nudged in the report |
| **Has stale PRs** | at least one candidate | Nudge via `AGENT_BOT` |

Do not approve, merge, rebase, or request reviewers at this layer.

## 4. Comment as the agent bot, tagging the human

Nudge body (what `AGENT_BOT` must post). Substitute `<NOTIFY_LOGIN>`, `<N>`, and `<title>` only:

```text
<!-- skillable-nudge-stale-prs -->
@<NOTIFY_LOGIN> this PR is over <N> days old and may not have shown up in your GitHub notifications. Please review/merge **<title>** when you can.
```

`<N>` is whole days since `createdAt` (floor), not the age-floor setting. Example: floor is 2, PR created 5.8 days ago → `over 5 days old`.

### Direct — `gh` is already `AGENT_BOT`

`gh api user` matches `AGENT_BOT`. Post the nudge body with `gh`. This is the only time `gh` may create the `@NOTIFY_LOGIN` comment.

```bash
gh api "repos/<owner>/<repo>/issues/<number>/comments" -f body="$NUDGE_BODY"
```

### Delegate — `gh` is `NOTIFY_LOGIN` (or any other non-bot)

Do **not** post `$NUDGE_BODY` with this token. Have `AGENT_BOT` post it:

1. Confirm the matching GitHub App is installed on the repo (or its owner):

```bash
gh api --paginate user/installations \
  --jq '.installations[] | {id, slug: .app_slug, account: .account.login}'
# then, for the installation whose slug matches this agent:
gh api --paginate "/user/installations/<id>/repositories?per_page=100" \
  --jq '.repositories[].full_name'
```

If listing installations 403s or the repo is not in the list, skip that repo: tell them to install the Cursor / Claude / Codex GitHub App on it (`https://github.com/apps/cursor`, `https://github.com/apps/claude`, `https://github.com/apps/chatgpt-codex-connector`). Do not @-mention an App that is not installed.

2. Post **one trigger** as the current `gh` user. This mention is `@cursor` / `@claude` / `@codex` (the bot), **not** a self-tag of `NOTIFY_LOGIN` for notification. Body **verbatim** except substitutions:

```text
<!-- skillable-nudge-stale-prs-trigger -->
@<AGENT_MENTION> Reply as yourself with exactly one top-level comment, then stop. Do not push, review, approve, or change code. The comment body must be exactly:

<!-- skillable-nudge-stale-prs -->
@<NOTIFY_LOGIN> this PR is over <N> days old and may not have shown up in your GitHub notifications. Please review/merge **<title>** when you can.
```

```bash
gh api "repos/<owner>/<repo>/issues/<number>/comments" -f body="$TRIGGER_BODY"
```

3. Optional: poll comments ~60–90 s on the first PR. If `AGENT_BOT` posted the nudge marker, proceed. If not, keep going and record "trigger posted, waiting on bot" rather than blocking the fleet.

Rules:

- **Do not merge. Do not approve. Do not close. Do not dismiss reviews.** Comment only.
- Do not `@`-mention anyone except `NOTIFY_LOGIN` (in the **bot** nudge) and `AGENT_MENTION` (in the trigger). Do not ping authors, reviewers, or CODEOWNERS.
- You cannot request yourself as a reviewer on your own PR — and a self-comment would not notify either. That is why the author must be `AGENT_BOT`.
- Comments in the **same repo** are sequential. Across repos: parallel with a concurrency cap of ~4–6; queue the rest. If subagents are unavailable, sequential. All children share one token: a `secondary rate limit` 403 means sleep ~60 s and retry — that is throttling, not a failure. If it persists, drop concurrency.
- A 403/404 on one comment is a skip-with-error for that PR, not a halt for the fleet.
- Never comment twice on the same PR in one run. Re-read markers if two workers might touch the same repo.
- Do not clone repositories. This skill is API-only.

## 5. Report

Organize **per repo that had a candidate or a comment**. Untouched repos are counts only.

```markdown
# Stale PR nudge — write-access repos

**Mode:** parallel | sequential
**Age floor:** 2 days
**Bots:** skipped | included
**Human tagged:** @login
**Commenter:** cursor[bot] | claude[bot] | chatgpt-codex-connector[bot]
**Path:** direct (gh is the bot) | delegated (@mention trigger)
**Owned orgs:** org1 (n repos), org2 (n repos)
**Repos scanned:** N (personal: P, from owned orgs: O, other writable: C)
**PRs nudged:** X — trigger posted: T, already nudged: Y, skipped (no App / self-mention blocked): S

## Per-repo results

### owner/repo1 — 2 nudged, 1 already nudged
| PR | Age | Author | Result |
|----|-----|--------|--------|
| [#12 fix login](https://github.com/owner/repo1/pull/12) | 5d | @you | Commented as cursor[bot] |
| [#13 add docs](https://github.com/owner/repo1/pull/13) | 11d | @teammate | Trigger posted; waiting on cursor[bot] |
| [#14 tweak ci](https://github.com/owner/repo1/pull/14) | 4d | @you | Already nudged |

## Repos probed but not nudged
- no open PRs: count
- open but none stale: count
- GitHub App not installed: owner/repo — install URL
- probe/comment failed: owner/repo#n — the error
```

Rules:

- Every candidate appears as a row with its URL, title, age in days, author, and outcome (`Commented as AGENT_BOT` or `Trigger posted` or `Already nudged` or `Skipped (no App)` or `Failed`).
- Mark rows where the author is `NOTIFY_LOGIN` — those are the notification-gap hits.
- If the write-access list looks wrong (missing an org, or an org they do not want), say how it was filtered so they can rerun with a narrower scope.
