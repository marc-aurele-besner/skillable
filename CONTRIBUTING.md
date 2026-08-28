# Contributing to Skillable

Thank you for helping grow this collection of agent skills.

## Adding a new skill

1. Copy `templates/skill/` to `skills/<your-skill-name>/`. The template lives outside `skills/` so `npx skills add` does not install the placeholder.
2. Edit `SKILL.md`:
   - Set a unique `name` (lowercase, hyphens, max 64 chars) that matches the directory name
   - Write a specific third-person `description` that includes both **what** the skill does and **when** the agent should use it
   - Replace the template body with your instructions
3. Add optional supporting files (`scripts/`, `references/`, `assets/`) only if they add real value.
4. Add a row to the **Available skills** table in `README.md` (alphabetical):
   `| [<your-skill-name>](skills/<your-skill-name>/) | Short description |`
5. Open a pull request with:
   - A short summary of the skill's purpose
   - Example trigger phrases a user might say
   - Any external dependencies (CLI tools, APIs, etc.)

CI runs on pull requests that add or change skills. It fails if the new skill is missing from the README table, or if `SKILL.md` does not follow the structure and formatting rules below. Run the same checks locally:

```bash
python3 scripts/validate_skills.py
```

To try a skill the way users will install it:

```bash
npx skills add ./skills/<your-skill-name>
```

## Skill quality checklist

Before submitting, verify:

- [ ] Skill is listed in the README **Available skills** table
- [ ] `name` is lowercase with hyphens only and matches the directory
- [ ] `description` is under 1024 characters and written in third person
- [ ] `SKILL.md` is under 500 lines
- [ ] Instructions are actionable — steps, not essays
- [ ] No secrets, API keys, or environment-specific paths hardcoded
- [ ] Scripts (if any) are documented and safe to run
- [ ] Terminology is consistent throughout the skill

## Naming conventions

| Good | Avoid |
|------|-------|
| `reviewing-pull-requests` | `helper`, `utils`, `tools` |
| `generating-commit-messages` | `my-skill-v2` |
| `deploying-to-vercel` | `PR_Review_Skill` |

## Updating an existing skill

- Keep changes focused on the skill you're editing
- Prefer improving clarity over adding length
- Note breaking changes in the PR description

## Code of conduct

Be respectful and constructive in issues and pull requests. Skills should be safe, useful, and free of harmful instructions.
