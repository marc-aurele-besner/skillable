# Gas pattern catalog

Load this during step 4 of the workflow. Each entry gives the **signal** to look for, the **fix**, a **typical saving** (mainnet EVM, Cancun/Prague pricing, optimizer on), and **when it is unsafe or not worth it**. Typical savings are starting points for a hypothesis — the report quotes the **measured** number, never this table.

## Reference costs

| Operation | Gas |
|-----------|-----|
| `SLOAD` cold / warm | 2 100 / 100 |
| `SSTORE` zero → non-zero (cold) | 22 100 |
| `SSTORE` non-zero → non-zero (cold / warm) | 5 000 / 2 900 |
| `SSTORE` no-op (same value, warm) | 100 |
| Refund for clearing a slot to zero | 4 800 (capped at 1/5 of tx gas, EIP-3529) |
| `TLOAD` / `TSTORE` (EIP-1153) | 100 / 100 |
| Cold account access (`CALL`, `BALANCE`, `EXTCODE*`) / warm | 2 600 / 100 |
| Calldata byte zero / non-zero | 4 / 16 (EIP-7623 floor: 10 / 40 for data-heavy txs) |
| Memory | 3 per word + words² / 512 |
| `LOG` | 375 + 375 per topic + 8 per data byte |
| Contract creation | 32 000 + 200 per runtime byte |
| Value-transfer `CALL` surcharge | 9 000 (2 300 stipend) |

## Storage

### S1 — Pack fields that are read or written together
- **Signal:** a struct or set of state variables spanning more slots than needed (`forge inspect <Contract> storage-layout`), where several fields are touched in the same call.
- **Fix:** order fields so co-accessed small types share a 32-byte slot (`uint128 + uint64 + uint32 + bool`, `address + uint96`).
- **Typical saving:** one cold `SLOAD` (~2 000) per extra read; ~2 900–20 000 per extra write avoided.
- **Unsafe / not worth it:** **upgradeable contracts** — reordering or retyping existing variables corrupts storage; only append, or use ERC-7201 namespaced storage for new fields. Packing fields that are written in *different* transactions saves nothing and adds masking ops. Narrowing a type below its real range (e.g. timestamps in `uint32` past 2106, token amounts in `uint64`) is a correctness bug.

### S2 — Cache storage reads in a local variable
- **Signal:** the same storage slot read more than once in a function, especially inside a loop (`for (...; i < arr.length; ...)` on a storage array, `s.total += x` in a loop).
- **Fix:** read once into a stack/memory variable, operate on it, write back once.
- **Typical saving:** ~100 per repeated warm read; ~2 900+ per avoided repeated write in a loop.
- **Unsafe:** when an external call in between can change the slot (reentrancy or callback re-reading stale state), or when the write-back is skipped on an early-return path.

### S3 — `constant` and `immutable`
- **Signal:** state variables set once (in the declaration or constructor) and never written again.
- **Fix:** `constant` for compile-time values, `immutable` for constructor-time values.
- **Typical saving:** ~2 100 per cold read → ~3.
- **Unsafe:** behind a proxy, `immutable` values live in the implementation bytecode, not proxy storage — every proxy shares them, and they are not set by `initialize`. Values that governance must be able to change must stay in storage.

### S4 — Avoid zero → non-zero writes for flags and counters
- **Signal:** a boolean or status slot toggled between `0` and `1` repeatedly (lock flags, per-epoch markers).
- **Fix:** use `1`/`2` (as OpenZeppelin `ReentrancyGuard` does), or transient storage for intra-transaction flags (S5).
- **Typical saving:** ~17 100 per toggle (22 100 → 5 000).
- **Unsafe:** when other code checks `== 0` / `!= 0` semantics or default-initialized state.

### S5 — Transient storage for intra-transaction state
- **Signal:** reentrancy locks, temporary approvals, or callback context written and cleared within one transaction.
- **Fix:** `transient` state variables (Solidity ≥ 0.8.28 for value types) or `tstore`/`tload` in assembly; OpenZeppelin `ReentrancyGuardTransient`.
- **Typical saving:** ~2 000–20 000 per lock cycle.
- **Unsafe:** target chain lacks Cancun (check `evm_version` and the chain). Transient values persist across calls **within the same transaction** — a value not cleared at the end of a call leaks into later calls in a multicall or bundle. Never use it for state that must survive the transaction.

### S6 — Bitmaps for many booleans
- **Signal:** `mapping(uint256 => bool)` for claim flags, nonces, airdrop indices.
- **Fix:** 256 flags per slot (OpenZeppelin `BitMaps`, Solady `LibBitmap`).
- **Typical saving:** ~17 000 per flag when neighbours already set the slot non-zero; best for sequential IDs.
- **Not worth it:** sparse, random keys — every flag still lands in its own slot.

### S7 — Do not copy whole structs from storage to memory
- **Signal:** `Position memory p = positions[id];` followed by use of one or two fields.
- **Fix:** `Position storage p = positions[id];` and read only the fields used.
- **Typical saving:** ~2 100 per unused slot avoided.
- **Unsafe:** when the code relies on a snapshot that must not change after a later write in the same function.

### S8 — Large immutable data as code (SSTORE2)
- **Signal:** large blobs (> ~100 bytes) written once and read many times (metadata, lookup tables, merkle leaves).
- **Fix:** deploy as contract bytecode and read with `EXTCODECOPY` (Solady `SSTORE2`).
- **Typical saving:** large for writes (200/byte vs 20 000/32 bytes) and for reads above a few slots.
- **Not worth it:** data that changes, or small values; adds a deploy per blob and an external code read (2 600 cold).

### S9 — Clear storage that is no longer needed
- **Signal:** entries consumed and never read again (filled orders, expired claims) left non-zero.
- **Fix:** `delete` them in the consuming call.
- **Typical saving:** 4 800 refund per slot (capped).
- **Unsafe:** when the value is still needed to prevent replay (a "used" marker must stay set).

## Calldata, memory, and ABI

### C1 — `calldata` for read-only external parameters
- **Signal:** `external`/`public` function with `bytes memory`, `string memory`, or `T[] memory` parameters that are never modified.
- **Fix:** `calldata`.
- **Typical saving:** proportional to size; hundreds to thousands for arrays.
- **Unsafe:** none for read-only use; the function cannot modify the argument and internal callers must pass calldata.

### C2 — Avoid repeated memory expansion
- **Signal:** `abi.encodePacked` / `bytes.concat` / array growth in loops, or allocating a large memory array then using a few elements.
- **Fix:** pre-size allocations, encode once, or stream.
- **Typical saving:** memory cost is quadratic; large loops save thousands.

### C3 — Cheaper hashing and encoding
- **Signal:** `keccak256(abi.encode(a, b))` on a hot path.
- **Fix:** keep it unless profiling shows it matters; Solady `EfficientHashLib` or a short assembly block saves ~100–300.
- **Unsafe:** switching `abi.encode` ↔ `abi.encodePacked` changes the hash (breaks signatures, storage keys, EIP-712 digests) and `encodePacked` with two dynamic types is collision-prone.

## Control flow and loops

### L1 — Unbounded loops over storage
- **Signal:** a loop whose bound is a storage array or set that users can grow (`holders`, `stakers`, `pendingWithdrawals`).
- **Fix:** pagination (`start`, `count`), pull-over-push, or per-user accounting (cumulative reward-per-share).
- **Typical saving:** turns O(n) per call into O(1); removes a block-gas-limit DoS.
- **Note:** this is primarily a **liveness/security** issue — report the DoS to the security reviewer's scope and keep the gas angle as context.

### L2 — Loop counter `unchecked` increments
- **Signal:** `unchecked { ++i; }` boilerplate, or a suggestion to add it.
- **Fix:** on Solidity **≥ 0.8.22** the compiler already omits the overflow check for simple `for` loop counters — do not suggest it there. On older compilers it saves ~30–60 per iteration.
- **Unsafe:** using `unchecked` on any arithmetic other than a provably bounded counter.

### L3 — Short-circuit and order checks
- **Signal:** expensive checks (storage reads, external calls) before cheap ones (argument checks) in `require`/`if` chains.
- **Fix:** cheapest, most-likely-to-fail first.
- **Typical saving:** cost of the skipped check on the failing path; often small.
- **Unsafe:** reordering checks with side effects, or moving an access-control check after logic that reverts with a more informative error (information leak is rarely an issue, but checks-effects-interactions order must stay intact).

### L4 — `unchecked` arithmetic with proven bounds
- **Signal:** subtraction right after a `require(a >= b)`, or additions bounded by a known total supply.
- **Fix:** wrap only that operation in `unchecked`, with a comment stating the invariant.
- **Typical saving:** ~20–40 per operation.
- **Unsafe:** whenever the bound is not proven in the same function — overflow bugs are critical. Defer to the security reviewer when unsure.

## Errors, events, and logs

### E1 — Custom errors instead of revert strings
- **Signal:** `require(cond, "long message")` or `revert("...")`.
- **Fix:** `error InsufficientBalance(uint256 have, uint256 want);` with `revert InsufficientBalance(...)` or `require(cond, InsufficientBalance(...))` (Solidity ≥ 0.8.26 via-IR, ≥ 0.8.27 legacy).
- **Typical saving:** deploy size (~ a few hundred bytes per distinct string, 200 gas/byte) and ~50–100 on the revert path.
- **Not worth it:** when integrators or frontends parse the revert string — changing it is an ABI change; mention it as a trade-off.

### E2 — Events instead of storage for offchain-only data
- **Signal:** storage arrays or mappings written but never read onchain (history logs, audit trails).
- **Fix:** emit an event and index it offchain.
- **Typical saving:** ~20 000 per slot written → ~375 + 375 per topic + 8 per byte.
- **Unsafe:** any contract (or future upgrade) that needs the data onchain; events cannot be read by contracts.

### E3 — Trim event payloads
- **Signal:** events re-emitting data already derivable (full structs, `msg.sender` twice), or indexing large values.
- **Fix:** emit only what indexers need; index only fields filtered on.
- **Typical saving:** 8 per byte, 375 per topic removed.
- **Unsafe:** removing fields indexers, subgraphs, or monitoring depend on — confirm consumers first.

## External calls and batching

### X1 — Batch user actions
- **Signal:** flows requiring several transactions (approve + deposit, claim per pool).
- **Fix:** `multicall`, permit (EIP-2612 / Permit2), or a batch entry point.
- **Typical saving:** 21 000 base cost per avoided tx plus cold-access warm-up sharing.
- **Unsafe:** `delegatecall`-based multicall in a `payable` contract reuses `msg.value` in every sub-call (double spend); multicall combined with transient storage or `msg.sender`-based trusted forwarders (ERC-2771) has known spoofing pitfalls. Defer to the security reviewer before recommending.

### X2 — Avoid redundant external calls
- **Signal:** the same external view called several times (`token.balanceOf(this)`, `oracle.latestRoundData()`).
- **Fix:** call once, cache the result.
- **Typical saving:** ~2 600 cold / ~100 warm + callee execution per avoided call.
- **Unsafe:** when the value can change between the calls by design (balance before/after a transfer to measure fee-on-transfer tokens).

### X3 — Minimal proxies for many instances
- **Signal:** a factory deploying full copies of the same contract.
- **Fix:** EIP-1167 clones or ERC-1167-with-immutable-args (Solady `LibClone`).
- **Typical saving:** deploy cost from hundreds of thousands to ~40 000–60 000.
- **Trade-off:** each call pays an extra `DELEGATECALL` (~100–2 700); not worth it for instances called very often. Clones need an initializer — an uninitialized clone is a security issue.

## Deploy and bytecode

### D1 — Contract size
- **Signal:** `forge build --sizes` shows a contract near or over 24 576 bytes, or high deploy cost on a frequently deployed contract.
- **Fix:** see [compiler-and-l2.md](compiler-and-l2.md#contract-size).

### D2 — Library linking vs inlining
- **Signal:** large internal library functions duplicated across contracts.
- **Fix:** `public`/`external` library functions are deployed once and called via `DELEGATECALL` — smaller bytecode, dearer calls. Measure both.

## Micro-optimizations — usually do not report

These are real but tiny, often erased by the optimizer, and they hurt readability. Mention them only when the user asks for exhaustive micro-tuning, and never as Medium or above:

- `++i` vs `i++` (~5 with optimizer, often 0).
- `!= 0` vs `> 0` for unsigned integers (0–6).
- `payable` on admin functions to skip the `CALLVALUE` check (~24) — risks locked ETH; do not recommend.
- Function selector ordering / name mining (~22 per position) — breaks readability and tooling.
- Assembly rewrites of plain Solidity (`mstore`-based `abi.encode`, assembly `address(0)` checks) — save tens of gas, add memory-safety risk, and need dedicated tests.
- `uint8` local variables "to save gas" — usually costs more (masking); the stack is 32 bytes wide.

## Unsafe "optimizations" — always reject

List these in the report's "Rejected for security" section if the code or a previous suggestion uses them:

- Removing reentrancy guards, access control, `nonReentrant` on functions with external calls, or checks-effects-interactions ordering.
- Replacing `SafeERC20` with raw `transfer`/`transferFrom` calls (non-standard tokens return nothing or `false`).
- Dropping overflow checks without a proven bound.
- `tx.origin` instead of `msg.sender`.
- Skipping signature `s`-value malleability checks, nonce checks, deadline or chain-id checks in signed messages.
- Unbounded `assembly` that ignores the free-memory pointer or is not `memory-safe`.
- Storage-layout changes on a deployed upgradeable contract.
- `selfdestruct`-based patterns (semantics changed in Cancun, EIP-6780).
</content>
</invoke>
