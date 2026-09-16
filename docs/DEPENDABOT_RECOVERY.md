# Dependabot qualification recovery

## Purpose

A dependency qualification failure can be a deterministic framework/security failure or a short-lived transport failure while publishing already-generated evidence. This repository distinguishes those cases without weakening any k6, container, provenance, or security gate.

`.github/scripts/dependency_recovery.py` may request one failed-job rerun only when the existing canonical Dependabot proposal, exact-head qualification run, failed job, failed step, and timestamp-bounded log evidence all satisfy the recovery policy. It never edits a Dependabot branch and never merges a pull request. Dependency governance remains the only autonomous merge authority.

## Recovery boundary

`maxRunAttempts` is `2`, so the original run can receive at most one automatic retry. Recovery requires canonical `dependabot[bot]` numeric identity, one verified GitHub-materialized Dependabot commit directly on current `main`, signed dependency metadata, an exact governed dependency scope, and an exact-head pull-request workflow run.

The retry allowlist is deliberately narrower than the framework's dependency surface. Only these evidence-transport steps are eligible: `Upload k6 summary`, `Upload extended evidence`, `Upload repository security evidence`, and `Upload container security evidence`. A failed upload must contain a recognized transient network/service signature inside that exact step's timestamp window.

Docker builds, k6 smoke execution, zero-traffic sustained-profile inspection, provenance validation, threshold/evidence validation, CodeQL, Trivy scanning, Dependency Review, and aggregate gates are never recovery steps. Missing artifact files are deterministic evidence failures and explicitly block recovery.

## Dependency semantics remain authoritative

Recovery does not relax dependency semantics. GitHub Actions proposals must still satisfy the immutable-SHA/action metadata policy. Go security-override proposals must still satisfy the exact minimal `go.mod`/`go.sum`, dependency-name, signed-metadata, and patch-only policy before recovery is eligible.

Docker proposals are intentionally human-reviewed because `docker/Dockerfile` jointly defines k6 source/runtime/toolchain provenance. Recovery may retry a proven transient evidence-upload failure for a canonical Docker proposal, but the proposal remains manual merge regardless of retry outcome.

## Deterministic failures win

Within an allowlisted upload step, deterministic evidence is evaluated before transient strings. Missing artifact files, client/policy HTTP 400/401/403/404/409/422/429 responses, permission failures, and disk exhaustion prevent recovery even if the same step also contains a transient-looking message.

Recognized transient evidence is narrow: DNS retry/resolution failures, connection resets/timeouts, unreachable network or host errors, socket timeouts/hangups, contextual HTTP 502/503/504 responses, exact gateway/service-outage responses, and bounded TLS timeout/unexpected-EOF failures. Generic `Service Unavailable` text without attributable status context is not enough.

## Native rebasing and authority separation

All three Dependabot ecosystems use `rebase-strategy: auto`. If a proposal is stale, recovery waits for Dependabot's native rebase and never calls GitHub update-branch, pushes to the bot branch, or issues synthetic Dependabot commands.

Recovery configuration/code, governance configuration/code/library, the governance workflow, and `.github/dependabot.yml` are manual-review control-plane paths. Pull-request self-tests run read-only. Only the trusted default-branch governance job holds `actions: write` for requesting a failed-job rerun.

A successful retry is not merge evidence. The normal exact-head CI, Extended, Security, and Docs workflows must complete successfully; dependency governance then independently re-proves provenance, semantics, and every stable aggregate gate before any eligible autonomous merge.
