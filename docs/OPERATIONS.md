# Operations Guide

## Purpose

This guide owns the detailed operating contract for the k6 Performance Quality Engineering Framework: target validation and authorization, smoke/load/stress/soak workload models, guardrails, deterministic fixture ownership, business metrics, threshold interpretation, summary evidence, packaged runtime provenance, dependency maintenance, and failure triage.

The main [`README.md`](../README.md) is intentionally concise. Deep target/runtime/client/evidence ownership remains in [`ARCHITECTURE.md`](ARCHITECTURE.md), while gate/profile semantics and exit criteria remain in [`TEST_STRATEGY.md`](TEST_STRATEGY.md).

## Quick start

Start the deterministic fixture:

```bash
node scripts/local-api.js
```

Run low-volume smoke:

```bash
K6_BASE_URL=http://127.0.0.1:4020 \
K6_RUN_ID=local-smoke \
bash scripts/run_k6.sh smoke
```

Validate guardrails and static contracts with zero scenario traffic:

```bash
bash scripts/test_guardrails.sh
python .github/scripts/validate_readme.py
python .github/scripts/validate_workflow_pins.py
```

Build/start the packaged runtime without traffic:

```bash
docker build -t qa-k6-runtime -f docker/Dockerfile .
docker run --rm qa-k6-runtime
```

Inspect a sustained profile without executing it:

```bash
K6_BASE_URL=https://example.invalid \
K6_ALLOW_LOAD_TEST=true \
K6_ALLOWED_HOSTS=example.invalid \
k6 inspect --include-system-env-vars tests/load.js
```

## Runtime configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `K6_BASE_URL` | Explicit target | required |
| `K6_RUN_ID` | Run correlation | generated ID |
| `K6_P95_MS` | Default p95 budget | `500` |
| `K6_ERROR_RATE` | Max normal error/business-failure rate | `0.01` |
| `K6_THINK_TIME_SECONDS` | Iteration pacing | `1` |
| `K6_ALLOW_LOAD_TEST` | Sustained-profile opt-in | disabled |
| `K6_ALLOWED_HOSTS` | Exact authorized hostnames | unset |
| `K6_SOAK_DURATION` | Soak duration | `10m` |
| `K6_SOAK_RATE` | Soak arrival rate | `5` |

`K6_BASE_URL` must be explicit, absolute HTTP(S), contain a valid hostname/port, contain no credentials/query/fragment, and may preserve an optional path prefix. `K6_RUN_ID` is a bounded correlation token.

## Target classification and authorization

Validated targets are classified for evidence:

- `local-fixture` — loopback (`127.0.0.1`, `localhost`, `::1`);
- `explicit-target` — every other validated hostname.

Classification is diagnostic only. It never authorizes traffic.

Every traffic-capable invocation requires `K6_BASE_URL`. Sustained profiles (`load`, `stress`, `soak`) additionally require all three conditions:

```text
K6_BASE_URL=<explicit target>
AND
K6_ALLOW_LOAD_TEST=true
AND
target hostname is an exact member of K6_ALLOWED_HOSTS
```

`scripts/run_k6.sh` fails early for operator ergonomics. `requireLoadAuthorization()` repeats sustained-traffic policy inside the JavaScript runtime so direct `k6 run` cannot bypass the shell guardrail.

The boolean and exact-host allowlist reduce accidental targeting risk; they are not proof of organizational authorization. Environment ownership, test windows, change control, data policy, downstream capacity, incident controls, and observability remain operational prerequisites.

## Deterministic smoke boundary

`scripts/local-api.js` provides `/health` and `/posts/1` on loopback. Primary CI starts it with bounded readiness polling and runs the repository-built k6 container against it.

The smoke proves script initialization, real k6 HTTP/check/metric/summary behavior, and basic threshold handling without public DNS, TLS, remote uptime, rate limits, or demo-data drift.

The repository fixture proves **framework correctness**, not service capacity.

## Zero-traffic safety verification

Primary CI tests shell/runtime refusal behavior before smoke. Extended CI uses `k6 inspect` for load/stress/soak and executes **zero sustained traffic**.

Guardrails prove rejection of:

- missing `K6_BASE_URL`;
- sustained execution without exact `K6_ALLOW_LOAD_TEST=true`;
- missing/incorrect `K6_ALLOWED_HOSTS` membership;
- unsafe target credentials/query strings;
- unsafe correlation IDs;
- malformed runtime configuration.

Valid authorized configuration must initialize successfully under `inspect`, but inspection remains configuration evidence—not a performance result.

## Workload model

| Profile | Executor | Question |
| --- | --- | --- |
| `smoke` | `shared-iterations` | Is the execution path healthy at negligible volume? |
| `load` | `ramping-arrival-rate` | Can expected throughput satisfy normal budgets? |
| `stress` | `ramping-arrival-rate` | How does behavior degrade beyond the normal envelope? |
| `soak` | `constant-arrival-rate` | Does stable demand reveal time-dependent degradation? |

Keep concepts separate:

- **rate/stage** — demand requested from the generator;
- **VU capacity** — generator ability to produce that schedule;
- **threshold** — pass/fail service objective;
- **check** — correctness observation;
- **business metric** — domain-level attempt/success/failure/duration;
- **dropped iterations** — generator scheduling/capacity shortfall.

Changing traffic shape and loosening thresholds in the same opaque change destroys interpretability.

## Client and business metrics

`lib/client.js` centralizes stable request behavior, run headers, endpoint tags, JSON/content checks, and metric updates. Scenario files own workload behavior and should not hide k6 behind a generic second DSL.

`lib/metrics.js` defines:

| Metric | Type | Meaning |
| --- | --- | --- |
| `business_attempts` | Counter | Domain request attempts |
| `business_success` | Rate | Check-complete business success |
| `business_failures` | Rate | Business/check failure rate |
| `business_duration` | Trend | Domain operation duration |

Endpoint/scenario tags remain low-cardinality and authoritative. Native HTTP/check metrics remain visible; business metrics supplement rather than replace them.

`lib/thresholds.js` is the common threshold-policy source. Profile-specific overrides should be explicit and reviewable.

## Evidence and interpretation

`handleSummary()` writes compact human output plus `reports/summary.json`. The structured evidence is an allowlisted projection containing:

- run ID;
- target host and `targetClass`;
- request count, HTTP failure rate, p95, and check rate;
- business attempt/success/failure/p95 values;
- explicit threshold-breach details.

Broad native runtime objects are not retained by default.

A p95 number has no useful interpretation without workload context. Interpret latency with requested/achieved throughput, checks, HTTP/business failures, threshold breaches, and `dropped_iterations`. If the generator failed to produce the requested schedule, the experiment answered a different question.

A threshold states whether an objective was satisfied under the exact run conditions. It does not explain root cause and is not a timeless SLA claim.

## Packaged runtime ownership

`docker/Dockerfile` is the single tracked runtime/provenance source used by primary and extended workflows. The official k6 stage acts as the upstream release marker; the executable binary is rebuilt from exact reviewed source identity with a pinned builder/runtime chain and explicit security overrides.

The final image defaults to `k6 version`, not a traffic scenario. Traffic requires an explicit `run` command and validated target; sustained traffic still requires the separate authorization contract.

CI verifies runtime identity before smoke. Extended jobs build the same image and use `inspect` only.

See the root README's packaged-runtime provenance block for the exact values required by repository documentation validation.

## CI topology

- `ci.yml` — zero-traffic guardrails, packaged-runtime contract, low-volume local smoke, semantic summary evidence, stable `ci-gate`.
- `extended.yml` — project-image `k6 inspect` contracts for load/stress/soak with **zero sustained traffic**, stable `extended-gate`.
- `security.yml` — supply-chain provenance, CodeQL, repository Trivy, built-image Trivy, Dependency Review when available, stable `security-gate`.
- `docs.yml` — README/governance plus immutable workflow dependency validation (`static-contracts`).

No workflow automatically runs sustained load/stress/soak traffic.

## Confidence boundaries

| Signal | Confidence gained | Deliberate limit |
| --- | --- | --- |
| Zero-traffic guardrails | Unsafe/missing targets and sustained authorization failures are rejected before traffic | Does not prove an approved target can handle a requested experiment |
| `k6 inspect` | Scenario, stage, threshold, and runtime configuration resolve without sustained traffic | Does not prove latency, throughput, saturation, or service behavior |
| Loopback smoke | Packaged runtime executes bounded workload, metrics, summary, basic thresholds | Not capacity/scalability/endurance/production-SLO evidence |
| Explicit sustained run | Intended workload executes against an exactly authorized hostname | Authorization does not substitute for environment/change/data/incident controls |
| Threshold result | Objective satisfied/violated under exact workload/environment | Not a timeless SLA or causal explanation |
| Runtime provenance | Executing k6 is tied to reviewed source/build/runtime identity and explicit overrides | Does not prove defect-free behavior or suitability for every environment |
| Built-image Trivy | Produced runtime image is scanned as built, including OS/binary dependencies | Bounded by scanner intelligence, detection, severity, and scope |
| Retained evidence | Expected profile/smoke resolved/executed with attributable machine-readable output | Does not replace native exit status or experiment context |

## Dependency maintenance

Dependabot maintains **Docker** and **GitHub Actions**.

- weekly Monday 09:00 America/New_York;
- grouped routine minor/patch updates;
- major runtime changes remain standalone;
- Docker updates surface the upstream release marker but reviewed runtime PRs must synchronize exact source identity;
- workflow Actions are executable supply-chain dependencies;
- dependency PRs must clear zero-traffic guardrails, image startup, local smoke, extended inspect, security, and docs workflows.

Dependabot does not replace source/image provenance, digest pinning, security override review, non-root policy, CodeQL, Trivy, Dependency Review, or workload authorization.

## Failure triage

| Signal | First interpretation |
| --- | --- |
| Missing/invalid `K6_BASE_URL` | Target ownership/configuration |
| Shell/runtime guardrail rejection | Operator safety/authorization policy |
| `k6 inspect` rejection | Runtime authorization/URL/profile policy |
| Image build/startup | Packaged runtime/dependency contract |
| Fixture readiness | Repository smoke fixture lifecycle |
| Smoke HTTP/check | Request/framework correctness |
| Business metric mismatch | Domain operation/check semantics |
| Target-class mismatch | Evidence/configuration classification |
| Threshold breach | Service objective under achieved workload |
| `dropped_iterations` | Generator capacity/scheduling |
| Sustained target unavailable | Explicit environment/infrastructure |
| Security/docs | Independent repository governance |

## Explicit anti-patterns

- implicit/public demonstration targets;
- image startup that generates traffic by default;
- duplicated k6 runtime versions across Dockerfile/workflow shell;
- sustained traffic from ordinary pull-request CI;
- treating `K6_ALLOW_LOAD_TEST=true` alone as authorization;
- wildcard/substring host authorization where exact ownership is required;
- treating target classification as authorization;
- hiding workload shape behind opaque helpers;
- interpreting p95 without achieved throughput/generator health;
- treating business metrics as replacements for native HTTP/check signals;
- treating dropped iterations as automatic server errors;
- loosening thresholds merely to make a run green.

## Related documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — target safety, runtime, workload, client, metrics, summary/evidence boundaries.
- [`TEST_STRATEGY.md`](TEST_STRATEGY.md) — gate model, profile semantics, interpretation, and exit criteria.

A strong performance framework makes the experiment answerable: what target was authorized/classified, what demand was requested/achieved, what HTTP/business signals reported, what threshold mattered, whether the runtime was controlled, and whether the generator became the bottleneck.
