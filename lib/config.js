function positiveNumber(name, fallback) {
  const raw = __ENV[name];
  const value = raw === undefined || raw === '' ? fallback : Number(raw);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${name} must be a positive number`);
  }
  return value;
}

function boundedRate(name, fallback) {
  const value = positiveNumber(name, fallback);
  if (value >= 1) throw new Error(`${name} must be greater than 0 and less than 1`);
  return value;
}

function baseUrl() {
  const value = (__ENV.K6_BASE_URL || 'https://jsonplaceholder.typicode.com').replace(/\/$/, '');
  if (!/^https?:\/\/[^\s]+$/i.test(value)) {
    throw new Error('K6_BASE_URL must be an absolute http(s) URL');
  }
  return value;
}

export const config = Object.freeze({
  baseUrl: baseUrl(),
  runId: __ENV.K6_RUN_ID || `k6-${Date.now()}`,
  p95Ms: positiveNumber('K6_P95_MS', 500),
  errorRate: boundedRate('K6_ERROR_RATE', 0.01),
  thinkTimeSeconds: positiveNumber('K6_THINK_TIME_SECONDS', 1),
});

export function requireLoadAuthorization(profile) {
  if (String(__ENV.K6_ALLOW_LOAD_TEST).toLowerCase() !== 'true') {
    throw new Error(
      `${profile} is disabled by default. Set K6_ALLOW_LOAD_TEST=true only for an authorized target.`
    );
  }
}
