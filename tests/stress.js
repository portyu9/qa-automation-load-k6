import { sleep } from 'k6';
import { config, requireLoadAuthorization } from '../lib/config.js';
import { getJson } from '../lib/client.js';
import { handleSummary } from '../lib/summary.js';

requireLoadAuthorization('stress profile');
export { handleSummary };

export const options = {
  scenarios: {
    stress: {
      executor: 'ramping-arrival-rate',
      startRate: 2,
      timeUnit: '1s',
      preAllocatedVUs: 20,
      maxVUs: 100,
      stages: [
        { duration: '30s', target: 10 },
        { duration: '30s', target: 20 },
        { duration: '30s', target: 30 },
        { duration: '30s', target: 0 },
      ],
      gracefulStop: '30s',
      tags: { profile: 'stress' },
    },
  },
  thresholds: {
    checks: ['rate>0.97'],
    http_req_failed: ['rate<0.03'],
    http_req_duration: [`p(95)<${Math.max(config.p95Ms * 2, 1000)}`],
    business_failures: ['rate<0.03'],
  },
};

export default function () {
  getJson('/posts', 'list_posts');
  sleep(Math.max(config.thinkTimeSeconds / 2, 0.1));
}
