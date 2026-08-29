# Test strategy

## Purpose

The performance suite separates low-volume framework correctness from sustained traffic experiments. Ordinary CI proves that target/authorization policy is fail-closed and that a tiny real-HTTP smoke flow works against a repository-owned loopback fixture. Meaningful load/stress/soak execution belongs to an explicitly owned and authorized environment.

The framework treats target identity, authorization, workload shape, generator capacity, service thresholds, business signals, runtime packaging, and retained evidence as separate review dimensions. Combining them casually makes a passing or failing performance result difficult to interpret.

## Gate model

| Gate | Sends scenario traffic? | Target | Purpose |
| --- | ---: | --- | --- |
| Shell guardrail self-test | No | None | Prove wrapper refuses missing target/load flag/allowlist and forwards valid invocation |
| Packaged-runtime startup | No | None | Prove the tracked project image starts with `k6 version`, not a traffic scenario |
| k6 `inspect` guardrail checks | No | Synthetic explicit URLs only | Prove scenario/runtime rejects unsafe target, correlation, and authorization configuration |
| Smoke | Yes, three iterations | Repository-owned `127.0.0.1:4020` fixture in CI | Verify real HTTP, checks, business metrics, thresholds, and summary plumbing |
| Extended profile contracts | No | `example.invalid` initialization target | Prove load/stress/soak configuration initializes only under explicit authorization |
| Load/stress/soak | Yes, sustained | Explicit approved environment only | Answer controlled performance questions outside ordinary CI |

The CI `smoke` job depends on `guardrails`; a framework that no longer enforces target ownership or sustained authorization must fail before even the low-volume smoke gate is considered valid.

## Target ownership and safety contracts

`K6_BASE_URL` is mandatory for every traffic-capable invocation. No public demonstration host is inferred by `lib/config.js`, the shell wrapper, the Docker image, or CI.

The target validator rejects:

- missing or blank `K6_BASE_URL`;
- non-HTTP(S) or malformed absolute URLs;
- URL credentials;
- query-bearing URLs;
- fragment-bearing URLs;
- invalid hostnames;
- nonnumeric ports;
- ports outside `1..65535`.

The validated hostname is classified as `local-fixture` for loopback hosts and `explicit-target` otherwise. That classification is diagnostic evidence only. It does **not** authorize sustained traffic.

Sustained profiles additionally require both `K6_ALLOW_LOAD_TEST=true` and an exact hostname match in `K6_ALLOWED_HOSTS`. CI explicitly verifies rejection of missing opt-in, allowlist mismatch, URL credentials, query-bearing targets, and unsafe run-correlation values without executing scenario traffic.

These checks reduce accidental targeting risk. They do not establish organizational authorization; environment ownership, load windows, change control, data policy, and operational approval remain prerequisites for sustained execution.

## Correlation identity

`K6_RUN_ID` groups one execution across request headers and retained summary evidence. When supplied explicitly it must be 1–128 ASCII letters, digits, dots, underscores, colons, or hyphens. If it is absent the framework generates an execution-local identifier.

This contract prevents raw control characters, whitespace, oversized values, or other untrusted material from becoming HTTP header content or evidence identity. Correlation is metadata, not a secret-bearing free-form label.

## Packaged runtime ownership

`docker/Dockerfile` is the single tracked source for the k6 runtime image used by CI and extended profile contracts. Workflows build that Dockerfile instead of independently hard-coding a second `grafana/k6:<version>` reference in shell commands.

This gives dependency automation one authoritative runtime source and prevents workflow/runtime drift. CI derives the expected runtime version from the Dockerfile and verifies the built image reports that version.

The image default command is deliberately non-traffic-generating: starting the image without an explicit scenario command runs `k6 version`. Traffic therefore requires an explicit `run ...` command plus a valid `K6_BASE_URL`; sustained traffic still requires the additional opt-in and exact-host allowlist.

## Deterministic smoke strategy

Required smoke CI starts `scripts/local-api.js`, waits for `/health` using a bounded readiness poll, builds the tracked project image, and executes that image against `http://127.0.0.1:4020` using Linux host networking.

The fixture is deliberately small and synthetic. It exists to prove the framework path, not external-provider compatibility or capacity. The smoke profile verifies:

- explicit target configuration and script initialization;
- safe run-correlation header plumbing;
- real HTTP transport through k6;
- HTTP 200/content-type/JSON parsing checks;
- deterministic domain semantics for `/posts/1`;
- native and custom business metric wiring;
- threshold evaluation;
- structured summary generation;
- target classification;
- fixture process readiness and cleanup ownership.

Because the target is repository-owned, a smoke failure is attributable to framework/request/runtime behavior rather than public DNS, TLS, vendor uptime, demonstration data drift, or rate limiting.

Do not turn smoke into a small stress test. Its value is fast correctness and execution-path validation at negligible volume.

## Zero-traffic guardrail strategy

The shell self-test replaces `k6` with a stub. It proves refusal and command-routing behavior without opening a network connection, including missing explicit target ownership.

Native k6 safety checks use the project-built image with `k6 inspect --include-system-env-vars`. `inspect` initializes imported modules and scenario options but does not execute the configured workload. This proves the JavaScript safety boundary itself is active even when the shell wrapper is bypassed.

The guardrail lane rejects missing sustained opt-in, exact-host mismatch, unsafe target URLs, and invalid `K6_RUN_ID` values. A matching allowlisted target with a safe run ID must initialize successfully.

Extended CI applies the same inspect-only pattern to `load`, `stress`, and `soak`. The synthetic `example.invalid` target is present solely to exercise explicit target parsing and exact-host authorization during initialization; no traffic is sent to it.

## Load strategy

The load profile uses arrival-rate scheduling to request traffic independently from iteration speed. It is appropriate for validating behavior around an expected service throughput region.

Interpret results using both service metrics and generator health. If `dropped_iterations` grows, k6 lacked enough VU capacity to produce the requested schedule; server latency at that point may not represent the intended workload.

A load run must name an approved `K6_BASE_URL`, set `K6_ALLOW_LOAD_TEST=true`, and list the exact hostname in `K6_ALLOWED_HOSTS` before execution.

## Stress strategy

Stress deliberately increases offered traffic beyond ordinary expectations to observe degradation/failure shape. It should identify where latency, error rate, dropped work, or business failures cease to meet the stress policy.

Stress thresholds may differ deliberately from normal load thresholds. Loosening a threshold and increasing traffic in the same unreviewed change makes regressions hard to interpret, so keep those decisions explicit.

Stress execution requires the same explicit target and exact-host authorization contract as load.

## Soak strategy

Soak holds a steady arrival rate for a configurable duration to expose time-dependent behavior such as resource leaks, connection exhaustion, queue growth, or periodic degradation.

Soak duration/rate are environment-specific controls and should be selected with environment capacity/observability owners. The explicit target and exact-host authorization contract applies unchanged.

## Request and metric-tag policy

`lib/client.js` centralizes stable request behavior without hiding k6 behind a generic DSL. Scenario files still own workload intent.

`getJson(path, endpoint, { tags })` records the explicit `endpoint` argument as the authoritative endpoint metric dimension. Caller-supplied tags may add bounded context such as scenario classification, but they cannot override `endpoint`. This prevents accidental metric relabeling and keeps threshold/filter semantics reviewable.

Do not place user IDs, request IDs, random values, raw URLs, or other high-cardinality data in metric tags. Metric cardinality is a generator/observability resource concern in its own right.

## Business metrics

Built-in HTTP/check metrics are supplemented by four domain-oriented metrics:

| Metric | Type | Meaning |
| --- | --- | --- |
| `business_attempts` | Counter | Domain operation attempts |
| `business_success` | Rate | Operations whose complete check set passed |
| `business_failures` | Rate | Operations whose complete check set failed |
| `business_duration` | Trend | Domain operation duration |

Custom metrics do not replace native HTTP metrics. They provide a business-level view that can be correlated with transport latency/failure, checks, requested load, and generator capacity.

## Threshold policy

Thresholds are automated pass/fail contracts, not descriptive dashboards. `lib/thresholds.js` centralizes common expressions so profile policy cannot drift accidentally.

At minimum interpret:

- `checks` rate;
- `http_req_failed` rate;
- `http_req_duration` p95;
- `business_success` and `business_failures` where applicable;
- `dropped_iterations` for arrival-rate profiles.

A threshold failure must be investigated in context of achieved throughput and generator capacity. Smoke thresholds validate framework/basic-health behavior; they are not evidence that a production SLO can be sustained at meaningful demand.

## Evidence and triage

`reports/summary.json` is the primary machine-readable artifact, accompanied by the native text summary. It records run identity, target host, `targetClass`, headline HTTP/check/business metrics, native metric detail, and explicit threshold-breach information.

Triage order:

1. was an explicit target supplied and accepted?;
2. is the run ID valid and safe for headers/evidence?;
3. for sustained profiles, did opt-in and exact-host authorization succeed?;
4. for CI smoke, did the repository-owned fixture become healthy?;
5. did the scenario achieve the intended request schedule?;
6. were iterations dropped due to generator capacity?;
7. did transport/check/business signals fail?;
8. which threshold expressions breached?;
9. for real performance runs, what did service/resource observability show during the same run ID/time window?

Do not interpret one p95 number without workload context.

## Failure classification

| Failure class | First interpretation |
| --- | --- |
| Missing/unsafe target | Configuration/target ownership defect |
| Invalid run ID | Correlation/header/evidence policy defect |
| Missing opt-in or host allowlist | Sustained-authorization defect |
| Shell guardrail regression | Operator-safety wrapper defect |
| Project-image startup/version mismatch | Runtime packaging/dependency ownership defect |
| `k6 inspect` regression | Runtime/module safety-policy defect |
| Local fixture startup/readiness | CI smoke infrastructure defect |
| Smoke HTTP/check/business failure | Client/request/fixture contract defect |
| Metric endpoint relabeling | Framework metric-tag ownership defect |
| Summary artifact missing | Evidence/lifecycle defect |
| Threshold breach | Service objective or experiment result |
| Dropped iterations | Generator/scheduling capacity issue |
| External sustained-only failure | Environment/service experiment signal |

## Change policy

Treat these as separate review dimensions:

- target ownership and URL validation;
- run-correlation validation;
- sustained authorization policy;
- packaged-runtime/dependency ownership;
- repository-owned smoke fixture lifecycle;
- scenario/executor/rate shape;
- VU generator capacity;
- metric naming/tag cardinality;
- thresholds/SLO policy;
- service request/check/business behavior;
- summary/reporting behavior.

A change to one should not silently redefine another.

## Exit criteria

A k6 framework change is ready when:

- missing target ownership is rejected before traffic;
- unsafe run-correlation values are rejected before traffic;
- zero-traffic shell and k6 runtime guardrail checks pass;
- unsafe targets/configuration are rejected before execution;
- the tracked Dockerfile builds and its default startup generates no traffic;
- the low-volume smoke gate passes against the repository-owned fixture using the project-built image;
- no required CI path depends on a public or deployed service;
- endpoint tags remain authoritative and bounded;
- business and native metrics remain separately interpretable;
- summary artifacts identify run/target class and threshold breaches;
- threshold policy changes are explicit and reviewed separately from workload shape;
- no sustained profile is added to ordinary CI against an uncontrolled target;
- extended load/stress/soak validation remains inspect-only;
- documentation reflects changed safety, traffic, runtime, metric, threshold, or evidence semantics.
