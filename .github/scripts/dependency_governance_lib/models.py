from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / ".github" / "dependency-governance.json"
PAGE_SIZE = 100
SAFE_TERMINAL_CONCLUSIONS = {"success", "neutral", "skipped"}
POSITIVE_INT = re.compile(r"^[1-9]\d*$")
SEMVER = re.compile(r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
ACTION_LINE = re.compile(
    r"^(?P<prefix>\s*-\s+uses:\s+)"
    r"(?P<action>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
    r"@(?P<ref>[0-9a-fA-F]{40})"
    r"(?P<suffix>\s+#\s+v(?P<version>\d+(?:\.\d+){0,2})\s*)$"
)
GO_SUM_LINE = re.compile(r"^[^\s]+\s+v[^\s]+(?:/go\.mod)?\s+h1:[A-Za-z0-9+/=]+$")


class GovernanceError(RuntimeError):
    """Operational or configuration failure. The governance workflow must fail."""


@dataclass(frozen=True)
class Assessment:
    pull: dict[str, Any]
    base_sha: str
    head_sha: str
    files: list[dict[str, Any]]
    commits: list[dict[str, Any]]
    ecosystem: str
    provenance: dict[str, Any]
    metadata: list[dict[str, str]]
    semantic: dict[str, Any]
    qualification: dict[str, Any]

    @property
    def eligible(self) -> bool:
        return bool(
            self.provenance.get("eligible")
            and self.semantic.get("eligible")
            and self.qualification.get("eligible")
        )

    @property
    def reasons(self) -> list[str]:
        values: list[str] = []
        for section in (self.provenance, self.semantic, self.qualification):
            values.extend(str(value) for value in section.get("reasons", []) if value)
        return unique(values)


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def parse_positive_integer(value: Any, name: str = "value") -> int:
    text = str(value if value is not None else "").strip()
    if not POSITIVE_INT.fullmatch(text):
        raise GovernanceError(f"{name} must be a positive integer")
    number = int(text)
    if number > 9_007_199_254_740_991:
        raise GovernanceError(f"{name} exceeds the safe integer range")
    return number


def parse_bool(value: Any, name: str = "value") -> bool:
    text = str(value if value is not None else "").strip().lower()
    if text == "true":
        return True
    if text in {"", "false"}:
        return False
    raise GovernanceError(f"{name} must be true or false")


def semver_tuple(value: str) -> tuple[int, int, int] | None:
    match = SEMVER.fullmatch(str(value).strip())
    if not match:
        return None
    return tuple(int(match.group(name)) for name in ("major", "minor", "patch"))


def normalize_version(value: str) -> str:
    text = str(value).strip()
    return text[1:] if text.startswith("v") else text


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or Path(os.environ.get("GOVERNANCE_CONFIG", DEFAULT_CONFIG))
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GovernanceError(f"unable to read governance config {config_path}: {exc}") from exc
    errors = validate_config(config)
    if errors:
        raise GovernanceError("invalid dependency governance config:\n- " + "\n- ".join(errors))
    return config


def validate_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    def nonempty(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    if config.get("schemaVersion") != 1:
        errors.append("schemaVersion must equal 1")
    if config.get("botLogin") != "dependabot[bot]":
        errors.append("botLogin must be dependabot[bot]")
    if not isinstance(config.get("botUserId"), int) or config.get("botUserId", 0) <= 0:
        errors.append("botUserId must be a positive integer")
    for key in (
        "botAuthorEmail",
        "trustedCommitterLogin",
        "gitCommitterName",
        "gitCommitterEmail",
        "signedOffBy",
        "baseBranch",
        "statusCommentMarker",
    ):
        if not nonempty(config.get(key)):
            errors.append(f"{key} must be non-empty")
    if config.get("mergeMethod") not in {"merge", "squash", "rebase"}:
        errors.append("mergeMethod is invalid")
    if not isinstance(config.get("automergeEnabled"), bool):
        errors.append("automergeEnabled must be boolean")
    if config.get("statusCommentMarker") != "<!-- dependency-governance:v1 -->":
        errors.append("statusCommentMarker must equal the v1 governance marker")

    for key, maximum in (
        ("maxChangedFiles", 100),
        ("maxPullRequestAgeDays", 90),
        ("maxPaginationPages", 20),
    ):
        value = config.get(key)
        if not isinstance(value, int) or not 1 <= value <= maximum:
            errors.append(f"{key} must be an integer from 1 to {maximum}")

    labels = config.get("manualReviewLabels")
    if not isinstance(labels, list) or not labels or not all(nonempty(x) for x in labels):
        errors.append("manualReviewLabels must be a non-empty string list")

    workflows = config.get("requiredWorkflows")
    if not isinstance(workflows, list) or not workflows:
        errors.append("requiredWorkflows must be non-empty")
    else:
        names: set[str] = set()
        gates: set[str] = set()
        files: set[str] = set()
        for item in workflows:
            if not isinstance(item, dict):
                errors.append("each required workflow must be an object")
                continue
            workflow, gate, filename = item.get("workflow"), item.get("gate"), item.get("file")
            if not all(nonempty(x) for x in (workflow, gate, filename)):
                errors.append("each required workflow needs workflow, gate, and file")
                continue
            if "/" in filename or not re.fullmatch(r"[A-Za-z0-9._-]+\.ya?ml", filename):
                errors.append(f"workflow file {filename} must be a workflow basename")
            if workflow in names:
                errors.append(f"duplicate workflow {workflow}")
            if gate in gates:
                errors.append(f"duplicate gate {gate}")
            if filename in files:
                errors.append(f"duplicate workflow file {filename}")
            names.add(str(workflow))
            gates.add(str(gate))
            files.add(str(filename))

    for key in ("allowedActionUpdateTypes", "allowedGoOverrideUpdateTypes"):
        values = config.get(key)
        if not isinstance(values, list) or not values or not all(nonempty(x) for x in values):
            errors.append(f"{key} must be a non-empty string list")
            continue
        if any("major" in str(value) for value in values):
            errors.append(f"{key} must never include major updates")
    go_types = config.get("allowedGoOverrideUpdateTypes") or []
    if any("minor" in str(value) for value in go_types):
        errors.append("allowedGoOverrideUpdateTypes must be patch-only")

    manual_paths = config.get("manualReviewPaths")
    if not isinstance(manual_paths, list):
        errors.append("manualReviewPaths must be a list")
        manual_paths = []
    critical = {
        ".github/workflows/security.yml",
        ".github/workflows/dependency-governance.yml",
        ".github/dependency-governance.json",
        ".github/scripts/dependency_governance.py",
        ".github/scripts/dependency_governance_selfcheck.py",
        ".github/scripts/dependency_governance_lib/__init__.py",
        ".github/scripts/dependency_governance_lib/models.py",
        ".github/scripts/dependency_governance_lib/github.py",
        ".github/scripts/dependency_governance_lib/provenance.py",
        ".github/scripts/dependency_governance_lib/semantics.py",
        ".github/scripts/dependency_governance_lib/qualification.py",
        ".github/scripts/dependency_governance_lib/reconcile.py",
        ".github/scripts/dependency_governance_lib/runner.py",
        ".github/dependabot.yml",
    }
    for path in sorted(critical):
        if path not in manual_paths:
            errors.append(f"{path} must require manual review")

    ecosystems = config.get("ecosystems")
    if not isinstance(ecosystems, dict):
        errors.append("ecosystems must be configured")
        return unique(errors)

    docker = ecosystems.get("docker")
    if not isinstance(docker, dict) or docker.get("mode") != "manual":
        errors.append("docker ecosystem must be explicitly manual")
    else:
        if docker.get("files") != ["docker/Dockerfile"]:
            errors.append("docker files must be exactly ['docker/Dockerfile']")
        if not nonempty(docker.get("reason")):
            errors.append("docker manual-review reason must be non-empty")

    gomod = ecosystems.get("gomod-security-override")
    if not isinstance(gomod, dict):
        errors.append("gomod-security-override ecosystem policy is missing")
    else:
        files = gomod.get("files")
        if not isinstance(files, list) or "docker/security-overrides/go.mod" not in files:
            errors.append("gomod-security-override must include its go.mod")
        dependencies = gomod.get("dependencies")
        if (
            not isinstance(dependencies, list)
            or not dependencies
            or not all(nonempty(value) for value in dependencies)
            or len(set(dependencies)) != len(dependencies)
        ):
            errors.append("gomod-security-override dependencies must be a unique non-empty string list")
        if not nonempty(gomod.get("module")):
            errors.append("gomod-security-override module must be non-empty")

    actions = ecosystems.get("github-actions")
    if not isinstance(actions, dict):
        errors.append("github-actions ecosystem policy is missing")
    else:
        if not nonempty(actions.get("workflowPrefix")):
            errors.append("github-actions workflowPrefix must be non-empty")
        extensions = actions.get("extensions")
        if not isinstance(extensions, list) or sorted(extensions) != [".yaml", ".yml"]:
            errors.append("github-actions extensions must be .yml and .yaml")

    return unique(errors)
