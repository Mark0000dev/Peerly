import type {
  APIResponse,
  Locator,
  Page,
  Request,
  Response,
  Route,
  TestInfo,
} from '@playwright/test';
import { test, expect } from '../../../../../testing/visual';
import { prepareStudyFixture, readStudyFixtureState } from '../../../../../testing/study-fixture';
import type { StudyCohort } from '../../../../../testing/study-fixture';
import type { Api } from '../../../api.generated';
import { isConversation, isHistory } from '../chats-contract';
import { absoluteChatTime } from '../chats-date';
import { isOwnFeedback, isOwnOutcome, isPrompt, isReceipt } from './study-contract';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly target: Readonly<Locator> }>,
  ) => Promise<void>;
}>;
async function actual(response: Readonly<APIResponse | Response>): Promise<unknown> {
  expect(response.status()).toBe(200);
  expect(response.headers()['cache-control']).toContain('no-store');
  const value: unknown = await response.json();
  return value;
}
async function ownOutcome(page: Readonly<Page>, seed: StudyCohort) {
  const value = await actual(
    await page.request.get(`/api/v1/conversations/${seed.conversationId}/study-outcome`),
  );
  if (!isOwnOutcome(value, seed.conversationId)) throw new Error('Invalid actual own outcome');
  return value;
}
async function ownFeedback(page: Readonly<Page>, seed: StudyCohort) {
  const value = await actual(
    await page.request.get(`/api/v1/conversations/${seed.conversationId}/feedback`),
  );
  if (!isOwnFeedback(value, seed.conversationId)) throw new Error('Invalid actual own feedback');
  return value;
}
function current(value: Api['schemas']['OwnFeedbackResponse']) {
  if (value.current === null) throw new Error('Missing actual current feedback');
  return value.current;
}
async function enter(page: Readonly<Page>, seed: StudyCohort) {
  const admission = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/conversations/${seed.conversationId}/study-prompt-visits`) &&
      response.request().method() === 'POST',
  );
  await page.goto(`/chats?conversation=${seed.conversationId}`);
  const value = await actual(await admission);
  if (!isPrompt(value, seed.conversationId)) throw new Error('Invalid actual prompt response');
  await expect(
    page.getByRole('list', { name: 'Confirmed messages' }).getByRole('listitem'),
  ).toHaveCount(seed.messageCount);
  const photos = page.getByRole('img', { name: 'Current chat participant photo', exact: true });
  await expect(photos.first()).toBeVisible();
  for (const photo of await photos.all()) {
    await expect(photo).toHaveJSProperty('complete', true);
    await expect(photo).toHaveJSProperty('naturalWidth', 64);
  }
  const times = page.locator('time');
  await expect(times.first()).toHaveText('Yesterday');
  expect((await times.allTextContents()).every((text) => text.trim() === 'Yesterday')).toBe(true);
  return value;
}
async function manual(page: Readonly<Page>): Promise<void> {
  await page.getByRole('button', { name: 'Study progress', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Study progress', exact: true })).toBeVisible();
}
async function workYes(page: Readonly<Page>): Promise<void> {
  await manual(page);
  await page
    .getByRole('region', { name: 'Study progress', exact: true })
    .getByRole('button', { name: 'Yes', exact: true })
    .click();
  await expect(page.getByRole('heading', { name: 'You said you’ve started' })).toBeVisible();
  await page.getByRole('button', { name: 'Give feedback', exact: true }).click();
  await expect(page.getByText('Would you study together again?')).toBeVisible();
}
async function noPeerLeak(page: Readonly<Page>, seed: StudyCohort): Promise<void> {
  const peer = await seed.readPeerFeedback();
  expect(isOwnFeedback(peer, seed.conversationId)).toBe(true);
  if (!isOwnFeedback(peer, seed.conversationId)) throw new Error('Invalid actual peer projection');
  expect(peer.outcome).toBeNull();
  expect(peer.current).toBeNull();
  const [details, messages] = await Promise.all([
    page.request.get(`/api/v1/conversations/${seed.conversationId}`).then(actual),
    page.request.get(`/api/v1/conversations/${seed.conversationId}/messages`).then(actual),
  ]);
  if (!isConversation(details) || !isHistory(messages)) throw new Error('Invalid actual chat read');
  expect(details.conversation_id).toBe(seed.conversationId);
  expect(details.request_id).toBe(seed.requestId);
  expect(details.read_position).toBeNull();
  expect(messages.messages).toHaveLength(seed.messageCount);
  for (const instant of [
    details.accepted_at,
    ...messages.messages.map((message) => message.sent_at),
  ]) {
    const time = page.locator(`time[datetime="${instant}"]`).first();
    await expect(time).toHaveText('Yesterday');
    await expect(time).toHaveAttribute('title', absoluteChatTime(instant));
  }
}

async function feedbackCheckpoint(
  scenario: Scenario,
  info: Readonly<TestInfo>,
  seed: StudyCohort,
  name: string,
): Promise<void> {
  // Compare the complete feature region. Native chat read-button eligibility
  // follows viewport intersection and has separate Chats coverage.
  // Keep the full screen as an explicitly uncompared diagnostic artifact.
  await noPeerLeak(scenario.page, seed);
  const viewport = scenario.page.viewportSize();
  if (viewport === null) throw new Error('Missing configured viewport');
  expect(
    await scenario.page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(viewport.width);
  await scenario.checkpoint(name, {
    target: scenario.page.getByRole('region', { name: 'Study progress actions', exact: true }),
  });
  await info.attach(`${name.replace(/\.png$/u, '')}-full-page-uncompared`, {
    body: await scenario.page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  });
}

test('F01 real aged pair offers once; dismiss and manual own answer do not rate the peer', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareStudyFixture(page, 'offered', info.project.name);
  const before = await readStudyFixtureState(page, seed.conversationId);
  expect((await ownOutcome(page, seed)).outcome).toBeNull();
  expect((await ownFeedback(page, seed)).current).toBeNull();
  expect(await readStudyFixtureState(page, seed.conversationId)).toEqual(before);
  expect((await enter(page, seed)).outcome).toBe('offered');
  const region = page.getByRole('region', { name: 'Study progress', exact: true });
  await expect(region.getByText('Have you started working on your goal together?')).toBeVisible();
  await checkpoint('real-study-offered.png');
  await region.getByRole('button', { name: 'Dismiss', exact: true }).click();
  await expect(region).toHaveCount(0);
  await checkpoint('real-study-dismissed.png');
  await manual(page);
  await region.getByRole('button', { name: 'Yes', exact: true }).click();
  await expect(region.getByRole('heading', { name: 'You said you’ve started' })).toBeVisible();
  expect((await ownOutcome(page, seed)).outcome).toEqual(
    expect.objectContaining({ answer: 'yes', version: 1, conversation_id: seed.conversationId }),
  );
  expect(await readStudyFixtureState(page, seed.conversationId)).toEqual({
    outcomeVersions: 1,
    feedbackVersions: 0,
    feedbackCurrent: 0,
    promptReceipts: 1,
    canonicalEvents: 2,
  });
  await noPeerLeak(page, seed);
  await checkpoint('real-study-own-yes-no-rating.png');
});

test('F02 real fresh pair no_offer stays manual; eligible feedback updates a single current record', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareStudyFixture(page, 'eligible', info.project.name);
  let acknowledgements = 0;
  page.on('request', (request: Readonly<Request>) => {
    if (
      new URL(request.url()).pathname ===
        `/api/v1/conversations/${seed.conversationId}/read-position` &&
      request.method() === 'PUT'
    )
      acknowledgements += 1;
  });
  expect((await enter(page, seed)).outcome).toBe('no_offer');
  const region = page.getByRole('region', { name: 'Study progress', exact: true });
  await expect(region).toHaveCount(0);
  expect(await readStudyFixtureState(page, seed.conversationId)).toEqual({
    outcomeVersions: 0,
    feedbackVersions: 0,
    feedbackCurrent: 0,
    promptReceipts: 0,
    canonicalEvents: 0,
  });
  await checkpoint('real-study-no-offer.png');
  await workYes(page);
  const projection = await ownFeedback(page, seed);
  expect(projection.can_submit).toBe(true);
  expect(projection.submission_publication).toBe('eligible');
  expect(projection.current).toBeNull();
  await page.getByRole('radio', { name: 'Yes', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Supportive', exact: true }).check();
  await page
    .getByRole('textbox', { name: 'Note for the team · optional' })
    .fill('We compared SQL examples together.');
  await feedbackCheckpoint(
    { page, checkpoint },
    info,
    seed,
    'real-feedback-eligible-draft-study-region.png',
  );
  await page.getByRole('button', { name: 'Save feedback', exact: true }).click();
  await expect(
    page.getByText('It counts once toward the other person’s summary.', { exact: false }),
  ).toBeVisible();
  const first = current(await ownFeedback(page, seed));
  expect(first.version).toBe(1);
  expect(first.again).toBe('yes');
  expect(first.worked_outcome_version).toBe(1);
  expect(first.team_note).toBe('We compared SQL examples together.');
  await feedbackCheckpoint(
    { page, checkpoint },
    info,
    seed,
    'real-feedback-eligible-saved-study-region.png',
  );
  await page.getByRole('button', { name: 'Back to chat', exact: true }).click();
  await manual(page);
  await page.getByRole('button', { name: 'Give feedback', exact: true }).click();
  await expect(page.getByRole('radio', { name: 'Yes', exact: true })).toBeChecked();
  await page.getByRole('radio', { name: 'No', exact: true }).check();
  await page.getByRole('button', { name: 'Update feedback', exact: true }).click();
  await expect(
    page.getByText('It counts once toward the other person’s summary.', { exact: false }),
  ).toBeVisible();
  const updated = current(await ownFeedback(page, seed));
  expect(updated.id).toBe(first.id);
  expect(updated.version).toBe(2);
  expect(updated.again).toBe('no');
  expect(await readStudyFixtureState(page, seed.conversationId)).toEqual({
    outcomeVersions: 1,
    feedbackVersions: 2,
    feedbackCurrent: 1,
    promptReceipts: 0,
    canonicalEvents: 3,
  });
  await noPeerLeak(page, seed);
  await feedbackCheckpoint(
    { page, checkpoint },
    info,
    seed,
    'real-feedback-updated-single-current-study-region.png',
  );
  expect(acknowledgements).toBe(0);
});

test('F02 real one-way conversation accepts team-only feedback without artificial messages', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareStudyFixture(page, 'private', info.project.name);
  expect((await enter(page, seed)).outcome).toBe('no_offer');
  await workYes(page);
  const region = page.getByRole('region', { name: 'Study progress', exact: true });
  const projection = await ownFeedback(page, seed);
  expect(projection.can_submit).toBe(true);
  expect(projection.submission_publication).toBe('private_only');
  await expect(region.getByRole('heading', { name: 'This goes to the team only' })).toBeVisible();
  await page.getByRole('radio', { name: 'Maybe', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Prepared', exact: true }).check();
  await page
    .getByRole('textbox', { name: 'Note for the team · optional' })
    .fill('We studied together away from the app.');
  await checkpoint('real-feedback-private-only-draft.png');
  await page.getByRole('button', { name: 'Send to the team', exact: true }).click();
  await expect(
    region.getByText('It goes to the team only and does not count toward the public summary.'),
  ).toBeVisible();
  const saved = await ownFeedback(page, seed);
  expect(saved.current_publication).toBe('private_only');
  expect(current(saved).captured_public_eligibility).toBe(false);
  expect(await readStudyFixtureState(page, seed.conversationId)).toEqual({
    outcomeVersions: 1,
    feedbackVersions: 1,
    feedbackCurrent: 1,
    promptReceipts: 0,
    canonicalEvents: 2,
  });
  await noPeerLeak(page, seed);
  await checkpoint('real-feedback-private-only-saved.png');
});

test('F02 real committed reply loss retries the exact key once without multiplying revisions or counts', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareStudyFixture(page, 'current', info.project.name);
  const before = await ownFeedback(page, seed);
  const original = current(before);
  expect(original.version).toBe(1);
  expect((await enter(page, seed)).outcome).toBe('no_offer');
  await manual(page);
  await page.getByRole('button', { name: 'Give feedback', exact: true }).click();
  const region = page.getByRole('region', { name: 'Study progress', exact: true });
  await expect(page.getByRole('radio', { name: 'Yes', exact: true })).toBeChecked();
  await expect(page.getByRole('textbox', { name: 'Note for the team · optional' })).toHaveValue(
    'We practised SQL together.',
  );
  await checkpoint('real-feedback-current.png');
  let attempts: readonly Request[] = [];
  let committed: Api['schemas']['FeedbackReceiptResponse'] | undefined;
  let receipts: readonly Api['schemas']['FeedbackReceiptResponse'][] = [];
  await page.route(
    `**/api/v1/conversations/${seed.conversationId}/feedback`,
    async (route: Readonly<Route>) => {
      if (route.request().method() !== 'PUT') {
        await route.fallback();
        return;
      }
      attempts = [...attempts, route.request()];
      const upstream = await route.fetch();
      const body = await actual(upstream);
      if (!isReceipt(body) || body.conversation_id !== seed.conversationId)
        throw new Error('Invalid actual committed receipt');
      receipts = [...receipts, body];
      if (attempts.length === 1) {
        committed = body;
        await route.fulfill({ status: 503, json: { code: 'temporarily_unavailable' } });
      } else {
        await route.fulfill({ response: upstream });
      }
    },
  );
  await page.getByRole('radio', { name: 'Maybe', exact: true }).check();
  await page
    .getByRole('textbox', { name: 'Note for the team · optional' })
    .fill('A replacement note for the team only.');
  await page.getByRole('button', { name: 'Update feedback', exact: true }).click();
  await expect(
    region.getByText('We couldn’t confirm whether this action was saved.', { exact: false }),
  ).toBeVisible();
  expect(await readStudyFixtureState(page, seed.conversationId)).toEqual({
    outcomeVersions: 1,
    feedbackVersions: 2,
    feedbackCurrent: 1,
    promptReceipts: 0,
    canonicalEvents: 3,
  });
  await checkpoint('real-feedback-committed-unknown.png');
  await page.getByRole('button', { name: 'Retry same action', exact: true }).click();
  await expect(
    region.getByText('It counts once toward the other person’s summary.', { exact: false }),
  ).toBeVisible();
  expect(attempts).toHaveLength(2);
  expect(receipts).toEqual([committed, committed]);
  expect(attempts[0]?.headers()['idempotency-key']).toBe(attempts[1]?.headers()['idempotency-key']);
  expect(attempts[0]?.postData()).toBe(attempts[1]?.postData());
  const replayed = current(await ownFeedback(page, seed));
  expect(replayed).toEqual(committed);
  expect(replayed.id).toBe(original.id);
  expect(replayed.version).toBe(2);
  expect(await readStudyFixtureState(page, seed.conversationId)).toEqual({
    outcomeVersions: 1,
    feedbackVersions: 2,
    feedbackCurrent: 1,
    promptReceipts: 0,
    canonicalEvents: 3,
  });
  await noPeerLeak(page, seed);
  await checkpoint('real-feedback-replay-single-current.png');
});
