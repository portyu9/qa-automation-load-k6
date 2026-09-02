from __future__ import annotations

import urllib.parse
from typing import Any

from .github import GitHubApi, classify_ecosystem, parse_dependabot_metadata
from .models import SAFE_TERMINAL_CONCLUSIONS, Assessment, GovernanceError, unique
from .provenance import validate_provenance
from .semantics import validate_semantics

def latest_runs_by_path(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for run in runs:
        path = str(run.get("path") or "")
        if not path:
            continue
        current = latest.get(path)
        if current is None or int(run.get("id") or 0) > int(current.get("id") or 0):
            latest[path] = run
    return latest


def validate_run_identity(
    run: dict[str, Any],
    expected: dict[str, str],
    pull: dict[str, Any],
    base_sha: str,
) -> list[str]:
    reasons: list[str] = []
    expected_path = f".github/workflows/{expected['file']}"
    if run.get("name") != expected["workflow"]:
        reasons.append(f"{expected_path} workflow name is {run.get('name')!r}, expected {expected['workflow']!r}")
    if run.get("path") != expected_path:
        reasons.append(f"workflow path is {run.get('path')!r}, expected {expected_path!r}")
    if run.get("event") != "pull_request":
        reasons.append(f"{expected_path} run event is {run.get('event')!r}, expected pull_request")
    head = pull.get("head") or {}
    if run.get("head_sha") != head.get("sha"):
        reasons.append(f"{expected_path} run is not bound to the current PR head SHA")
    if run.get("head_branch") != head.get("ref"):
        reasons.append(f"{expected_path} run is not bound to the current PR head branch")
    if run.get("status") != "completed":
        reasons.append(f"{expected_path} run is still {run.get('status') or 'unknown'}")
    if run.get("conclusion") != "success":
        reasons.append(f"{expected_path} run conclusion is {run.get('conclusion') or 'unknown'}, not success")
    associations = run.get("pull_requests") or []
    if associations:
        number = pull.get("number")
        if len(associations) != 1 or associations[0].get("number") != number:
            reasons.append(f"{expected_path} run PR association does not match PR #{number}")
        else:
            associated_base = (associations[0].get("base") or {}).get("sha")
            if associated_base and associated_base != base_sha:
                reasons.append(f"{expected_path} run tested obsolete base {associated_base}")
    return reasons


def validate_qualification(
    api: GitHubApi,
    pull: dict[str, Any],
    base_sha: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    head = pull.get("head") or {}
    head_sha = str(head.get("sha") or "")
    if not head_sha:
        return {"eligible": False, "reasons": ["PR head SHA is missing"], "runs": []}
    query = urllib.parse.urlencode({"head_sha": head_sha, "event": "pull_request"})
    runs = api.paginate(f"/actions/runs?{query}", selector="workflow_runs")
    latest = latest_runs_by_path(runs)
    reasons: list[str] = []
    evidence: list[dict[str, Any]] = []

    for path, run in latest.items():
        if run.get("status") != "completed":
            reasons.append(f"latest PR workflow {path} is still {run.get('status') or 'unknown'}")
        elif run.get("conclusion") not in SAFE_TERMINAL_CONCLUSIONS:
            reasons.append(f"latest PR workflow {path} concluded {run.get('conclusion') or 'unknown'}")

    for expected in config["requiredWorkflows"]:
        path = f".github/workflows/{expected['file']}"
        run = latest.get(path)
        if not run:
            reasons.append(f"required workflow has not started on exact head: {path}")
            continue
        identity_reasons = validate_run_identity(run, expected, pull, base_sha)
        reasons.extend(identity_reasons)
        gate_state = "missing"
        if not identity_reasons or run.get("status") == "completed":
            jobs = api.paginate(f"/actions/runs/{run.get('id')}/jobs", selector="jobs")
            gates = [job for job in jobs if job.get("name") == expected["gate"]]
            if len(gates) != 1:
                reasons.append(f"{path} must expose exactly one stable gate job {expected['gate']}")
            else:
                gate = gates[0]
                gate_state = str(gate.get("conclusion") or gate.get("status") or "unknown")
                if gate.get("status") != "completed" or gate.get("conclusion") != "success":
                    reasons.append(f"stable gate {expected['gate']} is {gate_state}, not success")
        evidence.append(
            {
                "workflow": expected["workflow"],
                "path": path,
                "runId": run.get("id"),
                "conclusion": run.get("conclusion"),
                "gate": expected["gate"],
                "gateState": gate_state,
            }
        )

    return {"eligible": not reasons, "reasons": unique(reasons), "runs": evidence}


def current_main_sha(api: GitHubApi, config: dict[str, Any]) -> str:
    branch = api.get(f"/branches/{urllib.parse.quote(config['baseBranch'], safe='')}")
    sha = str((branch.get("commit") or {}).get("sha") or "")
    if not sha:
        raise GovernanceError("unable to resolve current main SHA")
    return sha


def fetch_assessment(api: GitHubApi, number: int, config: dict[str, Any]) -> Assessment:
    pull = api.get(f"/pulls/{number}")
    base_sha = current_main_sha(api, config)
    files = api.paginate(f"/pulls/{number}/files")
    commits = api.paginate(f"/pulls/{number}/commits")
    head_sha = str((pull.get("head") or {}).get("sha") or "")
    repository = api.repository
    provenance = validate_provenance(pull, commits, base_sha, config, repository)
    message = str(((commits[0].get("commit") or {}).get("message") if len(commits) == 1 else "") or "")
    metadata = parse_dependabot_metadata(message)
    ecosystem = classify_ecosystem(files, config)
    semantic = validate_semantics(api, ecosystem, base_sha, head_sha, files, metadata, config)
    qualification = validate_qualification(api, pull, base_sha, config)
    return Assessment(
        pull=pull,
        base_sha=base_sha,
        head_sha=head_sha,
        files=files,
        commits=commits,
        ecosystem=ecosystem,
        provenance=provenance,
        metadata=metadata,
        semantic=semantic,
        qualification=qualification,
    )

