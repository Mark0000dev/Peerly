import type { Page } from '@playwright/test';
import { expect } from './visual';

// Driver-only loopback projection from the real isolated PostgreSQL fixture.
export async function readGoalAiFixtureState(
  page: Readonly<Page>,
  project: string,
): Promise<Readonly<{ readonly jobs: number; readonly intents: number }>> {
  const response = await page.request.get(
    `http://127.0.0.1:8768/__fixture/goal-ai/state/${encodeURIComponent(project)}`,
  );
  expect(response.status()).toBe(200);
  const value: unknown = await response.json();
  if (
    typeof value !== 'object' ||
    value === null ||
    !('jobs' in value) ||
    typeof value.jobs !== 'number' ||
    !Number.isSafeInteger(value.jobs) ||
    value.jobs < 0 ||
    !('intents' in value) ||
    typeof value.intents !== 'number' ||
    !Number.isSafeInteger(value.intents) ||
    value.intents < 0
  )
    throw new Error('Invalid real AI admission projection');
  return { jobs: value.jobs, intents: value.intents };
}
