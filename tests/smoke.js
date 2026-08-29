import exec from 'k6/execution';
import { check, group, sleep } from 'k6';
import { config } from '../lib/config.js';
import { getJson } from '../lib/client.js';
import { handleSummary } from '../lib/summary.js';
import { sloThresholds } from '../lib/thresholds.js';

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
  thresholds: sloThresholds({
    checksRate: 0.99,
    errorRate: config.errorRate,
    p95Ms: Math.max(config.p95Ms, 1000),
    includeBusinessFailures: false,
    includeDroppedIterations: false,
  }),
};

export function setup() {
  const { body, passed } = getJson('/health', 'setup_health', {
    tags: { phase: 'setup' },
  });
  if (!passed || body?.status !== 'ok') {
    throw new Error('smoke setup health contract failed');
  }
  return Object.freeze({ expectedPostId: 1 });
}

export default function (data) {
  const tags = {
    scenario: exec.scenario.name,
    operation: 'read_post',
  };

  group('read post contract', () => {
    const { body, passed } = getJson('/posts/1', 'get_post', { tags });
    const execution = {
      body,
      passed,
      scenario: exec.scenario.name,
      vuId: exec.vu.idInTest,
      iteration: exec.scenario.iterationInTest,
    };

    check(
      execution,
      {
        'transport and JSON contract passed': (value) => value.passed,
        'post id matches setup data': (value) => value.body?.id === data.expectedPostId,
        'execution context identifies smoke scenario': (value) => value.scenario === 'smoke',
        'execution context exposes positive VU id': (value) => value.vuId >= 1,
        'execution context exposes iteration index': (value) => value.iteration >= 0,
      },
      tags
    );
  });

  sleep(0.2);
}

export function teardown(data) {
  const { body, passed } = getJson('/health', 'teardown_health', {
    tags: { phase: 'teardown' },
  });
  if (!passed || body?.status !== 'ok' || data.expectedPostId !== 1) {
    throw new Error('smoke teardown health contract failed');
  }
}
