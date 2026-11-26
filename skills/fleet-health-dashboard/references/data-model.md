# Fleet health: queries and data model

## Collection

### PRs and repo fields (GraphQL, batched)

Query up to ~20 repos per request with aliases to stay well under rate limits:

```graphql
query {
  r0: repository(owner: "OWNER", name: "REPO") { ...health }
  r1: repository(owner: "OWNER", name: "REPO2") { ...health }
}

fragment health on Repository {
  nameWithOwner
  isPrivate
  pushedAt
  primaryLanguage { name }
  defaultBranchRef { name }
  issues(states: OPEN) { totalCount }
  pullRequests(states: OPEN, first: 100) {
    totalCount
    nodes {
      number
      url
      isDraft
      updatedAt
      author { login }
      mergeable
      assignees { totalCount }
      reviewRequests { totalCount }
      reviews { totalCount }
      commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
    }
  }
}
```

Run with `gh api graphql -f query=@query.graphql`. Classify each PR:

- **Bot PR**: author login is `dependabot`, `dependabot[bot]`, `renovate`, or `renovate[bot]`. Green = rollup `SUCCESS`; red = `FAILURE`/`ERROR`; pending otherwise; conflicting = `mergeable == CONFLICTING`.
- **Unassigned**: not a draft, not authored by the user or a bot, and `assignees`, `reviewRequests`, and `reviews` are all 0.
- **Stale**: not a draft and `updatedAt` older than 2 days.

### Dependabot alerts (REST)

```bash
gh api --paginate "repos/OWNER/REPO/dependabot/alerts?state=open&per_page=100" \
  --jq '[.[] | .security_advisory.severity] | group_by(.) | map({(.[0]): length}) | add'
```

403/404 → `alerts: null` with `alertsNote: "disabled or no access"`.

### Default-branch CI (REST)

```bash
gh api "repos/OWNER/REPO/actions/runs?branch=DEFAULT&status=completed&per_page=20" \
  --jq '.workflow_runs | map({name, conclusion, html_url, created_at})'
```

Take the latest completed run per workflow name. The branch is red if any latest run concluded `failure`, `timed_out`, or `startup_failure`. Record the first red run's URL. No workflows → `ci: "none"`.

### Node version

Check, in order, and keep the first hit: `.nvmrc`, `.node-version`, `package.json` `engines.node`, `actions/setup-node` `node-version` in `.github/workflows/*.yml`. Fetch with `gh api repos/OWNER/REPO/contents/PATH --jq .content | base64 -d`. Compare the major against the current Active LTS from `https://nodejs.org/dist/index.json` (first entry whose `lts` is not `false`). Non-JS repos → `node: null`.

## Database collections

### `repos`: one document per repo, id `OWNER__REPO`

```json
{
  "repo": "owner/repo",
  "org": "owner",
  "source": "personal | owned-org | controlled",
  "private": true,
  "language": "TypeScript",
  "pushedAt": "2026-10-18T09:12:00Z",
  "openIssues": 4,
  "botPrs": { "total": 3, "green": 2, "red": 1, "pending": 0, "conflicting": 0, "url": "https://github.com/owner/repo/pulls?q=is%3Aopen+author%3Aapp%2Fdependabot" },
  "unassignedPrs": 1,
  "stalePrs": 2,
  "alerts": { "critical": 0, "high": 2, "medium": 1, "low": 0 },
  "alertsNote": null,
  "ci": { "state": "red | green | none", "url": "https://github.com/owner/repo/actions/runs/123", "since": "2026-10-17T22:01:00Z" },
  "node": { "pinned": "20", "lts": "24", "behind": true },
  "status": "red | yellow | green",
  "reasons": ["2 high alerts", "main red"],
  "actions": ["/sweep-dependency-prs owner/repo", "/fix-failing-ci https://github.com/owner/repo/actions/runs/123"],
  "updatedAt": "2026-10-19T07:00:00Z"
}
```

### `runs`: one document per refresh, id = ISO timestamp

```json
{ "at": "2026-10-19T07:00:00Z", "repos": 58, "red": 4, "yellow": 11, "green": 43, "alerts": { "critical": 1, "high": 6 }, "botPrs": 17, "durationSec": 94 }
```

### `meta`: single document `config`

```json
{ "user": "login", "orgs": ["org1", "org2"], "filters": "none", "lastRefresh": "2026-10-19T07:00:00Z" }
```

## KPI tile filters

Each KPI tile and sub-line chip is a filter over `repos` documents. Repo-count tiles show the number of documents matching their predicate, so the count and the filtered table always agree.

| Tile / chip | Hash | Predicate |
| --- | --- | --- |
| Needs you | `#status=red` | `status == "red"` |
| Attention | `#status=yellow` | `status == "yellow"` |
| Healthy | `#status=green` | `status == "green"` (sub-line "of N repos" clears the filter) |
| Critical + high alerts | `#alerts=critical-high` | `alerts.critical + alerts.high > 0` |
| ↳ critical | `#alerts=critical` | `alerts.critical > 0` |
| ↳ moderate | `#alerts=medium` | `alerts.medium > 0` |
| ↳ repos with alerts off | `#alerts=off` | `alerts == null` |
| Red default branch | `#ci=red` | `ci.state == "red"` |
| ↳ repos with no Actions runs | `#ci=none` | `ci.state == "none"` |
| Open bot PRs | `#bot=open` | `botPrs.total > 0` |
| ↳ red | `#bot=red` | `botPrs.red > 0` |
| ↳ repos on Node below LTS | `#node=behind` | `node.behind == true` |

Alert tiles count alerts but filter to the repos that have them; say so in the filter label ("10 alerts in 6 repos"). An unknown or stale hash falls back to no filter.

## Refresh semantics

- Upsert every collected repo document; delete documents for repos no longer in the union.
- Append exactly one `runs` document per refresh; keep the last 90.
- The page sorts red → yellow → green, then by alert severity, then by repo name.
