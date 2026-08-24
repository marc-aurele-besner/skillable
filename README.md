<div align="center">

# ⚡ Skillable

**Teach your AI agent the workflows you're tired of repeating.**

A curated, community-driven collection of [Agent Skills](https://cursor.com/docs/context/skills) — plain-markdown playbooks that turn "explain it to the agent again" into a single slash command.

[![Skills](https://img.shields.io/badge/skills-10-blueviolet)](#-skill-catalog)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Made for Cursor](https://img.shields.io/badge/made%20for-Cursor-black)](https://cursor.com)

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

**Install every skill globally** (available in all your projects):

```bash
git clone https://github.com/marc-aurele-besner/skillable.git
cp -r skillable/skills/* ~/.cursor/skills/
```

Restart Cursor or start a new agent session — skills are picked up automatically from their `description` field, or invoked directly as `/skill-name`.

**Or share one skill with your team** by dropping it into a project:

```bash
cp -r skillable/skills/<skill-name> .cursor/skills/
```

> **Tip:** the `SKILL.md` format is plain markdown + frontmatter, so these skills also work with other agents that read skill folders (e.g. Claude Code via `~/.claude/skills/`).

## 📚 Skill catalog

### 🤖 Dependency autopilot

| Skill | What it does |
|-------|--------------|
| [sweep-all-dependency-prs](skills/sweep-all-dependency-prs/) | Fan out across **every repo you own** (orgs included) and sweep their bot PRs in parallel |
| [sweep-dependency-prs](skills/sweep-dependency-prs/) | Approve & merge every green Dependabot/Renovate PR in a repo; dispatch fixes for the red ones |
| [fix-renovate-pr](skills/fix-renovate-pr/) | Take over a Renovate bump PR and push commits until CI passes |
| [fix-dependabot-pr](skills/fix-dependabot-pr/) | Same, for Dependabot PRs — including grouped updates and major-version migrations |
| [fix-dependabot-alert](skills/fix-dependabot-alert/) | Remediate a Dependabot **security alert** end-to-end: bump/override, branch, PR |
| [dedupe-and-prune-deps](skills/dedupe-and-prune-deps/) | Collapse duplicate versions, declare phantom imports, remove unused dependencies |

### 🚑 CI & issues

| Skill | What it does |
|-------|--------------|
| [fix-failing-ci](skills/fix-failing-ci/) | Paste a red Actions run URL; get diagnosis, a fix on the built branch, and a green build |
| [fix-issue](skills/fix-issue/) | Pick an open GitHub issue, implement it on a fresh branch, open the PR |

### 🛠 Upgrades & building

| Skill | What it does |
|-------|--------------|
| [upgrade-node-version](skills/upgrade-node-version/) | Bump Node across `.nvmrc`, `engines`, CI workflows, and Dockerfiles — then fix the fallout |
| [build-landing-page](skills/build-landing-page/) | Idea → scaffolded, designed, analytics-wired, **deployed** landing page with a live URL |

Want to write your own? Start from [`skills/_template/SKILL.md`](skills/_template/SKILL.md).

## 🔍 Anatomy of a skill

```text
skills/<skill-name>/
├── SKILL.md         # Required — frontmatter (name, description, triggers) + instructions
├── reference.md     # Optional — detailed docs the agent loads on demand
├── examples.md      # Optional — usage examples
└── scripts/         # Optional — helper scripts
```

A good skill has four traits:

- **One specific purpose** — a clear workflow, not a catch-all prompt dump
- **A trigger-rich description** — tells the agent *when* to reach for it, unprompted
- **A concise body** — assume the agent is smart; only add what it wouldn't know
- **Progressive disclosure** — keep `SKILL.md` under 500 lines; push depth into reference files

## 🤝 Contributing

Got a workflow you've explained to an agent more than twice? That's a skill waiting to be written. Read [CONTRIBUTING.md](CONTRIBUTING.md) for naming conventions, review criteria, and the submission process — then open a PR.

## ⭐ Support the project

If a skill here just merged a week's worth of bot PRs while you drank your coffee, **star the repo** — it's how other people find it, and it keeps new skills coming.

## 📄 License

MIT — see [LICENSE](LICENSE).
