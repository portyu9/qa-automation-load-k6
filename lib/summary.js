export function handleSummary(data) {
  const metrics = data.metrics || {};
  const requests = metrics.http_reqs?.values?.count ?? 0;
  const failedRate = metrics.http_req_failed?.values?.rate ?? 0;
  const p95 = metrics.http_req_duration?.values?.['p(95)'] ?? null;
  const checksRate = metrics.checks?.values?.rate ?? null;

  const compact = {
    requests,
    failedRate,
    p95Ms: p95,
    checksRate,
    state: data.state,
    rootGroup: data.root_group,
    metrics,
  };

  return {
    stdout: `\nrequests=${requests} failedRate=${failedRate} p95Ms=${p95} checksRate=${checksRate}\n`,
    'reports/summary.json': JSON.stringify(compact, null, 2),
  };
}
