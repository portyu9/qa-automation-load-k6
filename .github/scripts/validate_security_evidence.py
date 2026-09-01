"""Validate retained Trivy evidence is attributable to the intended k6 security plane."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "docker" / "Dockerfile"
SECURITY_OVERRIDE_MOD = ROOT / "docker" / "security-overrides" / "go.mod"
TRIVY_VERSION = "0.74.0"


def load_report(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"missing Trivy JSON evidence: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("SchemaVersion") != 2:
        raise ValueError(f"unexpected Trivy SchemaVersion: {report.get('SchemaVersion')}")
    if report.get("Trivy", {}).get("Version") != TRIVY_VERSION:
        raise ValueError(f"unexpected Trivy version: {report.get('Trivy', {}).get('Version')}")
    results = report.get("Results")
    if not isinstance(results, list) or not results:
        raise ValueError("Trivy evidence contains no attributed Results")
    return report


def findings(report: dict, field: str) -> int:
    total = 0
    for result in report.get("Results", []):
        values = result.get(field) or []
        if not isinstance(values, list):
            raise ValueError(f"Trivy result field {field} must be an array when present")
        total += len(values)
    return total


def validate_repository(report: dict) -> None:
    docker_results = [
        result
        for result in report["Results"]
        if result.get("Target") == "docker/Dockerfile"
        and result.get("Class") == "config"
        and result.get("Type") == "dockerfile"
    ]
    if len(docker_results) != 1:
        raise ValueError(
            f"repository Trivy evidence must contain one Dockerfile configuration result; found {len(docker_results)}"
        )
    misconfigurations = findings(report, "Misconfigurations")
    secrets = findings(report, "Secrets")
    if misconfigurations or secrets:
        raise ValueError(
            f"repository Trivy gate contains findings after a successful scan: misconfigurations={misconfigurations}, secrets={secrets}"
        )
    print(
        f"repository Trivy evidence: version={TRIVY_VERSION} dockerfileResults=1 "
        f"misconfigurations={misconfigurations} secrets={secrets}"
    )


def docker_versions() -> tuple[str, str]:
    text = DOCKERFILE.read_text(encoding="utf-8")
    k6 = re.search(r"^ARG K6_VERSION=([0-9]+\.[0-9]+\.[0-9]+)$", text, re.MULTILINE)
    go = re.search(r"^FROM --platform=\$BUILDPLATFORM golang:([0-9]+\.[0-9]+\.[0-9]+)-alpine", text, re.MULTILINE)
    if not k6 or not go:
        raise ValueError("unable to derive k6/Go versions from Dockerfile provenance")
    return k6.group(1), go.group(1)


def security_override_version() -> str:
    if not SECURITY_OVERRIDE_MOD.is_file():
        raise ValueError("tracked Go security override module is missing")
    text = SECURITY_OVERRIDE_MOD.read_text(encoding="utf-8")
    match = re.search(
        r"(?:^require\s+golang\.org/x/crypto\s+|^\s*golang\.org/x/crypto\s+)(v\d+\.\d+\.\d+)\s*$",
        text,
        re.MULTILINE,
    )
    if not match:
        raise ValueError("unable to derive golang.org/x/crypto version from tracked security override")
    return match.group(1)


def package_map(result: dict) -> dict[str, set[str]]:
    packages = result.get("Packages") or []
    if not isinstance(packages, list):
        raise ValueError("Trivy Packages must be an array")
    mapped: dict[str, set[str]] = {}
    for package in packages:
        name = package.get("Name")
        version = package.get("Version")
        if isinstance(name, str) and isinstance(version, str):
            mapped.setdefault(name, set()).add(version)
    return mapped


def require_package(packages: dict[str, set[str]], name: str, version: str) -> None:
    observed = packages.get(name, set())
    if version not in observed:
        raise ValueError(
            f"built-image Go inventory does not prove {name} {version}; observed={sorted(observed)}"
        )


def validate_image(report: dict) -> None:
    k6_version, go_version = docker_versions()
    x_crypto_version = security_override_version()
    os_results = [
        result
        for result in report["Results"]
        if result.get("Class") == "os-pkgs" and result.get("Type") == "alpine"
    ]
    go_results = [
        result
        for result in report["Results"]
        if result.get("Target") == "usr/bin/k6"
        and result.get("Class") == "lang-pkgs"
        and result.get("Type") == "gobinary"
    ]
    if len(os_results) != 1:
        raise ValueError(f"built-image evidence must contain one Alpine OS package result; found {len(os_results)}")
    if len(go_results) != 1:
        raise ValueError(f"built-image evidence must contain one usr/bin/k6 Go package result; found {len(go_results)}")

    os_packages = os_results[0].get("Packages") or []
    go_packages = go_results[0].get("Packages") or []
    if len(os_packages) < 10:
        raise ValueError(f"built-image Alpine package inventory is unexpectedly small: {len(os_packages)}")
    if len(go_packages) < 50:
        raise ValueError(f"built-image Go package inventory is unexpectedly small: {len(go_packages)}")

    packages = package_map(go_results[0])
    # The upstream source tag/commit remains exact, but applying the governed
    # dependency override deliberately dirties that checkout. Requiring +dirty
    # prevents the evidence layer from pretending the binary is pristine while
    # the separate provenance validator still binds it to the exact upstream
    # tag/commit and tracked override input.
    require_package(packages, "go.k6.io/k6/v2", f"v{k6_version}+dirty")
    require_package(packages, "stdlib", f"v{go_version}")
    require_package(packages, "golang.org/x/crypto", x_crypto_version)

    vulnerabilities = findings(report, "Vulnerabilities")
    if vulnerabilities:
        raise ValueError(
            f"built-image Trivy gate contains HIGH/CRITICAL findings after a successful scan: {vulnerabilities}"
        )

    print(
        f"built-image Trivy evidence: version={TRIVY_VERSION} alpinePackages={len(os_packages)} "
        f"goPackages={len(go_packages)} k6=v{k6_version}+dirty go=v{go_version} "
        f"x-crypto={x_crypto_version} vulnerabilities={vulnerabilities}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("repository", "image"))
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        report = load_report(args.report)
        if args.mode == "repository":
            validate_repository(report)
        else:
            validate_image(report)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"security evidence contract failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
