# License policy reference

Reference for the `audit-licenses` skill: SPDX ids per tier, the obligation cheat-sheet, how to handle `UNKNOWN` and `NOASSERTION`, a worked policy file, the exception record format, and per-ecosystem commands.

This is engineering hygiene, not legal advice. A qualified lawyer owns the final call on any obligation described here.

## Tiers

The policy file has three tiers. A package's tier is decided by its normalized SPDX id.

### Allowed — permissive, ship freely

| SPDX id | Notes |
|---------|-------|
| `MIT` | Attribution in the shipped artifact or a bundled notice file |
| `BSD-2-Clause` | Attribution; no endorsement clause |
| `BSD-3-Clause` | Attribution; no endorsement clause |
| `ISC` | Attribution |
| `Apache-2.0` | Attribution **plus** a `NOTICE` file when the upstream has one; patent grant and termination clause |
| `Unlicense` | Public-domain dedication; nothing required |
| `0BSD` | Attribution |

### Restricted — copyleft or otherwise conditional, allowed with obligations

Allowed only when the obligations are met, and only after the owner has agreed to the distribution model.

| SPDX id | Notes |
|---------|-------|
| `GPL-2.0-only`, `GPL-3.0-only` | Strong copyleft: on distribution of a derived work, the whole work must be under the same license and the source must be offered |
| `LGPL-2.1-only`, `LGPL-3.0-only` | Weak copyleft: dynamic linking is usually fine; static linking and modifications trigger relinking and source obligations |
| `MPL-2.0` | File-level copyleft: modified MPL files stay MPL; larger files can be proprietary; source of modified files must be available |
| `EPL-1.0`, `EPL-2.0` | Weak copyleft, similar shape to MPL/LGPL |
| `CDDL-1.0`, `CDDL-1.1` | File-level copyleft, source-available; the CDDL text must ship |
| `EUPL-1.1`, `EUPL-1.2` | Copyleft with an EU compatibility clause |
| `Artistic-2.0` | Permissive with a distribution condition |
| `PSF-2.0`, `Python-2.0` | Permissive with a notice condition |

### Forbidden — do not ship without an explicit, reviewed exception

| SPDX id | Notes |
|---------|-------|
| `AGPL-3.0-only`, `AGPL-3.0-or-later` | Network copyleft: offering the software as a service can trigger the source-offer obligation |
| `SSPL-1.0` | Server Side Public License; a service-triggered source obligation |
| `BUSL-1.1` | Business Source License; time-delayed open sourcing with a commercial-use restriction |
| `Elastic-2.0` | Source-available; forbids competing SaaS |
| `LicenseRef-Proprietary` | Proprietary, non-redistributable code |
| `UNLICENSED` | The npm marker for "not licensed for redistribution" |
| `UNKNOWN`, `NOASSERTION` | The license could not be determined; treat as forbidden until resolved |
| `LicenseRef-Custom` | A bespoke or file-based license that must be read by a human |

A permissive alternative that is in the allowed list wins over a restricted one when a dependency offers a choice (for example `MIT OR Apache-2.0`).

## Obligation cheat-sheet

What each license actually requires, and when the notice has to ship. "Distributed" means the artifact leaves the user's machine: a published package, a shipped binary, a container image, an installer, an on-premise release.

| License | Keep what | When the notice ships | Source offer | Extra obligations |
|---------|-----------|----------------------|-------------|-------------------|
| `MIT` | Copyright notice and permission text | With the distribution, in a notice file or the shipped LICENSE | No | None |
| `BSD-2-Clause` / `BSD-3-Clause` | Copyright notice, conditions, disclaimer | With the distribution | No | BSD-3 adds the no-endorsement clause |
| `ISC` | Copyright notice and permission text | With the distribution | No | None |
| `Apache-2.0` | License text; upstream `NOTICE` content if present | With the distribution, plus a `NOTICE` file carrying the upstream notices | No, unless the patent grant is terminated | Express patent grant; trademark use is not granted |
| `Unlicense` | Nothing required | Optional | No | None |
| `0BSD` | Copyright notice | With the distribution | No | None |
| `LGPL-3.0-only` | LGPL text; notices for the LGPL components | With the distribution | Only for the LGPL components you modified | Relinking right for dynamic linking; static linking requires object files or relinkable source |
| `MPL-2.0` | MPL text; notices | With the distribution | Source of the MPL files you modified must be available | Modified MPL files stay MPL; the `MPL-2.0` files must be identified |
| `GPL-2.0-only` / `GPL-3.0-only` | GPL text; complete corresponding source | With the distribution | Yes: the complete corresponding source of the derived work | The whole derived work must be GPL; the source offer must travel with the artifact |
| `CDDL-1.0` | CDDL text; notices | With the distribution | Source of modified CDDL files must be available | Modified files stay CDDL; larger works can combine |
| `EPL-2.0` | EPL text; notices | With the distribution | Source of modified EPL files must be available | Modified files stay EPL |
| `AGPL-3.0-only` | AGPL text; complete corresponding source | With the distribution | Yes | Section 13: **offering the software over a network** can trigger the source obligation, even without distribution |
| `SSPL-1.0` | SSPL text; notices | With the distribution | Yes, for service offerings | Broad service-triggered source obligation; not OSI-approved |
| `BUSL-1.1` | BUSL text | With the distribution | Only after the change date | Commercial use restricted until the change date |

### Distribution model decides the outcome

| Model | What ships | AGPL / SSPL | GPL |
|-------|-----------|-------------|-----|
| **Application or container** (binary, image, installer) | Binaries and images | Forbidden without an exception: the binary is distributed | Requires the whole work under GPL plus a source offer; usually fatal for a proprietary product |
| **Published library** (npm, PyPI, crates.io) | The package tarball | Forbidden without an exception | Requires GPL for the package and a source offer |
| **Hosted SaaS** (no artifact distributed) | Nothing | AGPL section 13 can still apply: offering the modified version over a network triggers the source offer. SSPL is likewise triggered by service offering | Ordinary GPL obligations generally do not trigger, because nothing is distributed |
| **Internal use only** | Nothing | No obligation | No obligation |

### Obligations that survive every model

- Never remove an existing notice, `NOTICE`, or `LICENSE` file that ships with the artifact.
- Keep the upstream copyright lines intact in the notice file.
- Do not use an upstream project's trademark or logo without permission (Apache-2.0 grants no trademark rights).
- Keep the dependency's license text with the artifact whenever the license requires it, even for a permissive license whose notice is already in your own `LICENSE` file.

## Handling `UNKNOWN` and `NOASSERTION`

These are not licenses. They are gaps in the metadata, and each one is a task, not a conclusion.

| Value | Meaning | Action |
|-------|---------|--------|
| `UNKNOWN` | No license field at all, or a string that could not be mapped to a known id | Read the package's own `LICENSE` / `COPYING` file and classify it by hand. If there is no license file, treat the package as forbidden |
| `NOASSERTION` | The metadata explicitly declines to assert a license (SPDX's way of saying "look elsewhere") | Read the package's license file. If it points to a file, follow it |
| `LicenseRef-Custom` | The package declares `SEE LICENSE IN <file>` or a bespoke license | Read that file. If it grants rights you cannot summarize in one line, escalate to a human |
| `LicenseRef-Proprietary` | The string said "proprietary", "commercial", or "private" | Do not redistribute. Treat as forbidden unless a reviewed exception exists |
| `UNLICENSED` | The npm "no redistribution" marker | Forbidden for any distributed artifact |

Rules:

- Never guess an SPDX id. An entry stays `UNKNOWN` until a human or a read license file resolves it.
- Never rewrite a package's metadata to make a check pass.
- Record every unresolved entry in the PR so it is visible, even when the check tolerates it.

## Worked policy file

`license-policy.json` at the repo root:

```json
{
  "$schema": "./license-policy.schema.json",
  "version": 1,
  "allowed": [
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "Unlicense",
    "0BSD"
  ],
  "restricted": [
    "GPL-2.0-only",
    "GPL-3.0-only",
    "LGPL-2.1-only",
    "LGPL-3.0-only",
    "MPL-2.0",
    "EPL-2.0",
    "EPL-1.0",
    "CDDL-1.0",
    "CDDL-1.1",
    "EUPL-1.1",
    "EUPL-1.2",
    "Artistic-2.0",
    "PSF-2.0",
    "Python-2.0"
  ],
  "forbidden": [
    "AGPL-3.0-only",
    "AGPL-3.0-or-later",
    "SSPL-1.0",
    "BUSL-1.1",
    "Elastic-2.0",
    "LicenseRef-Proprietary",
    "UNLICENSED",
    "UNKNOWN",
    "NOASSERTION"
  ],
  "exceptions": [
    {
      "package": "internal-licensing-service",
      "license": "SSPL-1.0",
      "reason": "Vendored SDK, used only in the internal control plane, never redistributed",
      "owner": "platform-team",
      "review_by": "2026-06-01"
    }
  ]
}
```

The `allowed` list is a whitelist: a package whose id is not listed is not allowed by default. Put the tier that matches your risk appetite in `allowed`; put everything else in `restricted` or `forbidden`.

### Exception record format

An exception is a deliberate, owned, dated decision to ship one specific package under one specific license.

| Field | Required | Meaning |
|-------|----------|---------|
| `package` | yes | The exact package name as it appears in the inventory |
| `license` | yes | The SPDX id the exception applies to; an exception for one license does not cover another |
| `reason` | yes | Why the dependency is acceptable, in one or two sentences |
| `owner` | yes | A person or team accountable for the decision |
| `review_by` | yes | An ISO date (`YYYY-MM-DD`) after which the exception must be revisited |

An exception without all five fields is invalid: the check ignores it and the package fails. A missing `review_by` means the exception expires silently; treat an expired exception as a failure on the next run.

## Per-ecosystem commands

### Node

```bash
# Installed tree (preferred - carries real license fields)
node -p "require('./node_modules/lodash/package.json').license"

# Lockfile inventory
npm ls --all --json
pnpm licenses list --json
yarn licenses list --json

# Own project license
npm pkg get license
```

### Python

```bash
pip show <package>
pip-licenses --format=json --with-urls --with-license-file
python -c "import importlib.metadata as m; print(m.metadata('requests').get('License-Expression'))"
python -c "import importlib.metadata as m; print(m.metadata('requests').get_all('Classifier'))"

# Own project license
grep -i license pyproject.toml setup.cfg setup.py 2>/dev/null
```

### Rust

```bash
cargo metadata --format-version 1 --no-deps
cargo license --json            # needs the cargo-license extension
cargo tree -e normal

# Own project license
grep -i "^license" Cargo.toml
```

### Go

```bash
go list -m -json all
go list -m -f '{{.Path}} {{.Version}} {{.Dir}}' all
cat "$(go env GOMODCACHE)/<module>@<version>/LICENSE"

# Own project license
ls LICENSE* COPYING*
```

### Ruby, PHP, and other ecosystems

```bash
bundle info <gem>              # gem license via gemspec
bundle licenses
composer show --format=json
composer licenses
```

## Attribution file layout

Two common shapes. Pick the one the project already uses; do not introduce a second.

`NOTICE` (Apache-style, for a project that ships an Apache-2.0 dependency or upstream `NOTICE` files):

```text
<project name>
Copyright (c) <year> <copyright holder>

This product includes software developed at <project>.

--------------------------------------------------------------------------------
<dependency name> <version>
<upstream copyright line>

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
...
```

`THIRD_PARTY_LICENSES` (a flat list, for a project with many dependencies):

```text
<dependency name>@<version> — <SPDX id> — <upstream URL>
```

Keep the file generated from the resolved tree when the ecosystem offers a generator (`license-checker`, `license-report`, `oss-attribution`, `cargo license`). A hand-maintained list drifts.

## Sources

- SPDX license list: <https://spdx.org/licenses/>
- Choose a license: <https://choosealicense.com/>
- GNU license texts: <https://www.gnu.org/licenses/>
- OSI approved licenses: <https://opensource.org/licenses>
