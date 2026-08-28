import http from 'k6/http';
import { check } from 'k6';
import { config } from './config.js';
import { businessDuration, businessFailures } from './metrics.js';

function parseJson(response) {
  try {
    return response.json();
  } catch (_) {
    return null;
  }
}

export function getJson(path, endpoint) {
  const response = http.get(`${config.baseUrl}${path}`, {
    headers: {
      Accept: 'application/json',
      'X-Test-Run-Id': config.runId,
    },
    tags: { endpoint },
    timeout: '15s',
  });

  const body = parseJson(response);
  const passed = check(response, {
    [`${endpoint}: status 200`]: (r) => r.status === 200,
    [`${endpoint}: json content type`]: (r) => /application\/json/i.test(r.headers['Content-Type'] || ''),
    [`${endpoint}: parseable json`]: () => body !== null,
  }, { endpoint });

  businessFailures.add(!passed, { endpoint });
  businessDuration.add(response.timings.duration, { endpoint });
  return { response, body };
}
