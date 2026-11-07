#!/usr/bin/env python3
"""Collect pull-request context into JSON so a reviewer starts from facts.

Stdlib-only and read-only. Shells out to the GitHub CLI (`gh`) to gather:

  - number, title, body, author, url, state, draft flag
  - base and head refs, head SHA, mergeability, review decision
  - additions / deletions / changed-file counts
  - every changed file with its additions and deletions
  - status check rollup (name, status, conclusion)
  - linked issues (closing references plus "Fixes #123" style mentions)

Usage:
    python3 -I pr_context.py <pr-number-or-url>
    python3 -I pr_context.py <pr-number-or-url> --repo <owner>/<repo>
    python3 -I pr_context.py <pr-number-or-url> --json context.json

Exit codes: 0 success, 1 error (bad input, gh missing, API failure).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from urllib.parse import urlparse

PR_URL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)"
    r"/pull/(?P<number>\d+)"
)
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ISSUE_MENTION_RE = re.compile(r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+(?:https://github\.com/\S+/issues/|#)(\d+)", re.IGNORECASE)

VIEW_FIELDS = (
    "number,title,body,url,state,isDraft,author,baseRefName,headRefName,headRefOid,"
    "mergeable,mergeStateStatus,reviewDecision,additions,deletions,changedFiles,"
    "files,statusCheckRollup,closingIssuesReferences,createdAt,updatedAt,labels,"
    "reviewRequests,maintainerCanModify"
)

MAX_BODY_CHARS = 20000


class ContextError(Exception):
    """A user-facing failure: bad input, missing tool, or API error."""


def run_gh(args: list[str], *, repo: str | None = None) -> str:
    """Run `gh` and return stdout. Raises ContextError on failure."""
    cmd = ["gh", *args]
    if repo:
        cmd += ["--repo", repo]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise ContextError(f"failed to run gh: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        message = detail[-1] if detail else f"exit code {proc.returncode}"
        raise ContextError(f"gh {' '.join(args[:2])} failed: {message}")
    return proc.stdout


def view_pr(reference: str, repo: str) -> dict:
    raw = run_gh(["pr", "view", reference, "--json", VIEW_FIELDS], repo=repo)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContextError(f"could not parse gh output as JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ContextError("unexpected gh output: expected a JSON object")
    return data


def detect_repo() -> str | None:
    """Best-effort owner/repo from the current git remote."""
    if shutil.which("git") is None:
        return None
    try:
        proc = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    url = proc.stdout.strip()
    if not url:
        return None
    match = re.search(r"github\.com[:/](?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$", url)
    if not match:
        return None
    return f"{match.group('owner')}/{match.group('repo')}"


def parse_target(raw: str, explicit_repo: str | None) -> tuple[str, str | None]:
    """Return (pr reference, repo). The reference is a number or a full URL."""
    value = raw.strip()
    if not value:
        raise ContextError("no pull request given")
    if value.isdigit():
        return value, explicit_repo
    if value.startswith("http://") or value.startswith("https://"):
        match = PR_URL_RE.match(value.rstrip("/"))
        if not match:
            raise ContextError(f"not a GitHub pull request URL: {raw}")
        repo = f"{match.group('owner')}/{match.group('repo')}"
        if explicit_repo and explicit_repo != repo:
            raise ContextError(
                f"--repo {explicit_repo} conflicts with the URL ({repo}); pass one or the other"
            )
        return match.group("number"), repo
    # Branch name or other gh-acceptable reference: let gh resolve it.
    return value, explicit_repo


def check_rollup(pr: dict) -> list[dict]:
    checks: list[dict] = []
    for entry in pr.get("statusCheckRollup") or []:
        checks.append(
            {
                "name": entry.get("name") or entry.get("context") or "unknown",
                "status": entry.get("status") or entry.get("state"),
                "conclusion": entry.get("conclusion"),
                "workflow": entry.get("workflowName"),
                "link": entry.get("detailsUrl") or entry.get("targetUrl"),
            }
        )
    return checks


def linked_issues(pr: dict, repo: str) -> list[dict]:
    linked: list[dict] = []
    seen: set[int] = set()
    for issue in pr.get("closingIssuesReferences") or []:
        number = issue.get("number")
        if number in seen:
            continue
        seen.add(number)
        linked.append(
            {
                "number": number,
                "title": issue.get("title"),
                "url": issue.get("url"),
                "state": issue.get("state"),
                "source": "closing-reference",
            }
        )
    body = pr.get("body") or ""
    for match in ISSUE_MENTION_RE.finditer(body):
        number = int(match.group(1))
        if number in seen:
            continue
        seen.add(number)
        linked.append(
            {
                "number": number,
                "title": None,
                "url": f"https://github.com/{repo}/issues/{number}",
                "state": None,
                "source": "body-mention",
            }
        )
    return linked


def build_context(raw: str, explicit_repo: str | None) -> dict:
    reference, repo = parse_target(raw, explicit_repo)
    if repo is None:
        repo = detect_repo()
    if repo is None:
        raise ContextError(
            "could not determine the repository; pass --repo <owner>/<repo>"
        )
    if not REPO_RE.match(repo):
        raise ContextError(f"invalid repository {repo!r}")

    pr = view_pr(reference, repo)

    body = pr.get("body") or ""
    truncated = len(body) > MAX_BODY_CHARS
    if truncated:
        body = body[:MAX_BODY_CHARS] + "\n[... body truncated by pr_context.py ...]"

    author = pr.get("author") or {}
    base = pr.get("baseRefName") or ""
    head = pr.get("headRefName") or ""

    files = [
        {
            "path": entry.get("path"),
            "additions": entry.get("additions"),
            "deletions": entry.get("deletions"),
            "changeType": entry.get("changeType"),
        }
        for entry in (pr.get("files") or [])
    ]

    checks = check_rollup(pr)
    conclusions = {check.get("conclusion") for check in checks}
    if not checks:
        check_summary = "none"
    elif "FAILURE" in conclusions or "CANCELLED" in conclusions or "TIMED_OUT" in conclusions:
        check_summary = "failing"
    elif "PENDING" in conclusions or "IN_PROGRESS" in conclusions:
        check_summary = "pending"
    else:
        check_summary = "passing"

    return {
        "repository": repo,
        "pr": {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "url": pr.get("url"),
            "state": pr.get("state"),
            "isDraft": pr.get("isDraft"),
            "author": author.get("login"),
            "authorName": author.get("name") or None,
            "isBot": bool(author.get("is_bot")),
            "baseRef": base,
            "headRef": head,
            "headSha": pr.get("headRefOid"),
            "createdAt": pr.get("createdAt"),
            "updatedAt": pr.get("updatedAt"),
            "mergeable": pr.get("mergeable"),
            "mergeStateStatus": pr.get("mergeStateStatus"),
            "reviewDecision": pr.get("reviewDecision"),
            "labels": [label.get("name") for label in (pr.get("labels") or [])],
            "additions": pr.get("additions"),
            "deletions": pr.get("deletions"),
            "changedFiles": pr.get("changedFiles"),
        },
        "body": body,
        "bodyTruncated": truncated,
        "files": files,
        "checks": checks,
        "checkSummary": check_summary,
        "linkedIssues": linked_issues(pr, repo),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect pull request context (metadata, files, checks, linked issues) as JSON."
    )
    parser.add_argument("pr", help="pull request number or GitHub pull request URL")
    parser.add_argument("--repo", help="owner/repo (defaults to the URL's repo, then the git remote)")
    parser.add_argument("--json", dest="json_path", help="write the JSON to this file instead of stdout")
    args = parser.parse_args()

    if shutil.which("gh") is None:
        print(
            "error: the GitHub CLI ('gh') is not installed or not on PATH.",
            file=sys.stderr,
        )
        return 1

    try:
        context = build_context(args.pr, args.repo)
    except ContextError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = json.dumps(context, indent=2, sort_keys=False)
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        pr = context["pr"]
        print(
            f"wrote {args.json_path}: PR #{pr['number']} {pr['changedFiles']} files, "
            f"{len(context['checks'])} checks ({context['checkSummary']})"
        )
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
