/**
 * Load test script using k6.
 * I use staged load to simulate ramp‑up, steady state and ramp‑down.
 * The checks validate HTTP status codes and response structure.
 */
import http from 'k6/http';
import { sleep, check } from 'k6';

export let options = {
  stages: [
    { duration: '30s', target: 20 }, // ramp up to 20 virtual users
    { duration: '1m', target: 20 },  // stay at 20 users
    { duration: '30s', target: 0 },  // ramp down to 0
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'], // 95% of requests should be below 500ms
    http_req_failed: ['rate<0.01'],   // error rate should be below 1%
  },
};

const BASE_URL = 'https://jsonplaceholder.typicode.com';

export default function () {
  const res = http.get(`${BASE_URL}/posts`);
  check(res, {
    'status is 200': (r) => r.status === 200,
    'content is array': (r) => Array.isArray(r.json()),
  });
  sleep(1);
}
