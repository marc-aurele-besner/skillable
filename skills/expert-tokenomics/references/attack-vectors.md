# Economic attack vectors

Load this in step 5, after the checklist. For each vector that applies, answer: **preconditions present? → attacker cost → attacker profit → who loses → what stops it.** Report a vector only when the preconditions exist in this design and you can sketch the numbers.

## Contents

- Sybil farming
- Mercenary liquidity
- Wash volume and self-dealing
- Death spirals and reflexive collateral
- Oracle manipulation and liquidation cascades
- Governance capture
- Flash-loan voting
- Bribe markets and vote-escrow capture
- Unlock and emission MEV
- Insider extraction
- Fix patterns

## Sybil farming

- **Preconditions:** rewards (airdrop, points, quests, referral) keyed on per-address activity; criteria cheap to repeat; no identity or cost floor.
- **Signals:** flat per-wallet rewards, low minimum activity, public criteria before snapshot, referral bonuses without a cap.
- **Numbers:** cost per farmed wallet (gas + capital lock) vs expected reward per wallet.
- **Fixes:** reward scaled by fees paid or time-weighted capital, not by address count; hidden or retroactive criteria; cluster analysis before distribution; vesting on airdrops; caps per cluster; proof-of-personhood only where acceptable.

## Mercenary liquidity

- **Preconditions:** TVL or liquidity paid mostly by emissions; no lock or loyalty multiplier; competitors offering similar rates.
- **Signals:** emission APR ≫ fee APR in the main pools; TVL that tracks emission schedule changes; LPs who claim and sell each epoch.
- **Numbers:** fee APR alone vs the market rate for the same asset; TVL share sustained by emissions; emissions value per dollar of fees generated.
- **Fixes:** protocol-owned liquidity, emissions tied to fees generated (fee-weighted gauges), lock-boosted rewards, tapering instead of cliffs, rewards paid partly in locked form.

## Wash volume and self-dealing

- **Preconditions:** rewards or rankings keyed on volume or borrowing; low or rebated fees; self-matching possible.
- **Signals:** trading rewards > fees paid; deposit-and-borrow the same asset earning net positive rewards; looping.
- **Fixes:** reward net fees paid, not notional; exclude self-matched trades; cap rewards at a fraction of fees; borrow rewards only on net borrows.

## Death spirals and reflexive collateral

- **Preconditions:** a stablecoin or synthetic backed by the protocol's own token; collateral valued at market price of a token whose demand depends on the stablecoin; mint/burn arbitrage that issues more token when price falls.
- **Signals:** "algorithmic" or "partially collateralized" pegs; redemption paid in the governance token; staking yields funded by minting.
- **Numbers:** what price drop of the token makes backing < 100%; how much token must be minted to defend the peg at that point vs daily liquidity.
- **Fixes:** exogenous collateral, over-collateralization with haircuts, redemption circuit breakers and rate limits, no yield funded by minting the backing token.

## Oracle manipulation and liquidation cascades

- **Preconditions:** lending or perps using a spot price from a thin pool; the protocol's own token accepted as collateral; high LTV; liquidation bonus large relative to manipulation cost.
- **Signals:** single-pool TWAP with a short window; no Chainlink/Pyth fallback; borrow caps absent on illiquid collateral; liquidations that sell into the same pool that prices the collateral.
- **Numbers:** capital needed to move the oracle X% for the TWAP window vs profit from forced liquidations or over-borrowing.
- **Fixes:** robust oracles with deviation checks, longer TWAP windows, supply and borrow caps on illiquid assets, lower LTV and isolated markets for the native token, liquidation bonuses sized to depth.

## Governance capture

- **Preconditions:** cost to pass a proposal < value controlled (treasury, minting, fee recipient, upgrades); low turnout; short timelock.
- **Signals:** quorum met by a few wallets; insiders able to pass proposals alone; treasury and upgrade powers in the same Governor.
- **Numbers:** tokens needed for quorum + majority at realistic turnout × price vs the treasury and mintable value.
- **Fixes:** higher quorum for treasury and supply actions, longer timelocks, guardian veto with sunset, rate limits on treasury outflow, separation of upgrade powers.

## Flash-loan voting

- **Preconditions:** voting power read at the current block, not a past snapshot; token borrowable in size.
- **Signals:** custom Governor using `balanceOf` instead of `getPastVotes`; snapshot taken at execution.
- **Fixes:** checkpointed votes (`ERC20Votes`) with snapshot at proposal creation and a voting delay ≥ 1 block (preferably days).

## Bribe markets and vote-escrow capture

- **Preconditions:** ve-lock voting on gauge weights or emissions; bribe platforms; aggregators accumulating locks.
- **Signals:** one aggregator > ~30% of ve-power; emissions directed to pools that pay bribes rather than generate fees.
- **Numbers:** bribe cost per vote vs emissions value directed per vote; if bribes are cheaper, emissions leak to the highest briber.
- **Fixes:** fee-weighted emissions, gauge caps, whitelisting, decay of boosts, limits on smart-contract lockers.

## Unlock and emission MEV

- **Preconditions:** large, predictable unlocks or reward distributions at known blocks; thin liquidity.
- **Signals:** quarterly cliff unlocks; epoch-based `notifyRewardAmount` with instant claim; reward per share jumping at a known time (just-in-time staking).
- **Fixes:** linear streaming instead of cliffs, reward accrual over time (not snapshot), minimum stake durations, staggered unlocks across buckets.

## Insider extraction

- **Preconditions:** insiders control emissions, fee splits, or treasury; vesting revocable by insiders; unlocks before value accrual exists.
- **Signals:** team or foundation earning emissions on unvested tokens; treasury grants to related parties; market-maker loans with call options.
- **Fixes:** non-revocable vesting held by a neutral contract, no rewards on unvested tokens, related-party disclosure, governance approval for insider-benefiting proposals.

## Fix patterns

Prefer fixes that move the constraint into code:

| Problem | Fix in code | Fix in policy (weaker) |
|---------|-------------|------------------------|
| Mutable critical parameter | Constant, bounded setter, or timelock + vote | Public commitment not to change it |
| Vesting is a promise | Funded, non-revocable vesting contract | Published wallet addresses |
| Emission-propped liquidity | POL, fee-weighted emissions, tapering | Announced roadmap to reduce emissions |
| Capturable governance | Higher quorum for treasury, rate limits, veto with sunset | Delegate program |
| Fragile oracle | Multi-source oracle, longer TWAP, caps | Monitoring and manual pause |
