# Audit report template

Fill every section. Delete a section only when it is genuinely empty, and say "None" rather than leaving a heading with nothing under it. Findings go most severe first; IDs restart per severity (`C-01`, `H-01`, `M-01`, `L-01`, `I-01`).

~~~markdown
# Security review — <project>

**Commit:** `<full sha>` (<repo URL>)
**Date:** <YYYY-MM-DD>
**Reviewer:** AI-assisted review (expert-smart-contract-security)
**Methodology:** threat model → automated analysis → line-by-line manual review → verification → PoC for High/Critical → invariant fuzzing
**Tools:** <Slither x.y.z, Aderyn x.y.z, Foundry forge x.y.z, Echidna x.y.z, Medusa x.y.z — or "manual only: no tools installed">
**Compiler:** solc <version>, optimizer <runs>, via_ir <true|false>
**Target chains:** <chains>

## Scope

| File | nSLOC |
|------|-------|
| src/Vault.sol | 312 |
| src/Oracle.sol | 98 |
| **Total** | **410** |

Out of scope: <libraries, mocks, scripts, contracts not listed>.
Known issues excluded: <link or list>.

## System overview

<Two to five sentences: what the protocol does and how value flows.>

**Assets:** <what holds value>
**Actors:** <role — capability — EOA/multisig/timelock>
**Trust assumptions:** <what each privileged role is trusted not to do; external dependencies trusted>
**Invariants:** <numbered list in plain words>

## Summary

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 1 |
| Medium | 2 |
| Low | 1 |
| Informational | 2 |

| ID | Title | Severity | Confidence |
|----|-------|----------|------------|
| H-01 | First depositor can steal subsequent deposits via share inflation | High | Confirmed (PoC) |
| M-01 | … | Medium | High |

## Findings

### H-01 — First depositor can steal subsequent deposits via share inflation

**Severity:** High (Impact: High — loss of user deposits · Likelihood: Medium — requires an empty vault, true at launch)
**Location:** `src/Vault.sol:87-104` (`deposit`, `_convertToShares`)
**Confidence:** Confirmed — PoC `test/audit/PoC_H01.t.sol` passes

**Description**
<What is wrong and why, referencing the exact lines.>

**Exploit scenario**
1. The vault is deployed empty.
2. Attacker deposits 1 wei and receives 1 share.
3. Attacker transfers 10 000 tokens directly to the vault, so 1 share is worth 10 000 tokens.
4. Victim deposits 10 000 tokens; `shares = 10_000e18 * 1 / (10_000e18 + 1)` rounds down to 0.
5. Attacker redeems 1 share for ~20 000 tokens. Victim's deposit is lost.

**Proof of concept**
<Path to the test and the command to run it; key output line. Omit working exploit code from public posts for live deployments.>

**Recommendation**
```diff
- return assets.mulDiv(totalSupply(), totalAssets(), Math.Rounding.Floor);
+ return assets.mulDiv(totalSupply() + 10 ** _decimalsOffset(), totalAssets() + 1, Math.Rounding.Floor);
```
<One line on why the fix works and any trade-off.>

---

<repeat per finding>

## Invariants tested

| # | Invariant | Tool | Runs / depth | Result |
|---|-----------|------|--------------|--------|
| 1 | Vault is solvent: assets ≥ assets owed to all shares | forge invariant | 500 / 100 | Holds |
| 2 | Deposit→redeem round trip never profits | Echidna | 100 000 calls | Broken → H-01 |

## Centralization risks

- <Role> can <action> without <timelock/bound>. Impact if the key is compromised: <outcome>.

## Worth checking (unverified)

- <Lead, why it may matter, what would confirm or refute it.>

## Notes

- <Tool false positives triaged, assumptions made, areas not covered and why.>

## Disclaimer

This is a time-boxed review of the commit above. It does not guarantee the absence of vulnerabilities, does not cover code outside the stated scope, and does not cover later changes. Treat it as one input to a security process that also includes independent audits, testing, monitoring, and a bug bounty.
~~~

## When the code is sound

~~~markdown
# Security review — <project>

**Commit:** `<sha>` · **Scope:** <n> files, <nSLOC> nSLOC · **Tools:** <list>

No Critical, High, or Medium findings at this commit.

**What was checked:** <one line per area from the checklist that applied>
**Invariants that held:** <list with runs/depth>
**This result rests on:** <trust assumptions — e.g. owner is a timelocked multisig, only allowlisted tokens>

<At most a handful of Low / Informational items that genuinely matter, each with file:line. Or: "No further suggestions.">

<Disclaimer as above.>
~~~
