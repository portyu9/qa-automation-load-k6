export function sloThresholds({
  checksRate = 0.99,
  errorRate,
  p95Ms,
  includeBusinessFailures = true,
  includeDroppedIterations = true,
}) {
  const thresholds = {
    checks: [`rate>=${checksRate}`],
    http_req_failed: [`rate<=${errorRate}`],
    http_req_duration: [`p(95)<${p95Ms}`],
  };

  if (includeBusinessFailures) {
    thresholds.business_failures = [`rate<=${errorRate}`];
    thresholds.business_success = [`rate>=${checksRate}`];
  }
  if (includeDroppedIterations) {
    thresholds.dropped_iterations = ['count<1'];
  }

  return thresholds;
}
