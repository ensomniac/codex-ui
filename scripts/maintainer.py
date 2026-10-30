#!/usr/bin/env python3
"""For Ryan's local agent: approve reviewed commits and optionally merge them."""
import argparse
from pathlib import Path
import subprocess
import time

from review_lib import REPO, envelope, gh_api, payload, sign


def reviewed_pr(number: int, head: str, base: str | None = None) -> dict:
    pr = gh_api(f"repos/{REPO}/pulls/{number}")
    if pr["state"] != "open" or pr["draft"] or pr["head"]["sha"] != head:
        raise SystemExit("PR is not ready or its head changed; review the current diff")
    if pr["base"]["ref"] != "main" or pr["user"]["login"] == "ensomniac":
        raise SystemExit("Requires a contributor PR targeting main; GitHub forbids self-approval")
    if base is not None and pr["base"]["sha"] != base:
        raise SystemExit("PR base changed while checking CI; review the updated diff")
    return pr


def is_pr_run(run: dict, pr: dict) -> bool:
    if run["event"] != "pull_request" or run["head_sha"] != pr["head"]["sha"]:
        return False
    links = run.get("pull_requests") or []
    if links:
        return any(item["number"] == pr["number"] for item in links)
    # GitHub can omit PR links for fork runs, including held first-time builds.
    # Require the exact source repository and branch as well as the event/SHA.
    repo_id = (pr["head"].get("repo") or {}).get("id")
    branch = pr["head"].get("ref")
    return (repo_id is not None and bool(branch)
            and (run.get("head_repository") or {}).get("id") == repo_id
            and run.get("head_branch") == branch)


def ensure_ci(pr: dict) -> None:
    """Start a held, reviewed PR build and wait for that PR's own CI result."""
    head = pr["head"]["sha"]
    result = gh_api(f"repos/{REPO}/actions/workflows/ci.yml/runs"
                    f"?event=pull_request&head_sha={head}&per_page=100")
    runs = [run for run in result["workflow_runs"] if is_pr_run(run, pr)]
    if not runs:
        raise SystemExit("The reviewed PR has no CI run yet; retry after GitHub creates it")
    run = max(runs, key=lambda item: item["id"])
    endpoint = f"repos/{REPO}/actions/runs/{run['id']}"
    if run["conclusion"] == "action_required":
        print(f"Starting reviewed PR CI: {run['html_url']}", flush=True)
        gh_api(endpoint + "/approve", method="POST")
    deadline = time.monotonic() + 1800
    previous = None
    while True:
        run = gh_api(endpoint)
        state = (run["status"], run["conclusion"])
        if state != previous:
            print(f"PR CI: {run['status']} / {run['conclusion'] or 'waiting'}", flush=True)
            previous = state
        if run["status"] == "completed" and run["conclusion"] != "action_required":
            if run["conclusion"] != "success":
                raise SystemExit(f"PR CI did not pass: {run['html_url']}")
            return
        reviewed_pr(pr["number"], head, pr["base"]["sha"])
        if time.monotonic() >= deadline:
            raise SystemExit(f"CI is still pending; resume this review later: {run['html_url']}")
        time.sleep(5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("number", type=int)
    parser.add_argument("--head", required=True, help="The exact commit actually reviewed")
    parser.add_argument("--body-file", required=True, type=Path, help="Review findings and evidence")
    parser.add_argument("--key", type=Path, default=Path.home() / ".config/codex-ui/maintainer_ed25519")
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()
    if gh_api("user")["login"] != "ensomniac":
        raise SystemExit("Trusted approval requires the ensomniac GitHub identity")
    pr = reviewed_pr(args.number, args.head)
    evidence = args.body_file.read_text(encoding="utf-8").strip()
    if len(evidence) < 30:
        raise SystemExit("Provide a concrete review and validation evidence in --body-file")
    ensure_ci(pr)
    pr = reviewed_pr(args.number, args.head, pr["base"]["sha"])
    checks = gh_api(f"repos/{REPO}/commits/{args.head}/check-runs?per_page=100")["check_runs"]
    ci = [c for c in checks if c["name"] == "CI"]
    if not ci or max(ci, key=lambda c: c["id"])["conclusion"] != "success":
        raise SystemExit("The current head must have a successful CI check")
    value = payload(args.number, args.head, pr["base"]["sha"])
    body = "Reviewed by Ryan's local agent.\n\n" + evidence + "\n\n" + envelope(value, sign(value, args.key))
    # Pin approval to the inspected commit; a subsequent push invalidates the gate.
    gh_api(f"repos/{REPO}/pulls/{args.number}/reviews",
           {"commit_id": args.head, "event": "APPROVE", "body": body})
    subprocess.run(["gh", "workflow", "run", "trusted-review.yml", "--repo", REPO,
                    "--ref", "main", "-f", f"pr={args.number}"], check=True)
    print(f"Approved {REPO}#{args.number} at {args.head}; trusted verification queued.")
    if args.merge:
        subprocess.run(["gh", "pr", "merge", str(args.number), "--repo", REPO,
                        "--squash", "--auto", "--match-head-commit", args.head], check=True)


if __name__ == "__main__":
    main()
