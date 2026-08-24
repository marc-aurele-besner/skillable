---
name: sweep-all-dependabot-alerts
description: >-
  List every GitHub repo the authenticated user owns or controls — including
  every repo in organizations they own — find open Dependabot security alerts,
  and for each affected repo run fix-dependabot-alert (serialized per repo,
  parallel across repos). Use whenever the user wants a security sweep of all
  their repos, to remediate Dependabot alerts across an org, or to fan out
  fix-dependabot-alert. Also triggers on /sweep-all-dependabot-alerts with
  optional severity filter and parallel|sequential.
argument-hint: "[critical|high|moderate|low] [parallel|sequential]"
disable-model-invocation: false
---

# Sweep All Dependabot Alerts

Goal: list **every repo the user owns or controls**, including **every repo in organizations they own**, find open Dependabot **security alerts**, and for each affected repo **call `fix-dependabot-alert`** per alert. This is the security twin of `sweep-all-dependency-prs`: that skill lands bot *PRs*; this one remediates open *alerts* that may have no PR yet. Do not reimplement bump/override/lockfile logic here — read and follow `fix-dependabot-alert`. The child opens a PR and does not merge; this parent must not merge those PRs either unless the user explicitly asks. This skill covers Dependabot application alerts only — not secret scanning, not CodeQL.

## 0. Mode and filters

Parse `$ARGUMENTS` / the user message for:

- **Severity floor** (optional): `critical`, `high`, `moderate` (accept `medium` as a synonym), or `low`. Default: **process `critical` and `high`**; **report** `moderate` and `low` without opening PRs unless the user asked for those severities. Dev-only alerts at or above the floor still get a child run, but the report must label them scope=`development`.
- **Mode:** `parallel` (default, across **repos**) or `sequential`. Honor an explicit ask. **Alerts in the same repo are always sequential** — they share a lockfile, and two writers on one lockfile corrupt each other's work.
- **Scope:** same as `sweep-all-dependency-prs` — if the user names an org or a subset ("only my public repos", "skip work orgs"), honor it as a filter on the union.

If `gh` is not authenticated, stop and tell the user to run `gh auth login`. If org-membership listing returns a 403, the token lacks `read:org` — stop and tell them to run `gh auth refresh -s read:org`. Never ask them to paste a repo list.

## 1. List repos they own or control

Use the **same three-source union as `sweep-all-dependency-prs`** — personal repos (`gh repo list <user> --limit 1000 --no-archived --source`), every repo in orgs where the membership is `state == "active"` and `role == "admin"` (`/user/memberships/orgs`, then `gh repo list <org>` / `GET /orgs/<org>/repos?type=all`), and other controlled repos (`/user/repos?affiliation=collaborator,organization_member` filtered to `permissions.admin` or `permissions.maintain`). Do not rely on `GET /user/repos` alone; do not invent a fourth scheme.

Deltas that matter here:

- Skip forks, archived, and disabled repos unless asked. Paginate every call to completion. Dedup by `full_name`.
- In the report, list the owned orgs and repo count per org so a missing organization is obvious.

## 2. Probe open alerts in parallel

For every remaining repo, in parallel batches of ~10–15 so rate limits survive:

```bash
gh api --paginate "repos/<owner>/<repo>/dependabot/alerts?state=open&per_page=100"
```

A 403/404 on a repo (Dependabot not enabled, no security permission for this token) is a **skip for that repo, not a halt** for the sweep. Record it under "Dependabot disabled / 403".

Keep an alert if:

- `state` is `open`
- its severity (`security_advisory.severity`) meets the floor (default critical+high)
- it is not dismissed (`dismissed_at` is null)

Extract per alert: number, HTML URL, package name, ecosystem, severity, GHSA/CVE IDs, manifest path (`dependency.manifest_path`), scope (`dependency.scope`: `runtime` or `development`), `dismissed_reason` if any, and whether a patched version exists (`security_vulnerability.first_patched_version`).

Bucket each **repo**:

| Bucket | When | Next step |
|--------|------|-----------|
| **No open alerts** | empty list | Skip. Do not call the child. |
| **Below floor only** | open alerts exist but all are under the severity floor | Do not call the child. List them under "Reported, not fixed". |
| **Has in-scope alerts** | at least one open alert at/above the floor | Call `fix-dependabot-alert` for each, **serialized in this repo** |

**Collapse duplicates:** alerts for the same package+manifest in the same repo become **one** child invocation (one PR), not one PR per GHSA on the same lockfile entry. Pass the canonical (most severe, else lowest-numbered) alert URL; mention the sibling GHSA IDs and alert numbers so the report and PR body cover them.

## 3. Dispatch `fix-dependabot-alert`

Read and follow **`fix-dependabot-alert`** with `https://github.com/<owner>/<repo>/security/dependabot/<number>` for each in-scope alert.

- **Per repo:** one isolated clone/worktree. Process that repo's in-scope alerts **one after another** in that worktree. When several alerts touch the same manifest, prefer combining them into **one branch and one PR per repo per run** rather than stacking PRs that each rewrite the lockfile. Never two writers on the same lockfile.
- **Across repos:** parallel with a concurrency cap of ~4–6, each repo in its own clone directory — never the current workspace for all of them. All children share one GitHub token: on a `secondary rate limit` 403, sleep ~60 s and retry — that is throttling, not a failure; if it persists, drop concurrency.
- If subagents/worktrees are unavailable, fall back to sequential across repos too.
- A child that stops (no patched version installable, override would break the parent, missing secret) must **not** abort the fleet. Record the blocker and continue with the next alert/repo.
- Do **not** dismiss alerts. Do **not** merge the child's PRs. Do **not** comment `@dependabot ignore` unless the user said so.

After each child returns, keep its **full report** (vulnerability path, remediation chosen, PR URL, CI status). Do not paraphrase it into a one-liner until the rollup below — the per-repo sections are built from these reports.

## 4. Report

Organized **per repo that was touched** (a child ran, or an alert was in-scope). Untouched repos are counts only.

```markdown
# Dependabot alert sweep — all controlled repos

**Mode:** parallel | sequential
**Severity floor:** critical+high (default) | …
**Owned orgs:** org1 (n repos), org2 (n repos)
**Repos scanned:** N (personal: P, from owned orgs: O, other controlled: C)
**Repos with in-scope alerts:** M — PRs opened: X, blocked: Y

## Per-repo results

### owner/repo1 — 2 PRs opened, 1 blocked
| Alert | Severity | Package | Result | Detail |
|-------|----------|---------|--------|--------|
| [#12](https://github.com/owner/repo1/security/dependabot/12) | high | lodash | PR opened | [#45](https://github.com/owner/repo1/pull/45) — bump direct dep |
| [#13](https://github.com/owner/repo1/security/dependabot/13) | critical | foo (transitive) | PR opened | same PR #45 — resolutions |
| [#14](https://github.com/owner/repo1/security/dependabot/14) | high | bar (development) | Blocked | no patched version installable; workaround noted |

## Reported, not fixed (below floor)
- owner/repo — alert #n moderate package (count per severity)

## Repos probed but not swept
- no open alerts: count
- Dependabot disabled / 403: owner/repo
- probe/child failed: owner/repo — the error
```

Rules:

- Every in-scope alert appears as a row with its alert URL, severity, package, GHSA/CVE IDs, and outcome. Collapsed duplicates share a row or reference the canonical row's PR.
- Label dev-scope alerts (`development`) in their row.
- State that alerts auto-resolve only after their PR merges on the default branch — an alert still showing `open` after a green PR is expected, not a failure.
- If the controlled-repo list looks wrong (missing an org, or an org they do not want), say how it was filtered so the user can rerun with a narrower scope.
