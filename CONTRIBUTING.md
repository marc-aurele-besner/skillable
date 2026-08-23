# Contributing to Skillable

Thank you for helping grow this collection of agent skills.

## Adding a new skill

1. Copy `skills/_template/` to `skills/<your-skill-name>/`.
2. Edit `SKILL.md`:
   - Set a unique `name` (lowercase, hyphens, max 64 chars)
   - Write a specific third-person `description` that includes both **what** the skill does and **when** the agent should use it
   - Replace the template body with your instructions
3. Add optional supporting files (`reference.md`, `examples.md`, `scripts/`) only if they add real value.
4. Open a pull request with:
   - A short summary of the skill's purpose
   - Example trigger phrases a user might say
   - Any external dependencies (CLI tools, APIs, etc.)

## Skill quality checklist

Before submitting, verify:

- [ ] `name` is lowercase with hyphens only
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
