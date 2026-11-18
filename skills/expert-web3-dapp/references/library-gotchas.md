# Library gotchas by stack and version

Load this after step 1 of the skill has detected the stack. The same symptom has different causes in different libraries, and a pattern that is a bug in one version is the safe default in another. Before reporting a library behavior, confirm it against the **installed** version (`node_modules/<pkg>/package.json`, or the lockfile), not the range in `package.json`. When in doubt, read the library source in `node_modules` for the function in question; it is the ground truth.

## viem (2.x)

- `waitForTransactionReceipt` **returns** a reverted receipt; it does not throw. Callers must check `receipt.status === 'success'`. Pass `onReplaced` to learn about speed-ups and cancels: `reason` is `'repriced'` (same intent, higher fee: keep tracking `replacedTransaction`'s successor), `'cancelled'` (0-value self-send), or `'replaced'` (different tx at the same nonce). It throws `WaitForTransactionReceiptTimeoutError` when `timeout` elapses; recent 2.x releases default `timeout` to 180 000 ms (older ones waited forever), so check the installed default before reporting a missing timeout.
- Errors are `BaseError` chains. Show `error.shortMessage`; `error.message` contains multi-line "Request Arguments / Details / Version" blocks. Find the cause with `error.walk(e => e instanceof ContractFunctionRevertedError)`; then `data?.errorName` and `data?.args` give the decoded custom error, `reason` gives a `require` string. Decoding needs the error definitions in the ABI passed to the call.
- `UserRejectedRequestError` (EIP-1193 code 4001) signals rejection. Walk the chain to find it; it is often wrapped.
- `simulateContract` returns `{ request, result }`; pass `request` to `writeContract` so the write uses exactly what was simulated.
- `http()` with no URL uses `chain.rpcUrls.default`, a public endpoint. `fallback([...], { rank: true })` ranks transports by latency and stability. `http(url, { batch: true })` enables JSON-RPC batching; `createPublicClient({ batch: { multicall: true } })` aggregates `readContract` calls.
- Logs carry `removed: true` only when the RPC reports a reorged log through a filter or subscription. Plain `getLogs` polling never revisits a range it already read, so a log from an orphaned block stays in app state unless the app re-queries the last few blocks or waits for `safe`/`finalized` before treating it as final. `watchContractEvent` polls over HTTP (it subscribes over WebSocket unless `poll: true`): it creates an `eth_newFilter` and reads `eth_getFilterChanges`, and uses `getLogs` only when the filter cannot be created. When a filter is uninstalled (common on load-balanced RPCs), it calls `onError` and recreates the filter, so logs emitted in the gap can be missed: check that the app passes `onError`, and re-reads a bounded range for anything it credits.
- `publicClient.verifyMessage` / `verifyTypedData` support ERC-1271 and ERC-6492 (smart and counterfactual accounts). The standalone `verifyMessage` util from `viem` is ecrecover-only.
- `formatUnits` returns a string. Passing it to `Number()` is fine for display, never for math that feeds a write.
- OP Stack: `publicActions` do not include the L1 data fee. Use the op-stack extension (`publicActionsL2()` from `viem/op-stack`) and `estimateTotalFee`.
- Account abstraction lives in `viem/account-abstraction`: `createBundlerClient`, `sendUserOperation`, `waitForUserOperationReceipt` (receipt has `success` and `reason`).
- Smart-account helpers (`toCoinbaseSmartAccount`, `toSimpleSmartAccount`, permissionless.js accounts) expose `address` (the smart account), distinct from the owner/signer.

## wagmi (2.x and 3.x, React)

- `useWriteContract().isSuccess` means the wallet returned a hash. It does not mean mined. Pair with `useWaitForTransactionReceipt({ hash })`.
- The `waitForTransactionReceipt` **action** in `@wagmi/core` 2.x and 3.x throws when the receipt is reverted (it replays the call to extract the reason), so `useWaitForTransactionReceipt().isError` covers reverts. The thrown value is a plain `Error` whose message is only a `require`/`Error(string)` reason: custom errors and panics come out as garbled text or `'unknown reason'` (3.x also gives up after 10 s), so decoding them needs a re-simulation with the full ABI. wagmi passes `timeout: 0` (wait forever) unless the caller sets one. Recent releases (2.22.x, 3.x) forward `onReplaced` from the hook's parameters; older 2.x releases may not, so check the installed `@wagmi/core/src/query/waitForTransactionReceipt.ts` or use the viem action directly for replacement-aware tracking.
- wagmi 3.x renames `useAccount` to `useConnection`, `useAccountEffect` to `useConnectionEffect`, and `useSwitchAccount` to `useSwitchConnection`; the old names remain as deprecated aliases (a rename is Report only). Everything below that says `useAccount` applies to `useConnection`.
- `useAccount()`: `chainId` is the wallet's current chain; `chain` is `undefined` when that chain is not in the config. `status` includes `'reconnecting'` and `'connecting'`.
- `useChainId()` returns the config's current chain, which can differ from the wallet's chain when the wallet is on an unsupported network. Gate writes on `useAccount().chainId`.
- Passing `chainId` to `writeContract` makes wagmi throw a chain-mismatch error instead of sending on the wrong chain. Without it, the write goes to whatever chain the wallet is on.
- `useSwitchChain().switchChain` adds the chain from config when the wallet lacks it (4902) for connectors that support it.
- `createConfig({ ssr: true })` plus `cookieStorage` and `cookieToInitialState(config, cookie)` for Next.js App Router; without it, hydration mismatches appear.
- `multiInjectedProviderDiscovery` (EIP-6963) is on by default.
- Query keys from wagmi hooks already include args and `chainId`. Custom `useQuery` calls built around wagmi data do not; check those.
- `useReadContracts` batches via multicall; `useBlockNumber({ watch: true })` in many components multiplies polling. Prefer one watcher and `query.refetchInterval` tuned per screen.
- bigint values break `JSON.stringify` (react-query persisters, logging, `localStorage`). Use wagmi `serialize`/`deserialize` or a replacer.
- `useSendCalls` / `useCapabilities` implement EIP-5792; capabilities are per chain and per wallet.

## wagmi 1.x / 0.x (legacy)

- Hooks are named differently (`usePrepareContractWrite` + `useContractWrite`, `useWaitForTransaction`, `useNetwork`, `useSwitchNetwork`). Legacy is not a finding by itself; report migration as **Report only** unless a concrete defect stems from it.
- wagmi 1.x pairs with viem 1.x; 0.x with ethers v5. WalletConnect v1 connectors in 0.x no longer work.

## ethers v6

- `BrowserProvider(window.ethereum)`. `provider.getSigner()` is async. Network changes: the provider detects them and requests fail with `NETWORK_ERROR` ("network changed"); recreate the provider on `chainChanged`.
- `tx.wait(confirms?, timeout?)` throws `CALL_EXCEPTION` when status is 0 and a `TRANSACTION_REPLACED` error with `reason` (`'repriced'` / `'cancelled'` / `'replaced'`), `replacement`, and `receipt` on replacement. A repriced replacement is usually success-equivalent: read `error.receipt`.
- Errors carry `code` (`ACTION_REJECTED`, `INSUFFICIENT_FUNDS`, `CALL_EXCEPTION`, `NONCE_EXPIRED`, `REPLACEMENT_UNDERPRICED`), `shortMessage`, and for reverts `reason` and `revert` (`{ name, args }` when the ABI has the error). `contract.interface.parseError(data)` decodes custom errors manually.
- Preflight: `contract.method.staticCall(...)`, gas: `contract.method.estimateGas(...)`.
- Amounts are native `bigint`; `parseUnits` / `formatUnits` are top-level exports. `ethers.MaxUint256` is the unlimited-approval constant.
- `FallbackProvider([...], network, { quorum })` for failover. `getDefaultProvider()` uses shared community keys: throttled.
- `ethers.verifyMessage` / `verifyTypedData` are ecrecover-only: they fail for ERC-1271 smart accounts.
- `NonceManager(signer)` wraps a signer for backend sequences; it is in-memory, so it does not survive restarts or coordinate across processes.

## ethers v5

- `Web3Provider(window.ethereum)` without `"any"` throws "underlying network changed" after a chain switch; the common pattern is `new Web3Provider(window.ethereum, "any")` plus a reload or provider recreate on `chainChanged`.
- Amounts are `BigNumber`; `.toNumber()` throws above 2^53, and `parseFloat(formatEther(x))` loses precision. `ethers.constants.MaxUint256` is unlimited.
- `tx.wait()` throws `CALL_EXCEPTION` on status 0 and `TRANSACTION_REPLACED` (with `cancelled`, `replacement`, `receipt`) on replacement.
- `contract.callStatic.method(...)` for preflight. Revert reasons often hide in `error.error.data` or `error.data.data` depending on wallet and RPC: decoding needs a careful walk.
- `_signTypedData` (underscore) is the v5 typed-data API.

## RainbowKit (2.x)

- `getDefaultConfig({ appName, projectId, chains, ssr })` builds the wagmi config; `projectId` is a WalletConnect Cloud / Reown id (public, domain-allowlisted).
- `ConnectButton` handles the wrong-network state; custom `ConnectButton.Custom` renderers often forget `chain.unsupported`. Check that branch.
- Authentication adapter (`RainbowKitAuthenticationProvider`, `createAuthenticationAdapter`, or `@rainbow-me/rainbowkit-siwe-next-auth`): nonce must come from the server; `verify` must check it server-side.

## WalletConnect / Reown AppKit

- v1 (`@walletconnect/client`, `@walletconnect/web3-provider`, `@walletconnect/qrcode-modal`) is dead: report as High if it is the only mobile path.
- Web3Modal v3/v4 (`@web3modal/*`) is renamed Reown AppKit (`@reown/appkit`); migration is Report only unless broken.
- `metadata.url` must match the page origin for the Verify API; mismatches show warnings in wallets.
- Sessions persist in storage across reloads; on disconnect, `disconnect()` must be awaited so the relay session closes.

## Account-abstraction SDKs

- permissionless.js: `createSmartAccountClient({ account, bundlerTransport, paymaster })`. `sendTransaction` on a smart-account client returns a **tx hash** after waiting for the user op; `sendUserOperation` returns a **userOpHash**. Mixing them is a common bug.
- Alchemy Account Kit (`@account-kit/*`, legacy `@alchemy/aa-*`), ZeroDev (`@zerodev/sdk`), Biconomy, Safe (`@safe-global/*`): each pins an EntryPoint version per account implementation. Check it matches the bundler and paymaster config.
- Safe apps: transactions are proposed, not executed; `safeTxHash` is not a chain tx hash until enough owners sign. The UI must show "awaiting co-signers".

## thirdweb, web3.js, web3-react, Web3-Onboard

- Same principles apply; read the installed version's docs for the equivalent of: receipt status, replacement handling, revert decoding, and chain gating. web3.js 1.x is deprecated (Report only unless broken).

## Non-EVM

Solana, Sui, Aptos, Starknet, and Cosmos dApps are out of scope for the EVM-specific checks in this skill (nonce, EIP-712, ERC-20 approvals, ERC-4337). The general UX principles in sections 1, 3, 5, 7 still apply; say so in the report and keep findings to those.
