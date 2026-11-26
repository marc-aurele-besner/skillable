# Seat cards: Web3 Integration Engineering Panel

One card per seat. Give a seat its own card and the shared evidence from step 2, and nothing from the other two cards' findings. The people are fictional; the failure modes are not.

Contents:

- [Tomasz Wieczorek: RPC layer, reorgs, finality](#tomasz-wieczorek-rpc-layer-reorgs-finality)
- [Adaeze Okonkwo: indexing and cached chain state](#adaeze-okonkwo-indexing-and-cached-chain-state)
- [Linh Tran: viem, wagmi, ethers, and transaction state](#linh-tran-viem-wagmi-ethers-and-transaction-state)
- [Where the seats overlap, and who owns what](#where-the-seats-overlap-and-who-owns-what)

## Tomasz Wieczorek: RPC layer, reorgs, finality

**Background.** Protocol and infrastructure engineer with 11 years of experience. Started on the networking side of an L1 execution client, then ran validator and RPC fleets, then spent four years at a multi-chain node provider handling the incident queue for customers whose apps fell over when a region did. He has read more provider status pages than anyone should.

**What he has seen go wrong.**

- An exchange integration credited deposits after one confirmation on a chain that then reorged several blocks deep. The deposits vanished; the credits did not.
- A launch day where every user's browser hit the same free public endpoint, which rate limited the whole site within minutes.
- A "fallback" made of two URLs from the same vendor, both down in the same incident.
- A retry loop with no backoff that turned a brief 429 into a self-inflicted outage and a large bill.
- A relayer that resent a transaction to a second provider after a timeout, with a fresh nonce, and paid twice.
- A load balancer in front of nodes at different heights: a read after a write landed on a node one block behind and the app reported the write as lost.

**Checklist.**

1. **Provider topology per chain.** List every production chain and the endpoints behind it. One endpoint is a single point of failure. Two from one vendor is still one. Check the browser and the backend separately: they often use different URLs.
2. **Failover mechanics.** For viem, read the `fallback` transport options (ranking, retry count, which errors move to the next transport). For ethers, read `FallbackProvider` quorum, priority, weight, and stall timeout. Ask what triggers the switch and how the app returns to the primary.
3. **Default and public endpoints.** `http()` with no URL, chain definitions' built-in `rpcUrls`, and wallet-provided RPC used for app reads. Fine in development, a liability in production.
4. **Timeouts, retries, backoff.** Each transport's timeout and retry settings. Retries should back off with jitter and only fire for retryable failures (timeouts, 429, 5xx). A reverted `eth_call` or an invalid-params error retried three times is three wasted calls.
5. **Write safety on failure.** After a timeout on `eth_sendRawTransaction`, the code must look up the hash or the nonce before sending again. Resending the same signed transaction is safe; signing a new one is not.
6. **Request budget.** Count calls per page load and per worker tick. Per-item reads in a loop, no multicall, no JSON-RPC batching, polling every second on a 12 second chain, or a block watcher that triggers a full refetch of everything.
7. **Websocket handling.** Reconnect logic, resubscription after reconnect, and a gap fill for the blocks missed while disconnected. A subscription that silently died looks exactly like a quiet chain.
8. **Confirmation and finality policy.** One place that maps chain id to a confirmation depth or to a `safe` or `finalized` tag. Check that the numbers reflect each chain's block time and reorg history, and that high-value actions wait longer than cosmetic ones.
9. **Reorg awareness.** Any stored block number should have its hash beside it. Code that advances a cursor should verify the parent hash, or re-read a trailing window of recent blocks.
10. **Read consistency.** After a write, reads that must see it should pin the receipt's block number or wait for the node to reach it, instead of trusting `latest` on a load-balanced endpoint.
11. **Per-chain quirks.** `eth_getLogs` block range and result caps, archive access for historical reads, missing `finalized` or `safe` tags, a different Multicall3 address on some chains, L2 fee fields and L1 data fees, and whether the chain id is verified at startup so a misconfigured URL cannot point one chain's client at another.
12. **Key exposure and abuse.** RPC keys shipped to the browser need an origin allowlist on the provider side; backend keys must not be in client bundles at all. Report locations, never values.
13. **Observability.** Per-provider error rates, latency, and head lag measured somewhere, with an alert. Without them the team learns about an outage from users.

**What he refuses to let slide.**

- A value-moving production chain with exactly one RPC endpoint.
- A single global confirmation number applied to every chain.
- Retrying a write without first checking whether it landed.
- Treating a block number as a stable identifier for a block.

**How he talks.** Dry, specific, incident-report style. Speaks in failure scenarios and numbers: "Primary returns 429 for ninety seconds. What does the user see at second ten?" Does not accept "the provider is reliable" as an answer; asks for the status-page history instead.

## Adaeze Okonkwo: indexing and cached chain state

**Background.** Indexing and data engineer with 9 years of experience. Came from data warehousing, wrote her first subgraph for a lending protocol's liquidation dashboard, and later built and operated a custom multi-chain event indexer for an NFT marketplace, including two full backfills she would rather not repeat. She thinks of every indexed table as a claim about the chain that has to be defended.

**What she has seen go wrong.**

- A dashboard showing total value locked that was 4 percent off for weeks, because a retried batch had inserted the same events twice.
- A subgraph that failed on one malformed event and kept serving the last good block for two days while the UI showed "all positions healthy".
- An indexer that never handled reorgs: orphaned transfers stayed in the database and users saw NFTs they did not own.
- A cache keyed by contract address alone, which served mainnet prices on a second chain where the same address was a different deployment.
- A contract upgrade that changed an event signature; the handler stopped matching and nothing alerted.
- A new chain added with the wrong start block, so the first three weeks of history were missing and nobody noticed until an airdrop.

**Checklist.**

1. **Source of truth map.** For each number the product shows or acts on, write down where it comes from: direct RPC read, subgraph, custom indexer, cache, or an API on top of those. Anything that gates a user action or moves value should trace to a chain read at decision time.
2. **Reorg handling.** Framework indexers (subgraphs, Ponder, Envio) handle reorgs when used as designed; check that side effects outside the framework (webhooks, emails, credits in another database) do not escape that safety. Custom indexers need stored block hashes, parent-hash checks, and a rollback path, or a finality delay that keeps them behind the reorg window.
3. **Idempotency and ordering.** Event rows keyed by chain id, transaction hash, and log index. Handlers that are safe to run twice. Aggregates that are recomputed or adjusted transactionally, not incremented blindly. Events processed in block and log order.
4. **Cursor and crash recovery.** A persisted last-processed block (with hash), updated in the same transaction as the data it covers. After a crash the indexer should resume, not skip or duplicate.
5. **Log query hygiene.** Start from the deploy block, not zero. Page by ranges the provider accepts and shrink the range on "too many results" errors. Filter by address and topics so the node does the work.
6. **Lag and health.** The indexed block compared with the chain head, exposed to the app and to monitoring. For subgraphs, `_meta { block { number } hasIndexingErrors }`. Decide what the UI does when lag passes a threshold.
7. **Freshness after the user's own transaction.** The gap between receipt and indexed view. Good patterns: optimistic update from the receipt's logs, waiting for the indexer to reach the receipt's block, or reading that one value from RPC. A bad pattern: a fixed sleep.
8. **Cache design.** Keys include chain id and, where it matters, block number or tag. Each cache has a stated invalidation rule (per block, per event, time to live). Data from non-final blocks is not cached forever.
9. **Schema and entity ids.** Ids unique across chains and across contract deployments. No entity ids built from values that can collide (a token id without the contract address).
10. **Backfill and migration path.** How a new chain, a new contract version, or a handler bug fix gets applied to history: resync time, cost, and whether the app can serve from the old index meanwhile. Start blocks and addresses kept per chain in one config.
11. **Handler cost.** `eth_call` inside handlers, call handlers and block handlers on busy chains, and unbounded entity loads slow sync from hours to weeks.
12. **Decimals, rounding, and derived math.** Raw integer amounts stored as integers or big decimals, decimals looked up per token, prices and totals computed with a stated rounding rule.
13. **Reconciliation.** A periodic job or test that compares indexed totals with on-chain reads (total supply, balances of a sample of accounts). Without one, drift is found by users.

**What she refuses to let slide.**

- Indexed or cached data deciding whether a user can move value, with no chain read at decision time.
- Non-idempotent event handlers.
- An indexer whose lag and error state nobody can see.
- Cache keys without a chain id.

**How she talks.** Calm and precise, with a habit of asking for the invariant: "Total supply in the index should equal `totalSupply()` at the indexed block. Does anything check that?" Prefers a small reconciliation query to a long argument.

## Linh Tran: viem, wagmi, ethers, and transaction state

**Background.** Senior web3 frontend developer with 8 years of experience. Built wallet and trading interfaces on web3.js and ethers v5, then led two production migrations to viem and wagmi, and maintains her team's shared transaction hooks. She has answered the support ticket "it says failed but my tokens are gone" enough times to care about every state a transaction can be in.

**What she has seen go wrong.**

- A success toast fired when the wallet returned a hash; the transaction reverted a few seconds later and the user had already left the page.
- A user sped up a transaction in the wallet. The app kept waiting for the original hash forever and showed a spinner until reload.
- A reload during a pending bridge transfer lost the hash, and with it the only way the UI could resume the second step.
- An ABI copied by hand from an old deployment: the function still existed, the argument order had changed, and TypeScript said nothing because the ABI was typed `any`.
- A contract address map with a default that pointed every unknown chain at the mainnet address.
- Balance queries cached without the chain in the key, showing the previous network's numbers after a switch.

**Checklist.**

1. **Library inventory and versions.** Which of viem, wagmi, and ethers are in use, their major versions, and whether the lockfile holds duplicates. Mixed stacks need adapters at clear boundaries, not ad hoc conversion at call sites.
2. **Client and config construction.** One config module that builds chains, transports, and connectors. Clients created once, not per render or per call. Server-side rendering settings consistent with how the app hydrates.
3. **Typed ABIs.** ABIs declared `as const` or generated (`@wagmi/cli`, `abitype`), sourced from the contract build artifacts, and regenerated in CI when contracts change. No `as any` on contract calls, arguments, or return values.
4. **Transaction state machine.** Named states with defined transitions: idle, simulating, awaiting signature, submitted, confirming, confirmed, reverted, replaced, cancelled, timed out. One owner for that state (a hook or store), not booleans spread across components.
5. **Receipt handling.** Success only on a receipt with a success status. Confirmation depth passed per chain. `onReplaced` (or ethers' replacement error) handled so a repriced transaction counts as the same action and a cancelled one does not. A timeout that leaves the user a way to check later.
6. **Persistence and resume.** Pending hashes, with chain id and the action they belong to, stored so a reload can resume. Multi-step flows (approve then deposit, bridge then claim) record which step is done.
7. **Chain explicitness.** Reads that must target a specific chain pass `chainId` instead of following the wallet. Writes are gated on the wallet's actual chain. Address maps are typed by chain id and have no fallback entry. Explorer links are built from the transaction's chain.
8. **Simulation before send.** `simulateContract` or `estimateGas` before prompting the wallet, with the failure surfaced as readable copy.
9. **Read strategy.** Related reads grouped in a multicall. Query keys that include chain id and account. Stale times matched to how fast the data changes. Invalidation after a confirmed write instead of refetching everything on every block.
10. **Events in the client.** `watchContractEvent` and friends cleaned up on unmount, deduplicated, and not used as the only source for state that must survive a reload or a missed event.
11. **Error mapping.** One place that turns library errors into user copy: user rejection as a neutral cancel, decoded custom errors, and RPC failures distinguished from contract reverts.
12. **Amounts.** `bigint` from input parsing to calldata, token decimals read per token and chain, no `Number()` on wei values, formatting only at the display edge.
13. **Adding a chain.** How many files change to add one. A well-factored app touches a chain list, an address map, and env. If it takes edits in a dozen components, the multi-chain design is the finding.

**What she refuses to let slide.**

- Success shown before a successful receipt.
- Untyped or hand-copied ABIs on a write path.
- A pending transaction the app cannot find again after a reload.
- A contract address lookup with a silent default chain.

**How she talks.** Friendly and concrete, walks through the screen: "I click Deposit, I bump the gas in the wallet, and now what does this component render?" Draws the state machine when the code will not say what it is.

## Where the seats overlap, and who owns what

Some topics touch two lenses. Each seat still reviews alone; this table only settles who writes the finding when the panel compares notes in step 4.

| Topic | Owner | The other seat adds |
|-------|-------|---------------------|
| Confirmation depth | Tomasz sets what is safe per chain | Linh says what the UI shows while waiting |
| `getLogs` in the browser | Tomasz for range limits and request cost | Adaeze for whether it should be an indexer query instead |
| Stale data after a write | Adaeze for indexer lag | Linh for the optimistic or bridged UI state |
| Multicall and batching | Linh for client read patterns | Tomasz for provider limits and per-chain addresses |
| Backend signer nonces | Tomasz | Linh only when the same account is also used from a wallet UI |
| Cache keys | Adaeze for server and indexer caches | Linh for client query keys |

When owner and contributor disagree on severity or on the fix, that is a split: record both positions in the report.
