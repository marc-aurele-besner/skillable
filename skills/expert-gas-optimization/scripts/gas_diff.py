#!/usr/bin/env python3
"""Compare two Foundry gas snapshots and print the per-test delta.

Read-only and stdlib-only. It parses two `.gas-snapshot` files (the format
written by `forge snapshot`), matches tests by name, and prints a Markdown
table sorted by absolute delta, plus a total over tests present in both.

    python3 -I scripts/gas_diff.py baseline.gas-snapshot after.gas-snapshot
    python3 -I scripts/gas_diff.py baseline.gas-snapshot after.gas-snapshot --json
    python3 -I scripts/gas_diff.py base.gas-snapshot after.gas-snapshot --min-delta 50

Line formats understood:

    Contract:testName() (gas: 12345)
    Contract:testFuzz(uint256) (runs: 256, μ: 12345, ~: 12000)
    Contract:invariant_x() (runs: 256, calls: 128000, reverts: 0)

For fuzz tests the median (`~`) is compared, because the mean is skewed by
outlier inputs. Invariant lines carry no gas figure and are skipped.

Exit codes:
  0  comparison printed
  2  usage error (missing, unreadable, or non-snapshot file)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LINE_RE = re.compile(r"^(?P<name>\S.*?\))\s+\((?P<body>[^()]*)\)\s*$")
GAS_RE = re.compile(r"\bgas:\s*(\d+)")
MEDIAN_RE = re.compile(r"~:\s*(\d+)")


def parse_snapshot(path: Path) -> dict[str, int]:
    results: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        match = LINE_RE.match(line)
        if not match:
            continue
        body = match.group("body")
        gas = GAS_RE.search(body) or MEDIAN_RE.search(body)
        if gas:
            results[match.group("name")] = int(gas.group(1))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("baseline", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    parser.add_argument(
        "--min-delta", type=int, default=0, help="hide rows whose absolute delta is below this"
    )
    args = parser.parse_args()

    try:
        base = parse_snapshot(args.baseline)
        after = parse_snapshot(args.after)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for path, parsed in ((args.baseline, base), (args.after, after)):
        if not parsed:
            print(f"error: no gas lines found in {path}; is it a forge snapshot file?", file=sys.stderr)
            return 2

    rows = []
    for name in sorted(base.keys() & after.keys()):
        delta = after[name] - base[name]
        pct = (delta / base[name] * 100) if base[name] else 0.0
        rows.append({"test": name, "before": base[name], "after": after[name], "delta": delta, "pct": round(pct, 2)})
    rows.sort(key=lambda r: (-abs(r["delta"]), r["test"]))

    total_before = sum(r["before"] for r in rows)
    total_after = sum(r["after"] for r in rows)
    only_base = sorted(base.keys() - after.keys())
    only_after = sorted(after.keys() - base.keys())
    shown = [r for r in rows if abs(r["delta"]) >= args.min_delta]

    if args.json:
        print(
            json.dumps(
                {
                    "rows": shown,
                    "total": {"before": total_before, "after": total_after, "delta": total_after - total_before},
                    "only_in_baseline": only_base,
                    "only_in_after": only_after,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print("| Test | Before | After | Δ gas | Δ % |")
    print("|------|-------:|------:|------:|----:|")
    for r in shown:
        print(f"| `{r['test']}` | {r['before']:,} | {r['after']:,} | {r['delta']:+,} | {r['pct']:+.2f}% |")
    print()
    print(f"Total over {len(rows)} shared tests: {total_before:,} → {total_after:,} ({total_after - total_before:+,})")
    if only_base:
        print(f"Only in baseline ({len(only_base)}): " + ", ".join(only_base))
    if only_after:
        print(f"Only in after ({len(only_after)}): " + ", ".join(only_after))
    return 0


if __name__ == "__main__":
    sys.exit(main())
