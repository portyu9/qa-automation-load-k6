# Performance test strategy

## Profiles

- **smoke**: verifies script/target correctness with negligible load; suitable for CI.
- **load**: validates expected sustained arrival rate and SLO thresholds.
- **stress**: increases arrival rate beyond expected load to observe degradation behavior and recovery.
- **soak**: sustains moderate traffic long enough to expose resource leaks, pool exhaustion, or time-dependent degradation.

Capacity, spike, breakpoint, and browser-performance profiles can be added when the system has explicit requirements for them.

## Workload model first

Define traffic assumptions before tuning VUs: arrival rate, endpoint mix, think time, payload distribution, authentication model, cache behavior, test duration, and expected concurrency. A realistic model matters more than a large VU number.

## Thresholds

Choose thresholds from service objectives or established baselines. Track percentile latency and error rate; averages hide tail degradation. Include dropped iterations for arrival-rate executors because they indicate the generator could not maintain the requested schedule.

## Environment

Performance results are comparable only when environment capacity, dataset, upstream dependencies, and competing traffic are understood. Do not compare a developer laptop run directly with a dedicated performance environment and call the difference a regression.

## Data and correlation

Avoid a single hot record unless hotspot contention is part of the scenario. Use bounded-cardinality tags. Run/request IDs belong in headers/logs, not metric tags, to avoid exploding time-series cardinality.

## Failure interpretation

A threshold failure means the tested workload did not meet the declared acceptance criterion. It does not by itself identify the bottleneck. Correlate k6 metrics with service CPU/memory, saturation, database metrics, traces, logs, queue depth, and dependency telemetry.

## CI policy

Pull-request CI runs only smoke. Sustained load should execute in a controlled environment through an explicitly authorized workflow. Keep test summaries and external time-series links/results with the change/release being evaluated.
