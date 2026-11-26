<div align="center">

# ⚡ Skillable: Agent Skills for Claude Code, Cursor, Codex & GitHub Copilot

**Teach your AI coding agent the workflows you're tired of repeating.**

Skillable is a free, open-source library of **68 Agent Skills**: plain-markdown `SKILL.md` playbooks that let AI coding agents such as Claude Code, Cursor, GitHub Copilot, OpenAI Codex, and Cline merge dependency PRs, fix failing CI, ship GitHub issues, review code like a senior specialist, test your product through user personas, and prototype UI, each with one slash command.

[![Skills](https://img.shields.io/badge/skills-68-blueviolet)](#available-skills)
[![skills.sh](https://img.shields.io/badge/skills.sh-install-black.svg)](https://skills.sh)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Format: Agent Skills](https://img.shields.io/badge/format-open%20Agent%20Skills-black)](https://agentskills.io)

[Quick start](#-quick-start) · [What's inside](#-whats-inside) · [How to use](#-how-to-use-a-skill) · [All skills](#available-skills) · [FAQ](#-faq) · [Contributing](#-contributing)

</div>

---

```bash
npx skills add -g marc-aurele-besner/skillable
```

Your agent is smart. It just doesn't know *your* routines: how you triage Dependabot PRs, what "fix CI" actually means in your world, which steps a Node upgrade always forgets. Skills fix that. Each one is a self-contained folder of markdown instructions the agent discovers automatically. No prompt copy-pasting, no re-explaining, no drift between sessions.

## 🧩 What is Skillable?

- **What it is:** a curated collection of [Agent Skills](https://agentskills.io) for software developers, maintained on GitHub and installable with the [`skills` CLI](https://skills.sh).
- **Who it is for:** developers, maintainers, and small teams who use an AI coding agent and want it to run real, multi-step engineering workflows the same way every time.
- **What a skill is:** a folder with a `SKILL.md` file (YAML frontmatter with `name` and `description`, plus step-by-step instructions) and optional `scripts/`, `references/`, and `assets/`. The format is an open standard, so the same skill works in any [skills-capable agent](https://agentskills.io/clients).
- **How it works:** the agent keeps only each skill's short `description` in context. When your request matches one, or you type `/skill-name`, it loads the full playbook and follows it, running your tools (`git`, `gh`, your package manager, your test runner) in your repo.
- **What it costs:** nothing. MIT licensed, no account, no hosted service. Skills are text files your agent reads.

### Scope: what these skills do and don't

| ✅ In scope | 🚫 Out of scope |
|-------------|-----------------|
| Repeatable developer workflows across GitHub, CI, dependencies, testing, SEO, performance, security, and design | Generic prompt libraries or "act as" one-liners |
| Changes delivered as a branch and a pull request you review | Pushing straight to your default branch |
| Read-only reviews (`expert-*`, `persona-*`) that report findings with exact locations and fixes | Silently editing code during a review |
| Fleet skills that fan out across every repo you own, with guardrails (only green PRs from verified bots get merged; `nudge-stale-prs` is a dry run until you confirm) | Hosted services, background daemons, or anything that runs without your agent |
| Working with the stack the repo already uses (pnpm, npm, Bun, Poetry, Next.js, Astro, Foundry, …) | Forcing a new framework or toolchain on your project |

## ☕ The morning routine, automated

The flagship demo: skills that call other skills. One command sweeps your entire GitHub account:

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

Install with the [skills CLI](https://vercel.com/docs/agent-resources/skills). It detects which agents you have (Cursor, Claude Code, GitHub Copilot, Codex, Cline, and [many others](https://agentskills.io/clients)) and puts the skills where they look. You need Node.js for `npx`; skills that touch GitHub also expect an authenticated [GitHub CLI](https://cli.github.com/) (`gh auth login`).

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

**Keep them current, or remove them:**

```bash
npx skills add marc-aurele-besner/skillable --list   # preview without installing
npx skills update                                    # pull the latest versions
npx skills remove sweep-dependency-prs               # uninstall one skill
npx skills find skillable                            # search the public directory
```

Start a **new agent session** after installing so the agent picks the skills up.

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

Using a different agent? Same idea: see the [client list](https://agentskills.io/clients) for its skills path.

</details>

## 🎯 How to use a skill

There are two ways to run one, and both work in every supported agent:

1. **Just ask.** Describe the job in plain words; the agent matches it to a skill's description and loads it on its own.
2. **Call it by name.** Type `/skill-name`, optionally followed by arguments: a URL, a repo, a count, or a focus.

| You want to… | Say or type |
|--------------|-------------|
| Merge every green Dependabot/Renovate PR in a repo | `/sweep-dependency-prs owner/repo` |
| Fix a red GitHub Actions build | `/fix-failing-ci https://github.com/owner/repo/actions/runs/123` |
| Ship a GitHub issue as a pull request | `/fix-issue 42` |
| Get a senior security review of your web app | "Review this app for OWASP Top 10 issues" → `expert-appsec` |
| See your site through a first-time, non-technical user | `/persona-grandma https://example.com` |
| Improve how Google and ChatGPT/Perplexity see your site | "Improve the SEO and AEO of this site" → `optimize-seo-aeo` |
| Explore several UX directions before building a feature | `/wireframe-feature team invites with roles` |
| Understand an unfamiliar codebase | `/architecture-map` |

Skills that change code work on a new branch and open a pull request for you to review. Review skills (`expert-*`, `persona-*`) are read-only and end with a ranked list of findings. Each skill's `SKILL.md` states exactly what it will and won't touch, so read it before you point a fleet skill at every repo you own.

## 📦 What's inside

68 skills in seven families. Each links to its folder; the [full catalog](#available-skills) below has a one-line summary of every skill.

- **🤖 Dependency autopilot (10)**: merge, fix, and secure dependency updates: [sweep-dependency-prs](skills/sweep-dependency-prs/), [sweep-all-dependency-prs](skills/sweep-all-dependency-prs/), [fix-renovate-pr](skills/fix-renovate-pr/), [fix-dependabot-pr](skills/fix-dependabot-pr/), [fix-dependabot-alert](skills/fix-dependabot-alert/), [sweep-all-dependabot-alerts](skills/sweep-all-dependabot-alerts/), [audit-vulnerabilities](skills/audit-vulnerabilities/), [dedupe-and-prune-deps](skills/dedupe-and-prune-deps/), [prune-deps-across-org](skills/prune-deps-across-org/), [align-minimum-release-age](skills/align-minimum-release-age/).
- **🚑 CI, issues & pull requests (10)**: keep the pipeline green and nothing stale: [fix-failing-ci](skills/fix-failing-ci/), [fix-flaky-tests](skills/fix-flaky-tests/), [fix-issue](skills/fix-issue/), [fix-all-issues](skills/fix-all-issues/), [review-pull-request](skills/review-pull-request/), [claim-unassigned-prs](skills/claim-unassigned-prs/), [claim-all-unassigned-prs](skills/claim-all-unassigned-prs/), [nudge-stale-prs](skills/nudge-stale-prs/), [optimize-github-actions](skills/optimize-github-actions/), [optimize-all-github-actions](skills/optimize-all-github-actions/).
- **🛠 Upgrades & building (12)**: ship improvements as one PR each: [optimize-seo-aeo](skills/optimize-seo-aeo/), [setup-seo](skills/setup-seo/), [optimize-pwa](skills/optimize-pwa/), [optimize-images](skills/optimize-images/), [audit-web-vitals](skills/audit-web-vitals/), [add-i18n](skills/add-i18n/), [add-missing-tests](skills/add-missing-tests/), [prune-dead-code](skills/prune-dead-code/), [standardize-repo-hygiene](skills/standardize-repo-hygiene/), [upgrade-node-version](skills/upgrade-node-version/), [upgrade-node-across-org](skills/upgrade-node-across-org/), [build-landing-page](skills/build-landing-page/).
- **🎲 Ideation & prototyping (8)**: see ideas before you build them: [wireframe-feature](skills/wireframe-feature/), [wireframe-redesign](skills/wireframe-redesign/), [wireframe-logo-design](skills/wireframe-logo-design/), [wireframe-og-design](skills/wireframe-og-design/), [save-wireframe](skills/save-wireframe/), [extract-design-system](skills/extract-design-system/), [spike-variants](skills/spike-variants/), [drift](skills/drift/).
- **🧭 Visibility & understanding (4)**: map code, stacks, licenses, and repos: [architecture-map](skills/architecture-map/), [isometric-stack-map](skills/isometric-stack-map/), [fleet-health-dashboard](skills/fleet-health-dashboard/), [audit-licenses](skills/audit-licenses/).
- **🎓 Expert review (12)**: a read-only senior specialist on your code: [expert-appsec](skills/expert-appsec/), [expert-accessibility](skills/expert-accessibility/), [expert-backend](skills/expert-backend/), [expert-frontend-performance](skills/expert-frontend-performance/), [expert-ui](skills/expert-ui/), [expert-ux](skills/expert-ux/), [expert-dx](skills/expert-dx/), [expert-qa](skills/expert-qa/), [expert-smart-contract-security](skills/expert-smart-contract-security/), [expert-gas-optimization](skills/expert-gas-optimization/), [expert-tokenomics](skills/expert-tokenomics/), [expert-web3-dapp](skills/expert-web3-dapp/).
- **👥 Persona review (12)**: a real-feeling user walks your product and reports in their own voice: [persona-grandma](skills/persona-grandma/), [persona-gen-z](skills/persona-gen-z/), [persona-mobile-commuter](skills/persona-mobile-commuter/), [persona-power-user](skills/persona-power-user/), [persona-accessibility-user](skills/persona-accessibility-user/), [persona-developer](skills/persona-developer/), [persona-designer](skills/persona-designer/), [persona-growth-hacker](skills/persona-growth-hacker/), [persona-investor](skills/persona-investor/), [persona-security-skeptic](skills/persona-security-skeptic/), [persona-crypto-newcomer](skills/persona-crypto-newcomer/), [persona-web3-degen](skills/persona-web3-degen/).

## Available skills

Legend: 🤖 dependency autopilot · 🚑 CI & issues · 🛠 upgrades & building · 🎲 ideation & prototyping · 🧭 visibility & understanding · 🎓 expert review · 👥 persona review

| Skill | What it does |
|-------|--------------|
| [add-i18n](skills/add-i18n/) | 🛠 Internationalize a site in one PR: locale routing and catalogs, per-locale metadata, reciprocal hreflang with `x-default`, RTL layouts, and `Intl` formatting, using your framework's own i18n tooling |
| [add-missing-tests](skills/add-missing-tests/) | 🛠 Find the code that has no real test coverage, write behavior-level tests for it with the repo's own framework, and open one PR with the coverage delta |
| [align-minimum-release-age](skills/align-minimum-release-age/) | 🤖 Sync the dependency cooldown between pnpm/npm/Poetry and Renovate to the most conservative value, for one repo or your whole fleet |
| [architecture-map](skills/architecture-map/) | 🧭 Parallel subagents map your codebase into an interactive explainer: module graph from real imports, key-flow sequence diagrams, guided tour with line permalinks, hotspots from git history |
| [audit-licenses](skills/audit-licenses/) | 🧭 Inventory every dependency license (direct and transitive), check it against a committed policy, generate the NOTICE / THIRD_PARTY_LICENSES artifacts the obligations require, and fail CI on a forbidden license |
| [audit-vulnerabilities](skills/audit-vulnerabilities/) | 🤖 Audit the **whole** dependency tree for known vulnerabilities, judge real reachability in your code, fix what is fixable, and open one PR with the residual risk stated |
| [audit-web-vitals](skills/audit-web-vitals/) | 🛠 Measure Core Web Vitals with field and lab data, turn them into a CI budget that blocks regressions, and fix the biggest offenders (LCP, INP, CLS, TTFB) in one PR |
| [build-landing-page](skills/build-landing-page/) | 🛠 Idea → scaffolded, designed, analytics-wired, **deployed** landing page with a live URL |
| [claim-all-unassigned-prs](skills/claim-all-unassigned-prs/) | 🚑 Find unassigned PRs opened by others across **every repo you can write to** (orgs included) and fan out claim-unassigned-prs |
| [claim-unassigned-prs](skills/claim-unassigned-prs/) | 🚑 Request your review on every open PR in a repo that has no assignee, reviewer, or review yet and was opened by someone else |
| [dedupe-and-prune-deps](skills/dedupe-and-prune-deps/) | 🤖 Collapse duplicate versions, declare phantom imports, remove unused dependencies |
| [drift](skills/drift/) | 🎲 One prompt, every possibility: k distinct answers with self-assessed probabilities, ranked from conventional to wild (verbalized sampling) |
| [expert-accessibility](skills/expert-accessibility/) | 🎓 Audit a web app against WCAG 2.2 AA like an accessibility specialist: semantics and landmarks, keyboard and focus, ARIA misuse, forms and errors, contrast, alt text, motion, screen-reader announcements, and target size; every finding verified, ranked by severity, and tied to the success criterion it fails, with an exact location and a concrete fix; read-only |
| [expert-appsec](skills/expert-appsec/) | 🎓 Defensive web app security review against OWASP Top 10 and ASVS: auth and sessions, IDOR, injection, XSS/CSP, CSRF, SSRF, secrets in code or client bundles, headers, CORS, uploads, rate limits, sensitive logs; every finding traced source to sink, verified, CVSS-rated, with a failure scenario and a framework-native fix; says so when the app is sound |
| [expert-backend](skills/expert-backend/) | 🎓 Staff-level backend and API architecture review: detects the stack and ORM, then checks contracts, versioning, pagination, idempotency, migrations, N+1 and missing indexes, transactions, caching, queues, timeouts and retries, scale limits, observability, and failure modes; verified findings ranked by severity with file:line and a concrete fix, or a plain "sound" |
| [expert-dx](skills/expert-dx/) | 🎓 Review a repo, library, SDK, CLI, or API as a developer adopting it: walk the quickstart literally and time it, then judge setup and scripts, error messages, API naming, typing, examples, changelog and migration notes, and the local dev loop; read-only findings ranked by severity with file:line and a concrete fix |
| [expert-frontend-performance](skills/expert-frontend-performance/) | 🎓 Review frontend code like a senior performance engineer: bundle size and splitting, heavy or duplicate deps, re-renders, hydration and SSR, fetch waterfalls, caching headers, fonts, images, third-party scripts, memory leaks; framework-aware (Next, Nuxt, SvelteKit, Astro, Vite, webpack), backed by build output, analyzers, and traces, ranked by severity; says so when it is sound |
| [expert-gas-optimization](skills/expert-gas-optimization/) | 🎓 Review smart contracts for gas and onchain efficiency the measure-first way: baseline `forge snapshot`, prove every saving by re-measuring, rank by gas saved on real hot paths (storage packing, SLOAD/SSTORE, calldata, loops, events, custom errors, optimizer runs, L2 data costs) with trade-offs; security always wins, and sound code gets "no findings" |
| [expert-qa](skills/expert-qa/) | 🎓 A senior QA engineer on your PR, feature, or release: risk-based test plan, the edge cases that break real products (empty, huge, unicode, timezones, concurrency, offline, permissions), exploratory checks when the app runs, verified coverage gaps, and a ship / ship-with-conditions / do-not-ship call. Read-only |
| [expert-smart-contract-security](skills/expert-smart-contract-security/) | 🎓 Audit Solidity/EVM contracts like a professional auditor: scope and threat model, Slither/Aderyn/Foundry/Echidna/Medusa when installed, a manual pass over reentrancy, access control, precision, oracles, flash loans, MEV, signature replay, and upgradeability; every finding ranked Critical to Informational with an exploit scenario, a fix, and an optional local-fork Foundry PoC |
| [expert-tokenomics](skills/expert-tokenomics/) | 🎓 Review a token or protocol economy like a tokenomics auditor: reconcile whitepaper claims against what the contracts and on-chain state actually enforce, project circulating supply from the real vesting and emission schedule, and stress incentives, value accrual, treasury, governance capture, and economic attacks (sybil farming, mercenary liquidity, death spirals, oracle liquidations); read-only, severity-ranked, not financial advice |
| [expert-ui](skills/expert-ui/) | 🎓 Senior visual design review of a UI, page, or PR: hierarchy, spacing rhythm, type scale, computed contrast, token and component consistency, breakpoints, light/dark parity, icons, and motion; verified findings ranked by severity with exact references and fixes, read-only |
| [expert-ux](skills/expert-ux/) | 🎓 Senior UX designer review of a feature, flow, or whole app: journeys, dead ends, navigation, forms, loading/empty/error states, onboarding, feedback, and microcopy; ranked by severity with exact locations and concrete fixes; read-only, and says so when the experience is sound |
| [expert-web3-dapp](skills/expert-web3-dapp/) | 🎓 Review a dApp's frontend and wallet integration like a senior web3 engineer: connection and chain switching, the full transaction lifecycle (simulate, sign, pending, replaced, reverted), readable EIP-712 signing, revert decoding, token-amount precision and fees, RPC failover, reorg-safe events, nonces, safe approvals, and ERC-4337; verified against your installed wagmi/viem/ethers versions, read-only, ranked by severity |
| [extract-design-system](skills/extract-design-system/) | 🎲 Extract tokens, themes, typography, and components from source into a living design-system artifact, plus a drift report of hard-coded values, that wireframes reuse |
| [fix-all-issues](skills/fix-all-issues/) | 🚑 Fix a list of issues (or every open, unclaimed issue in the repo) with one subagent, one worktree, and one PR per issue, in parallel |
| [fix-dependabot-alert](skills/fix-dependabot-alert/) | 🤖 Remediate a Dependabot **security alert** end-to-end: bump/override, branch, PR |
| [fix-dependabot-pr](skills/fix-dependabot-pr/) | 🤖 Take over a Dependabot bump PR (grouped updates and major migrations included) and push commits until CI passes |
| [fix-failing-ci](skills/fix-failing-ci/) | 🚑 Paste a red Actions run URL; get diagnosis, a fix on the built branch, and a green build |
| [fix-flaky-tests](skills/fix-flaky-tests/) | 🚑 Prove a test is flaky, find the real cause (shared state, timing, environment, randomness, resource leaks, unmocked externals), fix it at the source, and open a PR; quarantine as a tracked last resort, never a blanket retry |
| [fix-issue](skills/fix-issue/) | 🚑 Pick an open GitHub issue, implement it on a fresh branch, open the PR |
| [fix-renovate-pr](skills/fix-renovate-pr/) | 🤖 Take over a Renovate bump PR and push commits until CI passes |
| [fleet-health-dashboard](skills/fleet-health-dashboard/) | 🧭 One live dashboard for **every repo you own** (orgs included): bot PRs, alerts, red CI, stale PRs, Node pins; each row names the skill that fixes it; refreshable on a schedule |
| [isometric-stack-map](skills/isometric-stack-map/) | 🧭 Turn a project into a single-file 3D isometric map of its network and tech stack, where components look like real hardware (servers, disk-stack DBs, chip caches, envelope queues). Staircase, tower, or flat-slate layouts; show, hide, and highlight any slice; play user actions to see what they trigger; switch parts off to see the blast radius; six themes plus custom |
| [nudge-stale-prs](skills/nudge-stale-prs/) | 🚑 Find open PRs older than 2 days across every repo you can write to and have Cursor/Claude/Codex's GitHub user tag you to review/merge; self-mentions do not notify |
| [optimize-all-github-actions](skills/optimize-all-github-actions/) | 🚑 Find every repo you own with Actions (orgs included) and fan out optimize-github-actions, one PR per repo |
| [optimize-github-actions](skills/optimize-github-actions/) | 🚑 Analyze workflows, cut wasted Actions minutes (duplicate runs, redundant jobs, matrix bloat), open a PR, without weakening security |
| [optimize-images](skills/optimize-images/) | 🛠 Cut image weight and layout shift in one PR: responsive srcset, AVIF/WebP with a fallback, explicit dimensions, correct LCP priority, SVG for icons, and a byte budget enforced in CI, using the project's own image tooling |
| [optimize-pwa](skills/optimize-pwa/) | 🛠 Make your web app installable and native-feeling on phones in one PR: manifest with real-size and maskable icons, a safe service worker with offline fallback and update prompt, install UX for Android and iOS, plus mobile fixes for zoom, notches, `100dvh`, tap targets, and mobile keyboards, using your framework's own PWA tooling |
| [optimize-seo-aeo](skills/optimize-seo-aeo/) | 🛠 Audit what search engines and AI answer engines actually see, then ship one PR with the fixes that matter: titles, descriptions, canonicals, OG tags, sitemap, robots.txt (AI search bots included), JSON-LD, llms.txt, and server-rendered content, using your framework's own APIs |
| [panel-accessibility](skills/panel-accessibility/) | 🏛 Seat three experts (a WCAG 2.2 and ARIA specialist, a screen-reader and keyboard power user, an inclusive designer) to judge whether people with disabilities can complete your core flows; each reviews alone, then the panel records its disagreements and gives one joint verdict with the blockers to fix before shipping, every finding tied to a location and its success criterion; read-only |
| [persona-accessibility-user](skills/persona-accessibility-user/) | 👥 Walk your site as a screen reader and keyboard-only user at 200% zoom with reduced motion; it tries to finish the main flows, reports in their own voice what they heard, where focus went, and where they got stuck, each blocker tied to a step and its WCAG criterion; read-only |
| [persona-crypto-newcomer](skills/persona-crypto-newcomer/) | 👥 A crypto newcomer who has never used a self-custody wallet tries your dApp from scratch and reports in their own voice where they got stuck, which words lost them (gas, bridge, slippage, L2, seed phrase), how custody and recovery came across, and every moment they feared losing money, with the explanation that would have helped; read-only, never signs |
| [persona-designer](skills/persona-designer/) | 👥 A senior product designer critiques your site as a user with a trained eye: focal point, spacing rhythm, type, component one-offs, hover/focus/loading/empty/error states, dark mode, icons, motion, and whether it feels finished or generic, in their own voice, ranked by impact, read-only |
| [persona-developer](skills/persona-developer/) | 👥 Walk your docs, API, SDK, CLI, contracts, or widget as a developer racing to hello world: find the quickstart, copy-paste the examples, get a key or testnet, make the first call, and report in their voice every step on the clock, each point of friction and out-of-date doc, and whether they would ship on it; read-only |
| [persona-gen-z](skills/persona-gen-z/) | 👥 A 19-year-old who tapped your link on TikTok or X reviews it on a phone in the in-app browser: vibe, aesthetic, tone and copy, cool or cringe, time to the fun part, screenshot and group-chat worthiness, and the exact moment they'd have bounced, in casual voice, with a plain-English fix list, read-only |
| [persona-grandma](skills/persona-grandma/) | 👥 Walk your site as a non-technical grandmother on an iPad at 150% zoom and hear it in her voice: could she tell what it is and what to do first in 10 seconds, which words and icons lost her, what she couldn't read or press, what felt like it could break her computer or take her money, and whether she finished alone or called a grandchild; read-only |
| [persona-growth-hacker](skills/persona-growth-hacker/) | 👥 A growth marketer uses your product from a shared link on their phone and reports in their own voice on the hook above the fold, time to aha, signup and activation leaks, CTAs, social proof, share cards, referral and invite loops, waitlists, and retention hooks, plus what they would A/B test first and whether anyone would share it unprompted; flags dark patterns as risks, read-only |
| [persona-investor](skills/persona-investor/) | 👥 A busy angel or VC partner gives your site a five-minute first pass before a pitch meeting: can they say what it does, for whom, and why now; differentiation, traction and team quoted only from the site, business model or token clarity, roadmap, the questions they'd ask, and whether they'd take the meeting; not investment advice |
| [persona-mobile-commuter](skills/persona-mobile-commuter/) | 👥 See your product through a phone user on a bus (one thumb, patchy 4G, interrupted every couple of minutes), walked live at phone width on a throttled network with app switches and reloads mid-task, reporting in their voice on thumb reach, missed taps, slow loads, keyboards, lost progress, wallet deep links and in-app browsers, and where mobile felt like an afterthought; read-only |
| [persona-power-user](skills/persona-power-user/) | 👥 A keyboard-first power user with ten tabs open and no patience walks your app at speed and reports in their own voice: responsiveness, density, shortcuts and command palette, bulk actions, settings, URL state, undo, edge-case input, export and API, with a speed scorecard and what would make them switch to a competitor; read-only |
| [persona-security-skeptic](skills/persona-security-skeptic/) | 👥 A security engineer who assumes every site is phishing walks your site or dApp and reports in their voice: domain and certificate, who runs it and whether socials link back, audit claims, every permission and wallet prompt (unlimited approvals, blind signing), trackers before consent, data asked for vs. the privacy policy, with real red flags kept apart from things that only look suspicious |
| [persona-web3-degen](skills/persona-web3-degen/) | 👥 See your dApp through a crypto-native degen who has used every DeFi app and judges yours in seconds: wallet connect and network switching, what each signing prompt asks for, gas and fee clarity, pending/failed/speed-up states, contracts, explorers and audits, token and points mechanics, and whether it feels legit or like a rug; read-only, never signs, ends with "would I ape in and come back?" |
| [prune-dead-code](skills/prune-dead-code/) | 🛠 Find and remove dead code in one reviewable PR: unused exports, orphan files, dead feature flags, unreachable routes, stale assets, proving each candidate is not referenced dynamically before deleting it |
| [prune-deps-across-org](skills/prune-deps-across-org/) | 🤖 Find every JS repo you own (orgs included) and fan out dedupe-and-prune-deps, one hygiene PR per repo |
| [review-pull-request](skills/review-pull-request/) | 🚑 Review a PR the way a careful senior reviewer would: read the repo's rules first, classify the risk, then verify every finding (correctness, tests, security, migrations, API contracts, performance) before reporting it, ranked by severity, optionally posted to GitHub |
| [save-wireframe](skills/save-wireframe/) | 🎲 Save a wireframe artifact into `.wireframe/<name>/` as a plain vanilla static site: split HTML/CSS/JS/data, no build, opens from disk, verified to behave like the original, with a manifest and an index of every saved wireframe |
| [setup-seo](skills/setup-seo/) | 🛠 Wire up search-indexing channels in one PR: an IndexNow key file at the site root, an automatic post-deploy ping for changed URLs (Bing, Yandex, Seznam, Naver, Yep, Amazonbot), plus the Google and Bing channels IndexNow does not cover: sitemap.xml, robots.txt, webmaster verification, and sitemap submission |
| [spike-variants](skills/spike-variants/) | 🎲 Build a feature N ways in parallel worktrees against one acceptance contract, compare them with real metrics, ship the winner as a PR |
| [standardize-repo-hygiene](skills/standardize-repo-hygiene/) | 🛠 Bring a repo up to professional standard for outside contributors and coding agents: LICENSE, README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CODEOWNERS, issue/PR templates, .editorconfig, .gitignore, .env.example, AGENTS.md, dependency bots; every file filled from the repo's real facts, never placeholders |
| [sweep-all-dependabot-alerts](skills/sweep-all-dependabot-alerts/) | 🤖 Find open Dependabot **security alerts** across every repo you own (orgs included) and fan out fix-dependabot-alert |
| [sweep-all-dependency-prs](skills/sweep-all-dependency-prs/) | 🤖 Fan out across **every repo you own** (orgs included) and sweep their bot PRs in parallel |
| [sweep-dependency-prs](skills/sweep-dependency-prs/) | 🤖 Approve & merge every green Dependabot/Renovate PR in a repo; dispatch fixes for the red ones |
| [upgrade-node-across-org](skills/upgrade-node-across-org/) | 🛠 Find every repo you own that pins Node (orgs included) and fan out upgrade-node-version, one PR per repo |
| [upgrade-node-version](skills/upgrade-node-version/) | 🛠 Bump Node across `.nvmrc`, `engines`, CI workflows, and Dockerfiles, then fix the fallout |
| [wireframe-feature](skills/wireframe-feature/) | 🎲 Turn a complex feature idea into several interactive, responsive wireframe variants, side by side in one artifact, that reuse your app's layout, tokens, and light/dark themes, then iterate on the one you pick |
| [wireframe-logo-design](skills/wireframe-logo-design/) | 🎲 Turn a logo idea into several directions, each 8 logos shown as marks and lockups in your app's own colors and fonts, side by side in one artifact; pick by number and refine |
| [wireframe-og-design](skills/wireframe-og-design/) | 🎲 Find your current og:image / twitter:image and redesign the social card in several 1200 × 630 variants in your app's own colors, fonts, and layout, each shown in X, LinkedIn, Slack, Discord, and iMessage previews, side by side in one artifact |
| [wireframe-redesign](skills/wireframe-redesign/) | 🎲 Redesign your **whole** site or app (every route, feature, role, and state, with real content) in several directions inside one artifact: switch variant on any page, force loading/empty/error, jump anywhere from the sitemap, compare the same page across variants |

## 🔍 Anatomy of a skill

```text
skills/<skill-name>/
├── SKILL.md          # Required: frontmatter (name, description) + instructions
├── scripts/          # Optional: helper scripts the agent can run
├── references/       # Optional: longer docs loaded on demand
└── assets/           # Optional: templates and other static files
```

A good skill has four traits:

- **One specific purpose**: a clear workflow, not a catch-all prompt dump
- **A trigger-rich description**: tells the agent *when* to reach for it, unprompted
- **A concise body**: assume the agent is smart; only add what it wouldn't know
- **Progressive disclosure**: keep `SKILL.md` under 500 lines; push depth into `references/`

Authoring a new one? Copy [`templates/skill/`](templates/skill/) into `skills/<your-skill-name>/`. It lives outside `skills/` so the CLI does not install the placeholder. Persona skills start from [`templates/persona/`](templates/persona/).

## ❓ FAQ

### What are Agent Skills?

Agent Skills are folders of instructions that an AI agent loads when a task needs them. Each one has a `SKILL.md` file with a `name`, a `description` that says when to use it, and the steps to follow. The format is an open standard documented at [agentskills.io](https://agentskills.io), so one skill works across many agents.

### Which AI agents does Skillable work with?

Any agent that supports the open `SKILL.md` format, including Claude Code, Cursor, GitHub Copilot, OpenAI Codex, and Cline. See the [client list](https://agentskills.io/clients) for the full set and where each one looks for skills. The `npx skills add` command detects the agents you have installed.

### How is a skill different from a prompt, a Cursor rule, or an MCP server?

A prompt is something you paste every time. A rule is always in context, whether it's relevant or not. An MCP server gives the agent new tools. A skill is a reusable *procedure*: it costs almost nothing until the agent needs it, then teaches the agent how to combine the tools it already has (`git`, `gh`, your package manager, MCP servers) into a complete workflow.

### Do the skills change my code or push to GitHub on their own?

Skills that change code create a branch, commit, and open a pull request. Merging is up to you, except in the dependency sweep skills, which only merge Dependabot/Renovate PRs from verified bots whose CI is green. Review skills (`expert-*`, `persona-*`) are read-only. Your agent's own permission settings still apply to every command.

### What do I need installed?

Node.js to run `npx skills`, and Git. Skills that work with GitHub need the [GitHub CLI](https://cli.github.com/) signed in (`gh auth login`). Each skill's `SKILL.md` lists any other tools it uses, such as Foundry or Slither for smart contract audits, and says what to do when they're missing.

### Some skills publish interactive pages. Do I need Claude for those?

The wireframe, dashboard, and map skills publish an interactive page as an Artifact when the agent supports it. Without that, they write the same page as a local HTML file and open it in your browser.

### How do I update or remove skills?

Run `npx skills update` to pull the latest versions and `npx skills remove <skill-name>` to uninstall one. If you copied folders manually, `git pull` the clone and copy them again.

### Can I write my own skill or suggest one?

Yes. If you've explained a workflow to an agent more than twice, it's a skill waiting to be written. Start from [`templates/skill/`](templates/skill/), run `python3 scripts/validate_skills.py`, and open a PR. See [CONTRIBUTING.md](CONTRIBUTING.md).

### Is Skillable free?

Yes. Every skill is MIT licensed, with no account or paid tier.

## 🤝 Contributing

Got a workflow you've explained to an agent more than twice? That's a skill waiting to be written. Read [CONTRIBUTING.md](CONTRIBUTING.md) for naming conventions, review criteria, and the submission process, then open a PR. CI runs `python3 scripts/validate_skills.py` on every change to check structure, formatting, and this README's catalog.

## ⭐ Support the project

If a skill here just merged a week's worth of bot PRs while you drank your coffee, **star the repo**. It's how other people find it, and it keeps new skills coming.

## 📄 License

MIT. See [LICENSE](LICENSE).
