# dApp frontend and integration checklist

Deep checklist behind step 5 of the skill. Each section lists what to look for, the code that signals it, the failure it causes, and the fix. Score every candidate with the severity scale in SKILL.md, then run it through the verification gate before it becomes a finding. Library-specific API facts (wagmi v1 vs v2, ethers v5 vs v6, viem quirks) live in [library-gotchas.md](library-gotchas.md).

## How to use this file

1. Load only the sections the target touches (SKILL.md step 2 maps the surface).
2. Read every lead with the file open: the line alone hides the guard three lines up.
3. For each candidate, write the user-visible failure: wallet state or input, then wrong outcome. No scenario, no finding.
4. Check "Do not report" at the bottom before writing anything up.

---

## 1. Wallet connection and session

| Look for | Signal in code | Failure | Fix |
|----------|----------------|---------|-----|
| Single injected provider assumed | `window.ethereum` read directly, `window.ethereum.isMetaMask` branches | With two extensions installed the last one to load wins; the user connects the wrong wallet | Use the connector library's EIP-6963 discovery (wagmi `injected()` with multi-injected discovery on by default in v2, RainbowKit/AppKit wallet lists) |
| Reconnect state treated as disconnected | Gating on `isConnected` only; `status === 'reconnecting'` or `'connecting'` not handled | Page flashes "Connect wallet", redirects away, or fires a disconnected-only effect on every reload | Treat `reconnecting` as loading; render a skeleton until status settles |
| SSR hydration mismatch | Next.js/Remix app with wagmi config lacking `ssr: true`, no `cookieStorage` + `cookieToInitialState` | Hydration errors, the connect button flickers, address-dependent markup differs server vs client | `createConfig({ ssr: true, storage: createStorage({ storage: cookieStorage }) })` and pass `initialState` to `WagmiProvider` |
| Cached data not keyed by account and chain | react-query keys or SWR keys without `address` and `chainId`; app-level store not cleared on change | After switching account, the UI shows the previous account's balance, allowance, or positions, and the user acts on it | Include `address` and `chainId` in every key; reset local stores in `useAccountEffect` / `accountsChanged` / `chainChanged` |
| Disconnect leaves state | Disconnect handler only calls `disconnect()` | Next user on a shared machine sees the previous user's positions; SIWE session stays valid | Clear app state and end the SIWE/backend session on disconnect |
| Address displayed truncated only at the decision point | Confirm dialog shows `0x1234…abcd` for a recipient or spender | Address-poisoning lookalikes pass visual check | Show full checksummed address (or ENS + full address on hover/expand) where the user commits |
| WalletConnect metadata | `metadata.url` not the deployed origin, or `projectId` with no domain allowlist in the Reown dashboard | Wallets show "unverified/mismatch" warnings (Verify API); a stolen projectId burns your quota | Set `metadata.url` to the real origin; allowlist domains in the dashboard. A public `projectId` itself is not a secret |
| WalletConnect v1 | `@walletconnect/web3-provider`, `@walletconnect/client`, `web3modal` v1 | Connection never completes: the v1 relay is shut down | Migrate to WalletConnect v2 via wagmi `walletConnect()`, RainbowKit, or Reown AppKit |
| Mobile and in-app browsers | No handling for "no injected provider" on mobile Safari/Chrome | Mobile users see a dead "Connect" button | Offer WalletConnect / deep links when no injected provider exists |
| Runtime-loaded wallet code | Script tag or loader pulling connect-kit code from a CDN at runtime | A compromised CDN package drains users (the Dec 2023 Ledger connect-kit incident) | Bundle pinned versions; lockfile; no runtime CDN loaders for wallet code |

## 2. Chain handling and switching

| Look for | Signal | Failure | Fix |
|----------|--------|---------|-----|
| Write sent on the wrong chain | `writeContract` without `chainId`, no check of `useAccount().chainId` vs the contract's chain | Tx goes to the same address on another chain: lost funds if the address is an EOA or a different contract there | Gate the action on chain match; pass `chainId` (wagmi asserts it); prompt `switchChain` first |
| Unsupported chain not represented | Code reads `useAccount().chain!.id` or assumes `chain` is defined | Crash or undefined-address calls when the wallet is on a chain not in config | Handle `chain === undefined` (wagmi v2) as "unsupported network" with a switch button |
| Contract address map not keyed by chain | A single `CONTRACT_ADDRESS` constant, or `addresses[chainId]` with silent fallback to mainnet | Testnet UI calls mainnet addresses, or calls an unrelated contract on an L2 | `Record<ChainId, Address>`; throw or block UI on a missing entry; never fall back |
| Switch rejection or missing chain | `switchChain` with no catch; no `addEthereumChain` path | User rejects and the UI hangs in "Switching…" forever; wallets without the chain get error 4902 | Catch rejection; wagmi `switchChain` adds the chain from config; reset the spinner on every path |
| Explorer links | `https://etherscan.io/tx/${hash}` hard-coded | Links 404 on every other chain | Build from `chain.blockExplorers.default.url` of the chain the tx was sent on |
| Reads on the wallet's chain instead of the app's | Reads use the connected wallet's provider for a chain-specific dashboard | Dashboard shows empty data when the wallet is on another chain | Reads use app transports with explicit `chainId`; only writes need the wallet's chain |

## 3. Transaction lifecycle UX

Every write should move through visible, distinct states: **idle → preparing (simulate/estimate) → awaiting signature → submitted (hash known) → pending (n of N confirmations) → confirmed | reverted | replaced | dropped**. Map each state the code renders, then look for the missing ones.

| Look for | Signal | Failure | Fix |
|----------|--------|---------|-----|
| "Success" on signature | Toast or redirect after `writeContract`/`sendTransaction` resolves, or on `useWriteContract().isSuccess` | User is told it worked; the tx then reverts or is dropped | Success only after a receipt with success status |
| Reverted receipt treated as success | Raw viem `waitForTransactionReceipt` result used without `receipt.status === 'success'` | A reverted tx shows as confirmed | Check `status`; decode the revert (section 5) |
| Replacement not handled | No `onReplaced` (viem) or `TRANSACTION_REPLACED` catch (ethers) | User speeds up or cancels in the wallet; the app waits on the old hash forever, or shows failure for a tx that succeeded as a replacement | Handle `repriced` as success-tracking of the new hash, `cancelled` as cancelled, `replaced` as "replaced by another tx" |
| No preflight simulation | Write called without `simulateContract`/`useSimulateContract` (viem/wagmi) or `staticCall` (ethers v6) | Wallet shows an opaque "this tx will likely fail" or the user pays gas for a revert | Simulate first; disable the button with the decoded reason when simulation fails |
| Stale simulation | `useSimulateContract` result reused after inputs changed or many blocks later | Submits a request built for old args or old allowance | Key simulation on all inputs; re-simulate on submit for value-moving actions |
| Double submit | Button not disabled during `awaiting signature` and `pending` | Two identical txs; double spend of the user's balance | Disable on `isPending`; idempotency key for backend-relayed actions |
| Pending tx lost on reload | Hash kept only in component state | User refreshes and the app forgets a pending deposit; they resend | Persist `{hash, chainId, from, kind}` and resume waiting on load |
| No timeout or "dropped" state | `wait()` with no timeout; no UI past N minutes | Spinner forever for a tx evicted from the mempool | Timeout with "still pending: check explorer / speed up in wallet" and keep polling in background |
| Rejection shown as an error | User-rejected request (code 4001 / `UserRejectedRequestError` / `ACTION_REJECTED`) shown as red error and sent to error tracking | Noise in Sentry; users think something broke | Treat rejection as a neutral cancel; do not log as error |
| Dependent tx sent before its predecessor confirms | `approve` then immediately `deposit` without waiting for the approve receipt | `deposit` estimation reverts on insufficient allowance, or wallet queues it with a stale estimate | Await approve receipt (success) before preparing the next write, or batch with EIP-5792 `sendCalls` when the wallet supports it |
| Confirmation depth | High-value flows (bridges, deposits credited off-chain) treat 1 confirmation as final | A reorg removes the tx after the UI credited it | Wait for `safe`/`finalized` or N confirmations for anything credited off-chain; label "soft-confirmed" on L2 |
| Data not refreshed after confirm | Balances/allowances not invalidated after receipt | UI shows the old balance; user retries | Invalidate the affected query keys on receipt |

## 4. Signing requests (EIP-712, personal_sign, SIWE, permits)

| Look for | Signal | Failure | Fix |
|----------|--------|---------|-----|
| `eth_sign` | `request({ method: 'eth_sign' })` | Signs an arbitrary hash: indistinguishable from signing a transaction; most wallets block or red-flag it | Use EIP-712 typed data or `personal_sign` with a readable message |
| Blind `personal_sign` | `signMessage({ message: keccak256(...) })` or a hex blob | The user cannot read what they authorize; phishing sites use the same UX | Sign typed data, or a human-readable message |
| Typed data domain incomplete | `domain` missing `chainId` or `verifyingContract`, or `chainId` hard-coded to 1 | Cross-chain and cross-contract replay; wallet rejects when `chainId` mismatches the active chain | Domain from the contract's `eip712Domain()` (EIP-5267) or the deployment config, with the active `chainId` |
| Unreadable typed data | Field names like `a`, `data`, `payload` of `bytes`; amounts as raw wei without token context | User signs something they cannot evaluate | Named fields; separate `token`, `spender`, `amount`, `deadline`; show a summary in the app before the wallet opens |
| Permit / Permit2 with unsafe defaults | `deadline` far in the future (`maxUint256`, years); `amount` max; Permit2 `expiration` max | A leaked signature is valid forever for unlimited amount | Exact amount, deadline minutes away, short Permit2 expiration; show these values in the UI |
| SIWE (EIP-4361) | Nonce generated client-side; no `domain`/`uri`/`chainId`/`expirationTime`; server does not check nonce single-use | Replayable login signatures; phishing on a lookalike domain works | Server-issued single-use nonce; verify domain, chainId, expiry server-side |
| Signature verification for smart accounts | Backend or frontend verifies with ecrecover-only (`ethers.verifyMessage`, `recoverMessageAddress`) | Safe, ERC-4337, and counterfactual smart-account users cannot log in | Verify with a public client that supports ERC-1271 and ERC-6492 (viem `publicClient.verifyMessage` / `verifyTypedData`) |
| Signature of the wrong account | Signs with a cached address after the user switched accounts | Backend binds the session to an account the user no longer controls in the UI | Read the account at sign time; re-auth on `accountsChanged` |

## 5. Errors and revert decoding

| Look for | Signal | Failure | Fix |
|----------|--------|---------|-----|
| Raw messages shown | `toast(error.message)`, `JSON.stringify(error)` in UI | Wall of RPC JSON, request bodies, or stack details; sometimes the RPC URL with its key | viem: show `error.shortMessage`; ethers v6: `error.shortMessage` / `error.reason`; map known cases to plain copy |
| Custom errors not decoded | ABI passed to the client lacks the `error` entries (and errors of libraries/inherited contracts) | User sees "execution reverted" with no reason | Include full ABI with errors; viem `err.walk(e => e instanceof ContractFunctionRevertedError)` → `data.errorName`, `data.args`; ethers v6 `iface.parseError(err.data)` |
| Panic codes not mapped | `Panic(uint256)` shown as hex | "0x11" means nothing to a user | Map 0x01 assert, 0x11 overflow/underflow, 0x12 division by zero, 0x32 out-of-bounds index to copy |
| Distinct causes collapsed | One "Transaction failed" for every error | User cannot tell rejection, insufficient funds for gas, slippage, and allowance apart | Branch on rejection, `InsufficientFundsError`, decoded custom error, RPC/network error, and unknown |
| Error swallowed | `catch {}` around write/wait | Button resets with no message; the user retries blindly | Surface and log (excluding rejection) |

## 6. Amounts, gas, and fee display

| Look for | Signal | Failure | Fix |
|----------|--------|---------|-----|
| Float math on amounts | `parseFloat(formatUnits(x))` used again in math, `Number(balance)`, `amount * 10 ** decimals` | Precision loss above 2^53 wei; "Max" sends dust-short or more than balance and reverts | Keep `bigint` end to end; `parseUnits(input, decimals)`; format only for display |
| Decimals assumed | `parseEther` / `formatEther` / `1e18` for ERC-20 amounts | USDC (6) and WBTC (8) amounts are off by 10^12 or 10^10 | Read `decimals()` per token (cached); never hard-code 18 for ERC-20 |
| User input parsing | `parseUnits(input)` with locale commas, spaces, scientific notation, or more decimals than the token has | Throws, or silently parses a different number | Normalize and validate input; reject extra decimal places with a message |
| "Max" for native token | Max fills full ETH balance | Tx fails: nothing left for gas | Subtract an estimated fee buffer for native-token max |
| Hard-coded gas limit | `gas: 300000n`, `gasLimit: 500000` | Out-of-gas when state grows, or overpays; fails on chains with different gas schedules (Arbitrum, zkSync) | Estimate; add a modest buffer only where the contract has variable paths |
| Legacy pricing on 1559 chains | `gasPrice` set on writes | Overpays in calm blocks, gets stuck in spikes | Let the wallet set fees, or use `maxFeePerGas` / `maxPriorityFeePerGas` from `estimateFeesPerGas` |
| Fee shown as a single exact number | "Fee: 0.00123 ETH" from `gas * gasPrice` | User is surprised when the wallet shows different; L2 L1-data fee missing so the estimate is far low on OP Stack chains | Show "≈" or "up to" in native and fiat; include L1 data fee on OP Stack (viem op-stack `estimateTotalFee`) |
| Slippage and deadline | Swap UIs with slippage default above a sane bound, or `deadline` = `maxUint256` | Sandwich losses; stale tx executes hours later | Conservative default, user-adjustable, deadline minutes away |
| Amount shown without token context | Balance rendered without symbol/decimals or with wrong token after chain switch | User misreads magnitude | Render with symbol and fixed significant digits; key by chain + token |

## 7. RPC transport, failover, and rate limits

| Look for | Signal | Failure | Fix |
|----------|--------|---------|-----|
| Public RPC in production | wagmi/viem `http()` with no URL; `getDefaultProvider()` | Rate limited (429) under real traffic; reads fail intermittently | Dedicated provider URL per chain |
| No failover | Single `http(url)` per chain | Provider outage takes down the whole dApp | viem `fallback([http(a), http(b)], { rank: true })`; ethers `FallbackProvider` |
| Request fan-out | One `readContract` per row; `useBlockNumber({ watch: true })` in many components; aggressive `refetchInterval` | Hundreds of RPC calls per page view; rate-limit bans | Multicall (`useReadContracts`, `batch: { multicall: true }`), JSON-RPC batching (`http(url, { batch: true })`), one block watcher, sane `pollingInterval` |
| Keyed URL in the client bundle | `NEXT_PUBLIC_ALCHEMY_KEY` / URL with key in source | Anyone can burn your quota | Restrict the key by origin/allowlist in the provider dashboard, or proxy through your backend. This is a cost/availability risk, not a funds risk, unless the key has write/admin scope |
| Retry storms | Custom retry with no backoff, or retries on deterministic reverts | Amplifies a rate limit into a ban; retries a revert forever | Exponential backoff with jitter on 429/5xx/timeouts only; never retry reverts or user rejections |
| WebSocket without reconnect | `webSocket(url)` or ethers `WebSocketProvider` with no reconnect handling | Subscriptions silently die after a drop | Reconnect with backoff, or use HTTP polling with a fallback transport |
| Reads through the wallet | Reads via the injected provider | Reads depend on the user's wallet RPC (often slow or rate-limited) | Reads via app transports; writes via the wallet |

## 8. Events, indexing, and reorgs

| Look for | Signal | Failure | Fix |
|----------|--------|---------|-----|
| Unbounded log range | `getLogs({ fromBlock: 0n })` / `queryFilter(filter, 0)` | Provider rejects ranges over its limit (often 500 to 10k blocks or 10k results); the history view is empty | Start at the deploy block; paginate in chunks; handle "range too large" by halving |
| Reorg removal ignored | Live watcher appends every log; no check of `log.removed` | Events from orphaned blocks stay in the UI or get credited | Drop or revert on `removed: true`; treat logs as tentative until `safe`/`finalized` |
| Duplicates | Merge of polled and pushed logs without a key | Activity feed shows the same transfer twice | Dedupe by `(transactionHash, logIndex)` |
| Filter expiry | `watchContractEvent`, hand-rolled `eth_newFilter` / `eth_getFilterChanges`, or ethers filters on a load-balanced RPC | Filters expire or hit another node: "filter not found", silent stop | Handle `onError`; re-read a bounded `getLogs` range after a filter is recreated (viem `watchContractEvent` recreates it but does not backfill); or poll `getLogs` directly |
| Indexer lag hidden | Subgraph / Ponder / Envio data shown as current | After a confirmed tx, the user's position is missing; they resend | Compare indexer head (`_meta { block { number } }`) to chain head; show "syncing" and optimistically merge the confirmed tx |
| Indexed vs non-indexed filtering | Filtering on a non-indexed arg via `args` | Returns everything or nothing depending on the client | Filter only on indexed params; post-filter the rest |
| Event-sourced balances | Balance derived by summing Transfer events client-side | Drifts with fee-on-transfer, rebasing tokens, missed blocks | Read `balanceOf`; use events for history only |

## 9. Nonce management

| Look for | Signal | Failure | Fix |
|----------|--------|---------|-----|
| Manual nonce in wallet flows | `nonce:` passed to `writeContract` / `sendTransaction` for a connected wallet | Fights the wallet's own nonce tracking; stuck or replaced txs | Let the wallet assign the nonce |
| `latest` instead of `pending` | `getTransactionCount({ blockTag: 'latest' })` in a backend signer | Two quick sends reuse a nonce; the second replaces the first | Use a nonce manager (viem `nonceManager` on the account, ethers `NonceManager`) or `pending`, serialized per signer |
| Concurrent relayer sends | Parallel requests share one hot wallet with no lock | Nonce collisions, gaps that block all later txs | Serialize per signer; persist nonce state; detect and fill gaps |
| Gap after a failed send | Local counter incremented before broadcast succeeded | Every later tx stuck behind a missing nonce | Increment on successful broadcast; resync from `pending` on error |

## 10. Approvals and allowance safety

| Look for | Signal | Failure | Fix |
|----------|--------|---------|-----|
| Unlimited approval by default | `approve(spender, maxUint256)` with no user choice | One spender compromise drains every approving user's whole balance | Default to the exact amount; offer "unlimited" as an explicit, explained opt-in |
| Allowance not checked first | Always sends `approve` | Extra tx and gas every time; confusing double prompt | Read `allowance(owner, spender)`; skip when sufficient |
| Spender from untrusted input | Spender or router address from URL params, API response, or user input | A crafted link gets approvals to an attacker | Spender from a per-chain config constant; verify against known deployments |
| Non-standard tokens | USDT-style token where changing a non-zero allowance reverts; `approve` returning no bool | Approval fails for USDT on mainnet | Reset to 0 first when current allowance is non-zero and token requires it; use a call that tolerates missing return values |
| Operator approvals | `setApprovalForAll(operator, true)` | Grants every NFT in the collection | Warn clearly; prefer single-token `approve`; operator from trusted config |
| Permit support ignored or misused | Two-tx approve flow where the token supports EIP-2612, or a permit signed with max amount and no deadline | Extra tx; or a long-lived unlimited signature | Use permit or Permit2 with exact amounts and short deadlines (section 4) |
| No path to revoke | Unlimited approvals and no revoke UI or link | Users cannot reduce exposure | Show current allowance and a revoke action, or link to a revoke tool |

## 11. Account abstraction (ERC-4337, smart accounts, EIP-5792, EIP-7702)

| Look for | Signal | Failure | Fix |
|----------|--------|---------|-----|
| userOpHash treated as a tx hash | Explorer link or `waitForTransactionReceipt` on the userOpHash | Link 404s; wait never resolves | `waitForUserOperationReceipt`, then use `receipt.receipt.transactionHash` for links |
| Bundle success read as op success | Only the bundle tx status checked | The bundle tx succeeds while the user's op reverted inside it | Check the user operation receipt's `success` and decode the revert reason |
| Owner vs smart-account address confused | Showing or funding the signer EOA when the smart account holds the funds (or vice versa) | User sends funds to the wrong address; balances look empty | One clear "account address"; label the owner/signer separately |
| Counterfactual account | `getCode` used to decide "is a contract", signatures verified with ERC-1271 only | Undeployed accounts fail signature checks and detection | ERC-6492-aware verification; treat undeployed as a valid smart account |
| Paymaster failure | Sponsored flow with no fallback when the paymaster rejects or runs out of balance | Users are stuck with an opaque error | Detect sponsorship failure; offer self-paid gas or a clear message |
| EntryPoint version mismatch | SDK configured for v0.6 while the account or bundler uses v0.7/v0.8 | Every op fails validation | Match EntryPoint version across account, bundler, and paymaster config |
| Session keys | Session key permissions unbounded or with no expiry | A stolen session key acts as the account | Scope by contract, function, value, and expiry |
| Batching without capability check | `sendCalls` assumed supported | Fails for EOAs and wallets without EIP-5792 | `getCapabilities` and a sequential fallback |
| EIP-7702 authorization requested by the dApp | dApp asks the user to sign a 7702 authorization to a contract it chose | Delegates the user's EOA to arbitrary code | Leave 7702 delegation to the wallet; never request authorizations from a dApp page |

## 12. Client-side security boundaries

| Look for | Signal | Failure | Fix |
|----------|--------|---------|-----|
| Key material in the client | `privateKeyToAccount(...)`, mnemonic, or a `*_PUBLIC_*PRIVATE_KEY` env var in browser code | Every visitor gets the key | Move signing to a backend or remove; rotate the key now |
| Asking for seed phrases | Any input that collects a mnemonic or private key | Indistinguishable from phishing | Remove |
| Trusting client checks | Eligibility, price, or allowlist enforced only in the frontend | Bypassed by calling the contract directly | Enforce in the contract or backend; frontend checks are UX only |
| Rendering token metadata | Token names/symbols/NFT metadata rendered as HTML | XSS from an attacker-deployed token | Render as text; sanitize SVG/HTML metadata |

---

## Do not report

- A public WalletConnect `projectId` or a public RPC key that is origin-restricted: not a secret.
- `maxUint256` used as a sentinel in comparisons, or in tests and scripts that never reach users.
- Absence of a feature the dApp does not need (no ERC-4337 checks for a dApp with no smart-account support; no Permit2 for a dApp with no approvals).
- Library defaults that already do the right thing (wagmi `writeContract` with `chainId` already asserts the chain; wagmi's `waitForTransactionReceipt` action already throws on reverted receipts in v2 and v3; ethers `wait()` already throws on status 0).
- Style, naming, or component structure. That is not this skill.
- Contract-level vulnerabilities (reentrancy, access control in Solidity). Mention them once as out of scope, at most.
