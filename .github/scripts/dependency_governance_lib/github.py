from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .models import GovernanceError, PAGE_SIZE

class GitHubApi:
    def __init__(self, token: str, repository: str, max_pagination_pages: int):
        if not token:
            raise GovernanceError("GITHUB_TOKEN is required")
        if repository.count("/") != 1:
            raise GovernanceError("GITHUB_REPOSITORY must be owner/repo")
        self.token = token
        self.repository = repository
        self.root = f"https://api.github.com/repos/{repository}"
        self.max_pagination_pages = max_pagination_pages

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = path if path.startswith("https://") else f"{self.root}{path}"
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "dependency-governance",
                **({"Content-Type": "application/json"} if payload is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1000]
            raise GovernanceError(
                f"GitHub API {method} {url} failed ({exc.code}): {detail}"
            ) from exc
        except OSError as exc:
            raise GovernanceError(f"GitHub API {method} {url} failed: {exc}") from exc
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GovernanceError(f"GitHub API {method} {url} returned invalid JSON") from exc

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("POST", path, payload)

    def patch(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("PATCH", path, payload)

    def put(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("PUT", path, payload)

    def paginate(self, path: str, selector: str | None = None) -> list[Any]:
        values: list[Any] = []
        for page in range(1, self.max_pagination_pages + 1):
            separator = "&" if "?" in path else "?"
            payload = self.get(f"{path}{separator}per_page={PAGE_SIZE}&page={page}")
            page_values = payload.get(selector) if selector else payload
            if not isinstance(page_values, list):
                raise GovernanceError(
                    f"pagination endpoint {path} did not return {selector or 'an array'}"
                )
            values.extend(page_values)
            if len(page_values) < PAGE_SIZE:
                return values
        raise GovernanceError(
            f"pagination safety limit reached for {path} after "
            f"{self.max_pagination_pages} page(s)"
        )

    def file_at(self, filename: str, ref: str, optional: bool = False) -> str | None:
        encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in filename.split("/"))
        try:
            payload = self.get(f"/contents/{encoded_path}?ref={urllib.parse.quote(ref, safe='')}")
        except GovernanceError as exc:
            if optional and "failed (404)" in str(exc):
                return None
            raise
        if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
            raise GovernanceError(f"unable to decode {filename}@{ref}")
        try:
            return base64.b64decode(payload["content"].replace("\n", "")).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GovernanceError(f"unable to decode UTF-8 content for {filename}@{ref}") from exc


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def parse_dependabot_metadata(message: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_block = False
    for line in str(message or "").splitlines():
        if line.strip() == "updated-dependencies:":
            in_block = True
            continue
        if not in_block:
            continue
        if line.strip() == "...":
            break
        match = re.match(r"\s*-\s+dependency-name:\s*(.+?)\s*$", line)
        if match:
            if current:
                result.append(current)
            current = {"name": _unquote(match.group(1))}
            continue
        if not current:
            continue
        for key, field in (
            ("version", "dependency-version"),
            ("dependencyType", "dependency-type"),
            ("updateType", "update-type"),
        ):
            match = re.match(rf"\s+{re.escape(field)}:\s*(.+?)\s*$", line)
            if match:
                current[key] = _unquote(match.group(1))
    if current:
        result.append(current)
    return result


def classify_ecosystem(files: list[dict[str, Any]], config: dict[str, Any]) -> str:
    names = [str(file.get("filename", "")) for file in files]
    if not names:
        return "unknown"
    docker_files = set(config["ecosystems"]["docker"]["files"])
    if all(name in docker_files for name in names):
        return "docker"
    go_files = set(config["ecosystems"]["gomod-security-override"]["files"])
    if all(name in go_files for name in names):
        return "gomod-security-override"
    actions = config["ecosystems"]["github-actions"]
    prefix = str(actions["workflowPrefix"])
    extensions = tuple(str(value) for value in actions["extensions"])
    if all(name.startswith(prefix) and name.endswith(extensions) for name in names):
        return "github-actions"
    return "unknown"
