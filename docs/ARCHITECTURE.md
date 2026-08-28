# Architecture

## Layers

- **Scenario scripts** define workload shape and profile-specific thresholds.
- **Client helpers** own request construction, safe headers, endpoint tags, and common checks.
- **Configuration** validates environment-controlled target and SLO inputs in the init context.
- **Custom metrics** expose business-oriented failure and duration signals alongside built-in HTTP metrics.
- **Summary handling** writes machine-readable end-of-test evidence.

The framework does not hide k6 executors behind a generic abstraction. Workload shape is an essential part of a performance test and should remain visible in each profile.

## Safety boundary

Smoke is the only profile that runs without an explicit opt-in. `load`, `stress`, and `soak` throw during initialization unless `K6_ALLOW_LOAD_TEST=true`. This prevents a copied command or CI change from unintentionally producing sustained traffic against a shared/public target.

Authorization for load testing is an operational prerequisite, not a code setting. The environment flag is a deliberate friction mechanism, not proof of authorization.

## Open workload model

Load and stress use `ramping-arrival-rate`, which schedules iteration starts independently of response time. This is useful when the requirement is throughput/arrival rate rather than “N concurrent virtual users.” Watch `dropped_iterations`: if VUs cannot sustain the scheduled rate, the workload generator is no longer delivering the intended model.

## Thresholds

Thresholds are executable SLO-style acceptance criteria. They determine process exit status and therefore CI gate behavior. Built-in request failure/duration metrics are combined with custom business failure metrics so protocol success cannot hide failed semantic checks.

## Tags

Every request has an `endpoint` tag and each scenario has a `profile` tag. This enables per-endpoint/per-profile analysis in external outputs without creating high-cardinality tags such as user IDs or random request IDs.

## Summary

`handleSummary()` writes `reports/summary.json`. In larger systems, stream time-series metrics to an approved backend (Prometheus remote write, Grafana Cloud, etc.) and keep the end summary as the CI artifact.
