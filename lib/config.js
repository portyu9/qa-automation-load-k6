const LOCAL_FIXTURE_HOSTS = new Set(['127.0.0.1', 'localhost', '::1']);
const SAFE_CORRELATION_TOKEN = /^[A-Za-z0-9._:-]{1,128}$/;

function positiveNumber(name, fallback) {
  const raw = __ENV[name];
  const value = raw === undefined || raw === '' ? fallback : Number(raw);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${name} must be a positive number`);
  }
  return value;
}

function nonNegativeNumber(name, fallback) {
  const raw = __ENV[name];
  const value = raw === undefined || raw === '' ? fallback : Number(raw);
  if (!Number.isFinite(value) || value < 0) {
    throw new Error(`${name} must be a non-negative number`);
  }
  return value;
}

function boundedRate(name, fallback) {
  const raw = __ENV[name];
  const value = raw === undefined || raw === '' ? fallback : Number(raw);
  if (!Number.isFinite(value) || value < 0 || value >= 1) {
    throw new Error(`${name} must be greater than or equal to 0 and less than 1`);
  }
  return value;
}

function correlationToken(name, fallback) {
  const value = String(__ENV[name] || '').trim() || fallback;
  if (!SAFE_CORRELATION_TOKEN.test(value)) {
    throw new Error(
      `${name} must be 1-128 ASCII letters, digits, dots, underscores, colons, or hyphens`
    );
  }
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

function validateDnsLikeHost(host) {
  if (host.length > 253) {
    throw new Error('K6_BASE_URL hostname is too long');
  }
  const labels = host.split('.');
  if (labels.some((label) =>
    !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i.test(label))) {
    throw new Error('K6_BASE_URL must contain a valid hostname');
  }
}

function validIpv4Tail(value) {
  const octets = value.split('.');
  return octets.length === 4 && octets.every((octet) => {
    if (!/^\d{1,3}$/.test(octet)) return false;
    const number = Number(octet);
    return number >= 0 && number <= 255 && String(number) === octet;
  });
}

function validIpv6Host(host) {
  if (!host.includes(':')) return false;
  if (host.indexOf('::') !== host.lastIndexOf('::')) return false;

  let source = host;
  if (source.includes('.')) {
    const lastColon = source.lastIndexOf(':');
    if (lastColon < 0 || !validIpv4Tail(source.slice(lastColon + 1))) return false;
    // An IPv4 tail occupies two IPv6 hextets. Replace it with two explicit
    // hextets while retaining the preceding colon so `::` compression remains
    // intact for forms such as 2001:db8::192.0.2.1.
    source = `${source.slice(0, lastColon + 1)}0:0`;
  }

  const hasCompression = source.includes('::');
  const halves = hasCompression ? source.split('::') : [source, ''];
  const left = halves[0] ? halves[0].split(':') : [];
  const right = hasCompression && halves[1] ? halves[1].split(':') : [];
  const hextets = [...left, ...right];
  if (hextets.some((part) => !/^[0-9a-f]{1,4}$/i.test(part))) return false;

  const units = hextets.length;
  return hasCompression ? units < 8 : units === 8;
}

function hostFromUrl(value) {
  const authority = value.replace(/^https?:\/\//i, '').split('/')[0];
  if (authority.startsWith('[')) {
    const closingBracket = authority.indexOf(']');
    if (closingBracket <= 1) {
      throw new Error('K6_BASE_URL must contain a valid hostname');
    }
    const host = authority.slice(1, closingBracket).toLowerCase();
    if (!validIpv6Host(host)) {
      throw new Error('K6_BASE_URL must contain a valid IPv6 hostname');
    }
    const suffix = authority.slice(closingBracket + 1);
    if (suffix) {
      if (!suffix.startsWith(':')) {
        throw new Error('K6_BASE_URL must contain a valid port');
      }
      validatePort(suffix.slice(1));
    }
    return host;
  }

  const parts = authority.split(':');
  if (parts.length > 2 || !parts[0]) {
    throw new Error('K6_BASE_URL must contain a valid hostname');
  }
  if (parts[1]) validatePort(parts[1]);
  const host = parts[0].toLowerCase();
  validateDnsLikeHost(host);
  return host;
}

function allowedHosts() {
  return String(__ENV.K6_ALLOWED_HOSTS || '')
    .split(',')
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
}

const resolvedBaseUrl = baseUrl();
const resolvedTargetHost = hostFromUrl(resolvedBaseUrl);

export const config = Object.freeze({
  baseUrl: resolvedBaseUrl,
  targetHost: resolvedTargetHost,
  targetClass: LOCAL_FIXTURE_HOSTS.has(resolvedTargetHost) ? 'local-fixture' : 'explicit-target',
  allowedHosts: Object.freeze(allowedHosts()),
  runId: correlationToken('K6_RUN_ID', `k6-${Date.now()}`),
  p95Ms: positiveNumber('K6_P95_MS', 500),
  errorRate: boundedRate('K6_ERROR_RATE', 0.01),
  thinkTimeSeconds: nonNegativeNumber('K6_THINK_TIME_SECONDS', 1),
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
