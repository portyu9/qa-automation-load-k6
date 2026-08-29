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
  const raw = String(__ENV.K6_BASE_URL || '').trim();
  if (!raw) {
    throw new Error('K6_BASE_URL is required');
  }

  const value = raw.replace(/\/$/, '');
  if (!/^https?:\/\/[^\s]+$/i.test(value)) {
    throw new Error('K6_BASE_URL must be an absolute http(s) URL');
  }
  if (/[?#]/.test(value)) {
    throw new Error('K6_BASE_URL must not contain a query string or fragment');
  }

  const authority = value.replace(/^https?:\/\//i, '').split('/')[0];
  if (authority.includes('@')) {
    throw new Error('K6_BASE_URL must not contain URL credentials');
  }
  return value;
}

function validatePort(raw) {
  if (!/^\d+$/.test(raw)) {
    throw new Error('K6_BASE_URL must contain a valid port');
  }
  const port = Number(raw);
  if (!Number.isInteger(port) || port < 1 || port > 65_535) {
    throw new Error('K6_BASE_URL port must be between 1 and 65535');
  }
}

function hostFromUrl(value) {
  const authority = value.replace(/^https?:\/\//i, '').split('/')[0];
  if (authority.startsWith('[')) {
    const closingBracket = authority.indexOf(']');
    if (closingBracket <= 1) {
      throw new Error('K6_BASE_URL must contain a valid hostname');
    }
    const suffix = authority.slice(closingBracket + 1);
    if (suffix) {
      if (!suffix.startsWith(':')) {
        throw new Error('K6_BASE_URL must contain a valid port');
      }
      validatePort(suffix.slice(1));
    }
    return authority.slice(1, closingBracket).toLowerCase();
  }

  const parts = authority.split(':');
  if (parts.length > 2 || !parts[0]) {
    throw new Error('K6_BASE_URL must contain a valid hostname');
  }
  if (parts[1]) validatePort(parts[1]);
  return parts[0].toLowerCase();
}

function allowedHosts() {
  return String(__ENV.K6_ALLOWED_HOSTS || '')
    .split(',')
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
}

const resolvedBaseUrl = baseUrl();

export const config = Object.freeze({
  baseUrl: resolvedBaseUrl,
  targetHost: hostFromUrl(resolvedBaseUrl),
  allowedHosts: Object.freeze(allowedHosts()),
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

  if (!config.allowedHosts.includes(config.targetHost)) {
    throw new Error(
      `${profile} target ${config.targetHost} is not listed in K6_ALLOWED_HOSTS.`
    );
  }
}
