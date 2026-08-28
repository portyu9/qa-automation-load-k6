import { sleep } from 'k6';
import { config } from '../lib/config.js';
import { getJson } from '../lib/client.js';
import { handleSummary } from '../lib/summary.js';

export { handleSummary };

export const options = {
  scenarios: {
    smoke: {
      executor: 'shared-iterations',
      vus: 1,
      iterations: 3,
      maxDuration: '30s',
      gracefulStop: '5s',
      tags: { profile: 'smoke' },
    },
  },
  thresholds: {
    checks: ['rate>0.99'],
    http_req_failed: [`rate<${config.errorRate}`],
    http_req_duration: [`p(95)<${Math.max(config.p95Ms, 1000)}`],
  },
};

export default function () {
  const { body } = getJson('/posts/1', 'get_post');
  if (body && body.id !== 1) {
    throw new Error(`unexpected post id: ${body.id}`);
  }
  sleep(0.2);
}
