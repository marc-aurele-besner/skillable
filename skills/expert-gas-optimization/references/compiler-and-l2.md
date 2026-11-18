# Compiler settings and L2 cost model

Load this when compiler settings, contract size, or an L2 deployment are in scope.

## Optimizer `runs`

- `runs` is the expected number of times each opcode will execute over the contract's lifetime — not a number of passes.
- Low (`1`–`200`): smaller bytecode, cheaper deploy, slightly dearer calls. Good for factories' children, rarely called contracts, and contracts near the 24 576 B limit.
- High (`10_000`–`1_000_000`): larger bytecode, cheaper calls. Good for hot singletons (tokens, AMMs, routers).
- Measure both sides: run `forge build --sizes` and `forge snapshot` at the current value and at the candidate value, and report deploy delta vs per-call delta with a break-even call count: `deploy_delta / per_call_saving`.
- Per-contract settings: Foundry `additional_compiler_profiles` + `compilation_restrictions` (or Hardhat `overrides`) let a hot contract use high runs while a large one stays small.

Experiment in the throwaway worktree only:

```bash
FOUNDRY_OPTIMIZER_RUNS=1000000 forge snapshot --snap <scratch>/runs-1m.gas-snapshot
FOUNDRY_OPTIMIZER_RUNS=1000000 forge build --sizes
```

## `via_ir`

- Pros: optimizes across functions, often cheaper runtime, removes most "stack too deep" errors.
- Cons: much slower compiles, bytecode differs from what was audited, and a few semantic differences from the legacy pipeline (evaluation order of some expressions, state-variable initialization order with inheritance). See https://docs.soliditylang.org/en/latest/ir/ir-breaking-changes.html.
- Recommend switching only with: a measured win on hot paths, a full green test run including fuzz and invariant suites, and an explicit note that the build must be re-audited before deployment.

## `evm_version` and `solc` version

- Newer EVM versions unlock cheaper opcodes: `PUSH0` (Shanghai, saves 1 gas and 1 byte per zero push), `MCOPY` and transient storage (Cancun).
- Check the **target chain** supports the chosen version before recommending it: some L2s and sidechains lag mainnet forks; `PUSH0` on a chain without Shanghai makes deployment fail.
- Newer `solc` versions improve codegen (e.g. 0.8.22 unchecked loop increments, 0.8.26 custom errors in `require`). Upgrading the compiler is a change requiring a full test run; mention it as Info unless the measured win is material.

## Contract size

- Limits: 24 576 B runtime (EIP-170), 49 152 B initcode (EIP-3860). Some L2s differ (check the chain's docs); zkSync-family chains compile with their own toolchain and cost model.
- Levers, cheapest first: custom errors, removing dead code, lower `runs` for that contract, moving logic to external libraries, splitting into modules, diamond/proxy patterns (heavy — only as a design discussion).

## L2 cost model

On rollups, the user pays **L2 execution gas** plus an **L1 data fee** for posting the transaction's data to Ethereum. Since EIP-4844 (Dencun), most rollups post data as blobs and the L1 data fee fell sharply, but for calldata-heavy transactions it can still dominate. Measure both before choosing what to optimize.

### OP Stack (Optimism, Base, and others)

- L1 data fee depends on the **compressed** size of the signed transaction (Fjord+ uses a FastLZ-based estimate) times the L1 base fee and blob base fee scalars.
- Estimate: call `getL1Fee(bytes)` / `getL1GasUsed(bytes)` on the `GasPriceOracle` predeploy at `0x420000000000000000000000000000000000000F` (e.g. `cast call 0x4200…000F "getL1Fee(bytes)(uint256)" <rlp-tx> --rpc-url <op-rpc>`).

### Arbitrum (One, Nova, Orbit)

- L1 component is charged in L2 gas based on a compressed (brotli) size estimate of the transaction.
- Estimate: `NodeInterface.gasEstimateL1Component` at virtual address `0x00000000000000000000000000000000000000C8` via `eth_call` against an Arbitrum RPC.

### Levers for L1 data cost

- Fewer bytes: tighter argument types encoded by the caller (e.g. pass `uint96` amounts and IDs packed in a `bytes32`, or a custom compact encoding decoded in the contract) — trade-off: more decoding gas on L2 and a less standard ABI.
- More compressible bytes: zeros and repeated patterns compress well; avoid random-looking padding where a shorter encoding exists.
- Avoid sending data the contract can derive or already stores (pass an index, not the full struct; use merkle roots with short proofs).
- Batch many actions per tx to share the fixed overhead.
- Signature aggregation or offchain data with onchain commitments for very data-heavy flows — design-level, report as Info.

When the report targets an L2, give both numbers per finding: `L2 execution Δ` and `L1 data Δ (bytes and estimated fee)`, and say which dominates at current prices.

## Other chains

- zkSync Era and similar zkEVMs use a different compiler (`zksolc`) and gas model (pubdata-based); mainnet opcode costs in [patterns.md](patterns.md) do not transfer. Measure with the chain's own tooling and say the catalog estimates do not apply.
- Polygon PoS, BNB Chain, Avalanche C-Chain: EVM-equivalent opcode pricing; low gas prices mean deploy-size and UX levers often matter more than per-call micro-savings.
</content>
</invoke>
