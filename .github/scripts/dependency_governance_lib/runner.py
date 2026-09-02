from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from .github import GitHubApi
from .models import GovernanceError, load_config, parse_bool, parse_positive_integer, unique
from .qualification import fetch_assessment
from .reconcile import reconcile_one, render_status, upsert_status_comment

def load_event() -> dict[str, Any]:
    path = os.environ.get("GITHUB_EVENT_PATH", "").strip()
    if not path:
        raise GovernanceError("GITHUB_EVENT_PATH is required")
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GovernanceError(f"unable to read GitHub event payload: {exc}") from exc


def target_pull_requests(
    api: GitHubApi,
    event_name: str,
    event: dict[str, Any],
    config: dict[str, Any],
) -> list[int]:
    if event_name == "workflow_dispatch":
        inputs = event.get("inputs") or {}
        return [parse_positive_integer(inputs.get("pr-number"), "workflow_dispatch pr-number")]
    if event_name == "pull_request_target":
        pull = event.get("pull_request") or {}
        if (pull.get("user") or {}).get("login") != config["botLogin"]:
            return []
        return [parse_positive_integer(pull.get("number"), "pull_request_target PR number")]
    if event_name == "workflow_run":
        run = event.get("workflow_run") or {}
        if run.get("event") != "pull_request":
            return []
        pulls = run.get("pull_requests") or []
        if len(pulls) != 1:
            return []
        return [parse_positive_integer(pulls[0].get("number"), "workflow_run PR number")]
    if event_name == "schedule":
        pulls = api.paginate(f"/pulls?state=open&base={urllib.parse.quote(config['baseBranch'], safe='')}")
        return [
            int(pull["number"])
            for pull in pulls
            if (pull.get("user") or {}).get("login") == config["botLogin"]
            and isinstance(pull.get("number"), int)
        ]
    raise GovernanceError(f"unsupported governance event {event_name}")


def write_step_summary(lines: list[str]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError as exc:
        raise GovernanceError(f"unable to write step summary: {exc}") from exc


def run_governance(config: dict[str, Any]) -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    api = GitHubApi(
        os.environ.get("GITHUB_TOKEN", "").strip(),
        repository,
        config["maxPaginationPages"],
    )
    event_name = os.environ.get("GITHUB_EVENT_NAME", "").strip()
    if not event_name:
        raise GovernanceError("GITHUB_EVENT_NAME is required")
    event = load_event()
    allow_merge = parse_bool(os.environ.get("ALLOW_MERGE", "false"), "ALLOW_MERGE")
    targets = unique([str(number) for number in target_pull_requests(api, event_name, event, config)])
    if not targets:
        write_step_summary(["## Dependency governance", "", "No Dependabot pull requests required reconciliation."])
        print("no Dependabot pull requests required reconciliation")
        return 0

    results: list[str] = []
    operational_errors: list[str] = []
    for text in targets:
        number = int(text)
        try:
            results.append(reconcile_one(api, number, config, allow_merge))
        except GovernanceError as exc:
            message = f"PR #{number}: operational failure: {exc}"
            results.append(message)
            operational_errors.append(message)
            try:
                pull = api.get(f"/pulls/{number}")
                if (pull.get("user") or {}).get("login") == config["botLogin"] and pull.get("state") == "open":
                    assessment = fetch_assessment(api, number, config)
                    upsert_status_comment(
                        api,
                        number,
                        render_status(assessment, "governance operational failure", [str(exc)]),
                        config,
                    )
            except GovernanceError:
                pass

    write_step_summary(["## Dependency governance", "", *[f"- {result}" for result in results]])
    for result in results:
        print(result)
    if operational_errors:
        raise GovernanceError(
            f"{len(operational_errors)} reconciliation(s) failed operationally; later PRs were still evaluated"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed Dependabot dependency governance")
    parser.add_argument("--validate-config", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_config()
        if args.validate_config:
            print("dependency governance config: ok")
            return 0
        return run_governance(config)
    except GovernanceError as exc:
        print(f"dependency governance error: {exc}", file=sys.stderr)
        return 1

