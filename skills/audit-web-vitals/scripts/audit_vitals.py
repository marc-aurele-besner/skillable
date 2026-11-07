#!/usr/bin/env python3
"""Check Lighthouse JSON reports against a Core Web Vitals budget.

Read-only and stdlib-only. It reads one or more Lighthouse JSON reports plus a
budget file, prints a pass/fail line per metric, lists every violation, and
exits non-zero when a measured value exceeds its budget.

    python3 -I scripts/audit_vitals.py report.json --budget budgets/vitals.json
    python3 -I scripts/audit_vitals.py reports/*.json --budget budgets/vitals.json --json

Budget file (JSON):

    {
      "defaults": { "lcp": 2500, "cls": 0.1, "inp": 200, "ttfb": 800 },
      "routes": {
        "/": { "lcp": 2000 },
        "/blog/*": { "lcp": 3000, "cls": 0.15 }
      }
    }

Metric keys and units:
  lcp   Largest Contentful Paint   milliseconds
  inp   Interaction to Next Paint   milliseconds (not always measured by Lighthouse)
  cls   Cumulative Layout Shift     unitless
  ttfb  Time to First Byte         milliseconds
  tbt   Total Blocking Time         milliseconds
  fcp   First Contentful Paint      milliseconds
  si    Speed Index                 milliseconds

Route keys are matched against the report path with glob semantics ("*" and "?"
match any characters, including "/"). The most specific matching route wins,
and route values override "defaults".

Exit codes:
  0  every measured metric is within its budget
  1  at least one metric exceeds its budget
  2  usage error (missing file, unreadable JSON, bad budget)
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path

# metric key -> (label, unit, lighthouse audit ids, lighthouse metrics[] names)
METRICS = {
    "lcp": (
        "LCP",
        "ms",
        ("largest-contentful-paint",),
        ("largestContentfulPaint",),
    ),
    "inp": (
        "INP",
        "ms",
        ("interaction-to-next-paint", "experimental-interaction-to-next-paint"),
        ("interactionToNextPaint", "experimentalInteractionToNextPaint"),
    ),
    "cls": (
        "CLS",
        "",
        ("cumulative-layout-shift",),
        ("cumulativeLayoutShift",),
    ),
    "ttfb": (
        "TTFB",
        "ms",
        ("server-response-time",),
        ("serverResponseTime",),
    ),
    "tbt": (
        "TBT",
        "ms",
        ("total-blocking-time",),
        ("totalBlockingTime",),
    ),
    "fcp": (
        "FCP",
        "ms",
        ("first-contentful-paint",),
        ("firstContentfulPaint",),
    ),
    "si": (
        "SI",
        "ms",
        ("speed-index",),
        ("speedIndex",),
    ),
}

METRIC_ORDER = ("lcp", "inp", "cls", "ttfb", "tbt", "fcp", "si")


class BudgetError(Exception):
    """Raised when the budget file or a report cannot be used."""


def load_json(path: Path, label: str):
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BudgetError(f"cannot read {label} {path}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BudgetError(f"{label} {path} is not valid JSON: {exc}") from exc


def normalize_budget(value, where: str) -> dict:
    """Accept {"lcp": 2500} and {"lcp": {"max": 2500}} shapes."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise BudgetError(f"budget entry {where} must be an object")
    out: dict = {}
    for key, raw in value.items():
        metric = key.strip().lower()
        if metric not in METRICS:
            raise BudgetError(
                f"budget entry {where} has unknown metric {key!r}; "
                f"known metrics: {', '.join(METRIC_ORDER)}"
            )
        if isinstance(raw, dict):
            raw = raw.get("max", raw.get("budget"))
        if raw is None:
            continue
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise BudgetError(f"budget entry {where}.{key} must be a number")
        if raw < 0:
            raise BudgetError(f"budget entry {where}.{key} must not be negative")
        out[metric] = float(raw)
    return out


def load_budget(path: Path) -> dict:
    data = load_json(path, "budget")
    if not isinstance(data, dict):
        raise BudgetError("budget file must contain a JSON object")
    defaults = normalize_budget(data.get("defaults", data.get("default")), "defaults")
    routes: dict = {}
    raw_routes = data.get("routes") or {}
    if not isinstance(raw_routes, dict):
        raise BudgetError("budget 'routes' must be an object")
    for route, spec in raw_routes.items():
        routes[str(route)] = normalize_budget(spec, f"routes[{route!r}]")
    if not defaults and not routes:
        raise BudgetError("budget file defines neither 'defaults' nor 'routes'")
    return {"defaults": defaults, "routes": routes}


def report_url(report: dict) -> str:
    for key in ("requestedUrl", "finalUrl", "finalDisplayedUrl", "mainDocumentUrl"):
        value = report.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def report_path(report: dict) -> str:
    url = report_url(report)
    if not url:
        return "/"
    without_scheme = url.split("://", 1)[-1]
    slash = without_scheme.find("/")
    path = without_scheme[slash:] if slash != -1 else "/"
    if not path.startswith("/"):
        path = "/" + path
    return path


def pick_route(routes: dict, url: str, path: str):
    """Return (route_key, budget) for the most specific matching route."""
    if not routes:
        return None, {}
    candidates = []
    for route in routes:
        spec = routes[route]
        matched = fnmatch.fnmatchcase(path, route) if route.startswith("/") else False
        if not matched and url:
            matched = fnmatch.fnmatchcase(url, route)
        if matched:
            candidates.append((len(route), route, spec))
    if not candidates:
        return None, {}
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, route, spec = candidates[0]
    return route, spec


def extract_metrics(report: dict) -> dict:
    """Pull metric values out of a Lighthouse JSON report."""
    audits = report.get("audits")
    if not isinstance(audits, dict):
        raise BudgetError("report has no 'audits' object; is this a Lighthouse JSON report?")

    metrics_entries = report.get("metrics")
    if not isinstance(metrics_entries, list):
        metrics_entries = []
    by_metric_name = {}
    for entry in metrics_entries:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            by_metric_name.setdefault(entry["name"], entry)

    values: dict = {}
    for metric, (_label, _unit, audit_ids, metric_names) in METRICS.items():
        value = None
        for audit_id in audit_ids:
            audit = audits.get(audit_id)
            if isinstance(audit, dict):
                raw = audit.get("numericValue")
                if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                    value = float(raw)
                    break
        if value is None:
            for metric_name in metric_names:
                entry = by_metric_name.get(metric_name)
                if isinstance(entry, dict):
                    raw = entry.get("value")
                    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                        value = float(raw)
                        break
        if value is not None:
            values[metric] = value
    return values


def format_value(metric: str, value: float) -> str:
    _label, unit, _a, _m = METRICS[metric]
    if metric == "cls":
        return f"{value:.3f}"
    if unit == "ms":
        return f"{int(round(value))} ms"
    return f"{value:.2f}"


def budget_label(metric: str, value: float) -> str:
    return format_value(metric, value)


def check_report(report: dict, budget: dict, source: str) -> dict:
    url = report_url(report)
    path = report_path(report)
    route, route_budget = pick_route(budget["routes"], url, path)
    thresholds = dict(budget["defaults"])
    thresholds.update(route_budget)

    measured = extract_metrics(report)
    checks = []
    violations = []
    for metric in METRIC_ORDER:
        if metric not in thresholds:
            continue
        limit = thresholds[metric]
        value = measured.get(metric)
        if value is None:
            checks.append(
                {
                    "metric": metric,
                    "label": METRICS[metric][0],
                    "value": None,
                    "budget": limit,
                    "status": "skip",
                    "detail": "not measured in this report",
                }
            )
            continue
        ok = value <= limit
        checks.append(
            {
                "metric": metric,
                "label": METRICS[metric][0],
                "value": value,
                "budget": limit,
                "status": "pass" if ok else "fail",
                "detail": "",
            }
        )
        if not ok:
            violations.append(
                {
                    "metric": metric,
                    "label": METRICS[metric][0],
                    "value": value,
                    "budget": limit,
                    "url": url or source,
                    "route": route or "(defaults)",
                }
            )
    return {
        "source": source,
        "url": url,
        "path": path,
        "route": route or "(defaults)",
        "checks": checks,
        "violations": violations,
    }


def print_report(results: list, budget_path: str) -> None:
    print(f"Web Vitals budget check — budgets: {budget_path}\n")
    for result in results:
        target = result["url"] or result["source"]
        print(f"Report: {result['source']}")
        print(f"URL:    {target}")
        print(f"Route:  {result['route']}\n")
        width_label = max([len(c["label"]) for c in result["checks"]] or [4])
        width_value = max(
            [
                max(
                    len(budget_label(c["metric"], c["budget"])),
                    len("not measured")
                    if c["value"] is None
                    else len(format_value(c["metric"], c["value"])),
                )
                for c in result["checks"]
            ]
            or [6]
        )
        header = (
            f"  {'METRIC'.ljust(width_label)}  "
            f"{'MEASURED'.rjust(width_value)}  "
            f"{'BUDGET'.rjust(width_value)}  STATUS"
        )
        print(header)
        print("  " + "-" * (len(header) - 2))
        for check in result["checks"]:
            if check["value"] is None:
                measured_text = "not measured".rjust(width_value)
            else:
                measured_text = format_value(check["metric"], check["value"]).rjust(width_value)
            budget_text = budget_label(check["metric"], check["budget"]).rjust(width_value)
            status = check["status"].upper()
            if check["status"] == "skip":
                status = "SKIP"
            print(
                f"  {check['label'].ljust(width_label)}  "
                f"{measured_text}  {budget_text}  {status}"
            )
            if check["detail"]:
                print(f"    ({check['detail']})")
        print()

    total = sum(len(r["violations"]) for r in results)
    if total == 0:
        print("No budget violations.")
        return
    print(f"{total} budget violation(s):\n")
    for result in results:
        for violation in result["violations"]:
            print(
                f"- {violation['label']} {format_value(violation['metric'], violation['value'])} "
                f"exceeds budget {budget_label(violation['metric'], violation['budget'])} "
                f"on {violation['url']} (route {violation['route']})"
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Lighthouse JSON reports against a Core Web Vitals budget.",
    )
    parser.add_argument("reports", nargs="+", type=Path, help="Lighthouse JSON report(s)")
    parser.add_argument(
        "--budget",
        required=True,
        type=Path,
        help="Budget file (JSON) with 'defaults' and/or 'routes'",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
    args = parser.parse_args()

    try:
        budget = load_budget(args.budget)
        results = []
        for report_path in args.reports:
            report = load_json(report_path, "report")
            if not isinstance(report, dict):
                raise BudgetError(f"report {report_path} must contain a JSON object")
            results.append(check_report(report, budget, str(report_path)))
    except BudgetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    violations = [v for result in results for v in result["violations"]]
    if args.json:
        print(
            json.dumps(
                {
                    "budget": str(args.budget),
                    "ok": not violations,
                    "violations": violations,
                    "reports": results,
                },
                indent=2,
                sort_keys=False,
            )
        )
    else:
        print_report(results, str(args.budget))

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
