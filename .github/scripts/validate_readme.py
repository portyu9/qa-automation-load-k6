"""Validate repository README contracts without third-party dependencies."""
from __future__ import annotations

import re
from html import unescape
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
LOCAL_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
WORKFLOW_BADGE_RE = re.compile(
    r"https://github\.com/[^/]+/[^/]+/actions/workflows/([^/]+)/badge\.svg"
)
STATIC_BADGE_RE = re.compile(
    r"https://img\.shields\.io/badge/[^\s)?]+-([0-9A-Fa-f]{6})(?:\?[^\s)]*)?"
)
SECURITY_BADGE_RE = re.compile(
    r"https://img\.shields\.io/badge/Security-Policy-([0-9A-Fa-f]{6})"
)
MERMAID_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
REPOSITORY_MAP_RE = re.compile(
    r"## Repository map\s*\n\s*```text\s*\n(.*?)```", re.DOTALL
)
MERMAID_ROOTS = (
    "flowchart",
    "graph",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "erDiagram",
    "journey",
    "gantt",
    "pie",
    "mindmap",
    "timeline",
    "quadrantChart",
    "xychart",
)
STABLE_GATES = {
    "ci-gate": ROOT / ".github" / "workflows" / "ci.yml",
    "extended-gate": ROOT / ".github" / "workflows" / "extended.yml",
    "security-gate": ROOT / ".github" / "workflows" / "security.yml",
}


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def validate_local_links(text: str, errors: list[str]) -> None:
    for raw in LOCAL_LINK_RE.findall(text):
        destination = unescape(raw.strip())
        if destination.startswith("<") and destination.endswith(">"):
            destination = destination[1:-1]
        if not destination or destination.startswith("#"):
            continue
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", destination) or destination.startswith("//"):
            continue
        destination = destination.split("#", 1)[0].split("?", 1)[0]
        if not destination:
            continue
        candidate = (ROOT / unquote(destination)).resolve()
        if not candidate.is_relative_to(ROOT):
            fail(f"README local link escapes repository root: {raw}", errors)
        elif not candidate.exists():
            fail(f"README local link target does not exist: {raw}", errors)


def validate_workflow_badges(text: str, errors: list[str]) -> None:
    for name in WORKFLOW_BADGE_RE.findall(text):
        if not (ROOT / ".github" / "workflows" / name).is_file():
            fail(f"workflow badge target does not exist: {name}", errors)


def validate_badge_palette(text: str, errors: list[str]) -> None:
    colors = [color.upper() for color in STATIC_BADGE_RE.findall(text)]
    duplicates = sorted({color for color in colors if colors.count(color) > 1})
    if duplicates:
        fail(
            "static Shields badge colors must be unique within README; duplicates: "
            + ", ".join(duplicates),
            errors,
        )
    match = SECURITY_BADGE_RE.search(text)
    if match and match.group(1).upper() != "24292F":
        fail("Security Policy badge must use GitHub-dark color 24292F", errors)


def validate_mermaid(text: str, errors: list[str]) -> None:
    for index, block in enumerate(MERMAID_RE.findall(text), 1):
        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip() and not line.lstrip().startswith("%%")
        ]
        if not lines:
            fail(f"Mermaid block {index} is empty", errors)
        elif not lines[0].startswith(MERMAID_ROOTS):
            fail(
                f"Mermaid block {index} does not start with a recognized diagram declaration: {lines[0]!r}",
                errors,
            )


def validate_repository_map(text: str, errors: list[str]) -> None:
    match = REPOSITORY_MAP_RE.search(text)
    if not match:
        fail("README must contain a fenced `Repository map` section", errors)
        return

    entries = 0
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line == ".":
            continue
        if "──" not in line:
            fail(f"repository map contains an unrecognized entry: {raw_line.strip()}", errors)
            continue
        entry = line.split("──", 1)[1].strip()
        entries += 1
        if not entry.endswith("/"):
            fail(
                f"repository map must contain directories only; file-like entry found: {entry}",
                errors,
            )

    if entries == 0:
        fail("repository map must list at least one directory", errors)


def validate_stable_gates(text: str, errors: list[str]) -> None:
    for gate, workflow in STABLE_GATES.items():
        if not workflow.is_file():
            fail(f"stable gate workflow is missing: {workflow.relative_to(ROOT)}", errors)
            continue
        workflow_text = workflow.read_text(encoding="utf-8")
        if not re.search(rf"^\s{{2}}{re.escape(gate)}:\s*$", workflow_text, re.MULTILINE):
            fail(f"workflow does not define stable aggregate job `{gate}`", errors)
        if f"`{gate}`" not in text:
            fail(f"README must document stable aggregate job `{gate}`", errors)


def main() -> int:
    errors: list[str] = []
    if not README.is_file():
        print("README contract failed: README.md is missing")
        return 1

    for required in (ROOT / "LICENSE", ROOT / ".github" / "SECURITY.md"):
        if not required.is_file():
            fail(
                f"required repository surface is missing: {required.relative_to(ROOT)}",
                errors,
            )

    text = README.read_text(encoding="utf-8")
    validate_local_links(text, errors)
    validate_workflow_badges(text, errors)
    validate_badge_palette(text, errors)
    validate_mermaid(text, errors)
    validate_repository_map(text, errors)
    validate_stable_gates(text, errors)

    if errors:
        print("README contract failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "README contract: local links, badges, Mermaid, directory-only map, and stable gates are consistent"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
