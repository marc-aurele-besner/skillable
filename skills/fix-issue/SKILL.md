---
name: fix-issue
description: Pick an open GitHub issue from the current repo, implement it on a new branch, and open a PR. Use whenever the user asks to grab, pick, work on, or fix an issue and ship it as a PR, even if they paste an issues URL. Also triggers on "/fix-issue" with an optional issue number.
---

# Fix Issue

End-to-end workflow: select an open issue in the current repo, implement it, and open a PR that closes it.

## 1. Select the issue

The repo is whatever `git remote get-url origin` points to. Never ask the user for the repo URL.

- If an issue number was given (e.g. `/fix-issue 42`), use it: `gh issue view 42`.
- Otherwise list candidates: `gh issue list --state open --json number,title,labels,assignees,url`
  - Skip issues that are assigned to someone else or already have a linked open PR (`gh pr list --search "linked:issue-N"` or check via `gh issue develop --list N`).
  - Prefer small, well-specified issues (bug > small feature > vague epic). Labels like `good first issue` or `bug` are good signals.
- State which issue you picked and why in one sentence, then proceed. Do not wait for confirmation unless the only candidates are large or ambiguous.

## 2. Branch

```
git fetch origin
git checkout -b <type>/<issue-number>-<short-slug> origin/<default-branch>
```

`<type>` is `fix`, `feat`, or `chore` based on the issue. Example: `fix/42-null-deploy-config`.

## 3. Implement

- Read the issue body and all comments fully before coding; comments often change the requirements.
- Explore the relevant code first, then make the minimal change that resolves the issue. No drive-by refactors.
- Match existing project conventions (lint config, test framework, commit style).
- Run the project's tests/lint/build if present. Add or update tests when the issue is a bug or behavior change.

## 4. Commit, push, PR

- Commit with a conventional message referencing the issue, e.g. `fix: handle null deploy config (#42)`.
- `git push -u origin <branch>`
- Create the PR against the default branch:

```
gh pr create --title "<concise title>" --body "$(cat <<'EOF'
## Summary
<what changed and why, 2-4 bullets>

## Test plan
<how it was verified>

Fixes #<issue-number>
EOF
)"
```

`Fixes #N` is mandatory so the issue auto-closes on merge.

## 5. Report

Finish with: issue picked, branch name, PR URL, and anything intentionally left out of scope.
