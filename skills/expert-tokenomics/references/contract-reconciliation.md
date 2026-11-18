# Contract reconciliation

Load this in step 2 of the workflow. It lists where token-economic parameters live in code and on-chain, and how to read them without writing anything.

## Contents

- Grep patterns by ecosystem
- What to read per standard
- Read-only on-chain commands
- Common doc-vs-code mismatches

## Grep patterns by ecosystem

Run from the repo root; exclude `node_modules`, `lib/`, and vendored dependencies so OpenZeppelin's own code does not drown the results.

```bash
# EVM (Solidity / Vyper): supply, mint, caps
rg -n -g '!lib/**' -g '!node_modules/**' -e '_mint\(' -e '\bmint\(' -e 'MAX_SUPPLY' -e 'cap\(' -e 'totalSupply' -e 'ERC20Capped' contracts src

# Control: owners, roles, upgrades, timelocks
rg -n -g '!lib/**' -e 'onlyOwner' -e 'onlyRole' -e 'AccessControl' -e 'Ownable' -e 'UUPSUpgradeable' -e '_authorizeUpgrade' -e 'TimelockController' -e 'minDelay' -e 'Pausable' contracts src

# Schedules and emissions
rg -n -g '!lib/**' -e 'VestingWallet' -e 'cliff' -e 'duration' -e 'rewardRate' -e 'emission' -e 'rewardsDuration' -e 'notifyRewardAmount' -e 'halving' -e 'epoch' contracts src

# Fees and sinks
rg -n -g '!lib/**' -e 'fee' -e 'feeRecipient' -e 'treasury' -e 'burn' -e 'buyback' -e '0x000000000000000000000000000000000000dEaD' contracts src

# Deploy-time values
rg -n -e 'new ' -e 'deploy' -e 'constructor' script deploy ignition scripts 2>/dev/null | head -80

# Solana (Anchor / SPL)
rg -n -e 'mint_to' -e 'mint_authority' -e 'set_authority' -e 'freeze_authority' -e 'AuthorityType' programs

# CosmWasm / Cosmos SDK
rg -n -e 'Mint' -e 'minter' -e 'cap' -e 'inflation' -e 'vesting' contracts x

# Move (Aptos / Sui)
rg -n -e 'coin::mint' -e 'MintCapability' -e 'TreasuryCap' -e 'burn' sources
```

## What to read per standard

| Contract / pattern | Read | Why it matters |
|--------------------|------|----------------|
| ERC-20 (any) | `totalSupply()`, `decimals()`, every reachable `_mint` | Real supply and who can grow it |
| `ERC20Capped` | `cap()` | Hard cap is enforced only here, not by a `MAX_SUPPLY` comment |
| `Ownable` / `AccessControl` | `owner()`, `hasRole(MINTER_ROLE, x)`, `getRoleMember` | Who controls mint, fees, pause |
| Proxy (UUPS / Transparent) | EIP-1967 admin slot, implementation slot | Upgrades can rewrite every rule |
| OZ `VestingWallet` | `start()`, `duration()`, `cliff()` (only on `VestingWalletCliff`, OZ v5.1+), `owner()` (beneficiary), token balance of the wallet | Vesting is real only if the wallet holds the tokens |
| Sablier / Hedgey / Superfluid streams | stream id, `startTime`, `cliffTime`, `endTime`, `cancelable` | Cancelable streams are revocable vesting |
| Staking / MasterChef / `StakingRewards` | `rewardRate`, `rewardsDuration`, `periodFinish`, `rewardPerToken`, who calls `notifyRewardAmount` | Emission rate and whether it is pre-funded or minted |
| ve-token (Curve-style) | `MAXTIME`, boost formula, gauge weights, `smart_wallet_checker` | Governance concentration, bribe surface |
| `Governor` (OZ / Bravo) | `votingDelay`, `votingPeriod`, `quorum`, `proposalThreshold`, `timelock()` | Cost and speed of capture |
| `TimelockController` | `getMinDelay()`, proposer and executor roles, `CANCELLER_ROLE` | Whether "timelocked" actually binds the admin |
| Gnosis Safe | `getOwners()`, `getThreshold()` | A 2-of-3 of team wallets is not decentralization |
| SPL mint | mint authority, freeze authority, supply | A live mint authority means supply is not fixed |
| Oracles | feed address, heartbeat, deviation, TWAP window, fallback | Liquidation and peg risk |

## Read-only on-chain commands

Use only view calls. Never pass `--private-key`, never `cast send`, never sign. The RPC URL comes from the user.

```bash
export RPC="<user-provided RPC URL>"
cast call  <token> "totalSupply()(uint256)" --rpc-url "$RPC"
cast call  <token> "decimals()(uint8)" --rpc-url "$RPC"
cast call  <token> "owner()(address)" --rpc-url "$RPC"
cast call  <token> "cap()(uint256)" --rpc-url "$RPC"
cast call  <token> "balanceOf(address)(uint256)" <vesting-wallet> --rpc-url "$RPC"
cast call  <vesting> "start()(uint64)" --rpc-url "$RPC"
cast call  <vesting> "duration()(uint64)" --rpc-url "$RPC"
cast call  <timelock> "getMinDelay()(uint256)" --rpc-url "$RPC"
cast call  <safe> "getThreshold()(uint256)" --rpc-url "$RPC"
cast call  <safe> "getOwners()(address[])" --rpc-url "$RPC"

# EIP-1967 proxy admin and implementation slots
cast storage <proxy> 0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103 --rpc-url "$RPC"
cast storage <proxy> 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc --rpc-url "$RPC"
```

Without `cast` or an RPC: use the explorer's verified source and "Read contract" tab, and cite the explorer URL. Solana: `spl-token display <mint>` (read-only) or the explorer's mint page for authorities and supply.

Holder concentration: the explorer's holder list or an analytics query. Label known contracts (vesting, staking, treasury, exchanges, bridges) before computing concentration; a CEX hot wallet is many holders, a vesting contract is one.

## Common doc-vs-code mismatches

| Doc says | Code often does | Check |
|----------|-----------------|-------|
| "Fixed supply" | `mint` behind `onlyOwner` or a role, or an upgradeable proxy | Every `_mint` call site and the proxy admin |
| "Team tokens vested 4 years" | Tokens sit in a multisig; vesting is a promise | Balance of the vesting contract, not the docs |
| "1-year cliff" | Base `VestingWallet` has no cliff: linear from `start` | OZ version and constructor args |
| "Fees are burned" | Fees sent to treasury, or to `0xdEaD` (float only) | `feeRecipient` and the transfer target |
| "50% of revenue to stakers" | Split is a setter with no bound | Setter, bound, and timelock |
| "Emissions end after 4 years" | `notifyRewardAmount` can be called forever | Who can call it and with what cap |
| "Governance controls the treasury" | Multisig can execute without the Governor | Safe owners and timelock proposer role |
| "Immutable" | Implementation behind a proxy, or `selfdestruct`/`delegatecall` admin path | Proxy slots and admin functions |
| "Total allocations 100%" | Constructor mints to buckets summing to ≠ cap | Sum of constructor / deploy-script mints |
