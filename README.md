# Skillable

A curated, community-driven collection of [Cursor Agent Skills](https://cursor.com/docs/context/skills) — reusable instructions that teach AI agents how to perform specific tasks.

Skills are markdown files with structured metadata. They give agents domain knowledge, workflows, and conventions without repeating the same prompts in every conversation.

## Quick start

**Use a skill in Cursor**

1. Clone this repository (or copy individual skill folders).
2. Install skills into your personal skills directory:

```bash
git clone https://github.com/marc-aurele-besner/skillable.git
cp -r skillable/skills/* ~/.cursor/skills/
```

3. Restart Cursor or start a new agent session. The agent discovers skills automatically from their `description` field.

**Use a skill in a project**

Copy a skill into your project's `.cursor/skills/` directory to share it with collaborators:

```bash
cp -r skillable/skills/<skill-name> .cursor/skills/
```

## Repository structure

```
skillable/
├── skills/                  # All published skills
│   └── <skill-name>/
│       ├── SKILL.md         # Required — main instructions + metadata
│       ├── reference.md     # Optional — detailed docs
│       ├── examples.md      # Optional — usage examples
│       └── scripts/         # Optional — helper scripts
├── CONTRIBUTING.md          # How to add or improve skills
└── README.md
```

Each skill is a self-contained directory. See [`skills/_template/SKILL.md`](skills/_template/SKILL.md) to get started.

## Available skills

| Skill | Description |
|-------|-------------|
| [_template](skills/_template/) | Starter template for authoring new skills |

> Skills will be listed here as they are added. See [CONTRIBUTING.md](CONTRIBUTING.md) to submit one.

## What makes a good skill?

- **Specific purpose** — one clear workflow or domain, not a catch-all prompt dump
- **Trigger-rich description** — tells the agent *when* to use it (see the template)
- **Concise body** — assume the agent is smart; add only what it wouldn't know
- **Progressive disclosure** — keep `SKILL.md` under 500 lines; link to reference files for depth

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) for naming conventions, review criteria, and the submission process.

## License

MIT — see [LICENSE](LICENSE).
