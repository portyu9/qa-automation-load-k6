"""Validate Docker runtime provenance and immutable image references."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "docker" / "Dockerfile"
SECURITY_OVERRIDE_MOD = ROOT / "docker" / "security-overrides" / "go.mod"
SHA256_RE = re.compile(r"@sha256:[0-9a-f]{64}$")
K6_VERSION_RE = re.compile(r"^ARG K6_VERSION=([0-9]+\.[0-9]+\.[0-9]+)$", re.MULTILINE)
K6_COMMIT_RE = re.compile(r"^ARG K6_COMMIT=([0-9a-f]{40})$", re.MULTILINE)
X_CRYPTO_RE = re.compile(r"(?:^require\s+golang\.org/x/crypto\s+|^\s*golang\.org/x/crypto\s+)(v\d+\.\d+\.\d+)\s*$", re.MULTILINE)


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

    if not SECURITY_OVERRIDE_MOD.is_file():
        errors.append("docker/security-overrides/go.mod must track emergency Go-module security overrides")
        x_crypto_match = None
    else:
        override_text = SECURITY_OVERRIDE_MOD.read_text(encoding="utf-8")
        x_crypto_match = X_CRYPTO_RE.search(override_text)
        if not x_crypto_match:
            errors.append("security override module must pin golang.org/x/crypto to an exact semantic version")

    required_override_tokens = (
        "COPY docker/security-overrides/go.mod /tmp/k6-security-overrides.mod",
        'GOFLAGS=-mod=mod go get "golang.org/x/crypto@${X_CRYPTO_VERSION}"',
        "go mod vendor",
    )
    for token in required_override_tokens:
        if token not in text:
            errors.append(f"Dockerfile must consume tracked Go security override: {token}")

    if errors:
        print("runtime provenance contract failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "runtime provenance contract: "
        f"k6={version_match.group(1)} commit={commit_match.group(1)} stages={len(from_refs)} "
        f"x-crypto-override={x_crypto_match.group(1)} vendor-sync=required immutable"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
