#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from dependency_governance_lib.github import GitHubApi, classify_ecosystem, parse_dependabot_metadata
from dependency_governance_lib.models import GovernanceError, load_config, parse_positive_integer, unique
from dependency_governance_lib.provenance import validate_provenance
from dependency_governance_lib.qualification import latest_runs_by_path
from dependency_governance_lib.semantics import validate_actions, validate_go_override

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECOVERY_CONFIG = ROOT / ".github" / "dependency-recovery.json"
TRUSTED_BASE_BRANCH = "main"
LOG_TIMESTAMP = re.compile(
    r"^\ufeff?(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s"
)
DEPENDABOT_BRANCH = re.compile(r"^dependabot/[A-Za-z0-9._/-]+$")
TERMINAL_NONBLOCKING_CONCLUSIONS = {"success", "skipped"}

TRANSIENT_SIGNATURES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("dns-eai-again", re.compile(r"\bEAI_AGAIN\b", re.I)),
    ("dns-resolution", re.compile(r"\b(?:Temporary failure in name resolution|Name or service not known)\b", re.I)),
    ("connection-reset", re.compile(r"\bECONNRESET\b", re.I)),
    ("connection-timeout", re.compile(r"\bETIMEDOUT\b", re.I)),
    ("socket-timeout", re.compile(r"\bERR_SOCKET_TIMEOUT\b", re.I)),
    ("network-unreachable", re.compile(r"\bENETUNREACH\b", re.I)),
    ("host-unreachable", re.compile(r"\bEHOSTUNREACH\b", re.I)),
    ("socket-hang-up", re.compile(r"\bsocket hang up\b", re.I)),
    (
        "http-5xx",
        re.compile(
            r"(?:server returned code|status(?: code)?|HTTP(?:/\d(?:\.\d)?)?)"
            r"\s*[:=]?\s*(?:502|503|504)\b",
            re.I,
        ),
    ),
    (
        "gateway-service-outage",
        re.compile(r"\b(?:502 Bad Gateway|503 Service Unavailable|504 Gateway Timeout)\b", re.I),
    ),
    (
        "tls-transient",
        re.compile(
            r"\bTLS\b.*\b(?:handshake|connection)\b.*"
            r"\b(?:timeout|timed out|unexpected EOF)\b",
            re.I,
        ),
    ),
)

NON_TRANSIENT_SIGNATURES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "missing-artifact-evidence",
        re.compile(r"(?:No files were found|No files were found with the provided path|if-no-files-found)", re.I),
    ),
    (
        "http-client-or-policy",
        re.compile(
            r"(?:server returned code|status(?: code)?|HTTP(?:/\d(?:\.\d)?)?)"
            r"\s*[:=]?\s*(?:400|401|403|404|409|422|429)\b",
            re.I,
        ),
    ),
    ("permission-denied", re.compile(r"\b(?:EACCES|EPERM|Permission denied)\b", re.I)),
    ("disk-space", re.compile(r"\b(?:ENOSPC|No space left on device)\b", re.I)),
)

NEVER_RECOVER_STEPS = {
    "Validate immutable workflow and runtime provenance",
    "Validate shell refusal contract",
    "Validate local fixture syntax",
    "Build tracked k6 image and validate non-traffic default",
    "Validate k6 runtime refusal contract without sending traffic",
    "Prepare writable report directory without pre-creating evidence",
    "Build tracked k6 image",
    "Run pinned k6 smoke gate against repository-owned fixture",
    "Validate meaningful allowlisted smoke evidence",
    "Publish smoke observability summary",
    "Prepare evidence directory",
    "Reject invalid soak configuration without traffic",
    "Inspect ${{ matrix.profile }} profile without executing traffic",
    "Validate resolved ${{ matrix.profile }} scenario and threshold evidence",
    "Publish profile observability summary",
    "Initialize CodeQL",
    "Analyze",
    "Scan repository configuration and committed secrets",
    "Require attributed repository security evidence",
    "Scan built k6 image",
    "Require attributed built-image security evidence",
    "Probe GitHub Dependency graph",
    "Review dependency changes",
    "Confirm independent fallback gates",
    "Require guardrails and deterministic smoke",
    "Require every sustained profile contract",
    "Require applicable security domains",
}

SAFE_TRANSIENT_STEPS = {
    "Upload k6 summary",
    "Upload extended evidence",
    "Upload repository security evidence",
    "Upload container security evidence",
}


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_recovery_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or Path(os.environ.get("RECOVERY_CONFIG", DEFAULT_RECOVERY_CONFIG))
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GovernanceError(f"unable to read recovery config {config_path}: {exc}") from exc
    errors = validate_recovery_config(config)
    if errors:
        raise GovernanceError("invalid dependency recovery config:\n- " + "\n- ".join(errors))
    return config


def validate_recovery_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if config.get("schemaVersion") != 1:
        errors.append("schemaVersion must equal 1")
    if not isinstance(config.get("enabled"), bool):
        errors.append("enabled must be boolean")
    attempts = config.get("maxRunAttempts")
    if attempts != 2:
        errors.append("maxRunAttempts must equal 2")
    steps = config.get("transientSteps")
    if not isinstance(steps, list) or not steps:
        errors.append("transientSteps must be a non-empty array")
    else:
        if any(not isinstance(step, str) or not step.strip() for step in steps):
            errors.append("every transientSteps entry must be a non-empty string")
        if len(set(steps)) != len(steps):
            errors.append("transientSteps must not contain duplicates")
        for step in steps:
            if step not in SAFE_TRANSIENT_STEPS:
                errors.append(f"{step} is not in the code-owned recovery allowlist")
        for forbidden in sorted(NEVER_RECOVER_STEPS):
            if forbidden in steps:
                errors.append(f"{forbidden} must never be eligible for automatic recovery")
    return unique(errors)


def matching_transient_signatures(logs: str) -> list[str]:
    return [name for name, pattern in TRANSIENT_SIGNATURES if pattern.search(str(logs or ""))]


def matching_non_transient_signatures(logs: str) -> list[str]:
    return [name for name, pattern in NON_TRANSIENT_SIGNATURES if pattern.search(str(logs or ""))]


def extract_step_log_window(logs: str, step: dict[str, Any]) -> str | None:
    started = _parse_timestamp(step.get("started_at"))
    completed = _parse_timestamp(step.get("completed_at"))
    if started is None or completed is None or completed < started:
        return None
    selected: list[str] = []
    for line in str(logs or "").splitlines():
        match = LOG_TIMESTAMP.match(line)
        if not match:
            continue
        timestamp = _parse_timestamp(match.group(1))
        if timestamp is not None and started <= timestamp <= completed:
            selected.append(line)
    return "\n".join(selected) if selected else None


def classify_leaf_job_failure(
    job: dict[str, Any], logs: str, recovery_config: dict[str, Any]
) -> dict[str, Any]:
    if job.get("conclusion") != "failure":
        return {"transient": False, "reason": "job conclusion is not failure", "signatures": []}
    failed_steps = [step for step in (job.get("steps") or []) if step.get("conclusion") == "failure"]
    if len(failed_steps) != 1:
        return {
            "transient": False,
            "reason": f"expected exactly one failed step, found {len(failed_steps)}",
            "signatures": [],
        }
    failed_step = failed_steps[0]
    name = str(failed_step.get("name") or "")
    if name not in recovery_config["transientSteps"]:
        return {
            "transient": False,
            "reason": f"failed step is not allowlisted for transient recovery: {name}",
            "signatures": [],
            "failedStep": name,
        }
    step_logs = extract_step_log_window(logs, failed_step)
    if step_logs is None:
        return {
            "transient": False,
            "reason": f"failed step has no attributable timestamp-bounded log window: {name}",
            "signatures": [],
            "failedStep": name,
        }
    blockers = matching_non_transient_signatures(step_logs)
    if blockers:
        return {
            "transient": False,
            "reason": "failed step contains deterministic or policy-blocking evidence: "
            + ", ".join(blockers),
            "signatures": [],
            "blockers": blockers,
            "failedStep": name,
        }
    signatures = matching_transient_signatures(step_logs)
    if not signatures:
        return {
            "transient": False,
            "reason": "allowlisted infrastructure step has no proven transient network/service "
            f"signature in its own log window: {name}",
            "signatures": [],
            "failedStep": name,
        }
    return {
        "transient": True,
        "reason": f"proven transient infrastructure failure in {name}",
        "signatures": signatures,
        "failedStep": name,
    }


def classify_run_failure(
    run: dict[str, Any],
    jobs: list[dict[str, Any]],
    logs_by_job_id: dict[int, str],
    gate_name: str,
    recovery_config: dict[str, Any],
) -> dict[str, Any]:
    if run.get("status") != "completed" or run.get("conclusion") != "failure":
        return {"rerunnable": False, "reason": "workflow run is not a completed failure", "failures": []}
    attempt = int(run.get("run_attempt") or 1)
    if attempt >= recovery_config["maxRunAttempts"]:
        return {
            "rerunnable": False,
            "reason": f"workflow run attempt {attempt} reached recovery cap {recovery_config['maxRunAttempts']}",
            "failures": [],
        }
    gates = [job for job in jobs if job.get("name") == gate_name]
    if len(gates) != 1 or gates[0].get("conclusion") != "failure":
        return {
            "rerunnable": False,
            "reason": "stable aggregate gate is missing, duplicated, or not a completed failure",
            "failures": [],
        }
    leaves = [job for job in jobs if job.get("name") != gate_name]
    ambiguous = [
        job
        for job in leaves
        if job.get("conclusion") != "failure"
        and job.get("conclusion") not in TERMINAL_NONBLOCKING_CONCLUSIONS
    ]
    if ambiguous:
        states = ", ".join(
            f"{job.get('name')}={job.get('conclusion') or 'unknown'}" for job in ambiguous
        )
        return {
            "rerunnable": False,
            "reason": f"leaf job has ambiguous terminal state: {states}",
            "failures": [],
        }
    failed = [job for job in leaves if job.get("conclusion") == "failure"]
    if not failed:
        return {
            "rerunnable": False,
            "reason": "no failed leaf job exists beneath the stable aggregate gate",
            "failures": [],
        }
    failures: list[dict[str, Any]] = []
    for job in failed:
        job_id = parse_positive_integer(job.get("id"), "job id")
        classification = classify_leaf_job_failure(job, logs_by_job_id.get(job_id, ""), recovery_config)
        failures.append({"jobId": job_id, "jobName": job.get("name"), **classification})
    if any(item.get("transient") is not True for item in failures):
        return {
            "rerunnable": False,
            "reason": "at least one failed leaf job is deterministic or ambiguous",
            "failures": failures,
        }
    return {
        "rerunnable": True,
        "reason": "every failed leaf job is a proven transient infrastructure failure",
        "failures": failures,
    }


def recovery_scope_assessment(
    api: GitHubApi,
    pull: dict[str, Any],
    files: list[dict[str, Any]],
    provenance: dict[str, Any],
    metadata: list[dict[str, str]],
    base_sha: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    reasons = list(provenance.get("reasons") or [])
    if config.get("baseBranch") != TRUSTED_BASE_BRANCH:
        reasons.append("governance baseBranch does not match the controller's literal trusted base")
    if pull.get("changed_files") != len(files):
        reasons.append(
            f"GitHub reports {pull.get('changed_files')} changed files but {len(files)} were enumerated"
        )
    if len(files) > config["maxChangedFiles"]:
        reasons.append(f"PR changes {len(files)} files, exceeding recovery limit {config['maxChangedFiles']}")
    protected = [
        str(file.get("filename"))
        for file in files
        if str(file.get("filename")) in config["manualReviewPaths"]
    ]
    if protected:
        reasons.append("recovery is disabled for control-plane path(s): " + ", ".join(protected))
    ecosystem = classify_ecosystem(files, config)
    head_sha = str((pull.get("head") or {}).get("sha") or "")
    semantic: dict[str, Any] = {"eligible": True, "reasons": []}
    merge_policy = "governed-autonomous"
    if ecosystem == "docker":
        merge_policy = "manual"
    elif ecosystem == "gomod-security-override":
        semantic = validate_go_override(api, base_sha, head_sha, files, metadata, config)
    elif ecosystem == "github-actions":
        semantic = validate_actions(files, metadata, config)
    else:
        semantic = {"eligible": False, "reasons": ["changed-file set does not map to one governed dependency ecosystem"]}
    if not semantic.get("eligible"):
        reasons.extend(str(value) for value in semantic.get("reasons") or [])
    return {
        "eligible": bool(provenance.get("eligible")) and not reasons,
        "reasons": unique(reasons),
        "ecosystem": ecosystem,
        "mergePolicy": merge_policy,
    }


def _current_base_sha(api: GitHubApi, config: dict[str, Any]) -> str:
    branch = api.get(f"/branches/{urllib.parse.quote(config['baseBranch'], safe='')}")
    sha = str((branch.get("commit") or {}).get("sha") or "")
    if not sha:
        raise GovernanceError("unable to resolve trusted base branch main")
    return sha


def _pull_files(api: GitHubApi, number: int, config: dict[str, Any]) -> list[dict[str, Any]]:
    files = api.paginate(f"/pulls/{number}/files")
    if len(files) > config["maxChangedFiles"]:
        raise GovernanceError(f"PR changes {len(files)} files; refusing oversized recovery input")
    return files


def _pull_commits(api: GitHubApi, number: int) -> list[dict[str, Any]]:
    commits = api.paginate(f"/pulls/{number}/commits")
    if len(commits) > 100:
        raise GovernanceError(f"PR contains {len(commits)} commits; refusing oversized recovery history")
    return commits


def _recovery_run_identity_reasons(
    run: dict[str, Any], expected: dict[str, str], pull: dict[str, Any], base_sha: str
) -> list[str]:
    reasons: list[str] = []
    path = f".github/workflows/{expected['file']}"
    head = pull.get("head") or {}
    if run.get("name") != expected["workflow"]:
        reasons.append(f"workflow name is {run.get('name')!r}, expected {expected['workflow']!r}")
    if run.get("path") != path:
        reasons.append(f"workflow path is {run.get('path')!r}, expected {path!r}")
    if run.get("event") != "pull_request":
        reasons.append("workflow event is not pull_request")
    if run.get("head_sha") != head.get("sha"):
        reasons.append("workflow run is not bound to the current PR head SHA")
    if run.get("head_branch") != head.get("ref"):
        reasons.append("workflow run is not bound to the current PR head branch")
    if run.get("status") != "completed" or run.get("conclusion") != "failure":
        reasons.append("workflow run is not a completed failure")
    associations = run.get("pull_requests") or []
    if associations:
        if len(associations) != 1 or associations[0].get("number") != pull.get("number"):
            reasons.append("workflow run PR association does not match the target pull request")
        else:
            associated_base = (associations[0].get("base") or {}).get("sha")
            if associated_base and associated_base != base_sha:
                reasons.append("workflow run tested an obsolete base SHA")
    return reasons


def _failed_qualification_runs(
    api: GitHubApi, pull: dict[str, Any], base_sha: str, config: dict[str, Any]
) -> list[tuple[dict[str, str], dict[str, Any]]]:
    head_sha = str((pull.get("head") or {}).get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise GovernanceError("pull request head SHA is not a canonical 40-character SHA")
    query = urllib.parse.urlencode({"head_sha": head_sha, "event": "pull_request"})
    runs = api.paginate(f"/actions/runs?{query}", "workflow_runs")
    latest = latest_runs_by_path(runs)
    failures: list[tuple[dict[str, str], dict[str, Any]]] = []
    for requirement in config["requiredWorkflows"]:
        path = f".github/workflows/{requirement['file']}"
        run = latest.get(path)
        if not run or run.get("status") != "completed" or run.get("conclusion") != "failure":
            continue
        reasons = _recovery_run_identity_reasons(run, requirement, pull, base_sha)
        if reasons:
            continue
        failures.append((requirement, run))
    return failures


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def download_job_logs(api: GitHubApi, job_id: int) -> str:
    url = f"{api.root}/actions/jobs/{job_id}/logs"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {api.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "dependency-recovery",
        },
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=30) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code not in {301, 302, 303, 307, 308}:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise GovernanceError(f"unable to download logs for job {job_id}: {exc.code} {detail}") from exc
        location = exc.headers.get("Location")
        if not location:
            raise GovernanceError(f"job {job_id} log redirect did not include a location") from exc
    parsed = urllib.parse.urlparse(location)
    if parsed.scheme != "https" or not parsed.netloc:
        raise GovernanceError(f"job {job_id} log redirect is not an absolute HTTPS URL")
    unsigned_request = urllib.request.Request(location, headers={"User-Agent": "dependency-recovery"})
    try:
        with urllib.request.urlopen(unsigned_request, timeout=30) as response:
            return response.read().decode("utf-8", "replace")
    except OSError as exc:
        raise GovernanceError(f"unable to follow signed log redirect for job {job_id}: {exc}") from exc


def _classify_requirement_failure(
    api: GitHubApi,
    requirement: dict[str, str],
    run: dict[str, Any],
    recovery_config: dict[str, Any],
    log_loader: Callable[[GitHubApi, int], str],
) -> dict[str, Any]:
    run_id = parse_positive_integer(run.get("id"), "workflow run id")
    jobs = api.paginate(f"/actions/runs/{run_id}/jobs", "jobs")
    failed_leaves = [
        job for job in jobs if job.get("conclusion") == "failure" and job.get("name") != requirement["gate"]
    ]
    logs_by_job_id: dict[int, str] = {}
    for job in failed_leaves:
        job_id = parse_positive_integer(job.get("id"), "job id")
        try:
            logs_by_job_id[job_id] = log_loader(api, job_id)
        except Exception:
            logs_by_job_id[job_id] = ""
    return {
        "workflow": requirement["workflow"],
        "runId": run_id,
        **classify_run_failure(run, jobs, logs_by_job_id, requirement["gate"], recovery_config),
    }


def _rerun_failed_jobs(api: GitHubApi, run_id: int) -> str:
    safe_run_id = parse_positive_integer(run_id, "workflow run id")
    try:
        api.post(f"/actions/runs/{safe_run_id}/rerun-failed-jobs", {})
        return "rerun-requested"
    except GovernanceError as exc:
        if "failed (409)" in str(exc):
            return "already-running"
        raise


def recover_pull(
    api: GitHubApi,
    number: int,
    governance_config: dict[str, Any],
    recovery_config: dict[str, Any],
    allow_rerun: bool,
    log_loader: Callable[[GitHubApi, int], str] = download_job_logs,
) -> dict[str, Any]:
    safe_number = parse_positive_integer(number, "pull request number")
    pull = api.get(f"/pulls/{safe_number}")
    user = pull.get("user") or {}
    if user.get("login") != governance_config["botLogin"] or user.get("id") != governance_config["botUserId"]:
        return {"pr": safe_number, "skipped": True, "reason": "not canonical Dependabot"}
    if pull.get("state") != "open":
        return {"pr": safe_number, "skipped": True, "reason": f"pull request state is {pull.get('state')}"}

    base_sha = _current_base_sha(api, governance_config)
    files = _pull_files(api, safe_number, governance_config)
    commits = _pull_commits(api, safe_number)
    provenance = validate_provenance(pull, commits, base_sha, governance_config, api.repository)
    message = str(((commits[0].get("commit") or {}).get("message") if len(commits) == 1 else "") or "")
    metadata = parse_dependabot_metadata(message)
    scope = recovery_scope_assessment(
        api, pull, files, provenance, metadata, base_sha, governance_config
    )

    if not recovery_config["enabled"]:
        return {"pr": safe_number, "skipped": True, "reason": "recovery kill switch is disabled", "scope": scope}
    if not scope["eligible"]:
        stale_only = provenance.get("reasons") == ["Dependabot commit parent is not the current main SHA"]
        return {
            "pr": safe_number,
            "skipped": True,
            "reason": (
                "waiting for Dependabot native auto-rebase; controller never mutates Dependabot branches"
                if stale_only
                else "recovery scope is not eligible"
            ),
            "scope": scope,
        }

    failures = [
        _classify_requirement_failure(api, requirement, run, recovery_config, log_loader)
        for requirement, run in _failed_qualification_runs(api, pull, base_sha, governance_config)
    ]
    actions: list[dict[str, Any]] = []
    for failure in failures:
        if not failure.get("rerunnable"):
            continue
        state = "dry-run" if not allow_rerun else _rerun_failed_jobs(api, int(failure["runId"]))
        actions.append(
            {
                "workflow": failure["workflow"],
                "runId": failure["runId"],
                "state": state,
                "reason": failure["reason"],
                "failures": [
                    {
                        "job": item.get("jobName"),
                        "step": item.get("failedStep"),
                        "signatures": item.get("signatures") or [],
                    }
                    for item in failure.get("failures") or []
                ],
            }
        )
    return {
        "pr": safe_number,
        "skipped": False,
        "head": (pull.get("head") or {}).get("sha"),
        "scope": scope,
        "failures": failures,
        "actions": actions,
    }


def _workflow_run_pull(api: GitHubApi, config: dict[str, Any]) -> int | None:
    direct = os.environ.get("TARGET_PR_NUMBER", "").strip()
    if direct:
        return parse_positive_integer(direct, "TARGET_PR_NUMBER")
    branch = os.environ.get("WORKFLOW_RUN_HEAD_BRANCH", "").strip()
    if not branch or not DEPENDABOT_BRANCH.fullmatch(branch):
        return None
    pulls = api.paginate("/pulls?state=open")
    matches = [
        pull
        for pull in pulls
        if ((pull.get("head") or {}).get("ref") == branch)
        and ((pull.get("user") or {}).get("login") == config["botLogin"])
        and ((pull.get("user") or {}).get("id") == config["botUserId"])
    ]
    if len(matches) != 1:
        return None
    return parse_positive_integer(matches[0].get("number"), "matched pull request number")


def run_dependency_recovery(
    api: GitHubApi,
    event_name: str,
    governance_config: dict[str, Any],
    recovery_config: dict[str, Any],
    allow_rerun: bool,
    log_loader: Callable[[GitHubApi, int], str] = download_job_logs,
) -> list[dict[str, Any]] | dict[str, Any] | None:
    if event_name == "schedule":
        pulls = api.paginate("/pulls?state=open")
        results: list[dict[str, Any]] = []
        for pull in pulls:
            user = pull.get("user") or {}
            if user.get("login") != governance_config["botLogin"] or user.get("id") != governance_config["botUserId"]:
                continue
            try:
                results.append(
                    recover_pull(
                        api,
                        parse_positive_integer(pull.get("number"), "scheduled pull request number"),
                        governance_config,
                        recovery_config,
                        allow_rerun,
                        log_loader,
                    )
                )
            except Exception as exc:
                results.append({"pr": pull.get("number"), "error": str(exc)})
        if any("error" in item for item in results):
            raise GovernanceError("scheduled dependency recovery encountered one or more controller errors")
        return results

    number = _workflow_run_pull(api, governance_config)
    if number is None:
        return None
    return recover_pull(api, number, governance_config, recovery_config, allow_rerun, log_loader)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed Dependabot qualification recovery")
    parser.add_argument("--validate-config", action="store_true")
    args = parser.parse_args()

    governance_config = load_config()
    recovery_config = load_recovery_config()
    if governance_config.get("baseBranch") != TRUSTED_BASE_BRANCH:
        raise GovernanceError("governance baseBranch must remain literal main for recovery")
    if args.validate_config:
        print("dependency recovery configuration: valid")
        return 0

    token = os.environ.get("GITHUB_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    event_name = os.environ.get("RECOVERY_EVENT_NAME", os.environ.get("GITHUB_EVENT_NAME", "")).strip()
    if event_name not in {"pull_request_target", "workflow_run", "schedule", "workflow_dispatch"}:
        raise GovernanceError(f"unsupported recovery event: {event_name or 'missing'}")
    api = GitHubApi(token, repository, governance_config["maxPaginationPages"])
    allow_rerun = os.environ.get("ALLOW_RECOVERY_RERUN", "false").strip().lower() == "true"
    result = run_dependency_recovery(api, event_name, governance_config, recovery_config, allow_rerun)
    print(json.dumps({"recovery": result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GovernanceError as exc:
        print(f"dependency recovery failed: {exc}", file=os.sys.stderr)
        raise SystemExit(1) from exc
