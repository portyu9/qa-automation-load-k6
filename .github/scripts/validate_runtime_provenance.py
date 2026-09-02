"""Validate Docker runtime provenance and compiled-dependency security overrides."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "docker" / "Dockerfile"
SECURITY_OVERRIDE_MOD = ROOT / "docker" / "security-overrides" / "go.mod"
SHA256_RE = re.compile(r"@sha256:[0-9a-f]{64}$")
K6_VERSION_RE = re.compile(r"^ARG K6_VERSION=([0-9]+\.[0-9]+\.[0-9]+)$", re.MULTILINE)
K6_COMMIT_RE = re.compile(r"^ARG K6_COMMIT=([0-9a-f]{40})$", re.MULTILINE)
REQUIRE_RE = re.compile(r"^require\s+([^\s]+)\s+(v\d+\.\d+\.\d+)\s*$")
EXPECTED_OVERRIDES = {"golang.org/x/crypto", "google.golang.org/grpc"}


def parse_overrides(text: str) -> dict[str, str] | None:
    versions: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("module ") or line.startswith("go "):
            continue
        match = REQUIRE_RE.fullmatch(line)
        if not match or match.group(1) in versions:
            return None
        versions[match.group(1)] = match.group(2)
    return versions if set(versions) == EXPECTED_OVERRIDES else None


def main() -> int:
    text = DOCKERFILE.read_text(encoding="utf-8")
    errors: list[str] = []

    version_match = K6_VERSION_RE.search(text)
    commit_match = K6_COMMIT_RE.search(text)
    if not version_match:
        errors.append("Dockerfile must pin numeric ARG K6_VERSION")
    if not commit_match:
        errors.append("Dockerfile must pin 40-character ARG K6_COMMIT")

    from_refs: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("FROM "):
            continue
        fields = stripped.split()
        index = 1
        while index < len(fields) and fields[index].startswith("--"):
            index += 1
        if index >= len(fields):
            errors.append(f"unable to parse Dockerfile FROM instruction: {stripped}")
            continue
        ref = fields[index]
        from_refs.append(ref)
        if not SHA256_RE.search(ref):
            errors.append(f"Dockerfile FROM image must be digest pinned: {ref}")

    if len(from_refs) != 3:
        errors.append(f"Dockerfile must retain release-marker, builder, and runtime stages; found {len(from_refs)}")

    if version_match and from_refs:
        expected_marker = f"grafana/k6:{version_match.group(1)}@"
        if not from_refs[0].startswith(expected_marker):
            errors.append(
                f"upstream release marker must match K6_VERSION {version_match.group(1)}: {from_refs[0]}"
            )

    builder = next((ref for ref in from_refs if ref.startswith("golang:")), None)
    runtime = next((ref for ref in from_refs if ref.startswith("alpine:")), None)
    if builder is None or not re.match(r"^golang:\d+\.\d+\.\d+-alpine\d+\.\d+@sha256:", builder):
        errors.append("Dockerfile builder must use a versioned digest-pinned golang Alpine image")
    if runtime is None or not re.match(r"^alpine:\d+\.\d+\.\d+@sha256:", runtime):
        errors.append("Dockerfile runtime must use a patch-versioned digest-pinned Alpine image")

    overrides: dict[str, str] | None = None
    if not SECURITY_OVERRIDE_MOD.is_file():
        errors.append("docker/security-overrides/go.mod must track compiled Go-module security overrides")
    else:
        overrides = parse_overrides(SECURITY_OVERRIDE_MOD.read_text(encoding="utf-8"))
        if overrides is None:
            errors.append(
                "security override module must contain exactly the allowlisted x/crypto and grpc semantic-version pins"
            )

    required_override_tokens = (
        "COPY docker/security-overrides/go.mod /tmp/k6-security-overrides.mod",
        "test \"$(wc -l < /tmp/k6-security-overrides.txt)\" -eq 2",
        "golang.org/x/crypto|google.golang.org/grpc",
        'GOFLAGS=-mod=mod go get "${MODULE}@${VERSION}"',
        "GOFLAGS=-mod=mod go list -m -f '{{.Version}}'",
        "go mod vendor",
    )
    for token in required_override_tokens:
        if token not in text:
            errors.append(f"Dockerfile must consume and verify tracked Go security overrides: {token}")

    if errors:
        print("runtime provenance contract failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    override_summary = ",".join(f"{name}={overrides[name]}" for name in sorted(overrides))
    print(
        "runtime provenance contract: "
        f"k6={version_match.group(1)} commit={commit_match.group(1)} stages={len(from_refs)} "
        f"overrides={override_summary} vendor-sync=required immutable"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
