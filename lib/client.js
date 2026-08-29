import http from 'k6/http';
import { check } from 'k6';
import { config } from './config.js';
import {
  businessAttempts,
  businessDuration,
  businessFailures,
  businessSuccess,
} from './metrics.js';

function parseJson(response) {
  try {
    return response.json();
  } catch (_) {
    return null;
  }
}

export function getJson(path, endpoint, { expectedStatus = 200, tags = {} } = {}) {
  const metricTags = { ...tags, endpoint };
  businessAttempts.add(1, metricTags);

  const response = http.get(`${config.baseUrl}${path}`, {
    headers: {
      Accept: 'application/json',
      'X-Test-Run-Id': config.runId,
    },
    tags: metricTags,
    timeout: '15s',
  });

  const body = parseJson(response);
  const passed = check(
    response,
    {
      [`${endpoint}: status ${expectedStatus}`]: (r) => r.status === expectedStatus,
      [`${endpoint}: json content type`]: (r) =>
        /application\/json/i.test(r.headers['Content-Type'] || ''),
      [`${endpoint}: parseable json`]: () => body !== null,
    },
    metricTags
  );

  businessFailures.add(!passed, metricTags);
  businessSuccess.add(passed, metricTags);
  businessDuration.add(response.timings.duration, metricTags);
  return { response, body, passed };
}
