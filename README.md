<div align="center">

# ⚡ Skillable

**Teach your AI agent the workflows you're tired of repeating.**

A curated, community-driven collection of [Agent Skills](https://agentskills.io) — plain-markdown playbooks that turn "explain it to the agent again" into a single slash command. Built on the open `SKILL.md` format, so they work with Cursor, Claude Code, and [any skills-capable agent](https://agentskills.io/clients).

[![Skills](https://img.shields.io/badge/skills-16-blueviolet)](#available-skills)
[![skills.sh](https://img.shields.io/badge/skills.sh-install-black.svg)](https://skills.sh)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Format: Agent Skills](https://img.shields.io/badge/format-open%20Agent%20Skills-black)](https://agentskills.io)

</div>

---

Your agent is smart. It just doesn't know *your* routines: how you triage Dependabot PRs, what "fix CI" actually means in your world, which steps a Node upgrade always forgets. Skills fix that. Each one is a self-contained folder of markdown instructions the agent discovers automatically — no prompt copy-pasting, no re-explaining, no drift between sessions.

## ☕ The morning routine, automated

The flagship demo — skills that call other skills. One command sweeps your entire GitHub account:

```text
you:    /sweep-all-dependency-prs

agent:  Listing every repo you own (and your orgs') …
        ├── repo-a → 3 bot PRs → /sweep-dependency-prs
        │     ├── #41 CI green ✅ → approved & merged
        │     ├── #42 CI green ✅ → approved & merged
        │     └── #43 CI red ❌ → /fix-renovate-pr → pushed fix → green → merged
        ├── repo-b → 1 bot PR → merged ✅
        └── report: 12 PRs merged, 2 fixed, 1 needs you
```

`sweep-all` fans out to `sweep`, which delegates red builds to `fix-renovate-pr` / `fix-dependabot-pr`. Composable playbooks, not one mega-prompt.

## 🚀 Quick start

Install with the [skills CLI](https://vercel.com/docs/agent-resources/skills). It detects which agents you have (Cursor, Claude Code, GitHub Copilot, Cline, and [18+ others](https://agentskills.io/clients)) and puts the skills where they look.

**Every skill, on every project on this machine:**

```bash
npx skills add -g marc-aurele-besner/skillable
```

**This project only** (committed with the repo, shared with your team):

```bash
npx skills add marc-aurele-besner/skillable
```

**One skill:**

```bash
npx skills add marc-aurele-besner/skillable --skill sweep-dependency-prs
```

Useful extras:

```bash
npx skills add marc-aurele-besner/skillable --list   # preview without installing
npx skills find skillable                            # search the public directory
```

Start a **new agent session** after installing. Skills load from their `description` when the task matches, or you can invoke one directly as `/skill-name`.

<details>
<summary>Manual install (clone and copy)</summary>

If you can't run the CLI, copy skill folders into your agent's skills directory:

```bash
git clone https://github.com/marc-aurele-besner/skillable.git
cp -r skillable/skills/* ~/.cursor/skills/   # Cursor
cp -r skillable/skills/* ~/.claude/skills/   # Claude Code
```

Share one skill with your team by dropping it into the project:

```bash
cp -r skillable/skills/<skill-name> .cursor/skills/   # or .claude/skills/, etc.
```

Using a different agent? Same idea — see the [client list](https://agentskills.io/clients) for its skills path.

</details>

## Available skills

Legend: 🤖 dependency autopilot · 🚑 CI & issues · 🛠 upgrades & building

| Skill | What it does |
|-------|--------------|
| [align-minimum-release-age](skills/align-minimum-release-age/) | 🤖 Sync the dependency cooldown between pnpm/npm/Poetry and Renovate to the most conservative value — one repo or your whole fleet |
| [build-landing-page](skills/build-landing-page/) | 🛠 Idea → scaffolded, designed, analytics-wired, **deployed** landing page with a live URL |
| [dedupe-and-prune-deps](skills/dedupe-and-prune-deps/) | 🤖 Collapse duplicate versions, declare phantom imports, remove unused dependencies |
| [fix-dependabot-alert](skills/fix-dependabot-alert/) | 🤖 Remediate a Dependabot **security alert** end-to-end: bump/override, branch, PR |
| [fix-dependabot-pr](skills/fix-dependabot-pr/) | 🤖 Take over a Dependabot bump PR — grouped updates and major migrations included — and push commits until CI passes |
| [fix-failing-ci](skills/fix-failing-ci/) | 🚑 Paste a red Actions run URL; get diagnosis, a fix on the built branch, and a green build |
| [fix-issue](skills/fix-issue/) | 🚑 Pick an open GitHub issue, implement it on a fresh branch, open the PR |
| [fix-renovate-pr](skills/fix-renovate-pr/) | 🤖 Take over a Renovate bump PR and push commits until CI passes |
| [optimize-all-github-actions](skills/optimize-all-github-actions/) | 🚑 Find every repo you own with Actions (orgs included) and fan out optimize-github-actions — one PR per repo |
| [optimize-github-actions](skills/optimize-github-actions/) | 🚑 Analyze workflows, cut wasted Actions minutes (duplicate runs, redundant jobs, matrix bloat), open a PR — without weakening security |
| [prune-deps-across-org](skills/prune-deps-across-org/) | 🤖 Find every JS repo you own (orgs included) and fan out dedupe-and-prune-deps — one hygiene PR per repo |
| [sweep-all-dependabot-alerts](skills/sweep-all-dependabot-alerts/) | 🤖 Find open Dependabot **security alerts** across every repo you own (orgs included) and fan out fix-dependabot-alert |
| [sweep-all-dependency-prs](skills/sweep-all-dependency-prs/) | 🤖 Fan out across **every repo you own** (orgs included) and sweep their bot PRs in parallel |
| [sweep-dependency-prs](skills/sweep-dependency-prs/) | 🤖 Approve & merge every green Dependabot/Renovate PR in a repo; dispatch fixes for the red ones |
| [upgrade-node-across-org](skills/upgrade-node-across-org/) | 🛠 Find every repo you own that pins Node (orgs included) and fan out upgrade-node-version — one PR per repo |
| [upgrade-node-version](skills/upgrade-node-version/) | 🛠 Bump Node across `.nvmrc`, `engines`, CI workflows, and Dockerfiles — then fix the fallout |

## 🔍 Anatomy of a skill

```text
skills/<skill-name>/
├── SKILL.md          # Required — frontmatter (name, description) + instructions
├── scripts/          # Optional — helper scripts the agent can run
├── references/       # Optional — longer docs loaded on demand
└── assets/           # Optional — templates and other static files
```

A good skill has four traits:

- **One specific purpose** — a clear workflow, not a catch-all prompt dump
- **A trigger-rich description** — tells the agent *when* to reach for it, unprompted
- **A concise body** — assume the agent is smart; only add what it wouldn't know
- **Progressive disclosure** — keep `SKILL.md` under 500 lines; push depth into `references/`

Authoring a new one? Copy [`templates/skill/`](templates/skill/) into `skills/<your-skill-name>/` — it lives outside `skills/` so the CLI does not install the placeholder.

## 🤝 Contributing

Got a workflow you've explained to an agent more than twice? That's a skill waiting to be written. Read [CONTRIBUTING.md](CONTRIBUTING.md) for naming conventions, review criteria, and the submission process — then open a PR.

## ⭐ Support the project

If a skill here just merged a week's worth of bot PRs while you drank your coffee, **star the repo** — it's how other people find it, and it keeps new skills coming.

## 📄 License

MIT — see [LICENSE](LICENSE).
