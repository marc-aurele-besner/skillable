# Tokenomics checklist

Load this in step 5. Walk only the sections the target touches. Each item is a question; a "no" or "unknown" is a candidate finding that still has to pass the verification gate in SKILL.md. Rough thresholds are heuristics from common practice, not rules — say so when you use one.

## Contents

- Supply and distribution
- Emissions and vesting
- Incentive alignment
- Value accrual
- Liquidity
- Treasury
- Governance
- Disclosure
- What not to report

## Supply and distribution

- Is the max supply enforced in code (`cap()`, no reachable `_mint` after construction, mint authority revoked), or only stated?
- Do allocation buckets sum to exactly the max supply, in both docs and deploy script?
- Who holds the minter role / mint authority today? Is it behind a timelock and a vote?
- What share goes to insiders (team, investors, advisors, foundation-controlled buckets)? Above ~40–50% combined is a governance and sell-pressure concern worth stating.
- Top-10 holder share after labeling vesting, staking, treasury, CEX, and bridge contracts.
- Is any bucket vague ("ecosystem", "reserve", "strategic") with no controller, schedule, or spending rule? That is insider supply until proven otherwise.
- Points, pre-mines, OTC deals, market-maker loans: disclosed with amounts?

## Emissions and vesting

- Emission curve: rate, decay, end date, terminal (tail) inflation. Finite or perpetual?
- Is the emission source minted or pre-funded? Pre-funded rewards can run dry; minted rewards dilute.
- Who can change the rate, and with what delay and bound?
- Insider vesting: cliff ≥ 12 months and total ≥ 36 months is the common baseline; shorter is not wrong but must be disclosed.
- Are vesting contracts funded with the tokens, and are they revocable? Who can revoke, and where do revoked tokens go?
- Unlock shape: monthly linear is gentler than quarterly or cliff lumps. Any month adding > ~10% of circulating?
- Do insider unlocks coincide with emission halvings, so supply arrives as incentives fall?
- Can locked/vesting tokens vote or be staked for rewards? If so, "locked" insiders still earn and govern.

## Incentive alignment

For every reward stream, fill: **pays for → behavior → value to the protocol → who pays**.

- Does the rewarded behavior (liquidity, borrowing, staking, volume) produce fees or security that outlast the reward?
- Is the reward cost (emissions × price) below the fees or value the behavior generates? If not, how many months does the subsidy run and what happens after?
- Can a user earn the reward without the intended behavior (self-lending loops, wash trading, deposit-borrow recursion, round-trip volume)?
- Staking with no slashing and no utility: what does staking secure? If nothing, it is a lock-up paid by dilution.
- Lock-up boosts: do they reward commitment, or just let the largest holders compound share?
- Are insiders, LPs, and users rewarded for the same outcome, or can insiders profit while users lose (e.g. team paid in emissions while protocol revenue falls)?
- Airdrop and points: do the criteria reward real usage, and are they sybil-resistant (see "Sybil farming" in attack-vectors.md)?

## Value accrual

- What is the path from protocol revenue to the token? Fee switch, buyback, burn, staking distribution, required collateral, gas, governance only?
- Is that path implemented in code, enabled, and not reversible by an admin without a vote?
- "Governance-only" token: is the governed value (treasury, fee switch, parameters) worth controlling? Then capture risk rises with it.
- Buybacks: funded by external revenue (stablecoins, ETH) or by the protocol's own token or emissions (circular)?
- Burns: from real fees, and does the burn exceed emissions at realistic volume? State the break-even volume.
- Could the protocol work identically with a stablecoin or ETH in place of the token? If yes, name the token's actual role or say it has none.
- Real yield: separate fee-funded and emission-funded APR in every figure.

## Liquidity

- Protocol-owned liquidity vs rented (incentivized) liquidity. What share of depth disappears if emissions stop?
- Pool concentration: one venue, one pair, one chain? A single pool sets the oracle price.
- Initial liquidity at TGE vs expected unlock flow: how many days of unlocks would one pool absorb before a large price move?
- Market-maker agreements: loan size, call options, and return terms disclosed?
- LP tokens locked or owned by the team (rug surface)?

## Treasury

- Size in stable terms, excluding the protocol's own token. Runway at current burn rate in months.
- Diversification: a treasury that is > ~80% own-token is not a runway, it is an overhang.
- Controller: Governor + timelock, a multisig (threshold and signers), or an EOA?
- Spending rules: budgets, streaming grants, caps per proposal, transparency reports.
- Can the treasury sell its own token without notice? Is there a disclosed policy?

## Governance

- Cost to reach quorum and to pass a proposal, in token terms and at current price, vs the value the Governor controls (treasury + mintable supply + fee switch). Cost < value is a capture finding.
- Quorum as % of circulating vs % of total supply; low participation makes small quorums easy.
- Top delegates' combined voting power; can 1–3 delegates pass anything?
- Voting power snapshot: taken at proposal creation (`getPastVotes`), or live and flash-loanable?
- Timelock length vs the time users need to exit (≥ 2 days is common; longer for upgrades).
- Emergency powers: guardian, pause, veto. Who holds them, are they bounded, do they expire?
- Insider voting: can unvested tokens vote? Do insiders control quorum alone?
- Bribe markets / vote-escrow: is the effective governor an aggregator?

## Disclosure

- Is every number needed to reproduce the supply model public (amounts, dates, start timestamps, addresses)?
- Do the docs say which addresses hold each bucket?
- Are changes to tokenomics versioned with dates?
- Is "circulating supply" defined, and does it match what is reported to aggregators?

## What not to report

- Price predictions, valuation comparisons, or "the market may not like this".
- Generic regulatory risk without a specific design element that triggers it (mention once in Report only if relevant, and say it is not legal advice).
- Smart-contract bugs as economic findings; move them to Report only with "needs a security audit".
- Missing features the design never claimed (no buyback is not a defect unless value accrual was promised).
- Thresholds above treated as hard rules; a 6-month cliff that is disclosed and small is a note, not a High.
