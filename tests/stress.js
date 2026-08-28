import { sleep } from 'k6';
import { config, requireLoadAuthorization } from '../lib/config.js';
import { getJson } from '../lib/client.js';
import { handleSummary } from '../lib/summary.js';
import { sloThresholds } from '../lib/thresholds.js';

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
  thresholds: sloThresholds({
    checksRate: 0.97,
    errorRate: 0.03,
    p95Ms: Math.max(config.p95Ms * 2, 1000),
    includeDroppedIterations: false,
  }),
};

export default function () {
  getJson('/posts', 'list_posts');
  sleep(Math.max(config.thinkTimeSeconds / 2, 0.1));
}
