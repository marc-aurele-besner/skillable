# Templates for repo hygiene artifacts

Adaptable skeletons for the artifacts this skill creates. Every `<...>` placeholder must be replaced with a fact read from the repository or supplied by the owner. A template that reaches a branch with placeholders still in it is a defect, not a draft.

## The placeholder list

Fill these from the repo before writing anything. If a value is not in the repo and the file needs it, ask the owner — do not guess.

| Placeholder | Where it comes from |
|-------------|--------------------|
| `<PROJECT_NAME>` | `package.json` `name`, `pyproject.toml` `name`, `Cargo.toml` `name`, or the repo name |
| `<PROJECT_DESCRIPTION>` | the repo's own one-line description, `gh repo view --json description` |
| `<REPO_URL>` | `gh repo view --json url`, or the `repository` field in the manifest |
| `<ORG>` / `<OWNER>` | the repo owner in the remote URL or `gh repo view --json owner` |
| `<PACKAGE_MANAGER>` | the lockfile: `pnpm-lock.yaml` → pnpm, `package-lock.json` → npm, `yarn.lock` → yarn, `bun.lock` → bun, `uv.lock`/`poetry.lock` → uv/poetry, `Cargo.lock` → cargo |
| `<INSTALL_CMD>` | the lockfile's install command (`pnpm install`, `npm ci`, `bun install`, `uv sync`, `poetry install`) |
| `<DEV_CMD>` | the dev/watch script in the manifest, if any |
| `<BUILD_CMD>` | the build script or command in the manifest |
| `<TEST_CMD>` | the test script or command in the manifest |
| `<TEST_SINGLE_CMD>` | how to run one test, from the manifest and the test framework's own CLI |
| `<LINT_CMD>` | the lint script or command in the manifest |
| `<FORMAT_CMD>` | the format script or command, if the project has one |
| `<TYPECHECK_CMD>` | the typecheck script, if the project has one |
| `<RELEASE_CMD>` | the release script or workflow, if the project publishes |
| `<SOURCE_DIR>` | where the source lives (`src/`, `lib/`, `app/`, `packages/`, `cmd/`) |
| `<TEST_DIR>` | where tests live, and the test file naming convention |
| `<MAIN_BRANCH>` | `git symbolic-ref refs/remotes/origin/HEAD`, usually `main` or `master` |
| `<STYLE_RULES>` | the formatter and linter configured in the repo, and their settings files |
| `<DEPLOY_TARGET>` | `vercel.json`, `netlify.toml`, `Dockerfile`, `fly.toml`, `app.yaml`, the deploy job in CI |
| `<SUPPORT_CHANNEL>` | the real channel the maintainer watches: a security-advisories URL, a support inbox, a discussion board, a tracker |
| `<SECURITY_EMAIL>` | **ask the owner.** never derive it from git history, a commit author, or a domain guess |
| `<CODEOWNER_TEAM>` | the team or person that owns the hot paths; ask when unsure |
| `<SUPPORTED_VERSIONS>` | the release lines the project still patches |
| `<RESPONSE_TIMELINE>` | what the owner commits to, e.g. "acknowledged within 3 business days" |
| `<TONE>` | the existing voice of the README and docs — plain, formal, friendly; match it |

Never write `<SECURITY_EMAIL>`, `<SUPPORT_CHANNEL>`, `<CODEOWNER_TEAM>`, or `<RESPONSE_TIMELINE>` without the owner's answer. Ask once, in a single batch, and wait.

## LICENSE

Do not template a license. A license is a legal document, and the owner chose theirs. Only:

- detect the existing one (`scripts/audit_repo_hygiene.py` does this) and report a mismatch with the manifest,
- or ask the owner which license to use, then fetch the canonical text from the SPDX license list rather than writing it from memory.

## CONTRIBUTING.md

````markdown
# Contributing to <PROJECT_NAME>

Thanks for your interest in <PROJECT_NAME>. This document covers how to set up
the project, run it, and get a change merged.

## Prerequisites

- <RUNTIME> (<VERSION_FROM_MANIFEST>)
- <PACKAGE_MANAGER>

## Setup

```bash
<INSTALL_CMD>
```

## Run the project locally

```bash
<DEV_CMD>
```

## Build

```bash
<BUILD_CMD>
```

## Test

```bash
<TEST_CMD>
```

To run a single test:

```bash
<TEST_SINGLE_CMD>
```

## Lint and format

```bash
<LINT_CMD>
<FORMAT_CMD>
```

<Typecheck section only if the project has a typecheck command.>

## Code style

- <STYLE_RULES>
- Keep pull requests focused on one change.
- <PROJECT_SPECIFIC_CONVENTIONS>

## Project layout

```text
<SOURCE_DIR>/   <WHAT_LIVES_HERE>
<TEST_DIR>/     <WHAT_LIVES_HERE>
```

## Pull requests

1. Branch from `<MAIN_BRANCH>`: `git checkout -b feat/short-description origin/<MAIN_BRANCH>`.
2. Make the change, add or update tests.
3. Run `<TEST_CMD>` and `<LINT_CMD>` locally.
4. Open a pull request and describe what changed and why.

## Reporting bugs

Open an issue with the <ISSUE_TEMPLATE_PATH> template. Include the version, the
steps to reproduce, and what you expected to happen.

## Security issues

Do not open a public issue for a security problem. Follow <SECURITY_FILE>.

## License

By contributing, you agree that your contributions are licensed under the
license in [LICENSE](LICENSE).
````

Keep it short. A 40-line CONTRIBUTING that a newcomer can follow beats a 200-line one they skim.

## CODE_OF_CONDUCT.md

**Propose it, then get the owner's OK.** A code of conduct implies commitments about enforcement and often names a committee. Write it only after the user confirms they want one and agrees with the enforcement route. Never invent an enforcement email or a committee.

```markdown
# Code of Conduct

## Our pledge

We as members, contributors, and maintainers pledge to make participation in
our community a harassment-free experience for everyone, regardless of age,
body size, visible or invisible disability, ethnicity, sex characteristics,
gender identity and expression, level of experience, education, socio-economic
status, nationality, personal appearance, race, religion, or sexual identity
and orientation.

## Our standards

Examples of behavior that contributes to a positive environment:

- Demonstrating empathy and kindness toward other people
- Being respectful of differing opinions, viewpoints, and experiences
- Giving and gracefully accepting constructive feedback

Examples of unacceptable behavior:

- The use of sexualized language or imagery, and sexual attention or advances
- Trolling, insulting or derogatory comments, and personal or political attacks
- Public or private harassment
- Publishing others' private information without their explicit permission

## Enforcement responsibilities

Maintainers are responsible for clarifying and enforcing these standards and
will take appropriate and fair corrective action in response to any behavior
they deem inappropriate, threatening, offensive, or harmful.

## Scope

This Code of Conduct applies within all community spaces, and also applies when
an individual is officially representing the community in public spaces.

## Enforcement

Instances of abusive, harassing, or otherwise unacceptable behavior may be
reported to <ENFORCEMENT_CONTACT> (ask the owner for the real route). All
complaints will be reviewed and investigated promptly and fairly.

All community leaders are obligated to respect the privacy and security of the
reporter of any incident.

## Attribution

This Code of Conduct is adapted from the [Contributor Covenant](https://www.contributor-covenant.org),
version 2.1, available at
<https://www.contributor-covenant.org/version/2/1/code_of_conduct.html>.
```

## SECURITY.md

The contact route is the whole point. Ask for it; never fabricate an address and never publish one found in git history.

```markdown
# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| <SUPPORTED_VERSIONS> |

## Reporting a vulnerability

Please report suspected vulnerabilities privately — do not open a public issue.

- Email: <SECURITY_EMAIL>
- Or use GitHub's private advisory form: <REPO_URL>/security/advisories/new

Include the affected version, a description of the issue, and steps to reproduce
if you have them. You can expect an acknowledgement within <RESPONSE_TIMELINE>.

## What to expect

1. Acknowledgement that the report was received.
2. An assessment of the impact and severity.
3. A fix, or a mitigation plan, for confirmed issues.
4. Credit in the release notes unless you prefer to stay anonymous.

## Disclosure

We ask that you give us <DISCLOSURE_WINDOW> to ship a fix before disclosing
the issue publicly.
```

Keep the supported-versions table real: list the versions that actually get
patched, not "latest only" unless that is true.

## Pull request template

`.github/pull_request_template.md`:

```markdown
## Summary

<!-- What changed, in one or two sentences. -->

## Related issue

<!-- Closes #123. Write "none" if there is no issue. -->

## Changes

-
-

## Testing

- [ ] Ran `<TEST_CMD>` locally
- [ ] Added or updated tests
- [ ] Ran `<LINT_CMD>` locally

## Checklist

- [ ] No secrets, credentials, or `.env` values in the diff
- [ ] Documentation updated if behavior changed
```

If the project prefers YAML frontmatter, GitHub also accepts it:

```yaml
---
name: Pull request
description: Describe the change and how it was tested
title: "[type]: "
body: |
  ## Summary

  ## Testing
labels: []
---
```

## Issue templates

`.github/ISSUE_TEMPLATE/bug_report.yml`:

```yaml
name: Bug report
description: Report something that does not work as documented
title: "[Bug]: "
labels: ["bug"]
body:
  - type: textarea
    id: description
    attributes:
      label: What happened
      description: What you did, what you expected, and what happened instead.
    validations:
      required: true
  - type: textarea
    id: reproduction
    attributes:
      label: Steps to reproduce
      placeholder: |
        1.
        2.
        3.
    validations:
      required: true
  - type: input
    id: version
    attributes:
      label: Version
      placeholder: <PROJECT_VERSION>
    validations:
      required: true
  - type: textarea
    id: environment
    attributes:
      label: Environment
      description: Operating system, runtime version, browser, and anything else that matters.
    validations:
      required: false
```

`.github/ISSUE_TEMPLATE/feature_request.yml`:

```yaml
name: Feature request
description: Suggest an idea or improvement
title: "[Feat]: "
labels: ["enhancement"]
body:
  - type: textarea
    id: problem
    attributes:
      label: What problem would this solve?
      description: Describe the problem, not the solution.
    validations:
      required: true
  - type: textarea
    id: proposal
    attributes:
      label: Proposed solution
    validations:
      required: false
  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives considered
    validations:
      required: false
```

`.github/ISSUE_TEMPLATE/config.yml` — the chooser. Keep it minimal unless the project wants to route issues to specific trackers:

```yaml
blank_issues_enabled: true
contact_links:
  - name: <SUPPORT_CHANNEL_NAME>
    url: <SUPPORT_CHANNEL_URL>
    about: <WHAT_THIS_CHANNEL_IS_FOR>
```

Required fields on an issue form are `name`, `description`, and `body`. A form
missing any of them does not render on GitHub.

## AGENTS.md / CLAUDE.md

This is the highest-leverage file: every later agent session on the repo gets faster because of it. Keep it factual, short, and specific to the repo. The same content works in `AGENTS.md` and `CLAUDE.md`; write `AGENTS.md` (the cross-tool convention) and add a one-line pointer from `CLAUDE.md` if both are in use.

````markdown
# <PROJECT_NAME> — agent guide

## Commands

| Task | Command |
|------|---------|
| Install | `<INSTALL_CMD>` |
| Build | `<BUILD_CMD>` |
| Test | `<TEST_CMD>` |
| Test one file | `<TEST_SINGLE_CMD>` |
| Lint | `<LINT_CMD>` |
| Format | `<FORMAT_CMD>` |
| Typecheck | `<TYPECHECK_CMD>` |

## Layout

```text
<SOURCE_DIR>/   <WHAT_LIVES_HERE>
<TEST_DIR>/     <WHAT_LIVES_HERE>
<OTHER_DIR>/    <WHAT_LIVES_HERE>
```

## Conventions

- <STYLE_RULES>
- <NAMING_CONVENTIONS>
- <ERROR_HANDLING_CONVENTIONS>
- <TESTING_CONVENTIONS>

## Working in this repo

- Branch from `<MAIN_BRANCH>`: `git checkout -b feat/short-description origin/<MAIN_BRANCH>`.
- Keep changes scoped to one concern; do not reformat files you only touched one line of.
- Run `<TEST_CMD>` and `<LINT_CMD>` before opening a pull request.
- Pull requests describe what changed and why, and link the issue they close.

## Things that will bite you

- <GOTCHA_1>
- <GOTCHA_2>
````

The "Things that will bite you" section is where an agent saves the most time:
a required env var, a generated file that must not be edited by hand, a test
that needs a service running, a directory with a non-obvious convention.

## .editorconfig

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = <INDENT>

[*.{md,mdx}]
trim_trailing_whitespace = false

[*.{yml,yaml,json}]
indent_size = 2
```

Read the real indentation from the project's formatter config instead of
guessing. If the repo uses tabs, use tabs.

## .gitignore

Extend what the project already has; never replace it. The parts that matter:

```gitignore
# Dependencies
node_modules/
<PYTHON_VENV>

# Build output
dist/
build/
<FRAMEWORK_OUTPUT>

# Environment
.env
.env.local
.env.*.local

# Logs
*.log
npm-debug.log*
<python_log_dir>

# Editor and OS
.DS_Store
.idea/
.vscode/
```

Keep `.env.example` (or `.env.sample`) tracked — it is the documented shape of
the env vars with no values in it.

## .github/FUNDING.yml

Only when the project actually accepts funding:

```yaml
github: <OWNER>
open_collective: <PROJECT_SLUG>
patreon: <CREATOR>
ko_fi: <CREATOR>
```

## Dependency automation

`.github/dependabot.yml` — only if the repo does not already use Renovate:

```yaml
version: 2
updates:
  - package-ecosystem: "<ECOSYSTEM>"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
```

Use the ecosystems that actually apply to the repo, and the directory that
actually holds the manifest. If Renovate is already configured, leave it alone.

## Issue labels and `good first issue`

Labels live in GitHub settings, not in a file, unless the project keeps a
`.github/labels.yml`. Read the current set with `gh label list`, and seed only
what the project will actually maintain:

```bash
gh label create "good first issue" --description "Small, self-contained task" --color "7057ff"
gh label create "help wanted" --description "Open to new contributors" --color "008672"
gh label create "bug" --description "Something does not work" --color "d73a4a"
gh label create "enhancement" --description "New feature or request" --color "a2eeef"
gh label create "documentation" --description "Docs need work" --color "0075ca"
```

Creating labels changes the repo's public surface. Show the user the list and
let them approve before running it, and only create the ones the project
already uses or clearly needs.

## docs/

Only create a `docs/` tree when the project has enough surface to justify it
(more than a handful of commands, an architecture worth describing, or
runbooks). Do not move existing content into it as part of a hygiene PR — that
is a refactor, not hygiene, and it breaks links.
