from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .github import parse_dependabot_metadata
from .models import unique

def validate_provenance(
    pull: dict[str, Any],
    commits: list[dict[str, Any]],
    base_sha: str,
    config: dict[str, Any],
    repository: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    now = now or datetime.now(timezone.utc)
    user = pull.get("user") or {}
    if user.get("login") != config["botLogin"]:
        reasons.append(f"PR author is {user.get('login') or 'unknown'}, not {config['botLogin']}")
    if user.get("id") != config["botUserId"]:
        reasons.append(
            f"PR author numeric identity is {user.get('id', 'unknown')}, expected {config['botUserId']}"
        )
    if pull.get("state") != "open":
        reasons.append("PR is not open")
    if pull.get("draft"):
        reasons.append("draft PRs are never autonomously merged")
    if config.get("automergeEnabled") is not True:
        reasons.append("repository autonomous merge kill switch is disabled")

    base = pull.get("base") or {}
    head = pull.get("head") or {}
    if base.get("ref") != config["baseBranch"]:
        reasons.append(f"base branch is {base.get('ref')}, expected {config['baseBranch']}")
    if (base.get("repo") or {}).get("full_name") != repository:
        reasons.append("base repository is not the governed repository")
    if (head.get("repo") or {}).get("full_name") != repository:
        reasons.append("Dependabot PR head must be in the governed repository")
    if not str(head.get("ref") or "").startswith("dependabot/"):
        reasons.append("head branch is not a Dependabot branch")

    labels = {
        label if isinstance(label, str) else label.get("name")
        for label in (pull.get("labels") or [])
    }
    for label in config["manualReviewLabels"]:
        if label in labels:
            reasons.append(f"PR carries manual-review label {label}")

    try:
        created_at = datetime.fromisoformat(str(pull.get("created_at")).replace("Z", "+00:00"))
        age_days = (now - created_at.astimezone(timezone.utc)).total_seconds() / 86400
        if age_days < 0:
            reasons.append("PR creation time is in the future")
        elif age_days > config["maxPullRequestAgeDays"]:
            reasons.append(
                f"PR age {age_days:.1f}d exceeds {config['maxPullRequestAgeDays']}d autonomous limit"
            )
    except (TypeError, ValueError):
        reasons.append("PR created_at is invalid")

    if len(commits) != 1:
        reasons.append(f"expected exactly one untouched Dependabot commit, found {len(commits)}")
        return {"eligible": False, "reasons": unique(reasons)}

    commit = commits[0]
    head_sha = str(head.get("sha") or "")
    if commit.get("sha") != head_sha:
        reasons.append("single commit SHA does not equal current PR head")
    parents = commit.get("parents") or []
    if len(parents) != 1 or (parents[0] or {}).get("sha") != base_sha:
        reasons.append("Dependabot commit parent is not the current main SHA")

    git = commit.get("commit") or {}
    author = git.get("author") or {}
    committer = git.get("committer") or {}
    if author.get("email") != config["botAuthorEmail"]:
        reasons.append("Git author email is not the canonical Dependabot identity")
    top_author = commit.get("author") or {}
    if top_author.get("login") != config["botLogin"] or top_author.get("id") != config["botUserId"]:
        reasons.append("materialized commit author is not the canonical Dependabot account")
    top_committer = commit.get("committer") or {}
    if top_committer.get("login") != config["trustedCommitterLogin"]:
        reasons.append("materialized commit committer is not GitHub web-flow")
    if committer.get("name") != config["gitCommitterName"]:
        reasons.append("Git committer name is not canonical GitHub")
    if committer.get("email") != config["gitCommitterEmail"]:
        reasons.append("Git committer email is not canonical GitHub")

    verification = git.get("verification") or {}
    if verification.get("verified") is not True:
        reasons.append("Dependabot commit signature is not verified")
    if verification.get("reason") != "valid":
        reasons.append(f"Dependabot signature reason is {verification.get('reason') or 'unknown'}, not valid")
    if not str(verification.get("signature") or "").strip():
        reasons.append("verified signature material is missing")
    if not str(verification.get("payload") or "").strip():
        reasons.append("verified signature payload is missing")
    message = str(git.get("message") or "")
    if config["signedOffBy"] not in message.splitlines():
        reasons.append("canonical Dependabot Signed-off-by trailer is missing")
    if not parse_dependabot_metadata(message):
        reasons.append("signed Dependabot updated-dependencies metadata is missing")

    return {"eligible": not reasons, "reasons": unique(reasons)}


def validate_manual_path_scope(files: list[dict[str, Any]], config: dict[str, Any]) -> list[str]:
    manual = set(str(path) for path in config["manualReviewPaths"])
    return [
        f"control-plane path {name} always requires manual review"
        for name in (str(file.get("filename", "")) for file in files)
        if name in manual
    ]


def validate_docker_manual(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "eligible": False,
        "reasons": [str(config["ecosystems"]["docker"]["reason"])],
        "changes": [],
    }
