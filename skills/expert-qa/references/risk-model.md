# Risk model and release-readiness rules

Load this at step 2 of the skill (risk mapping) and again at step 7 (verdict).

## How to score an area

Score each changed area on two axes, then combine.

**Likelihood of breaking**

| Score | Signals |
|-------|---------|
| 3 — high | New logic with branches; concurrency, retries, or async ordering; date/time math; parsing external input; migrations; no tests; area with recent `fix`/`revert` commits |
| 2 — medium | Modified existing logic with some tests; config or default changes; new dependency or major bump; refactor touching many call sites |
| 1 — low | Copy, styling, docs, rename with compiler/type coverage, pure additions behind a flag that is off |

**Blast radius**

| Score | Signals |
|-------|---------|
| 3 — high | Money, auth, permissions, PII, data writes or deletion, anything irreversible; every user affected; public API or event schema other systems read |
| 2 — medium | A core journey for some users; admin tools; background jobs with retry; caching layer |
| 1 — low | A secondary screen, internal tooling, a reversible setting |

**Combined risk** = likelihood × radius: 7–9 Critical, 4–6 High, 2–3 Medium, 1 Low. Raise one level when the area is uncovered or has many callers; never lower a money/auth/data-loss area below High.

## Finding the indirect blast radius

```bash
# who calls the changed symbol
rg -n '<symbol>\(' -g '!node_modules' -g '!dist'
# shared UI or tokens
rg -n -l '<ComponentName>|<css-var-or-token>' src app components
# history of trouble
git log --oneline -20 -- <path> | rg -i 'fix|revert|hotfix|regress'
# changed defaults / env
git diff <range> -- '*.env*' '*config*' '*settings*'
```

List each indirect consumer that the change can alter and whether it has a test.

## Choosing the test layer for a gap

| Behavior | Cheapest layer that proves it |
|----------|------------------------------|
| Pure logic, parsing, math, date handling | Unit |
| DB queries, transactions, migrations, permissions checks, external API contracts | Integration (real DB/container or a contract test) |
| Multi-step user journey, auth redirects, client/server handoff | E2E on the critical path only |
| Visual layout, responsive breakpoints | Visual regression or a manual release check |
| Production-only behavior (CDN, real payment provider, email deliverability) | Manual release check + monitoring, stated as a condition |

Recommend the lowest layer that would actually fail when the behavior breaks. Do not recommend e2e for what a unit test proves.

## Test plan priorities

- **P0** — Critical-risk paths and every reproduced failure. Must exist before release.
- **P1** — High-risk paths, main negative cases (permission denied, invalid input, provider error).
- **P2** — Medium edge cases from the catalog that apply.
- **P3** — Nice to have; list only if cheap.

Cap the plan at what the team will actually run. A focused 10–20 row plan is usually right for a PR; group by feature for a release.

## Verdict decision table

| Condition | Verdict |
|-----------|---------|
| Any reproduced Critical or High failure | Do not ship |
| Critical path uncovered and no mitigation | Do not ship |
| Required CI check red, or required tests newly skipped | Do not ship |
| Irreversible migration with no rollback or backup plan | Do not ship |
| High gap with a named mitigation (flag off by default, staged rollout, manual check, alert) | Ship with conditions |
| Only Medium gaps | Ship with conditions (list them) or Ship if the team accepts them |
| Only Low gaps or none; CI green; exploration clean or not applicable | Ship |

## Regression risk

State it separately from the verdict:

- **High** — existing behavior on a core path changes, or shared code with weak coverage was modified.
- **Medium** — existing secondary behavior changes, or core changes that are well covered.
- **Low** — additive change, behind a flag, or fully covered.

Always name *what* could regress and *for whom* ("users with saved carts from before v3", "API clients that send `limit=0`").

## Mitigations worth suggesting

- Feature flag, off by default, with a kill switch.
- Staged rollout (percentage, internal users first, one region).
- A specific manual check on staging before release, with steps.
- A monitor or alert on the metric that would show the failure (error rate on route X, refund mismatch count).
- A rollback plan: revert the deploy, down-migration, or a data backfill script.

Only suggest mitigations the project can actually use — check for an existing flag system or rollout tooling first.
