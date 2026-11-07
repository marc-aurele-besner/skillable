#!/usr/bin/env python3
"""Run a test command N times and report how often it fails.

Stdlib-only. Use it to measure the flake rate of a suspect test before and
after a fix:

    python3 -I flake_probe.py --runs 20 -- pytest tests/test_orders.py -k refund
    python3 -I flake_probe.py --runs 10 -- npm test -- --runInBand
    python3 -I flake_probe.py --runs 20 --json before.json -- pytest tests/

Everything after the `--` separator is the command to run, verbatim, as a
list of arguments. It is never passed through a shell, so quoting and
globs are the caller's responsibility.

For each run the probe records the exit code and the wall-clock duration,
then prints one row per iteration plus a summary. Exit code is 0 only when
every iteration passed; it is 1 when any iteration failed, and 2 on a usage
error.

Options:
  --runs N      number of iterations (default 20)
  --json PATH   write the full result as JSON to PATH
  --cwd DIR     run the command with DIR as the working directory
  --stop-on-fail  stop at the first failing iteration (default: keep going)
  --quiet       print only the summary table
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

MIN_RUNS = 1
MAX_RUNS = 1000


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a test command repeatedly and report the flake rate.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=20,
        help="number of iterations to run (default: 20)",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        default=None,
        help="write the full result as JSON to this path",
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="working directory for the command (default: current directory)",
    )
    parser.add_argument(
        "--stop-on-fail",
        action="store_true",
        help="stop at the first failing iteration instead of running all of them",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print only the summary, not the per-iteration rows",
    )
    return parser


def split_command(argv: list[str]) -> tuple[list[str], argparse.Namespace]:
    """Split `--` separated argv into probe options and the command to run."""
    if "--" in argv:
        index = argv.index("--")
        return argv[:index], argv[index + 1 :]
    return argv, []


def format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}m{rest:04.1f}s"


def run_once(command: list[str], cwd: str | None) -> dict:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        code = completed.returncode
        output = completed.stdout.decode("utf-8", "replace")
    except FileNotFoundError:
        code = 127
        output = f"command not found: {command[0]}\n"
    except PermissionError as exc:
        code = 126
        output = f"could not execute {command[0]}: {exc}\n"
    duration = time.monotonic() - started
    return {"exit_code": code, "duration_seconds": round(duration, 3), "output": output}


def tail(text: str, max_lines: int = 20) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n".join(lines[-max_lines:])


def main(argv: list[str]) -> int:
    probe_argv, command = split_command(argv)
    parser = build_parser()
    args = parser.parse_args(probe_argv)

    if not command:
        parser.error("no command given; use `-- <test command>`")
    if args.runs < MIN_RUNS or args.runs > MAX_RUNS:
        parser.error(f"--runs must be between {MIN_RUNS} and {MAX_RUNS}")
    if args.cwd and not Path(args.cwd).is_dir():
        parser.error(f"--cwd directory does not exist: {args.cwd}")

    cwd = os.path.abspath(args.cwd) if args.cwd else None
    print(f"command: {' '.join(command)}")
    print(f"runs:    {args.runs}")
    print(f"cwd:     {cwd or os.getcwd()}")
    print()

    results: list[dict] = []
    failed_indices: list[int] = []
    for iteration in range(1, args.runs + 1):
        result = run_once(command, cwd)
        result["iteration"] = iteration
        results.append(result)
        if result["exit_code"] != 0:
            failed_indices.append(iteration)
            status = "FAIL"
        else:
            status = "pass"
        print(f"run {iteration:>3}/{args.runs}  {status}  exit={result['exit_code']}  "
              f"{format_duration(result['duration_seconds'])}")
        if failed_indices and args.stop_on_fail:
            print()
            print("stopping at the first failure (--stop-on-fail)")
            break

    passed = len(results) - len(failed_indices)
    total = len(results)
    rate = (len(failed_indices) / total * 100) if total else 0.0

    print()
    print("summary")
    print("-------")
    print(f"iterations: {total}")
    print(f"passed:     {passed}")
    print(f"failed:     {len(failed_indices)}")
    print(f"flake rate: {rate:.1f}%")
    if failed_indices:
        print(f"failed on runs: {', '.join(str(index) for index in failed_indices)}")

    if failed_indices and not args.quiet:
        for index in failed_indices:
            result = results[index - 1]
            print()
            print(f"--- output of failing run {index} (exit={result['exit_code']}) ---")
            print(tail(result["output"]))

    if args.json_path:
        payload = {
            "command": command,
            "cwd": cwd or os.getcwd(),
            "requested_runs": args.runs,
            "iterations": total,
            "passed": passed,
            "failed": len(failed_indices),
            "flake_rate_percent": round(rate, 2),
            "failed_iterations": failed_indices,
            "results": [
                {
                    "iteration": item["iteration"],
                    "exit_code": item["exit_code"],
                    "duration_seconds": item["duration_seconds"],
                }
                for item in results
            ],
        }
        path = Path(args.json_path)
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print()
        print(f"json written to {path}")

    return 1 if failed_indices else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
