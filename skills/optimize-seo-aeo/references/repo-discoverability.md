# Repo discoverability (libraries, CLIs, packages)

For a project without its own site, the pages that rank and get cited are the GitHub repo, the package registry page, and any docs host. Optimize those sources in the repo; list the GitHub settings as `gh` commands for the user to approve.

## Package metadata

| Ecosystem | Fields that show up in search and registry pages |
|-----------|-----------------------------------------------|
| npm (`package.json`) | `description` (one plain sentence), `keywords` (5–12 real search terms), `homepage`, `repository`, `bugs`, `license`, `author` |
| Python (`pyproject.toml`) | `description`, `readme`, `keywords`, `classifiers`, `[project.urls]` (Homepage, Documentation, Repository, Changelog) |
| Rust (`Cargo.toml`) | `description`, `keywords` (max 5), `categories`, `homepage`, `documentation`, `repository`, `readme` |
| Go | First sentence of the package doc comment (`// Package x …`) becomes the pkg.go.dev summary |
| Ruby (`.gemspec`) | `summary`, `description`, `homepage`, `metadata` URIs |

Keep the one-line description identical (or near) across package metadata, the GitHub "About" box, and the README's first line.

## README

- **First line after the title** says what it is and who it is for in plain words — this is what search snippets and assistants quote.
- **Install and minimal usage** in the first screen, as copy-pasteable code blocks.
- **Headings people search for:** Installation, Usage, Configuration, API, FAQ, Comparison/Alternatives, License.
- **Comparison section** ("X vs Y") only with true, checkable claims.
- Badges below the summary, not instead of it. Alt text on images and diagrams.
- Link to docs, changelog, and examples with descriptive anchor text.

## GitHub repo settings (ask before running)

```bash
gh repo view --json description,homepageUrl,repositoryTopics
gh repo edit --description "<one sentence>" --homepage "<docs or package URL>"
gh repo edit --add-topic <topic> --add-topic <topic>   # up to 20, lowercase, hyphenated
```

Also suggest: a social preview image (Settings → Social preview; design it with `wireframe-og-design`), a `CITATION.cff` for research software, and enabling GitHub Pages for docs if none exist.

## Docs and llms.txt

If the repo has a `docs/` folder or a docs site, run the website flow on it. Otherwise, a root `llms.txt` (see `aeo-playbook.md`) linking to the README, docs pages, and examples via their GitHub URLs is cheap and helps assistants that read it.
