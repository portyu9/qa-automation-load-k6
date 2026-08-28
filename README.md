# k6 Performance Test Framework

A Grafana k6 framework for smoke, load, stress, and soak testing with explicit workload models, SLO-style thresholds, endpoint tags, custom business metrics, machine-readable summaries, and safeguards against accidental sustained traffic.

## Baseline

- k6 2.2.0 official Docker image;
- scenario executors instead of a single global `stages` block;
- arrival-rate models for load/stress;
- pass/fail thresholds on latency, failure rate, checks, business failures, and dropped iterations;
- environment-driven targets and threshold values;
- `X-Test-Run-Id` correlation header;
- summary JSON retained by CI;
- load/stress/soak opt-in safety control.

## Structure

```text
.
├── lib/
│   ├── config.js
│   ├── client.js
│   ├── metrics.js
│   └── summary.js
├── tests/
│   ├── smoke.js
│   ├── load.js
│   ├── stress.js
│   └── soak.js
├── scripts/run_k6.sh
├── docker/Dockerfile
├── docs/
└── .github/workflows/ci.yml
```

## Safety requirement

`smoke` is the only profile enabled by default. Before running `load`, `stress`, or `soak`, confirm the target is explicitly authorized for performance testing and then set:

```bash
export K6_BASE_URL=https://performance.example.internal
export K6_ALLOW_LOAD_TEST=true
```

The flag is a guardrail; it is not a substitute for authorization, capacity coordination, or a test window.

## Local execution

With k6 installed:

```bash
./scripts/run_k6.sh smoke
./scripts/run_k6.sh load       # requires K6_ALLOW_LOAD_TEST=true
./scripts/run_k6.sh stress     # requires K6_ALLOW_LOAD_TEST=true
./scripts/run_k6.sh soak       # requires K6_ALLOW_LOAD_TEST=true
```

Pinned Docker execution:

```bash
mkdir -p reports
docker run --rm \
  -e K6_BASE_URL \
  -e K6_RUN_ID \
  -e K6_ALLOW_LOAD_TEST \
  -v "$PWD:/src" -w /src \
  grafana/k6:2.2.0 run tests/smoke.js
```

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `K6_BASE_URL` | target base URL | JSONPlaceholder |
| `K6_RUN_ID` | request correlation | generated timestamp |
| `K6_P95_MS` | p95 latency threshold for load/soak | `500` |
| `K6_ERROR_RATE` | max failure rate | `0.01` |
| `K6_THINK_TIME_SECONDS` | pacing between iterations | `1` |
| `K6_ALLOW_LOAD_TEST` | explicit sustained-load opt-in | unset/false |
| `K6_SOAK_DURATION` | soak duration override | `10m` |
| `K6_SOAK_RATE` | soak iterations per second | `5` |

## Workload profiles

### Smoke

One VU performs three iterations to validate target reachability, checks, scripts, and report generation. This is the CI profile.

### Load

Uses `ramping-arrival-rate` to reach 5 then 10 iterations/second. Arrival-rate executors model incoming work independently from response latency; `dropped_iterations` is therefore a critical validity metric.

### Stress

Raises the requested arrival rate in steps and uses intentionally looser thresholds to observe degradation rather than claim normal-load SLO compliance.

### Soak

Uses a constant arrival rate for a configurable duration. A real soak window is normally much longer than the safe repository default and should run only in a controlled environment.

## Metrics and thresholds

Built-in `http_req_duration`, `http_req_failed`, `checks`, and `dropped_iterations` are combined with:

- `business_failures` — rate of failed common semantic/protocol checks;
- `business_duration` — endpoint-tagged response duration trend.

Threshold failures produce a non-zero k6 exit code. Do not suppress that exit code in CI.

## Tagging

Requests use stable low-cardinality endpoint tags (`get_post`, `list_posts`). Do not tag metrics with GUIDs, user IDs, timestamps, or request IDs; high-cardinality metric labels create expensive and difficult-to-query time series. Use correlation headers/logs for per-request tracing.

## CI

GitHub Actions runs only the smoke profile in the pinned 2.2.0 container and uploads `reports/summary.json`. Sustained load is deliberately excluded from pull-request CI.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/TEST_STRATEGY.md`](docs/TEST_STRATEGY.md) for workload modeling, threshold, safety, and analysis guidance.
