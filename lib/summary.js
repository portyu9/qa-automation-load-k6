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
  const requests = metrics.http_reqs?.values?.count ?? 0;
  const failedRate = metrics.http_req_failed?.values?.rate ?? 0;
  const p95 = metrics.http_req_duration?.values?.['p(95)'] ?? null;
  const checksRate = metrics.checks?.values?.rate ?? null;
  const breaches = thresholdBreaches(metrics);

  const compact = {
    schemaVersion: 1,
    run: {
      runId: config.runId,
      targetHost: config.targetHost,
    },
    headline: {
      requests,
      failedRate,
      p95Ms: p95,
      checksRate,
      thresholdBreaches: breaches,
    },
    state: data.state,
    rootGroup: data.root_group,
    metrics,
  };

  const text = [
    `runId=${config.runId}`,
    `target=${config.targetHost}`,
    `requests=${requests}`,
    `failedRate=${failedRate}`,
    `p95Ms=${p95}`,
    `checksRate=${checksRate}`,
    `thresholdBreaches=${breaches.length}`,
  ].join(' ');

  return {
    stdout: `\n${text}\n`,
    'reports/summary.txt': `${text}\n`,
    'reports/summary.json': JSON.stringify(compact, null, 2),
  };
}
