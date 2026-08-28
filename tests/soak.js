import { sleep } from 'k6';
import { config, requireLoadAuthorization } from '../lib/config.js';
import { getJson } from '../lib/client.js';
import { handleSummary } from '../lib/summary.js';
import { sloThresholds } from '../lib/thresholds.js';

requireLoadAuthorization('soak profile');
export { handleSummary };

const duration = __ENV.K6_SOAK_DURATION || '10m';

export const options = {
  scenarios: {
    soak: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.K6_SOAK_RATE || 5),
      timeUnit: '1s',
      duration,
      preAllocatedVUs: 10,
      maxVUs: 50,
      gracefulStop: '30s',
      tags: { profile: 'soak' },
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
