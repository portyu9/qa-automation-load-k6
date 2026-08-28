import { sleep } from 'k6';
import { config, requireLoadAuthorization } from '../lib/config.js';
import { getJson } from '../lib/client.js';
import { handleSummary } from '../lib/summary.js';
import { sloThresholds } from '../lib/thresholds.js';

requireLoadAuthorization('load profile');
export { handleSummary };

export const options = {
  scenarios: {
    load: {
      executor: 'ramping-arrival-rate',
      startRate: 2,
      timeUnit: '1s',
      preAllocatedVUs: 10,
      maxVUs: 50,
      stages: [
        { duration: '30s', target: 5 },
        { duration: '1m', target: 10 },
        { duration: '30s', target: 0 },
      ],
      gracefulStop: '30s',
      tags: { profile: 'load' },
    },
  },
  thresholds: sloThresholds({
    errorRate: config.errorRate,
    p95Ms: config.p95Ms,
  }),
};

export default function () {
  getJson('/posts', 'list_posts');
  sleep(config.thinkTimeSeconds);
}
