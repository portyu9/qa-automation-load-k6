import { config } from './config.js';

function thresholdBreaches(metrics) {
  const breaches = [];
  for (const [metricName, metric] of Object.entries(metrics)) {
    for (const [expression, result] of Object.entries(metric.thresholds || {})) {
      if (result && result.ok === false) {
        breaches.push({ metric: metricName, threshold: expression });
      }
    }
  }
  return breaches;
}

export function handleSummary(data) {
  const metrics = data.metrics || {};
  const iterations = metrics.iterations?.values?.count ?? 0;
  const requests = metrics.http_reqs?.values?.count ?? 0;
  const failedRate = metrics.http_req_failed?.values?.rate ?? 0;
  const p95 = metrics.http_req_duration?.values?.['p(95)'] ?? null;
  const checksRate = metrics.checks?.values?.rate ?? null;
  const businessAttempts = metrics.business_attempts?.values?.count ?? 0;
  const businessSuccessRate = metrics.business_success?.values?.rate ?? null;
  const businessFailureRate = metrics.business_failures?.values?.rate ?? null;
  const businessP95 = metrics.business_duration?.values?.['p(95)'] ?? null;
  const breaches = thresholdBreaches(metrics);

  const compact = {
    schemaVersion: 1,
    run: {
      runId: config.runId,
      targetHost: config.targetHost,
      targetClass: config.targetClass,
    },
    headline: {
      iterations,
      requests,
      failedRate,
      p95Ms: p95,
      checksRate,
      businessAttempts,
      businessSuccessRate,
      businessFailureRate,
      businessP95Ms: businessP95,
      thresholdBreaches: breaches,
    },
  };

  const text = [
    `runId=${config.runId}`,
    `target=${config.targetHost}`,
    `targetClass=${config.targetClass}`,
    `iterations=${iterations}`,
    `requests=${requests}`,
    `failedRate=${failedRate}`,
    `p95Ms=${p95}`,
    `checksRate=${checksRate}`,
    `businessAttempts=${businessAttempts}`,
    `businessSuccessRate=${businessSuccessRate}`,
    `businessFailureRate=${businessFailureRate}`,
    `businessP95Ms=${businessP95}`,
    `thresholdBreaches=${breaches.length}`,
  ].join(' ');

  return {
    stdout: `\n${text}\n`,
    'reports/summary.txt': `${text}\n`,
    'reports/summary.json': JSON.stringify(compact, null, 2),
  };
}
