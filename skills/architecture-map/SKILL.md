---
name: architecture-map
description: >-
  Map a codebase into an interactive architecture explainer, split the repo
  into modules, explore each one with parallel read-only subagents, then
  synthesize a published page with a system context diagram, a module
  dependency graph derived from real imports, sequence diagrams for the key
  request and data flows, the data model, a guided tour of the most important
  files with permalinks to exact lines, and a hotspot and risk map from git
  history. Diagrams are inline SVG that work in light and dark themes. Use
  whenever the user wants to understand, document, onboard onto, or explain an
  unfamiliar codebase, see how a system fits together, prepare for a large
  refactor, or produce an architecture overview for a team. Also triggers on
  /architecture-map with an optional focus area.
argument-hint: "[focus=<area|flow|refactor:<path>>]"
---

# Architecture Map

Goal: give someone who has never seen this repo an accurate mental model in fifteen minutes, what the pieces are, how a request travels through them, where the data lives, which files matter, and where the dragons are. Every claim is grounded in a file and line they can open.

## When to use

- "Explain this codebase" / "how does this all fit together?"
- Onboarding a new teammate, or returning to a repo after months away
- "Before we refactor X, show me everything it touches"
- "Make an architecture overview we can share with the team"
- `/architecture-map [focus=<area>]`: e.g. `focus=auth`, `focus=checkout flow`, `focus=refactor:src/billing`
- Not for answering one narrow question about a file (just read it).

## 1. Survey the repo

Quickly establish the frame before splitting the work:

- Languages, frameworks, package manager, monorepo layout (`workspaces`, `packages/`, `apps/`, `go.work`, Cargo workspace).
- Entry points: servers, CLIs, workers, cron jobs, serverless handlers, front-end routes, mobile app roots.
- External systems: databases, queues, caches, third-party APIs, auth providers (from config, env var names in `.env.example`, IaC, `docker-compose`).
- Deploy shape: Dockerfiles, IaC (Terraform, Pulumi, CDK), CI deploy jobs.
- Size: files and lines per top-level directory (`git ls-files | …`) to decide how to split.

Then pick **4–8 modules** of comparable weight that follow the repo's real boundaries (packages, bounded contexts, layers). With a focus, give the focus area finer modules and summarize the rest coarsely.

## 2. Explore modules in parallel

**Claude Code:** launch one read-only exploring subagent per module **in a single message** so they run concurrently. Other agents: explore the modules one after another. Each brief is self-contained (repo summary from step 1, the module's paths, the focus if any) and asks for this structured result, conclusions with `path:line` citations, not file dumps:

```text
module, paths, one-sentence purpose
public surface: exported functions/classes, routes, events, CLI commands (path:line)
depends on: other modules and external systems, and how (import, HTTP, queue, DB)
data: entities/tables/schemas owned or read (path:line)
key flows that pass through it, step by step (path:line per step)
the 3–5 files a newcomer must read first, and why
smells and risks: cycles, god files, dead code, missing tests, TODO/FIXME clusters
open questions the code alone could not answer
```

## 3. Verify and enrich centrally

Subagents summarize; the orchestrator checks:

- **Dependency graph from real imports**, not prose. Use the stack's tooling when present (`madge --json`, `depcruise`, `go list -deps`, `cargo metadata`, `pydeps`) or a targeted `rg` over import statements, aggregated to module level. Flag cycles.
- **Hotspots from git history**: change frequency × size highlights where complexity and risk concentrate:

```bash
git log --since=12.months --name-only --pretty=format: | rg -v '^$' | sort | uniq -c | sort -rn | head -30
```

  Combine with file line counts and test presence; also note bus factor (`git shortlog -sn -- <path>`) for the top hotspots.
- **Spot-check citations**: open a sample of cited lines from every module and fix any that do not say what the summary claims.

## 4. Synthesize the explainer

One self-contained page. Diagram rules and SVG patterns are in [references/diagram-patterns.md](references/diagram-patterns.md). Sections, in reading order:

1. **TL;DR**, what the system does, in three sentences, and the stack in one line.
2. **System context**, the system, its users, and the external systems it talks to.
3. **Module map**, the module dependency graph (cycles in a warning color), each node clickable to its module card.
4. **Key flows**, 2–4 sequence diagrams for the flows that matter most (a typical request, a write path, a background job, auth). Each step links to its code.
5. **Data model**, the core entities and relationships, and which module owns each.
6. **Module cards**, purpose, public surface, dependencies, "read these first" files, risks.
7. **Guided tour**, an ordered walk through 8–12 files ("start here, then…") with why each matters.
8. **Hotspots and risks**, the churn × size table, cycles, untested critical paths, single-owner areas.
9. **Glossary**, domain terms as the code names them.
10. **Open questions**, what the code could not answer, for the team to fill in.

**Links:** when the repo has a GitHub remote, link citations as permalinks pinned to the current commit (`https://github.com/<owner>/<repo>/blob/<sha>/<path>#L<start>-L<end>`) so they survive later changes; otherwise show `path:line` as text. Never inline large code blocks, short excerpts (≤ 10 lines) only where a snippet explains a flow.

The page works in light and dark themes, at phone width, with a sticky section nav. No network calls beyond pinned CDN libraries and fonts; no secrets or `.env` values.

## 5. Publish

- **Artifact-capable agent:** publish as an artifact titled `<Repo> Architecture` (or `<Repo> · <Focus>` with a focus). Republish in place on later runs.
- **Otherwise:** write `architecture-<repo>.html` outside the tracked tree and open it locally.
- Do not commit the page to the repo unless the user asks; if they do, offer `docs/architecture.html` or a Markdown version with Mermaid diagrams.

## 6. Report

```markdown
**<Repo> architecture** · <N> modules · <F> flows · pinned to <short-sha> · <link>

**In one line:** <what it is>
**Read first:** <3 files>
**Biggest risks:** <2–3 bullets with paths>
**Open questions:** <count>: listed at the end of the page
```

## 7. Iterate

- "Zoom into X" → a focused re-run on that area, republished as its own section or page.
- "This is wrong about Y" → fix the claim, re-verify its citation, republish in place.
- Before a refactor, offer a **blast-radius** view: every module, flow, and test that depends on the target path.

## Quality bar before reporting

- [ ] Every module, edge, and flow step cites real code; a sample of citations was opened and checked
- [ ] The dependency graph comes from actual imports, with cycles marked
- [ ] Diagrams are legible in both themes and at phone width
- [ ] Hotspots come from git history, not guesses
- [ ] No secrets, credentials, or `.env` values on the page
