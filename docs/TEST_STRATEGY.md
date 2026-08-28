# Test strategy

## Purpose

The performance suite separates low-volume correctness checks from sustained traffic profiles. Ordinary CI proves that the framework is safe to initialize and that a tiny smoke flow works; meaningful load/stress/soak execution belongs to an explicitly owned and authorized environment.

## Gate model

| Gate | Sends scenario traffic? | Purpose |
| --- | ---: | --- |
| Shell guardrail self-test | No | Prove wrapper refuses missing load flag/allowlist and forwards valid invocation |
| k6 `inspect` guardrail checks | No | Prove scenario/runtime rejects unsafe target/authorization configuration |
| Smoke | Yes, very low volume | Verify request/check/summary plumbing against the configured smoke target |
| Load/stress/soak | Yes, sustained | Answer controlled performance questions outside ordinary PR CI |

The CI `smoke` job depends on `guardrails`; a framework that no longer enforces authorization must fail before even the low-volume smoke gate is considered valid.

## Target safety contracts

Sustained profiles require both `K6_ALLOW_LOAD_TEST=true` and an exact hostname match in `K6_ALLOWED_HOSTS`. CI explicitly verifies rejection of:

- missing opt-in;
- mismatched allowlist;
- URL credentials;
- query-bearing base URLs.

`K6_BASE_URL` validation also rejects fragments and invalid/out-of-range ports.

These checks reduce accidental targeting risk. They do not establish authorization; execution approval, environment ownership, and load windows remain operational prerequisites.

## Smoke strategy

Smoke uses a tiny bounded workload intended to prove:

- script initialization;
- target connectivity;
- common request helper behavior;
- JSON/content checks;
- custom/built-in metric wiring;
- summary generation;
- threshold plumbing.

Do not turn smoke into a small stress test. Its value is fast correctness and execution-path validation.

## Load strategy

The load profile uses arrival-rate scheduling to request traffic independently from iteration speed. It is appropriate for validating behavior around an expected service throughput region.

Interpret results using both service metrics and generator health. If `dropped_iterations` grows, k6 lacked enough VU capacity to produce the requested schedule; server latency at that point may not represent the intended workload.

## Stress strategy

Stress deliberately increases offered traffic beyond ordinary expectations to observe degradation/failure shape. It should identify where latency, error rate, dropped work, or business failures cease to meet the stress policy.

Stress thresholds may differ deliberately from normal load thresholds. Loosening a threshold and increasing traffic in the same unreviewed change makes regressions hard to interpret, so keep those decisions explicit.

## Soak strategy

Soak holds a steady arrival rate for a configurable duration to expose time-dependent behavior such as resource leaks, connection exhaustion, queue growth, or periodic degradation.

Soak duration/rate are environment-specific controls and should be selected with environment capacity/observability owners.

## Threshold policy

Thresholds are automated pass/fail contracts, not descriptive dashboards. `lib/thresholds.js` centralizes the common expressions so smoke/load/soak policy cannot drift accidentally.

At minimum interpret:

- `checks` rate;
- `http_req_failed` rate;
- `http_req_duration` p95;
- `business_failures` where applicable;
- `dropped_iterations` for arrival-rate profiles.

A threshold failure must be investigated in context of achieved throughput and generator capacity.

## Evidence and triage

`reports/summary.json` is the primary machine-readable artifact. It records key metrics plus explicit threshold breach details.

Triage order:

1. did the guardrail/configuration initialize correctly?;
2. did the scenario achieve the intended request schedule?;
3. were iterations dropped due to generator capacity?;
4. did transport/business checks fail?;
5. which threshold expressions breached?;
6. what did external service/resource observability show during the same run ID/time window?

Do not interpret one p95 number without workload/throughput context.

## Change policy

Treat these as separate review dimensions:

- target/authorization policy;
- scenario/executor/rate shape;
- VU generator capacity;
- thresholds/SLO policy;
- service request behavior/checks;
- summary/reporting behavior.

A change to one should not silently redefine another.

## Exit criteria

A k6 framework change is ready when:

- zero-traffic shell and k6 runtime guardrail checks pass;
- unsafe targets/configuration are rejected before execution;
- the pinned-version smoke gate passes;
- summary artifacts are produced;
- threshold policy changes are explicit and reviewed separately from workload shape;
- no sustained profile is added to ordinary CI against an uncontrolled target;
- documentation reflects changed safety, traffic, threshold, or evidence semantics.
