# k6 Performance Quality Engineering Framework

[![CI](https://github.com/portyu9/qa-automation-load-k6/actions/workflows/ci.yml/badge.svg)](https://github.com/portyu9/qa-automation-load-k6/actions/workflows/ci.yml)
[![Extended](https://github.com/portyu9/qa-automation-load-k6/actions/workflows/extended.yml/badge.svg)](https://github.com/portyu9/qa-automation-load-k6/actions/workflows/extended.yml)
[![Security](https://github.com/portyu9/qa-automation-load-k6/actions/workflows/security.yml/badge.svg)](https://github.com/portyu9/qa-automation-load-k6/actions/workflows/security.yml)
[![Docs](https://github.com/portyu9/qa-automation-load-k6/actions/workflows/docs.yml/badge.svg)](https://github.com/portyu9/qa-automation-load-k6/actions/workflows/docs.yml)

[![k6](https://img.shields.io/badge/k6-performance-7D64FF?logo=k6&logoColor=white)](https://k6.io/)
[![JavaScript](https://img.shields.io/badge/JavaScript-scripting-F7DF1E?logo=javascript&logoColor=black)](https://grafana.com/docs/k6/latest/using-k6/javascript-api/)
[![Bash](https://img.shields.io/badge/Bash-guardrails-4EAA25?logo=gnubash&logoColor=white)](https://www.gnu.org/software/bash/)
[![Docker](https://img.shields.io/badge/Docker-runtime-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-CI-2088FF?logo=githubactions&logoColor=white)](https://github.com/features/actions)
[![Trivy](https://img.shields.io/badge/Trivy-security-1904DA?logo=trivy&logoColor=white)](https://trivy.dev/)
[![License](https://img.shields.io/badge/License-MIT-2EA44F?logo=opensourceinitiative&logoColor=white)](LICENSE)
[![Security Policy](https://img.shields.io/badge/Security-Policy-24292F?logo=github&logoColor=white)](.github/SECURITY.md)

A k6 performance quality-engineering framework for **smoke, load, stress, and soak** analysis with explicit workload models, centralized threshold policy, business metrics, exact-host authorization, deterministic smoke execution, zero-traffic safety verification, and machine-readable summaries.

> [!CAUTION]
> `load`, `stress`, and `soak` are controlled traffic experiments—not ordinary automated test cases. Authorization, target identity, demand shape, generator capacity, service thresholds, and evidence are separate concerns. Routine CI must never silently become sustained traffic.

**Read by intent:** [capabilities](#capability-map) · [safety model](#target-and-authorization-model) · [quick start](#quick-start) · [workload model](#workload-and-threshold-model) · [evidence](#evidence-and-interpretation) · [dependencies](#dependency-maintenance) · [triage](#failure-triage)

## Capability map

| Plane | Question | Traffic behavior | Evidence |
| --- | --- | --- | --- |
| Guardrails | Will unsafe/missing configuration be rejected? | **Zero traffic** | Shell contract + `k6 inspect` |
| Smoke | Does the request/check/metric/summary path work? | Very low volume to repository loopback API | Structured summary |
| Extended profiles | Do load/stress/soak initialize under authorized config? | **Zero traffic — inspect only** | Per-profile inspect evidence |
| Load | Can expected demand satisfy service objectives? | Explicit operator execution | k6 metrics + thresholds |
| Stress | Where does controlled degradation begin? | Explicit operator execution | k6 metrics + failure shape |
| Soak | Does stable demand expose cumulative degradation? | Explicit operator execution | Time-dependent metrics |
| Security | Repository dependency/configuration exposure | No target traffic | Trivy findings |
| Documentation | README/workflow/governance consistency | No target traffic | Actions status |

## Architecture

```mermaid
flowchart TD
    CHANGE[Change] --> GUARD[Shell + runtime guardrails]
    GUARD --> FIX[Repository loopback API]
    FIX --> SMOKE[Low-volume smoke]
    CHANGE --> EXT[Extended profile contracts]
    EXT --> L[k6 inspect · load]
    EXT --> ST[k6 inspect · stress]
    EXT --> SO[k6 inspect · soak]
    L --> ZERO[Zero sustained traffic]
    ST --> ZERO
    SO --> ZERO
    OP[Authorized operator] -->|target + opt-in + exact host| RUN[load / stress / soak]
    RUN --> SUMMARY[Metrics + thresholds + summary]

    classDef entry fill:#ddf4ff,stroke:#0969da,color:#24292f,stroke-width:1.5px;
    classDef core fill:#f6f8fa,stroke:#57606a,color:#24292f,stroke-width:1.5px;
    classDef gate fill:#fbefff,stroke:#8250df,color:#24292f,stroke-width:1.5px;
    classDef evidence fill:#dafbe1,stroke:#1a7f37,color:#24292f,stroke-width:1.5px;
    class CHANGE,OP entry;
    class GUARD,FIX core;
    class SMOKE,EXT,L,ST,SO,RUN gate;
    class ZERO,SUMMARY evidence;
    linkStyle default stroke:#57606a,stroke-width:1.4px;
```

## Engineering invariants

| Concern | Framework contract |
| --- | --- |
| Target ownership | `K6_BASE_URL` is always explicit; there is no public-service fallback. |
| Required smoke | CI uses repository-owned `127.0.0.1:4020`. |
| Sustained authorization | `K6_ALLOW_LOAD_TEST=true` **and** exact hostname membership in `K6_ALLOWED_HOSTS`. |
| Target URL | Absolute HTTP(S), valid hostname/port, no credentials, query, or fragment. |
| Defense in depth | Shell wrapper and k6 runtime independently enforce safety. |
| Wrapper privacy | Unvalidated raw targets are not echoed into routine output. |
| Traffic model | Arrival-rate executors describe requested demand independently of iteration duration. |
| Thresholds | Shared service-level policy is centralized; deviations are explicit. |
| Capacity | `dropped_iterations` is a generator/scheduling signal, not automatically a server failure. |
| Evidence | Native metrics plus structured threshold-breach summaries remain authoritative. |
| Reproducibility | CI runs pinned `grafana/k6:2.2.0`; the project image runs non-root. |

## Target and authorization model

Every traffic-capable invocation requires `K6_BASE_URL`. Sustained profiles additionally require:

```text
K6_BASE_URL=<explicit target>
AND
K6_ALLOW_LOAD_TEST=true
AND
target hostname ∈ K6_ALLOWED_HOSTS
```

The shell wrapper fails early for normal operator ergonomics. `requireLoadAuthorization()` repeats the policy inside the traffic-capable JavaScript so direct `k6 run` cannot bypass it.

> [!IMPORTANT]
> An allowlist and boolean flag reduce accidental targeting risk; they are not proof of organizational authorization. Change control, ownership, maintenance windows, data policy, and observability remain operational prerequisites.

## Repository map

```text
.
├── docker/Dockerfile
├── lib/{client.js,config.js,metrics.js,summary.js,thresholds.js}
├── scripts/{local-api.js,run_k6.sh,test_guardrails.sh}
├── tests/{smoke.js,load.js,stress.js,soak.js}
├── docs/{ARCHITECTURE.md,TEST_STRATEGY.md}
└── .github/workflows/{ci,docs,extended,security}.yml
```

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

Validate guardrails without scenario traffic:

```bash
bash scripts/test_guardrails.sh
python .github/scripts/validate_readme.py
```

Inspect a sustained profile without executing it:

```bash
K6_BASE_URL=https://example.invalid \
K6_ALLOW_LOAD_TEST=true \
K6_ALLOWED_HOSTS=example.invalid \
k6 inspect --include-system-env-vars tests/load.js
```

<details>
<summary><strong>Runtime configuration</strong></summary>

| Variable | Purpose | Default |
| --- | --- | --- |
| `K6_BASE_URL` | Explicit target | required |
| `K6_RUN_ID` | Run correlation | generated ID |
| `K6_P95_MS` | Default p95 budget | `500` |
| `K6_ERROR_RATE` | Max normal error/business-failure rate | `0.01` |
| `K6_THINK_TIME_SECONDS` | Iteration pacing | `1` |
| `K6_ALLOW_LOAD_TEST` | Sustained-profile opt-in | unset / disabled |
| `K6_ALLOWED_HOSTS` | Exact authorized hostnames | unset |
| `K6_SOAK_DURATION` | Soak duration | `10m` |
| `K6_SOAK_RATE` | Soak arrival rate | `5` |

</details>

## Deterministic smoke boundary

`scripts/local-api.js` provides `/health` and `/posts/1` on loopback. CI starts it with bounded readiness polling, then runs pinned k6 using host networking. This preserves real k6 HTTP/check/metric/summary behavior while removing DNS, TLS, public service uptime, public rate limits, and demo-data drift from required CI.

The local fixture proves **framework correctness**, not service capacity.

## Workload and threshold model

| Profile | Executor | Question |
| --- | --- | --- |
| `smoke` | `shared-iterations` | Is the execution path healthy at negligible volume? |
| `load` | `ramping-arrival-rate` | Can expected throughput satisfy normal budgets? |
| `stress` | `ramping-arrival-rate` | How does behavior degrade beyond the normal envelope? |
| `soak` | `constant-arrival-rate` | Does stable demand reveal time-dependent degradation? |

Keep these concepts separate:

- **rate/stage** → demand requested from the generator;
- **VU capacity** → ability to generate that schedule;
- **threshold** → pass/fail service objective;
- **check** → correctness observation;
- **business metric** → domain-level failure/success signal;
- **dropped iterations** → generator scheduling/capacity shortfall.

Changing workload shape and loosening thresholds in the same opaque change destroys interpretability.

## Client and metric policy

`lib/client.js` centralizes stable request behavior, run headers, endpoint tags, JSON/content checks, and custom metric updates. Scenario files own workload behavior; they should not duplicate transport boilerplate or hide k6 behind a generic DSL.

`lib/thresholds.js` centralizes common threshold expressions. Profile-specific differences should be deliberate and reviewable.

## Evidence and interpretation

`handleSummary()` writes a compact stdout headline and `reports/summary.json` with key request/error/check/latency values and threshold-breach details.

A p95 number has no meaning without workload context. Interpret latency together with achieved throughput, HTTP/business failures, and `dropped_iterations`. If the generator did not produce the intended schedule, the experiment answered a different question.

## CI topology

- `ci.yml` — zero-traffic guardrails + low-volume local smoke.
- `extended.yml` — zero-traffic `k6 inspect` contracts for sustained profiles.
- `security.yml` — repository vulnerability/misconfiguration analysis.
- `docs.yml` — deterministic README/governance validation.

No workflow automatically runs sustained load/stress/soak traffic.

## Dependency maintenance

Dependabot maintains **Docker** and **GitHub Actions** dependencies.

- weekly Monday 09:00 America/New_York;
- grouped minor/patch updates for routine maintenance;
- major Docker/runtime updates remain standalone because k6/runtime behavior can change materially;
- Actions are reviewed as executable supply-chain dependencies;
- dependency PRs must clear zero-traffic guardrails, pinned smoke, extended inspect, security, and docs gates.

Dependabot does not replace image pinning, non-root container policy, Trivy, or workload authorization.

## Failure triage

| Signal | First interpretation |
| --- | --- |
| Missing/invalid `K6_BASE_URL` | Target ownership/configuration |
| Shell guardrail rejection | Operator safety policy |
| `k6 inspect` rejection | Runtime authorization/URL policy |
| Fixture readiness failure | Repository smoke fixture lifecycle |
| Smoke check/HTTP failure | Request/framework correctness |
| Threshold breach | Service objective under achieved workload |
| `dropped_iterations` | Generator capacity/scheduling |
| Sustained target unavailable | Explicit environment/infrastructure |
| Security/docs | Independent repository governance |

## Explicit anti-patterns

- implicit/public demo targets;
- running sustained traffic from ordinary pull-request CI;
- treating `K6_ALLOW_LOAD_TEST=true` alone as authorization;
- substring/wildcard host authorization where exact ownership is required;
- hiding workload shape behind opaque helpers;
- interpreting p95 without achieved throughput/generator health;
- treating dropped iterations as automatic server errors;
- loosening thresholds merely to make a run green.

## Design references

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — target safety, workload, client, metric, and evidence boundaries.
- [`docs/TEST_STRATEGY.md`](docs/TEST_STRATEGY.md) — gate model, profile semantics, interpretation, and exit criteria.

A strong performance framework makes the experiment answerable: **what target was authorized, what demand was requested, what demand was achieved, what failed, what threshold mattered, and whether the generator itself became the bottleneck**.
