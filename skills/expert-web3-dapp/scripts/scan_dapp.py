#!/usr/bin/env python3
"""Map a dApp frontend's web3 stack and list code-level review leads as JSON.

Stdlib-only and read-only: it never runs project code, installs packages,
opens network connections, or writes to the target. It reads:

  - every package.json under the root (node_modules and build output skipped)
    and reports the web3 libraries it declares, with their version ranges
  - the installed version of each detected library from node_modules/<pkg>/
    package.json when present (the range in package.json is not the version
    that ships)
  - source files (.ts .tsx .js .jsx .mjs .cjs .vue .svelte) for patterns that
    are frequent sources of dApp defects (unlimited approvals, eth_sign,
    hard-coded gas, float math on token amounts, default public RPCs, ...)

Every hit is a LEAD, not a finding: the reviewer must open the file, read the
surrounding code, and confirm a concrete failure before reporting it.

Usage:
    python3 -I scan_dapp.py <project-root>
    python3 -I scan_dapp.py <project-root> --max-per-pattern 20
    python3 -I scan_dapp.py <project-root> --json leads.json

Exit codes: 0 success, 1 error (bad path).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = frozenset(
    {
        "node_modules", ".git", ".next", ".nuxt", ".svelte-kit", ".turbo", ".vercel",
        ".output", "dist", "build", "out", "coverage", ".cache", "artifacts",
        "typechain-types", "broadcast", "target",
    }
)
SOURCE_EXTS = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte"})
MAX_FILE_BYTES = 1_000_000

# Libraries in view, grouped by role. Prefix entries end with "/".
LIBRARIES = {
    "client": ["viem", "ethers", "web3", "@ethersproject/", "thirdweb", "@thirdweb-dev/"],
    "react-bindings": ["wagmi", "@wagmi/", "@tanstack/react-query", "@usedapp/core", "@web3-react/"],
    "wallet-ui": [
        "@rainbow-me/rainbowkit", "connectkit", "@reown/", "@web3modal/", "@walletconnect/",
        "@coinbase/onchainkit", "@coinbase/wallet-sdk", "@privy-io/", "@dynamic-labs/",
        "@web3-onboard/", "@metamask/sdk", "@safe-global/safe-apps-sdk",
    ],
    "account-abstraction": [
        "permissionless", "@account-kit/", "@alchemy/aa-", "@zerodev/", "@biconomy/",
        "@safe-global/", "@pimlico/", "userop", "@stackup/",
    ],
    "signing-auth": ["siwe", "@uniswap/permit2-sdk", "@spruceid/siwe-parser", "next-auth"],
    "indexing": ["@apollo/client", "graphql-request", "urql", "@ponder/", "ponder", "@envio-dev/"],
    "out-of-scope-chains": ["@solana/", "@coral-xyz/anchor", "@mysten/", "@aptos-labs/", "starknet", "@cosmjs/"],
}

DEPRECATED = {
    "@walletconnect/web3-provider": "WalletConnect v1 provider; the v1 relay is shut down",
    "@walletconnect/client": "WalletConnect v1 client; the v1 relay is shut down",
    "@walletconnect/qrcode-modal": "WalletConnect v1 modal; the v1 relay is shut down",
    "web3modal": "Legacy Web3Modal v1; superseded by Reown AppKit",
    "@web3-react/walletconnect": "web3-react WalletConnect v1 connector",
    "@ledgerhq/connect-kit-loader": "Loads code from a CDN at runtime (Dec 2023 supply-chain incident)",
}

# (id, regex, hint). Keep the hints short; the checklist has the detail.
PATTERNS = [
    ("unlimited-approval",
     r"maxUint256|MaxUint256|constants\.MaxUint256|2n\s*\*\*\s*256n\s*-\s*1n|0xf{64}\b|type\(uint256\)\.max",
     "Unlimited allowance: is it opt-in, shown to the user, and to a trusted spender?"),
    ("operator-approval", r"setApprovalForAll",
     "Operator approval over a whole collection: warn, and check the operator comes from trusted config"),
    ("eth-sign", r"[\"']eth_sign[\"']",
     "eth_sign signs an opaque hash; wallets warn or block it. Use EIP-712 or personal_sign"),
    ("personal-sign", r"personal_sign|signMessage\s*\(",
     "Check the message is human-readable (not a hex hash) and carries domain, nonce, expiry"),
    ("typed-data", r"signTypedData|_signTypedData|eth_signTypedData",
     "Check domain.chainId, verifyingContract, deadline, and that amounts/spender are readable"),
    ("hardcoded-gas", r"\b(gasLimit|gas)\s*:\s*(BigInt\()?\s*['\"]?\d{4,}",
     "Hard-coded gas limit: breaks when state or chain changes; estimate instead"),
    ("legacy-gas-price", r"\bgasPrice\s*:",
     "Legacy gasPrice on an EIP-1559 chain overpays or underprices; use maxFeePerGas/maxPriorityFeePerGas"),
    ("manual-nonce", r"\bnonce\s*:\s*(?!undefined)",
     "Manual nonce in a wallet flow fights the wallet's nonce manager; only relayers/backends should set it"),
    ("float-amount",
     r"(parseFloat|Number|toFixed)\s*\([^)]*(formatUnits|formatEther|balance|amount|allowance|value)",
     "Float math on token amounts loses precision above 2^53 wei; keep bigint until display"),
    ("hardcoded-decimals", r"\b1e18\b|10\s*\*\*\s*18\b|10n\s*\*\*\s*18n|parseEther\s*\(",
     "Assumes 18 decimals: wrong for USDC/USDT (6), WBTC (8); read decimals() for ERC-20 amounts"),
    ("default-public-rpc", r"\bhttp\(\s*\)|webSocket\(\s*\)|getDefaultProvider\s*\(",
     "No RPC URL: falls back to the chain's public endpoint, which rate-limits real traffic"),
    ("hardcoded-rpc",
     r"https://[A-Za-z0-9.-]*(infura\.io|alchemy\.com|quiknode\.pro|ankr\.com|llamarpc\.com|cloudflare-eth\.com|drpc\.org|blastapi\.io|chainstack\.com)[^\s'\"`]*",
     "RPC URL in source: is the key origin-restricted, and is there a fallback transport?"),
    ("injected-provider", r"window\.ethereum",
     "Direct window.ethereum: multiple wallets clobber it; prefer EIP-6963 discovery via the connector library"),
    ("receipt-wait", r"waitForTransactionReceipt|useWaitForTransactionReceipt|\.wait\s*\(\s*\d*\s*\)",
     "Check reverted status, replacement (speed-up/cancel), confirmations, and timeout handling"),
    ("replacement-handled", r"onReplaced|TRANSACTION_REPLACED|TransactionReplaced",
     "Positive signal: replacement is handled here"),
    ("event-read", r"getLogs|getContractEvents|queryFilter|watchContractEvent|useWatchContractEvent|watchEvent|createEventFilter",
     "Check block-range limits, reorgs (log.removed), dedupe by txHash+logIndex, and filter expiry"),
    ("logs-from-genesis", r"fromBlock\s*:\s*(0n?\b|['\"]earliest['\"]|BigInt\(0\))",
     "Log query from genesis: exceeds provider block-range limits and is slow; start at deploy block"),
    ("raw-error-message", r"(toast|setError|alert|notify|showError)[\w.]*\s*\([^)]*\b(e|err|error)\.message",
     "Raw error.message shown to users: viem messages carry multi-line details; use shortMessage + decoded revert"),
    ("user-rejection", r"UserRejectedRequestError|ACTION_REJECTED|\b4001\b",
     "Positive signal: user rejection is distinguished from failure"),
    ("revert-decoding", r"ContractFunctionRevertedError|decodeErrorResult|parseError\s*\(|\.revert\b|errorName",
     "Positive signal: revert data is decoded"),
    ("client-secret", r"(NEXT_PUBLIC|VITE|REACT_APP|PUBLIC|EXPO_PUBLIC)_\w*(PRIVATE_KEY|MNEMONIC|SECRET)|privateKeyToAccount|Wallet\.fromPhrase|fromMnemonic|mnemonicToAccount",
     "Key material in client-bundled code is shipped to every visitor"),
    ("chain-switch", r"useSwitchChain|switchChain|wallet_switchEthereumChain|wallet_addEthereumChain",
     "Check unsupported-chain state, rejection, and that writes are gated on the switched chain"),
    ("chain-events", r"accountsChanged|chainChanged|watchAccount|watchChainId|useAccountEffect",
     "Check that cached balances, allowances, and pending state are reset on account/chain change"),
    ("batch-calls", r"useSendCalls|sendCalls|wallet_sendCalls|useCapabilities|getCapabilities",
     "EIP-5792 batching: check capability detection and the sequential fallback"),
    ("user-operation", r"sendUserOperation|waitForUserOperationReceipt|UserOperation|entryPoint|paymaster",
     "ERC-4337: userOpHash is not a tx hash; check receipt.success, paymaster failure, and EntryPoint version"),
    ("signature-verify", r"verifyMessage|verifyTypedData|recoverMessageAddress|recoverAddress|ecrecover",
     "Off-chain verification: ecrecover-only fails for smart accounts; use ERC-1271/ERC-6492-aware verify"),
]

COMPILED = [(pid, re.compile(rx), hint) for pid, rx, hint in PATTERNS]
POSITIVE = frozenset({"replacement-handled", "user-rejection", "revert-decoding"})


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            yield Path(dirpath) / name


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def role_of(pkg: str) -> str | None:
    for role, names in LIBRARIES.items():
        for name in names:
            if (name.endswith("/") and pkg.startswith(name)) or pkg == name:
                return role
            if name.endswith("-") and pkg.startswith(name):
                return role
    return None


def installed_version(manifest_dir: Path, root: Path, pkg: str) -> str | None:
    for base in (manifest_dir, root):
        meta = read_json(base / "node_modules" / pkg / "package.json")
        if meta.get("version"):
            return meta["version"]
    return None


def scan_manifests(root: Path) -> tuple[list[dict], list[dict]]:
    manifests, deprecated = [], []
    for path in iter_files(root):
        if path.name != "package.json":
            continue
        data = read_json(path)
        found = {}
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            for pkg, rng in (data.get(section) or {}).items():
                if pkg in DEPRECATED:
                    deprecated.append({"manifest": path.relative_to(root).as_posix(), "package": pkg,
                                       "range": rng, "why": DEPRECATED[pkg]})
                role = role_of(pkg)
                if role:
                    found[pkg] = {"role": role, "range": rng, "section": section,
                                  "installed": installed_version(path.parent, root, pkg)}
        if found:
            manifests.append({"manifest": path.relative_to(root).as_posix(),
                              "name": data.get("name"), "libraries": found})
    return manifests, deprecated


def scan_sources(root: Path, max_per_pattern: int) -> tuple[list[dict], dict[str, int]]:
    leads: list[dict] = []
    counts: dict[str, int] = {}
    for path in iter_files(root):
        if path.suffix not in SOURCE_EXTS or path.name.endswith((".min.js", ".d.ts")):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        is_test = bool(re.search(r"(^|/)(test|tests|__tests__|e2e|spec)/|\.(test|spec)\.", rel))
        for line_no, line in enumerate(text.splitlines(), start=1):
            if len(line) > 2000:
                continue
            for pid, rx, hint in COMPILED:
                if not rx.search(line):
                    continue
                counts[pid] = counts.get(pid, 0) + 1
                if counts[pid] > max_per_pattern:
                    continue
                snippet = line.strip()
                # Never echo what may be a key or a keyed RPC URL in full.
                if pid in {"client-secret", "hardcoded-rpc"}:
                    snippet = re.sub(r"(0x)?[A-Fa-f0-9]{32,}|[A-Za-z0-9_-]{24,}", "<redacted>", snippet)
                leads.append({"id": pid, "file": rel, "line": line_no, "test_file": is_test,
                              "positive_signal": pid in POSITIVE, "text": snippet[:200], "hint": hint})
    return leads, counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", help="project root to scan")
    parser.add_argument("--max-per-pattern", type=int, default=40, help="cap leads listed per pattern")
    parser.add_argument("--json", dest="out", help="also write the result to this file")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 1

    manifests, deprecated = scan_manifests(root)
    leads, counts = scan_sources(root, max(1, args.max_per_pattern))
    roles = sorted({lib["role"] for m in manifests for lib in m["libraries"].values()})
    result = {
        "root": str(root),
        "roles_detected": roles,
        "manifests": manifests,
        "deprecated_packages": deprecated,
        "lead_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "leads": leads,
        "note": "Leads are not findings. Open each file and confirm a concrete failure before reporting.",
    }
    payload = json.dumps(result, indent=2)
    print(payload)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
