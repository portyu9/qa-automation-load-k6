/**
 * Smoke test script for k6. I use this to perform a quick
 * sanity check against the JSONPlaceholder API, verifying that
 * a single post returns status 200 and has the expected id.
 */

import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 1,
  iterations: 1,
};

const BASE_URL = 'https://jsonplaceholder.typicode.com';

export default function () {
  const res = http.get(`${BASE_URL}/posts/1`);
  check(res, {
    'status is 200': (r) => r.status === 200,
    'post id is 1': (r) => JSON.parse(r.body).id === 1,
  });
}
