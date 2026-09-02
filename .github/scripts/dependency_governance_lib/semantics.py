from __future__ import annotations

import re
from typing import Any

from .github import GitHubApi
from .models import ACTION_LINE, GO_SUM_LINE, normalize_version, semver_tuple, unique
from .provenance import validate_docker_manual, validate_manual_path_scope

def parse_override_go_mod(text: str, config: dict[str, Any]) -> tuple[str, str, str] | None:
    module = ""
    go_version = ""
    dependency_version = ""
    dependency = str(config["ecosystems"]["gomod-security-override"]["dependency"])
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("module "):
            if module:
                return None
            module = line.removeprefix("module ").strip()
        elif line.startswith("go "):
            if go_version:
                return None
            go_version = line.removeprefix("go ").strip()
        elif line.startswith("require "):
            parts = line.split()
            if len(parts) != 3 or parts[1] != dependency or dependency_version:
                return None
            dependency_version = parts[2]
        else:
            return None
    expected_module = str(config["ecosystems"]["gomod-security-override"]["module"])
    if module != expected_module or not go_version or not dependency_version:
        return None
    return module, go_version, dependency_version


def validate_go_override(
    api: GitHubApi,
    base_sha: str,
    head_sha: str,
    files: list[dict[str, Any]],
    metadata: list[dict[str, str]],
    config: dict[str, Any],
) -> dict[str, Any]:
    reasons = validate_manual_path_scope(files, config)
    allowed_files = set(config["ecosystems"]["gomod-security-override"]["files"])
    names = {str(file.get("filename", "")) for file in files}
    go_mod = "docker/security-overrides/go.mod"
    if go_mod not in names:
        reasons.append("Go security override update must change go.mod")
    unexpected = sorted(name for name in names if name not in allowed_files)
    if unexpected:
        reasons.append("unexpected Go override files: " + ", ".join(unexpected))

    base_text = api.file_at(go_mod, base_sha)
    head_text = api.file_at(go_mod, head_sha)
    if base_text is None or head_text is None:
        reasons.append("Go security override go.mod must exist at base and head")
        return {"eligible": False, "reasons": unique(reasons), "changes": []}
    base_model = parse_override_go_mod(base_text, config)
    head_model = parse_override_go_mod(head_text, config)
    if not base_model or not head_model:
        reasons.append("Go security override go.mod shape is outside the governed minimal model")
        return {"eligible": False, "reasons": unique(reasons), "changes": []}
    if base_model[:2] != head_model[:2]:
        reasons.append("module path and Go language version must remain unchanged")

    old_version = semver_tuple(base_model[2])
    new_version = semver_tuple(head_model[2])
    if not old_version or not new_version:
        reasons.append("Go security override versions must be strict semantic versions")
    elif not (
        new_version[0] == old_version[0]
        and new_version[1] == old_version[1]
        and new_version[2] > old_version[2]
    ):
        reasons.append("Go security override autonomous updates are patch-only within the same minor line")

    dependency = str(config["ecosystems"]["gomod-security-override"]["dependency"])
    if len(metadata) != 1 or metadata[0].get("name") != dependency:
        reasons.append(f"signed metadata must describe exactly one {dependency} update")
    else:
        item = metadata[0]
        if item.get("updateType") not in config["allowedGoOverrideUpdateTypes"]:
            reasons.append(f"Go override update type {item.get('updateType') or 'unknown'} is not autonomous")
        if normalize_version(item.get("version", "")) != normalize_version(head_model[2]):
            reasons.append("signed Go override dependency-version does not match head go.mod")

    go_sum = "docker/security-overrides/go.sum"
    if go_sum in names:
        head_sum = api.file_at(go_sum, head_sha, optional=True)
        if head_sum is None:
            reasons.append("changed go.sum is missing at head")
        else:
            bad_lines = [line for line in head_sum.splitlines() if line.strip() and not GO_SUM_LINE.fullmatch(line.strip())]
            if bad_lines:
                reasons.append("go.sum contains non-checksum content")
            lines = [line.strip() for line in head_sum.splitlines() if line.strip()]
            if len(lines) != len(set(lines)):
                reasons.append("go.sum contains duplicate checksum lines")

    change = {
        "dependency": dependency,
        "from": base_model[2],
        "to": head_model[2],
    }
    return {"eligible": not reasons, "reasons": unique(reasons), "changes": [change]}


def action_diff_pairs(patch: str) -> tuple[list[tuple[re.Match[str], re.Match[str]]], list[str]]:
    removed: list[re.Match[str]] = []
    added: list[re.Match[str]] = []
    reasons: list[str] = []
    for line in str(patch or "").splitlines():
        if line.startswith(("@@", "---", "+++")):
            continue
        if line.startswith("-"):
            match = ACTION_LINE.fullmatch(line[1:])
            if not match:
                reasons.append("removed workflow content is not an immutable uses: line")
            else:
                removed.append(match)
        elif line.startswith("+"):
            match = ACTION_LINE.fullmatch(line[1:])
            if not match:
                reasons.append("added workflow content is not an immutable uses: line")
            else:
                added.append(match)
    if not removed or len(removed) != len(added):
        reasons.append("workflow update must replace immutable uses: lines one-for-one")
        return [], unique(reasons)
    pairs: list[tuple[re.Match[str], re.Match[str]]] = []
    for old, new in zip(removed, added, strict=True):
        if old.group("action") != new.group("action"):
            reasons.append("workflow update may not replace one action with another")
        if old.group("ref").lower() == new.group("ref").lower():
            reasons.append("workflow action SHA replacement did not change the SHA")
        if old.group("prefix") != new.group("prefix"):
            reasons.append("workflow action replacement changed line structure")
        pairs.append((old, new))
    return pairs, unique(reasons)


def validate_actions(
    files: list[dict[str, Any]],
    metadata: list[dict[str, str]],
    config: dict[str, Any],
) -> dict[str, Any]:
    reasons = validate_manual_path_scope(files, config)
    changes: list[dict[str, str]] = []
    for file in files:
        filename = str(file.get("filename", ""))
        patch = file.get("patch")
        if not isinstance(patch, str) or not patch.strip():
            reasons.append(f"workflow patch is unavailable for {filename}; refusing ambiguous update")
            continue
        pairs, pair_reasons = action_diff_pairs(patch)
        reasons.extend(f"{filename}: {reason}" for reason in pair_reasons)
        for old, new in pairs:
            changes.append(
                {
                    "file": filename,
                    "action": new.group("action"),
                    "fromSha": old.group("ref").lower(),
                    "toSha": new.group("ref").lower(),
                    "version": new.group("version"),
                }
            )
    if not changes:
        reasons.append("no immutable GitHub Action SHA updates were proven")

    metadata_by_name: dict[str, dict[str, str]] = {}
    for item in metadata:
        name = item.get("name", "")
        if not name or name in metadata_by_name:
            reasons.append("signed action metadata contains missing or duplicate dependency names")
            continue
        metadata_by_name[name] = item
    changed_actions = {change["action"] for change in changes}
    if set(metadata_by_name) != changed_actions:
        reasons.append("signed dependency metadata does not exactly match changed GitHub Actions")
    for action in sorted(changed_actions):
        item = metadata_by_name.get(action)
        action_changes = [change for change in changes if change["action"] == action]
        versions = {normalize_version(change["version"]) for change in action_changes}
        if len(versions) != 1:
            reasons.append(f"{action} has inconsistent version annotations across workflow files")
        if not item:
            continue
        if item.get("updateType") not in config["allowedActionUpdateTypes"]:
            reasons.append(f"{action} update type {item.get('updateType') or 'unknown'} is not autonomous")
        signed_version = normalize_version(item.get("version", ""))
        if versions and signed_version not in versions:
            reasons.append(f"{action} signed dependency-version does not match the workflow annotation")
        version = semver_tuple(signed_version)
        if not version:
            reasons.append(f"{action} signed version is not strict semantic version metadata")
        elif version[0] == 0 and "minor" in str(item.get("updateType", "")):
            reasons.append(f"{action} 0.x minor updates remain manual breaking-risk changes")

    return {"eligible": not reasons, "reasons": unique(reasons), "changes": changes}


def validate_semantics(
    api: GitHubApi,
    ecosystem: str,
    base_sha: str,
    head_sha: str,
    files: list[dict[str, Any]],
    metadata: list[dict[str, str]],
    config: dict[str, Any],
) -> dict[str, Any]:
    if len(files) > config["maxChangedFiles"]:
        return {
            "eligible": False,
            "reasons": [f"PR changes {len(files)} files; limit is {config['maxChangedFiles']}"],
            "changes": [],
        }
    if ecosystem == "docker":
        return validate_docker_manual(config)
    if ecosystem == "gomod-security-override":
        return validate_go_override(api, base_sha, head_sha, files, metadata, config)
    if ecosystem == "github-actions":
        return validate_actions(files, metadata, config)
    return {
        "eligible": False,
        "reasons": ["changed-file scope does not match an autonomously governed dependency ecosystem"],
        "changes": [],
    }

