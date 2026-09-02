from __future__ import annotations

import urllib.parse
from typing import Any

from .github import GitHubApi
from .models import Assessment, GovernanceError
from .qualification import fetch_assessment

def render_status(assessment: Assessment, decision: str, extra: list[str] | None = None) -> str:
    marker = "<!-- dependency-governance:v1 -->"
    reasons = assessment.reasons + list(extra or [])
    lines = [
        marker,
        "## Dependency governance",
        "",
        f"- Decision: **{decision}**",
        f"- Ecosystem: `{assessment.ecosystem}`",
        f"- Exact head: `{assessment.head_sha or 'unknown'}`",
        f"- Current base: `{assessment.base_sha}`",
        f"- Canonical Dependabot provenance: **{'pass' if assessment.provenance.get('eligible') else 'block'}**",
        f"- Semantic dependency scope: **{'pass' if assessment.semantic.get('eligible') else 'block'}**",
        f"- Exact-head workflow qualification: **{'pass' if assessment.qualification.get('eligible') else 'block'}**",
    ]
    changes = assessment.semantic.get("changes") or []
    if changes:
        lines.extend(["", "Proven semantic changes:"])
        for change in changes[:20]:
            if "action" in change:
                lines.append(f"- `{change['action']}` -> `{change['version']}` in `{change['file']}`")
            else:
                lines.append(f"- `{change.get('dependency')}`: `{change.get('from')}` -> `{change.get('to')}`")
    if reasons:
        lines.extend(["", "Blocking reasons:"])
        lines.extend(f"- {reason}" for reason in reasons[:30])
    lines.extend(
        [
            "",
            "Privileged reconciliation executes only trusted default-branch governance code; pull-request code is never executed with write permissions.",
        ]
    )
    return "\n".join(lines) + "\n"


def upsert_status_comment(api: GitHubApi, number: int, body: str, config: dict[str, Any]) -> None:
    comments = api.paginate(f"/issues/{number}/comments")
    marker = str(config["statusCommentMarker"])
    matches = [comment for comment in comments if marker in str(comment.get("body") or "")]
    if len(matches) > 1:
        raise GovernanceError(
            f"PR #{number} has {len(matches)} governance status comments; refusing ambiguous update"
        )
    if matches:
        api.patch(f"/issues/comments/{matches[0]['id']}", {"body": body})
    else:
        api.post(f"/issues/{number}/comments", {"body": body})


def dispatch_main_qualification(api: GitHubApi, config: dict[str, Any]) -> None:
    failures: list[str] = []
    for expected in config["requiredWorkflows"]:
        try:
            api.post(
                f"/actions/workflows/{urllib.parse.quote(expected['file'], safe='')}/dispatches",
                {"ref": config["baseBranch"]},
            )
        except GovernanceError as exc:
            failures.append(f"{expected['workflow']}: {exc}")
    if failures:
        raise GovernanceError(
            "post-merge main qualification dispatch failed for " + "; ".join(failures)
        )


def merge_exact_head(api: GitHubApi, assessment: Assessment, config: dict[str, Any]) -> dict[str, Any]:
    number = int(assessment.pull["number"])
    refreshed = fetch_assessment(api, number, config)
    if refreshed.head_sha != assessment.head_sha:
        raise GovernanceError("PR head changed during pre-merge refresh")
    if refreshed.base_sha != assessment.base_sha:
        raise GovernanceError("main changed during pre-merge refresh")
    if not refreshed.eligible:
        return {"merged": False, "assessment": refreshed}
    result = api.put(
        f"/pulls/{number}/merge",
        {
            "sha": refreshed.head_sha,
            "merge_method": config["mergeMethod"],
            "commit_title": str(refreshed.pull.get("title") or "Dependabot qualified update"),
            "commit_message": (
                "Autonomously merged by the repository dependency-governance policy after "
                "canonical Dependabot provenance, semantic dependency validation, and exact-head "
                "CI/Extended/Security/Docs qualification were revalidated immediately before merge."
            ),
        },
    )
    if not isinstance(result, dict) or result.get("merged") is not True:
        raise GovernanceError(f"GitHub rejected exact-head merge for PR #{number}: {result}")
    return {"merged": True, "assessment": refreshed, "result": result}


def reconcile_one(
    api: GitHubApi,
    number: int,
    config: dict[str, Any],
    allow_merge: bool,
) -> str:
    pull = api.get(f"/pulls/{number}")
    user = pull.get("user") or {}
    if user.get("login") != config["botLogin"]:
        return f"PR #{number}: ignored non-Dependabot pull request"
    assessment = fetch_assessment(api, number, config)
    if not assessment.eligible:
        upsert_status_comment(api, number, render_status(assessment, "manual review required"), config)
        return f"PR #{number}: blocked ({'; '.join(assessment.reasons[:3])})"
    if not allow_merge:
        upsert_status_comment(api, number, render_status(assessment, "qualified; merge deferred"), config)
        return f"PR #{number}: qualified; merge deferred"

    merged = merge_exact_head(api, assessment, config)
    refreshed: Assessment = merged["assessment"]
    if not merged["merged"]:
        upsert_status_comment(api, number, render_status(refreshed, "manual review required"), config)
        return f"PR #{number}: pre-merge refresh blocked"

    dispatch_errors: list[str] = []
    try:
        dispatch_main_qualification(api, config)
    except GovernanceError as exc:
        dispatch_errors.append(str(exc))
    decision = "merged; main requalification dispatched" if not dispatch_errors else "merged; post-merge dispatch failed"
    try:
        upsert_status_comment(api, number, render_status(refreshed, decision, dispatch_errors), config)
    except GovernanceError as exc:
        dispatch_errors.append(f"status comment update failed after merge: {exc}")
    if dispatch_errors:
        raise GovernanceError("; ".join(dispatch_errors))
    return f"PR #{number}: merged exact head {refreshed.head_sha}"

