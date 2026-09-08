"""Validate Docker runtime provenance and compiled-dependency security overrides."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "docker" / "Dockerfile"
SECURITY_OVERRIDE_MOD = ROOT / "docker" / "security-overrides" / "go.mod"
SECURITY_OVERRIDE_PINS = ROOT / "docker" / "security-overrides" / "pins.go"
SHA256_RE = re.compile(r"@sha256:[0-9a-f]{64}$")
K6_VERSION_RE = re.compile(r"^ARG K6_VERSION=([0-9]+\.[0-9]+\.[0-9]+)$", re.MULTILINE)
K6_COMMIT_RE = re.compile(r"^ARG K6_COMMIT=([0-9a-f]{40})$", re.MULTILINE)
VERSION = r"v\d+\.\d+\.\d+"
REQUIRE_RE = re.compile(rf"^require\s+([^\s]+)\s+({VERSION})\s*$")
INDIRECT_REQUIRE_RE = re.compile(rf"^require\s+([^\s]+)\s+({VERSION})\s+//\s*indirect\s*$")
BLOCK_REQUIRE_RE = re.compile(rf"^([^\s]+)\s+({VERSION})\s*$")
INDIRECT_BLOCK_REQUIRE_RE = re.compile(rf"^([^\s]+)\s+({VERSION})\s+//\s*indirect\s*$")
PIN_IMPORT_RE = re.compile(r'^\s*_\s+"([^"]+)"\s*$')
EXPECTED_OVERRIDES = {"golang.org/x/crypto", "google.golang.org/grpc"}
EXPECTED_PIN_IMPORTS = {"golang.org/x/crypto/cryptobyte", "google.golang.org/grpc/codes"}
TRUST_STORE_COPY = (
    "COPY --from=builder /etc/ssl/certs/ca-certificates.crt "
    "/etc/ssl/certs/ca-certificates.crt"
)


@dataclass(frozen=True)
class OverrideManifest:
    """Direct override authority plus non-authoritative transitive metadata."""

    direct: dict[str, str]
    indirect: dict[str, str]


def parse_overrides(text: str) -> OverrideManifest | None:
    """Parse a constrained go.mod without promoting indirect modules to override authority."""
    direct: dict[str, str] = {}
    indirect: dict[str, str] = {}
    in_require_block = False
    saw_module = False
    saw_go = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue

        if line.startswith("module "):
            if in_require_block or saw_module or len(line.split()) != 2:
                return None
            saw_module = True
            continue
        if line.startswith("go "):
            if in_require_block or saw_go or len(line.split()) != 2:
                return None
            saw_go = True
            continue

        if line == "require (":
            if in_require_block:
                return None
            in_require_block = True
            continue
        if line == ")":
            if not in_require_block:
                return None
            in_require_block = False
            continue

        if in_require_block:
            indirect_match = INDIRECT_BLOCK_REQUIRE_RE.fullmatch(line)
            direct_match = BLOCK_REQUIRE_RE.fullmatch(line)
        else:
            indirect_match = INDIRECT_REQUIRE_RE.fullmatch(line)
            direct_match = REQUIRE_RE.fullmatch(line)

        match = indirect_match or direct_match
        if match is None:
            return None

        module, version = match.groups()
        if module in direct or module in indirect:
            return None
        if indirect_match is not None:
            indirect[module] = version
        else:
            direct[module] = version

    if in_require_block or not saw_module or not saw_go:
        return None
    if set(direct) != EXPECTED_OVERRIDES:
        return None
    return OverrideManifest(direct=direct, indirect=indirect)


def parser_selfcheck() -> bool:
    valid_with_indirect = """\
module example.invalid/security-overrides

go 1.26.0

require (
    golang.org/x/crypto v0.56.0
    google.golang.org/grpc v1.83.2
    golang.org/x/sys v0.47.0 // indirect
)
"""
    parsed = parse_overrides(valid_with_indirect)
    if parsed is None:
        return False
    if parsed.direct != {
        "golang.org/x/crypto": "v0.56.0",
        "google.golang.org/grpc": "v1.83.2",
    }:
        return False
    if parsed.indirect != {"golang.org/x/sys": "v0.47.0"}:
        return False

    rejected = (
        valid_with_indirect.replace(
            "    golang.org/x/sys v0.47.0 // indirect",
            "    golang.org/x/sys v0.47.0",
        ),
        valid_with_indirect.replace(
            "    golang.org/x/sys v0.47.0 // indirect",
            "    example.invalid/unapproved v1.2.3",
        ),
        valid_with_indirect.replace(
            ")\n",
            "    golang.org/x/crypto v0.56.0 // indirect\n)\n",
        ),
        valid_with_indirect + "replace golang.org/x/crypto => example.invalid/fork v0.56.0\n",
        valid_with_indirect.replace("v0.47.0 // indirect", "v0.47 // indirect"),
    )
    return all(parse_overrides(candidate) is None for candidate in rejected)


def parse_pin_imports(text: str) -> set[str]:
    return {match.group(1) for line in text.splitlines() if (match := PIN_IMPORT_RE.fullmatch(line))}


def final_runtime_stage(text: str, runtime_ref: str) -> str | None:
    marker = f"FROM {runtime_ref} AS runtime"
    if text.count(marker) != 1:
        return None
    return text.split(marker, 1)[1]


def main() -> int:
    text = DOCKERFILE.read_text(encoding="utf-8")
    errors: list[str] = []

    if not parser_selfcheck():
        errors.append("security override parser self-check failed")

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
    else:
        runtime_stage = final_runtime_stage(text, runtime)
        if runtime_stage is None:
            errors.append("Dockerfile must contain exactly one named final runtime stage")
        else:
            if re.search(r"\bapk\s+(?:add|upgrade|update)\b", runtime_stage):
                errors.append(
                    "final runtime stage must not mutate digest-pinned OS packages through live apk repositories"
                )
            if TRUST_STORE_COPY not in runtime_stage:
                errors.append(
                    "final runtime stage must copy the CA trust bundle from the digest-pinned builder stage"
                )
            if "RUN adduser -D -u 12345 -g 12345 k6" not in runtime_stage:
                errors.append("final runtime stage must create the governed non-root k6 identity locally")
            if not re.search(r"(?m)^USER 12345\s*$", runtime_stage):
                errors.append("final runtime stage must execute as numeric user 12345")

    override_manifest: OverrideManifest | None = None
    if not SECURITY_OVERRIDE_MOD.is_file():
        errors.append("docker/security-overrides/go.mod must track compiled Go-module security overrides")
    else:
        override_manifest = parse_overrides(SECURITY_OVERRIDE_MOD.read_text(encoding="utf-8"))
        if override_manifest is None:
            errors.append(
                "security override module must contain exactly the allowlisted direct x/crypto and grpc "
                "semantic-version pins; additional requirements are permitted only as valid // indirect metadata"
            )

    if not SECURITY_OVERRIDE_PINS.is_file():
        errors.append("docker/security-overrides/pins.go must anchor the allowlisted modules for Go maintenance tooling")
    else:
        pin_imports = parse_pin_imports(SECURITY_OVERRIDE_PINS.read_text(encoding="utf-8"))
        if pin_imports != EXPECTED_PIN_IMPORTS:
            errors.append("security override anchors must contain exactly the approved x/crypto and grpc package imports")

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

    if override_manifest is None or version_match is None or commit_match is None:
        raise AssertionError("validated provenance state is incomplete")
    override_summary = ",".join(
        f"{name}={override_manifest.direct[name]}" for name in sorted(override_manifest.direct)
    )
    print(
        "runtime provenance contract: "
        f"k6={version_match.group(1)} commit={commit_match.group(1)} stages={len(from_refs)} "
        f"overrides={override_summary} indirect={len(override_manifest.indirect)} "
        "anchors=qualified vendor-sync=required final-os-packages=immutable"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
