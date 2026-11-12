import type { Page, Request, Response, TestInfo } from '@playwright/test';
import type { Api } from '../../../../api.generated';
import { test, expect } from '../../../../../../testing/visual';
import { verifyFixtureStudent } from '../../../../../../testing/verified-student';
import { readGoalAiFixtureState } from '../../../../../../testing/goal-ai-fixture';
import { isCatalogue } from '../goal-contract';
import { isGoal, isOwnGoal } from '../../../study-context-contract';
import { isUuid } from './goal-assistance-contract';

interface Scenario {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}
function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function assertDraftRequest(
  request: Readonly<Request>,
  kind: 'clarify_goal' | 'suggest_subject',
  ids: readonly string[],
): void {
  expect(request.method()).toBe('POST');
  const headers = request.headers();
  expect(typeof headers['x-csrf-token'] === 'string').toBe(true);
  expect(typeof headers['idempotency-key'] === 'string').toBe(true);
  const body: unknown = request.postDataJSON();
  if (!record(body) || !record(body['source'])) throw new Error('Missing actual AI draft request');
  expect(body['kind']).toBe(kind);
  expect(body['source']['kind']).toBe('draft');
  expect(isUuid(body['source']['id'])).toBe(true);
  expect(
    typeof body['source']['version'] === 'number' &&
      Number.isSafeInteger(body['source']['version']) &&
      body['source']['version'] >= 1,
  ).toBe(true);
  if (kind === 'clarify_goal') {
    expect(body['target']).toBe('context');
    expect(body['text']).toBe('I want to practise SQL JOINs with NULLs.');
  } else {
    const candidates = body['candidate_ids'];
    expect(Array.isArray(candidates)).toBe(true);
    if (!Array.isArray(candidates)) throw new Error('Missing captured catalogue candidates');
    expect(candidates.length).toBeGreaterThanOrEqual(1);
    expect(candidates.length).toBeLessThanOrEqual(20);
    expect(candidates.every((id: unknown) => typeof id === 'string' && ids.includes(id))).toBe(
      true,
    );
  }
}
async function unavailable(response: Readonly<Response>): Promise<void> {
  expect(response.status()).toBe(503);
  const headers = response.headers();
  expect(headers['location']).toBeUndefined();
  const value: unknown = await response.json();
  if (!record(value)) throw new Error('Invalid actual disabled admission response');
  expect(value['code']).toBe('ai_unavailable');
  expect('id' in value).toBe(false);
}

function verified(value: unknown): void {
  if (!record(value) || !record(value['capabilities']))
    throw new Error('Missing actual verified actor');
  expect(value['account_status']).toBe('active');
  expect(value['membership_status']).toBe('verified');
  expect(value['capabilities']['can_use_student_features']).toBe(false);
}
function catalogueBody(value: unknown): Api['schemas']['SubjectsResponse'] {
  if (!isCatalogue(value)) throw new Error('Malformed actual catalogue');
  return value;
}
function firstChoice(value: Api['schemas']['SubjectsResponse']): Api['schemas']['SubjectResponse'] {
  const first = value.items[0];
  if (first === undefined) throw new Error('Actual fixture has no catalogue choice');
  return first;
}
function savedBody(value: unknown): Api['schemas']['GoalResponse'] {
  if (!isGoal(value)) throw new Error('Malformed actual saved Goal');
  return value;
}
function ownBody(value: unknown): Api['schemas']['OwnGoalResponse'] {
  if (!isOwnGoal(value)) throw new Error('Malformed actual persisted Goal');
  return value;
}

test('G01 real verified preactivation student gets disabled AI admission with zero PostgreSQL jobs and can manually save and reload Goal', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  await verifyFixtureStudent(page, info.project.name, 'goal-ai');
  const identityResponse = await page.request.get('/api/v1/me');
  expect(identityResponse.status()).toBe(200);
  verified(await identityResponse.json());
  expect(await readGoalAiFixtureState(page, info.project.name)).toEqual({ jobs: 0, intents: 0 });
  const catalogueResponse = await page.request.get('/api/v1/subjects?query=&limit=20');
  expect(catalogueResponse.status()).toBe(200);
  const catalogue = catalogueBody(await catalogueResponse.json());
  const choice = firstChoice(catalogue);
  const ids = catalogue.items.map((item) => item.id);
  // Count observable requests only; this does not intercept or fabricate an API response.
  let requestCount = 0;
  page.on('request', (request: Readonly<Request>) => {
    if (new URL(request.url()).pathname === '/api/v1/ai/jobs' && request.method() === 'POST')
      requestCount += 1;
  });
  await page.getByRole('button', { name: 'Your study goal', exact: true }).click();
  await expect(page.getByLabel('Knowledge area', { exact: true })).toHaveValue('');
  await page.getByLabel('Knowledge area', { exact: true }).fill(choice.name);
  await page
    .getByRole('option')
    .filter({ has: page.getByText(choice.name, { exact: true }) })
    .click();
  await page.getByLabel('Task or topic · optional', { exact: true }).fill('SQL JOINs');
  await page
    .getByLabel('Context or module · optional', { exact: true })
    .fill('I want to practise SQL JOINs with NULLs.');
  await expect(
    page.getByRole('button', { name: 'Suggest clearer wording', exact: true }),
  ).toBeEnabled();
  await checkpoint('g01-real-ai-offered-preactivation.png');
  const clarify = page.waitForResponse(
    (response: Readonly<Response>) =>
      response.url().endsWith('/api/v1/ai/jobs') && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Suggest clearer wording', exact: true }).click();
  const clarified = await clarify;
  assertDraftRequest(clarified.request(), 'clarify_goal', ids);
  await unavailable(clarified);
  await expect(
    page.getByText('AI assistance isn’t available right now. You can write and save as usual.', {
      exact: true,
    }),
  ).toBeVisible();
  expect(await readGoalAiFixtureState(page, info.project.name)).toEqual({ jobs: 0, intents: 0 });
  await checkpoint('g01-real-clarify-disabled-no-job.png');
  const suggest = page.waitForResponse(
    (response: Readonly<Response>) =>
      response.url().endsWith('/api/v1/ai/jobs') && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Suggest a knowledge area', exact: true }).click();
  const suggested = await suggest;
  assertDraftRequest(suggested.request(), 'suggest_subject', ids);
  await unavailable(suggested);
  expect(await readGoalAiFixtureState(page, info.project.name)).toEqual({ jobs: 0, intents: 0 });
  await checkpoint('g01-real-area-advice-disabled-no-job.png');
  const saving = page.waitForResponse(
    (response: Readonly<Response>) =>
      response.url().endsWith('/api/v1/me/goal') && response.request().method() === 'PUT',
  );
  await page.getByRole('button', { name: 'Save goal', exact: true }).click();
  const savedResponse = await saving;
  expect(savedResponse.status()).toBe(200);
  const saved = savedBody(await savedResponse.json());
  expect(saved.version).toBe(1);
  expect(saved.subject).toMatchObject({ id: choice.id, label: choice.name });
  expect(saved.context).toBe('I want to practise SQL JOINs with NULLs.');
  expect(saved.topic).toBe('SQL JOINs');
  await expect(
    page.getByText('Goal saved. New requests will use this goal.', { exact: true }),
  ).toBeVisible();
  await checkpoint('g01-real-manual-goal-saved-after-disabled-ai.png');
  await page.reload();
  await page.getByRole('button', { name: 'Your study goal', exact: true }).click();
  await expect(page.getByLabel('Knowledge area', { exact: true })).toHaveValue(choice.name);
  await expect(page.getByLabel('Context or module · optional', { exact: true })).toHaveValue(
    'I want to practise SQL JOINs with NULLs.',
  );
  const reloadedResponse = await page.request.get('/api/v1/me/goal');
  expect(reloadedResponse.status()).toBe(200);
  const reloaded = ownBody(await reloadedResponse.json());
  expect(reloaded.goal).toEqual(saved);
  expect(requestCount).toBe(2);
  expect(await readGoalAiFixtureState(page, info.project.name)).toEqual({ jobs: 0, intents: 0 });
  await checkpoint('g01-real-manual-goal-reloaded-no-ai-job.png');
});
