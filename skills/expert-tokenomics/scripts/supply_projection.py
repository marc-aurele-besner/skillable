#!/usr/bin/env python3
"""Project circulating token supply month by month from a vesting/emission schedule.

Read-only and stdlib-only. It reads one JSON schedule file, prints a monthly
table (or JSON / CSV), a summary, and a list of flags worth a reviewer's
attention. It never touches the network, a wallet, or the filesystem beyond
reading the schedule.

    python3 -I scripts/supply_projection.py schedule.json
    python3 -I scripts/supply_projection.py schedule.json --months 60 --every 3
    python3 -I scripts/supply_projection.py schedule.json --json
    python3 -I scripts/supply_projection.py schedule.json --csv > supply.csv

Schedule file (JSON). Month 0 is TGE / launch. All amounts are whole tokens
(not base units: divide on-chain values by 10**decimals before writing them).

    {
      "token": "XYZ",
      "max_supply": 1000000000,          # null when uncapped
      "horizon_months": 48,               # optional, default 48
      "allocations": [
        {
          "name": "Team",
          "category": "insider",          # insider | community | treasury | liquidity | other
          "type": "vesting",              # default
          "amount": 200000000,
          "tge_pct": 0,                   # fraction released at month 0
          "cliff_months": 12,             # no linear release before this month
          "cliff_pct": 0.25,              # fraction released as a lump at the cliff
          "vesting_months": 36            # rest released in equal monthly steps
        },                                #   at months cliff+1 .. cliff+vesting
        {
          "name": "Liquidity mining",
          "category": "community",
          "type": "emission",
          "amount": 300000000,            # budget cap; omit or null for uncapped tail emission
          "rate_per_month": 12500000,
          "start_month": 1,               # default 1
          "halving_months": 12,           # optional: rate halves every N months
          "annual_decay": 0.0             # optional: rate *= (1 - d) every 12 months
        },
        {
          "name": "Ecosystem",
          "category": "treasury",
          "type": "custom",
          "unlocks": {"0": 10000000, "6": 40000000, "18": 50000000}
        }
      ],
      "burns": [                          # optional, reduces circulating and total supply
        {"name": "Fee burn", "per_month": 500000, "from_month": 1}
      ]
    }

Semantics worth knowing (they are the usual source of mismatch with a whitepaper):
  - "vesting_months" counts the linear period AFTER the cliff, not including it.
    "1-year cliff, 4-year vest, 25% at cliff" is cliff_months=12, cliff_pct=0.25,
    vesting_months=36.
  - Linear releases are monthly steps; contracts that stream per second release
    slightly more by mid-month. The difference is under one month of emissions.
  - "Circulating" here means "unlocked". Unlocked tokens held by the treasury or
    a staking contract may not be liquid; categorize them and read the
    per-category columns instead of trusting one headline number.

Flags raised:
  ALLOCATION_MISMATCH  sum of capped allocations differs from max_supply
  SUPPLY_EXCEEDS_CAP   projected total supply passes max_supply
  UNCAPPED_EMISSION    an emission has no budget cap
  UNLOCK_CLIFF         a single month adds more than --cliff-threshold of circulating
  LOW_FLOAT            TGE circulating is under --low-float of max (or total) supply
  INSIDER_MAJORITY     insiders hold more than half of circulating supply in some month
  HIGH_INFLATION       annualized inflation above --inflation-threshold after month 12

Exit codes:
  0  projection printed (flags are informational)
  2  usage error (missing file, bad JSON, invalid schedule)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

CATEGORIES = ("insider", "community", "treasury", "liquidity", "other")


class ScheduleError(ValueError):
    pass


def _num(value, field: str, name: str, default=None, minimum=0.0):
    if value is None:
        if default is None:
            raise ScheduleError(f"{name}: '{field}' is required")
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or math.isnan(value):
        raise ScheduleError(f"{name}: '{field}' must be a number")
    if minimum is not None and value < minimum:
        raise ScheduleError(f"{name}: '{field}' must be >= {minimum}")
    return float(value)


def vesting_releases(a: dict, horizon: int) -> list[float]:
    name = a.get("name", "?")
    amount = _num(a.get("amount"), "amount", name)
    tge = _num(a.get("tge_pct"), "tge_pct", name, 0.0)
    cliff_pct = _num(a.get("cliff_pct"), "cliff_pct", name, 0.0)
    cliff = int(_num(a.get("cliff_months"), "cliff_months", name, 0.0))
    vest = int(_num(a.get("vesting_months"), "vesting_months", name, 0.0))
    if tge + cliff_pct > 1.0 + 1e-9:
        raise ScheduleError(f"{name}: tge_pct + cliff_pct exceeds 1")
    out = [0.0] * (horizon + 1)
    out[0] += amount * tge
    rest = amount * (1.0 - tge - cliff_pct)
    if cliff <= horizon:
        out[cliff] += amount * cliff_pct
    if vest == 0:
        if cliff <= horizon:
            out[cliff] += rest
    else:
        step = rest / vest
        for m in range(cliff + 1, min(cliff + vest, horizon) + 1):
            out[m] += step
    return out


def emission_releases(a: dict, horizon: int) -> list[float]:
    name = a.get("name", "?")
    rate = _num(a.get("rate_per_month"), "rate_per_month", name)
    start = int(_num(a.get("start_month"), "start_month", name, 1.0))
    cap = a.get("amount")
    cap = None if cap is None else _num(cap, "amount", name)
    halving = a.get("halving_months")
    halving = None if halving is None else _num(halving, "halving_months", name, minimum=1.0)
    decay = _num(a.get("annual_decay"), "annual_decay", name, 0.0)
    if decay >= 1.0:
        raise ScheduleError(f"{name}: annual_decay must be < 1")
    out = [0.0] * (horizon + 1)
    emitted = 0.0
    for m in range(start, horizon + 1):
        k = m - start
        r = rate
        if halving:
            r *= 0.5 ** (k // int(halving))
        if decay:
            r *= (1.0 - decay) ** (k // 12)
        if cap is not None:
            r = max(0.0, min(r, cap - emitted))
        out[m] = r
        emitted += r
    return out


def custom_releases(a: dict, horizon: int) -> list[float]:
    name = a.get("name", "?")
    unlocks = a.get("unlocks")
    if not isinstance(unlocks, dict) or not unlocks:
        raise ScheduleError(f"{name}: custom allocation needs a non-empty 'unlocks' object")
    out = [0.0] * (horizon + 1)
    for month, amt in unlocks.items():
        try:
            m = int(month)
        except (TypeError, ValueError) as exc:
            raise ScheduleError(f"{name}: unlock month '{month}' is not an integer") from exc
        if m < 0:
            raise ScheduleError(f"{name}: unlock month must be >= 0")
        if m <= horizon:
            out[m] += _num(amt, f"unlocks[{month}]", name)
    return out


def allocation_total(a: dict) -> float | None:
    kind = a.get("type", "vesting")
    if kind == "vesting":
        return float(a["amount"])
    if kind == "emission":
        return None if a.get("amount") is None else float(a["amount"])
    return float(sum(a["unlocks"].values()))


def project(schedule: dict, horizon_override: int | None):
    if not isinstance(schedule, dict):
        raise ScheduleError("schedule must be a JSON object")
    allocations = schedule.get("allocations")
    if not isinstance(allocations, list) or not allocations:
        raise ScheduleError("'allocations' must be a non-empty list")
    horizon = horizon_override or int(schedule.get("horizon_months") or 48)
    if horizon < 1 or horizon > 1200:
        raise ScheduleError("horizon must be between 1 and 1200 months")
    max_supply = schedule.get("max_supply")
    if max_supply is not None:
        max_supply = _num(max_supply, "max_supply", "schedule", minimum=1.0)

    per_cat = {c: [0.0] * (horizon + 1) for c in CATEGORIES}
    per_alloc = {}
    uncapped = []
    for a in allocations:
        if not isinstance(a, dict):
            raise ScheduleError("each allocation must be an object")
        kind = a.get("type", "vesting")
        cat = a.get("category", "other")
        if cat not in CATEGORIES:
            raise ScheduleError(f"{a.get('name', '?')}: category must be one of {', '.join(CATEGORIES)}")
        if kind == "vesting":
            rel = vesting_releases(a, horizon)
        elif kind == "emission":
            rel = emission_releases(a, horizon)
            if a.get("amount") is None:
                uncapped.append(a.get("name", "?"))
        elif kind == "custom":
            rel = custom_releases(a, horizon)
        else:
            raise ScheduleError(f"{a.get('name', '?')}: unknown type '{kind}'")
        per_alloc[a.get("name", "?")] = rel
        for m, v in enumerate(rel):
            per_cat[cat][m] += v

    burns = [0.0] * (horizon + 1)
    for b in schedule.get("burns") or []:
        name = b.get("name", "burn")
        rate = _num(b.get("per_month"), "per_month", name)
        start = int(_num(b.get("from_month"), "from_month", name, 1.0))
        for m in range(start, horizon + 1):
            burns[m] += rate

    rows = []
    circ = 0.0
    cum = {c: 0.0 for c in CATEGORIES}
    burned = 0.0
    for m in range(horizon + 1):
        minted = sum(per_cat[c][m] for c in CATEGORIES)
        for c in CATEGORIES:
            cum[c] += per_cat[c][m]
        burn = min(burns[m], circ + minted)
        burned += burn
        prev = circ
        circ = circ + minted - burn
        net = minted - burn
        monthly_infl = (net / prev) if prev > 0 else None
        rows.append(
            {
                "month": m,
                "unlocked_this_month": minted,
                "burned_this_month": burn,
                "circulating": circ,
                "pct_of_max": (circ / max_supply) if max_supply else None,
                "monthly_inflation": monthly_infl,
                "insider_share": (cum["insider"] / (circ + burned)) if circ > 0 else None,
                **{f"cum_{c}": cum[c] for c in CATEGORIES},
            }
        )
    for i, r in enumerate(rows):
        if i >= 12 and rows[i - 12]["circulating"] > 0:
            r["annualized_inflation"] = r["circulating"] / rows[i - 12]["circulating"] - 1.0
        else:
            r["annualized_inflation"] = None
    return rows, per_alloc, max_supply, uncapped


def build_flags(schedule, rows, max_supply, uncapped, args):
    flags = []
    totals = [allocation_total(a) for a in schedule["allocations"]]
    capped_sum = sum(t for t in totals if t is not None)
    if max_supply and abs(capped_sum - max_supply) > max_supply * 1e-6:
        flags.append(
            ("ALLOCATION_MISMATCH",
             f"capped allocations sum to {capped_sum:,.0f} but max_supply is {max_supply:,.0f} "
             f"(diff {capped_sum - max_supply:+,.0f})")
        )
    if max_supply:
        total_minted = rows[-1]["circulating"] + sum(r["burned_this_month"] for r in rows)
        over = next((r for r in rows if sum(r[f"cum_{c}"] for c in CATEGORIES) > max_supply * (1 + 1e-9)), None)
        if over:
            flags.append(("SUPPLY_EXCEEDS_CAP", f"minted supply passes max_supply at month {over['month']} "
                          f"({total_minted:,.0f} minted by month {rows[-1]['month']})"))
    for name in uncapped:
        flags.append(("UNCAPPED_EMISSION", f"'{name}' has no budget cap; supply grows without bound"))
    for prev, r in zip(rows, rows[1:]):
        if prev["circulating"] > 0 and r["unlocked_this_month"] / prev["circulating"] > args.cliff_threshold:
            flags.append(("UNLOCK_CLIFF", f"month {r['month']}: +{r['unlocked_this_month']:,.0f} "
                          f"= {r['unlocked_this_month'] / prev['circulating']:.1%} of prior circulating"))
    ref = max_supply or rows[-1]["circulating"]
    if ref and rows[0]["circulating"] / ref < args.low_float:
        flags.append(("LOW_FLOAT", f"TGE circulating is {rows[0]['circulating'] / ref:.1%} of "
                      f"{'max' if max_supply else 'horizon'} supply (FDV/MC ~ {ref / max(rows[0]['circulating'], 1):.1f}x)"))
    maj = [r["month"] for r in rows if r["insider_share"] and r["insider_share"] > 0.5]
    if maj:
        flags.append(("INSIDER_MAJORITY", f"insiders hold >50% of unlocked supply in months {_ranges(maj)}"))
    hot = [r["month"] for r in rows if r["annualized_inflation"] is not None
           and r["annualized_inflation"] > args.inflation_threshold]
    if hot:
        flags.append(("HIGH_INFLATION", f"annualized inflation above {args.inflation_threshold:.0%} in months {_ranges(hot)}"))
    return flags


def _ranges(months):
    out, start, prev = [], months[0], months[0]
    for m in months[1:]:
        if m == prev + 1:
            prev = m
            continue
        out.append(f"{start}-{prev}" if start != prev else f"{start}")
        start = prev = m
    out.append(f"{start}-{prev}" if start != prev else f"{start}")
    return ", ".join(out)


def summary(rows, max_supply):
    tge = rows[0]["circulating"]
    biggest = max(rows[1:], key=lambda r: r["unlocked_this_month"], default=rows[0])
    s = {
        "tge_circulating": tge,
        "tge_pct_of_max": (tge / max_supply) if max_supply else None,
        "fdv_to_mcap_at_tge": (max_supply / tge) if max_supply and tge else None,
        "final_circulating": rows[-1]["circulating"],
        "largest_unlock_month": biggest["month"],
        "largest_unlock_amount": biggest["unlocked_this_month"],
    }
    if max_supply:
        for pct in (0.5, 0.9):
            hit = next((r["month"] for r in rows if r["circulating"] >= max_supply * pct), None)
            s[f"month_reaching_{int(pct * 100)}pct_of_max"] = hit
    return s


def _fmt_pct(v):
    return "-" if v is None else f"{v:.2%}"


def print_table(rows, every, out):
    head = f"{'month':>5} {'unlocked':>16} {'circulating':>18} {'% max':>8} {'mo infl':>8} {'yoy infl':>9} {'insider':>8}"
    print(head, file=out)
    print("-" * len(head), file=out)
    for r in rows:
        if r["month"] % every and r["month"] != rows[-1]["month"]:
            continue
        print(
            f"{r['month']:>5} {r['unlocked_this_month']:>16,.0f} {r['circulating']:>18,.0f} "
            f"{_fmt_pct(r['pct_of_max']):>8} {_fmt_pct(r['monthly_inflation']):>8} "
            f"{_fmt_pct(r['annualized_inflation']):>9} {_fmt_pct(r['insider_share']):>8}",
            file=out,
        )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Project circulating supply from a token schedule (read-only).")
    p.add_argument("schedule", type=Path, help="path to the schedule JSON file")
    p.add_argument("--months", type=int, help="override horizon_months")
    p.add_argument("--every", type=int, default=1, help="print every Nth month in the table (default 1)")
    p.add_argument("--cliff-threshold", type=float, default=0.10,
                   help="flag a month whose unlock exceeds this fraction of prior circulating (default 0.10)")
    p.add_argument("--low-float", type=float, default=0.10,
                   help="flag TGE float under this fraction of max supply (default 0.10)")
    p.add_argument("--inflation-threshold", type=float, default=0.25,
                   help="flag annualized inflation above this fraction (default 0.25)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--json", action="store_true", help="print rows, summary, and flags as JSON")
    g.add_argument("--csv", action="store_true", help="print rows as CSV")
    args = p.parse_args(argv)

    try:
        schedule = json.loads(args.schedule.read_text(encoding="utf-8"))
        rows, per_alloc, max_supply, uncapped = project(schedule, args.months)
        flags = build_flags(schedule, rows, max_supply, uncapped, args)
    except FileNotFoundError:
        print(f"error: {args.schedule} not found", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON in {args.schedule}: {exc}", file=sys.stderr)
        return 2
    except (ScheduleError, KeyError, TypeError) as exc:
        print(f"error: invalid schedule: {exc}", file=sys.stderr)
        return 2

    s = summary(rows, max_supply)
    if args.json:
        json.dump({"token": schedule.get("token"), "max_supply": max_supply, "summary": s,
                   "flags": [{"code": c, "detail": d} for c, d in flags], "rows": rows},
                  sys.stdout, indent=2)
        print()
        return 0
    if args.csv:
        w = csv.DictWriter(sys.stdout, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
        return 0

    print(f"Token: {schedule.get('token', '?')}   max_supply: "
          f"{'uncapped' if max_supply is None else f'{max_supply:,.0f}'}   horizon: {rows[-1]['month']} months\n")
    print_table(rows, max(1, args.every), sys.stdout)
    print("\nSummary")
    for k, v in s.items():
        if isinstance(v, float) and k.endswith(("pct_of_max",)):
            v = _fmt_pct(v)
        elif isinstance(v, float):
            v = f"{v:,.2f}" if k.startswith("fdv") else f"{v:,.0f}"
        print(f"  {k}: {'-' if v is None else v}")
    print("\nFlags" if flags else "\nFlags: none")
    for code, detail in flags:
        print(f"  {code}: {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
