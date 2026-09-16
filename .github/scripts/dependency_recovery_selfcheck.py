#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from dependency_governance_lib.models import load_config  # noqa: E402
from dependency_recovery import (  # noqa: E402
    _workflow_run_pull,
    classify_leaf_job_failure,
    classify_run_failure,
    extract_step_log_window,
    matching_non_transient_signatures,
    matching_transient_signatures,
    recover_pull,
    validate_recovery_config,
)

ROOT = SCRIPT_DIR.parents[1]
GOVERNANCE = load_config()
RECOVERY = json.loads((ROOT / ".github" / "dependency-recovery.json").read_text(encoding="utf-8"))
SUCCESS_START = "2026-09-16T12:00:00Z"
SUCCESS_END = "2026-09-16T12:00:02Z"
FAILURE_START = "2026-09-16T12:00:03Z"
FAILURE_END = "2026-09-16T12:00:05Z"


def logs(before: str = "", failed: str = "", after: str = "") -> str:
    return "\n".join(
        (
            f"2026-09-16T12:00:01.0000000Z {before}",
            f"2026-09-16T12:00:04.0000000Z {failed}",
            f"2026-09-16T12:00:06.0000000Z {after}",
        )
    )


def job(
    *,
    job_id: int = 10,
    name: str = "smoke",
    step: str = "Upload k6 summary",
    conclusion: str | None = "failure",
    started_at: str | None = FAILURE_START,
    completed_at: str | None = FAILURE_END,
) -> dict[str, Any]:
    return {
        "id": job_id,
        "name": name,
        "conclusion": conclusion,
        "steps": [
            {"name": "Set up job", "conclusion": "success", "started_at": SUCCESS_START, "completed_at": SUCCESS_END},
            {"name": step, "conclusion": conclusion, "started_at": started_at, "completed_at": completed_at},
        ],
    }


def gate(name: str = "ci-gate", conclusion: str = "failure") -> dict[str, Any]:
    return {
        "id": 99,
        "name": name,
        "conclusion": conclusion,
        "steps": [
            {"name": "Require guardrails and deterministic smoke", "conclusion": conclusion, "started_at": FAILURE_START, "completed_at": FAILURE_END}
        ],
    }


def canonical_fixture() -> dict[str, Any]:
    base_sha = "a" * 40
    head_sha = "b" * 40
    old_action_sha = "1" * 40
    new_action_sha = "2" * 40
    repository = "portyu9/fixture"
    pull = {
        "number": 61,
        "state": "open",
        "draft": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "labels": [],
        "commits": 1,
        "changed_files": 1,
        "user": {"login": GOVERNANCE["botLogin"], "id": GOVERNANCE["botUserId"]},
        "base": {"ref": "main", "sha": base_sha, "repo": {"full_name": repository}},
        "head": {"ref": "dependabot/github_actions/routine-actions", "sha": head_sha, "repo": {"full_name": repository}},
    }
    message = (
        "deps(deps): bump actions/checkout\n\n---\nupdated-dependencies:\n"
        "- dependency-name: actions/checkout\n"
        "  dependency-version: '7.0.2'\n"
        "  dependency-type: direct:production\n"
        "  update-type: version-update:semver-patch\n"
        "...\n\n"
        + GOVERNANCE["signedOffBy"]
    )
    commit = {
        "sha": head_sha,
        "author": {"login": GOVERNANCE["botLogin"], "id": GOVERNANCE["botUserId"]},
        "committer": {"login": GOVERNANCE["trustedCommitterLogin"]},
        "parents": [{"sha": base_sha}],
        "commit": {
            "author": {"email": GOVERNANCE["botAuthorEmail"]},
            "committer": {"name": GOVERNANCE["gitCommitterName"], "email": GOVERNANCE["gitCommitterEmail"]},
            "verification": {"verified": True, "reason": "valid", "signature": "fixture-signature", "payload": "fixture-payload"},
            "message": message,
        },
    }
    file = {
        "filename": ".github/workflows/ci.yml",
        "patch": (
            f"-      - uses: actions/checkout@{old_action_sha} # v7.0.1\n"
            f"+      - uses: actions/checkout@{new_action_sha} # v7.0.2"
        ),
    }
    requirement = GOVERNANCE["requiredWorkflows"][0]
    run = {
        "id": 501,
        "name": requirement["workflow"],
        "path": f".github/workflows/{requirement['file']}",
        "event": "pull_request",
        "head_sha": head_sha,
        "head_branch": pull["head"]["ref"],
        "pull_requests": [{"number": pull["number"], "base": {"sha": base_sha}}],
        "status": "completed",
        "conclusion": "failure",
        "run_attempt": 1,
        "updated_at": "2026-09-16T12:00:10Z",
    }
    return {"base_sha": base_sha, "head_sha": head_sha, "pull": pull, "commit": commit, "file": file, "run": run}


class FakeApi:
    def __init__(self, fixture: dict[str, Any], jobs: list[dict[str, Any]]) -> None:
        self.repository = "portyu9/fixture"
        self.root = f"https://api.github.com/repos/{self.repository}"
        self.fixture = fixture
        self.jobs = jobs
        self.reruns: list[int] = []

    def get(self, path: str) -> Any:
        if path == f"/pulls/{self.fixture['pull']['number']}":
            return self.fixture["pull"]
        if path == "/branches/main":
            return {"commit": {"sha": self.fixture["base_sha"]}}
        raise AssertionError(f"unexpected GET {path}")

    def paginate(self, path: str, selector: str | None = None) -> list[Any]:
        number = self.fixture["pull"]["number"]
        if path.startswith(f"/pulls/{number}/files"):
            return [self.fixture["file"]]
        if path.startswith(f"/pulls/{number}/commits"):
            return [self.fixture["commit"]]
        if path.startswith("/actions/runs?"):
            return [self.fixture["run"]]
        if path.startswith(f"/actions/runs/{self.fixture['run']['id']}/jobs"):
            return self.jobs
        if path == "/pulls?state=open":
            return [self.fixture["pull"]]
        raise AssertionError(f"unexpected paginate {path} selector={selector}")

    def post(self, path: str, payload: dict[str, Any]) -> None:
        match = re.fullmatch(r"/actions/runs/(\d+)/rerun-failed-jobs", path)
        if not match:
            raise AssertionError(f"unexpected POST {path}")
        self.reruns.append(int(match.group(1)))


class RecoverySelfCheck(unittest.TestCase):
    def test_config_is_bounded_to_artifact_transport_only(self) -> None:
        self.assertEqual(validate_recovery_config(RECOVERY), [])
        self.assertEqual(RECOVERY["maxRunAttempts"], 2)
        self.assertEqual(
            set(RECOVERY["transientSteps"]),
            {
                "Upload k6 summary",
                "Upload extended evidence",
                "Upload repository security evidence",
                "Upload container security evidence",
            },
        )
        for forbidden in (
            "Build tracked k6 image",
            "Run pinned k6 smoke gate against repository-owned fixture",
            "Validate meaningful allowlisted smoke evidence",
            "Inspect ${{ matrix.profile }} profile without executing traffic",
            "Initialize CodeQL",
            "Analyze",
            "Scan repository configuration and committed secrets",
            "Scan built k6 image",
            "Review dependency changes",
            "Require guardrails and deterministic smoke",
            "Require every sustained profile contract",
            "Require applicable security domains",
        ):
            self.assertNotIn(forbidden, RECOVERY["transientSteps"])
        for attempts in (1, 3, 4):
            self.assertTrue(
                validate_recovery_config({**RECOVERY, "maxRunAttempts": attempts}),
                f"maxRunAttempts={attempts} must be rejected",
            )
        expanded = {
            **RECOVERY,
            "transientSteps": [*RECOVERY["transientSteps"], "Download future k6 runtime"],
        }
        self.assertTrue(validate_recovery_config(expanded))

    def test_signature_model_is_narrow_and_missing_artifacts_block(self) -> None:
        self.assertEqual(matching_transient_signatures("HTTP 503"), ["http-5xx"])
        self.assertEqual(matching_transient_signatures("Service Unavailable"), [])
        self.assertIn("missing-artifact-evidence", matching_non_transient_signatures("No files were found with the provided path"))
        self.assertIn("http-client-or-policy", matching_non_transient_signatures("HTTP 403"))

    def test_failed_step_timestamp_window_is_authoritative(self) -> None:
        candidate = job()
        window = extract_step_log_window(logs("EAI_AGAIN", "HTTP 403", "HTTP 503"), candidate["steps"][1])
        self.assertIsNotNone(window)
        assert window is not None
        self.assertIn("HTTP 403", window)
        self.assertNotIn("EAI_AGAIN", window)
        result = classify_leaf_job_failure(candidate, logs("EAI_AGAIN", "HTTP 403"), RECOVERY)
        self.assertFalse(result["transient"])

    def test_only_allowlisted_upload_with_transient_evidence_is_retryable(self) -> None:
        self.assertTrue(classify_leaf_job_failure(job(), logs(failed="ECONNRESET"), RECOVERY)["transient"])
        self.assertFalse(classify_leaf_job_failure(job(), logs(failed="artifact upload failed"), RECOVERY)["transient"])
        for step in (
            "Build tracked k6 image",
            "Run pinned k6 smoke gate against repository-owned fixture",
            "Validate meaningful allowlisted smoke evidence",
            "Inspect ${{ matrix.profile }} profile without executing traffic",
            "Scan repository configuration and committed secrets",
            "Scan built k6 image",
            "Review dependency changes",
        ):
            self.assertFalse(classify_leaf_job_failure(job(step=step), logs(failed="EAI_AGAIN HTTP 503"), RECOVERY)["transient"], step)

    def test_run_requires_failed_gate_unambiguous_siblings_and_one_retry_cap(self) -> None:
        run = {"status": "completed", "conclusion": "failure", "run_attempt": 1}
        positive = classify_run_failure(run, [job(), gate()], {10: logs(failed="EAI_AGAIN")}, "ci-gate", RECOVERY)
        self.assertTrue(positive["rerunnable"], positive["reason"])
        sibling = {"id": 20, "name": "sibling", "conclusion": "cancelled", "steps": []}
        self.assertFalse(classify_run_failure(run, [job(), sibling, gate()], {10: logs(failed="EAI_AGAIN")}, "ci-gate", RECOVERY)["rerunnable"])
        capped = classify_run_failure({"status": "completed", "conclusion": "failure", "run_attempt": 2}, [job(), gate()], {10: logs(failed="EAI_AGAIN")}, "ci-gate", RECOVERY)
        self.assertFalse(capped["rerunnable"])

    def test_control_plane_is_manual_review(self) -> None:
        for path in (
            ".github/dependabot.yml",
            ".github/dependency-governance.json",
            ".github/dependency-recovery.json",
            ".github/scripts/dependency_governance.py",
            ".github/scripts/dependency_governance_selfcheck.py",
            ".github/scripts/dependency_recovery.py",
            ".github/scripts/dependency_recovery_selfcheck.py",
            ".github/workflows/dependency-governance.yml",
        ):
            self.assertIn(path, GOVERNANCE["manualReviewPaths"], path)

    def test_exact_provenance_and_action_semantics_request_one_rerun(self) -> None:
        fixture = canonical_fixture()
        api = FakeApi(fixture, [job(), gate()])
        result = recover_pull(
            api,
            fixture["pull"]["number"],
            GOVERNANCE,
            RECOVERY,
            True,
            log_loader=lambda _api, _job_id: logs(failed="EAI_AGAIN"),
        )
        self.assertEqual(api.reruns, [fixture["run"]["id"]])
        self.assertEqual(result["actions"][0]["state"], "rerun-requested")
        self.assertEqual(result["scope"]["ecosystem"], "github-actions")

    def test_stale_base_waits_for_native_rebase_without_mutation(self) -> None:
        fixture = canonical_fixture()
        fixture["commit"]["parents"] = [{"sha": "c" * 40}]
        api = FakeApi(fixture, [job(), gate()])
        result = recover_pull(api, fixture["pull"]["number"], GOVERNANCE, RECOVERY, True, log_loader=lambda _api, _job_id: logs(failed="EAI_AGAIN"))
        self.assertEqual(api.reruns, [])
        self.assertTrue(result["skipped"])
        self.assertIn("native auto-rebase", result["reason"])

    def test_workflow_run_resolution_accepts_only_dependabot_branch(self) -> None:
        fixture = canonical_fixture()
        api = FakeApi(fixture, [])
        previous = {name: os.environ.get(name) for name in ("TARGET_PR_NUMBER", "WORKFLOW_RUN_HEAD_BRANCH")}
        try:
            os.environ.pop("TARGET_PR_NUMBER", None)
            os.environ["WORKFLOW_RUN_HEAD_BRANCH"] = fixture["pull"]["head"]["ref"]
            self.assertEqual(_workflow_run_pull(api, GOVERNANCE), fixture["pull"]["number"])
            os.environ["WORKFLOW_RUN_HEAD_BRANCH"] = "feature/not-dependabot"
            self.assertIsNone(_workflow_run_pull(api, GOVERNANCE))
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_wiring_requires_native_rebase_and_recovery_before_governance(self) -> None:
        dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "dependency-governance.yml").read_text(encoding="utf-8")
        self.assertEqual(dependabot.count("rebase-strategy: auto"), 3)
        self.assertIn("RECOVERY_CONFIG: .github/dependency-recovery.json", workflow)
        self.assertIn("python .github/scripts/dependency_recovery.py --validate-config", workflow)
        self.assertIn("python .github/scripts/dependency_recovery_selfcheck.py", workflow)
        self.assertIn("ALLOW_RECOVERY_RERUN:", workflow)
        self.assertLess(workflow.index("Attempt bounded dependency recovery"), workflow.index("Reconcile dependency governance"))
        self.assertNotIn("update-branch", (SCRIPT_DIR / "dependency_recovery.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
