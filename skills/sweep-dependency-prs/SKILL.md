---
name: sweep-dependency-prs
description: >-
  Sweep every open Dependabot and Renovate PR in a given GitHub repo: review
  (approve) each one, merge it when every CI check is green and there is no
  conflict, and if CI is red run fix-renovate-pr or fix-dependabot-pr on that
  PR URL. Use whenever the user asks for a morning GitHub sweep, to review and
  merge bot PRs, to process all Dependabot/Renovate PRs in a repo, or to
  attack those PRs in parallel or one after the other. Also triggers on
  /sweep-dependency-prs with an owner/repo (or repo URL) and optional
  parallel|sequential.
argument-hint: "<owner/repo-or-url> [parallel|sequential]"
disable-model-invocation: false
---

# Sweep Dependency PRs

Goal: for a given repo, process **every open Dependabot and Renovate PR** with this flow — review (approve), then merge if every CI check passed and there is no conflict; if some CI checks fail, run `fix-renovate-pr` or `fix-dependabot-pr` with the PR link. Human PRs are out of scope. Do not open new PRs.

## 0. Repo and mode

Parse `$ARGUMENTS` (and the user message) for:

- **Repo:** `owner/repo`, or a GitHub URL. If omitted, use `git remote get-url origin` of the current workspace. Never ask for the repo URL when origin is enough.
- **Mode:** `parallel` (default when two or more PRs need a CI fix) or `sequential` (one red PR after the other). Honor an explicit ask either way. Approve/status fetches are always parallel. **Merges are always one after another** (GitHub serializes onto the same base branch; parallel merges race into conflicts).

## 1. List only bot PRs

```bash
gh pr list --repo <owner>/<repo> --state open --limit 100 \
  --json number,title,url,author,headRefName,isDraft,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup
```

Keep a PR only if **any** of:

- `author.login` matches `dependabot` or `renovate` (including `[bot]` / `app/` forms)
- `headRefName` starts with `dependabot/` or `renovate/`

If exactly 100 PRs come back, re-run with a higher `--limit` — never silently truncate the sweep.

A branch prefix alone is weak evidence: anyone can push a branch named `dependabot/...`. If a PR matches only by prefix and the author is a plain user account (legitimate for self-hosted Renovate running as a machine user), skim it extra hard in step 2 and call it out in the report.

Skip drafts. Skip everything else, even with a `dependencies` label. If none match, stop and say so.

## 2. Classify each PR

Fetch checks in parallel (`gh pr checks <n> --repo <owner>/<repo>` plus `gh pr view <n> --repo <owner>/<repo> --json files,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup,autoMergeRequest`). Note: `gh pr checks` exits non-zero when any check is failing or pending — that is data, not a command error.

Skim title, version change, and files. This is a review-to-approve pass, not a full design review. Skip (do not approve or merge) only if it does not look like a bot dependency bump (unexpected authors, huge unrelated diffs). Note majors in the report; still process them.

Bucket:

| Bucket | When | Action |
|--------|------|--------|
| **Ready** | Not dirty, every completed check is success/neutral/skipped, none pending or failing | Approve (if needed) and merge |
| **Pending** | No failures, but checks still running | Approve (if needed), enable auto-merge, do not wait forever |
| **Red** | Any check failed | Approve (if needed), then run the matching fix skill |
| **Conflict** | `mergeable` is `CONFLICTING` or `mergeStateStatus` is `DIRTY` | Do not merge. Ask the bot to rebase if nobody else has pushed (see below). Re-classify after. |
| **Blocked** | Still blocked after our approval (CODEOWNERS, branch protection, `CHANGES_REQUESTED` by someone else) | Report; do not merge |

A PR can be both red and dirty — **Conflict wins**: the fix skills can't help while the branch doesn't merge cleanly. Get it rebased first, then re-classify (it may land back in Red).

`mergeStateStatus` cheat sheet: `CLEAN` = ready (still confirm no failed checks), `UNSTABLE` = treat as red if any check failed, `DIRTY` = conflict, `BLOCKED` = reviews/required checks, `BEHIND` = not up to date — do not merge if protection requires a linear branch; request a bot rebase first.

**Bot rebase only when the branch is still the bot's** (no human/agent commits yet). The two bots are **not** the same:

- **Dependabot:** comment `@dependabot rebase`
- **Renovate:** do **not** comment. `@renovate rebase` (or any comment that tags the bot with the word rebase) is ignored. Edit the PR **description** and check the rebase box:
  `- [ ] <!-- rebase-check -->If you want to rebase/retry this PR, check this box`
  →
  `- [x] <!-- rebase-check -->If you want to rebase/retry this PR, check this box`
  Use `gh pr edit` on the body (see **`fix-renovate-pr`**). Leave the `<!-- rebase-check -->` marker in place.

Never comment `recreate` after anyone else has pushed (it force-pushes and wipes those commits). Never check Renovate's rebase box after anyone else has pushed — Renovate regenerates the branch and wipes those commits.

After requesting the rebase, poll `mergeable`/`mergeStateStatus` every ~30 s for up to ~3 minutes. If the rebase has not landed by then, don't stall the sweep: leave the PR in Conflict, do one last re-check at the end of the sweep, and report it as "rebase requested".

## 3. Approve

For every PR that passed the skim and is not skipped/blocked by someone else's requested changes:

```bash
gh pr review <number> --repo <owner>/<repo> --approve
```

Skip if `reviewDecision` is already `APPROVED` by you. Run these reviews in parallel.

## 4. Merge the ready bucket

Prefer squash (`gh pr merge <n> --repo <owner>/<repo> --squash`). If squash is disabled, fall back to merge commit, then rebase. Never `--admin`, never force.

Merge **one PR at a time** (ascending number is fine). After each merge, refresh `mergeable` / `mergeStateStatus` on the remaining "ready" PRs before the next merge:

- `DIRTY` (or a merge fails with a conflict) → move to **Conflict**.
- `BEHIND` with protection requiring up-to-date branches → request a bot rebase (rules above) and treat like Conflict: bounded wait, re-check at the end.

For **Pending**: `gh pr merge <n> --repo <owner>/<repo> --squash --auto` and list them as waiting on CI. If `--auto` fails because the repo has auto-merge disabled, don't camp on the checks — re-check those PRs once at the end of the sweep, merge the ones that turned green, and report the rest as waiting on CI.

## 5. Fix red PRs with the existing skills

Pick the skill from the PR, not from guesswork:

- Dependabot (`dependabot/` branch or dependabot author) → read and follow **`fix-dependabot-pr`** with that PR URL
- Renovate (`renovate/` branch or renovate author) → read and follow **`fix-renovate-pr`** with that PR URL

Those skills push fixes and **do not merge**. After each one returns, this skill owns merge (step 6).

### Parallel (default for 2+ red PRs)

Launch one isolated agent/worktree per red PR. Each agent gets the PR URL and must follow the matching fix skill end to end. They must **not** share a working tree (checkouts will clobber each other). Cap concurrency around 4 if there are many; queue the rest. If subagents/worktrees are unavailable, fall back to sequential.

### Sequential

Process red PRs one after the other in the current workspace. Finish the fix skill (including remote CI watch) on PR N before checking out PR N+1.

If a fix skill stops with a real blocker (incompatible peer, missing secret, flake), leave that PR unmerged and continue the rest.

## 6. Merge newly green PRs

When a red PR's checks are green and it is not dirty, merge it (same rules as step 4: squash, one at a time, refresh mergeability). Branch protection may dismiss stale approvals when the fix skill pushes — re-check `reviewDecision` and re-approve first if needed. If still red after the fix skill's retry limit, leave it and report.

## 7. Report

```markdown
# Dependency PR sweep — <owner>/<repo>

**Mode:** parallel | sequential
**Open bot PRs:** N

## Merged
- #n title — squash, checks were green

## Auto-merge enabled (CI still running)
- #n title

## Fixed then merged
- #n title — what broke, fix skill used

## Still open
- #n title — conflict | still red | blocked | skipped (why)

## Out of scope
- human PRs ignored (count)
```

Include PR URLs. Mention majors even when merged. If a rebase was requested, say whether it has landed yet.