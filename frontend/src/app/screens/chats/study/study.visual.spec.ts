import { assertNaturalWordWrapping } from '../../../../../testing/readable-text';
import type { Locator, Page, Request, Route, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../../testing/visual';
import type { Api } from '../../../api.generated';
import { conversation, history, identity, page as conversations, shares } from '../chats.fixtures';
import { isOutcome, isReceipt } from './study-contract';
import { offered, outcome, ownFeedback, receipt } from './study.fixtures';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?:
      Readonly<{ readonly target: Readonly<Locator> }> | Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}>;

const base = `/api/v1/conversations/${conversation.conversation_id}`;
async function setup(
  page: Readonly<Page>,
  initial: Api['schemas']['OwnFeedbackResponse'] = ownFeedback,
) {
  let current = initial;
  let ownOutcome: Api['schemas']['StudyOutcomeResponse'] | null = initial.outcome;
  let writes: readonly Request[] = [];
  await page.clock.setFixedTime(new Date('2026-11-08T06:20:00Z'));
  await page.route('**/api/v1/me', (route: Readonly<Route>) => route.fulfill({ json: identity }));
  await page.route(/\/api\/v1\/conversations(?:\?.*)?$/, (route: Readonly<Route>) =>
    route.fulfill({ json: conversations }),
  );
  await page.route(`**${base}`, (route: Readonly<Route>) => route.fulfill({ json: conversation }));
  await page.route(`**${base}/image-preparations`, (route: Readonly<Route>) =>
    route.fulfill({ json: { preparations: [] } }),
  );
  await page.route(`**${base}/messages*`, (route: Readonly<Route>) =>
    route.fulfill({ json: history }),
  );
  await page.route(`**${base}/goal-shares*`, (route: Readonly<Route>) =>
    route.fulfill({ json: shares }),
  );
  await page.route(`**${base}/study-prompt-visits`, (route: Readonly<Route>) => {
    writes = [...writes, route.request()];
    return route.fulfill({ json: { outcome: 'no_offer' } });
  });
  await page.route(`**${base}/study-outcome`, async (route: Readonly<Route>) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { outcome: ownOutcome } });
    writes = [...writes, route.request()];
    const body: unknown = route.request().postDataJSON();
    if (
      typeof body !== 'object' ||
      body === null ||
      !('answer' in body) ||
      !('expected_version' in body) ||
      typeof body.expected_version !== 'number'
    )
      throw new Error('Invalid outcome write');
    const saved: unknown = { ...outcome, answer: body.answer, version: body.expected_version + 1 };
    if (!isOutcome(saved)) throw new Error('Invalid outcome body');
    ownOutcome = saved;
    current = { ...current, outcome: saved };
    return route.fulfill({ json: saved });
  });
  await page.route(`**${base}/feedback`, async (route: Readonly<Route>) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: current });
    writes = [...writes, route.request()];
    const body: unknown = route.request().postDataJSON();
    if (
      typeof body !== 'object' ||
      body === null ||
      !('expected_version' in body) ||
      typeof body.expected_version !== 'number'
    )
      throw new Error('Invalid feedback write');
    const saved: unknown = { ...receipt, ...body, version: body.expected_version + 1 };
    if (!isReceipt(saved)) throw new Error('Invalid feedback body');
    current = { ...current, current: saved, current_publication: current.submission_publication };
    return route.fulfill({ json: saved });
  });
  return () => writes;
}
async function open(page: Readonly<Page>): Promise<void> {
  await page.goto(`/chats?conversation=${conversation.conversation_id}`);
  await page.getByRole('button', { name: 'Study progress', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Study progress', exact: true })).toBeVisible();
}
async function feedback(page: Readonly<Page>): Promise<void> {
  await open(page);
  await page.getByRole('button', { name: 'Give feedback', exact: true }).click();
}
function releaseHeldFeedback(release: (() => void) | undefined): void {
  if (release === undefined) throw new Error('Missing held feedback response');
  release();
}
async function checkpointStudy(
  scenario: Scenario,
  info: Readonly<TestInfo>,
  name: string,
): Promise<void> {
  const viewport = scenario.page.viewportSize();
  if (viewport === null) throw new Error('Missing configured study viewport');
  expect(
    await scenario.page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(viewport.width);
  const dialog = scenario.page.getByRole('dialog');
  await scenario.checkpoint(
    name,
    (await dialog.isVisible())
      ? { fullPage: false }
      : {
          target: scenario.page.getByRole('region', {
            name: 'Study progress actions',
            exact: true,
          }),
        },
  );
  await info.attach(`${name.replace(/\.png$/u, '')}-full-page-uncompared`, {
    body: await scenario.page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  });
}

test('F01/F02 loading reads stay read-only and expose accessible progress', async ({
  page,
  checkpoint,
}: Scenario) => {
  const writes = await setup(page);
  let releaseOutcome: (() => void) | undefined;
  const outcomeReady = new Promise<void>((resolve) => {
    releaseOutcome = resolve;
  });
  await page.route(`**${base}/study-outcome`, async (route: Readonly<Route>) => {
    await outcomeReady;
    await route.fulfill({ json: { outcome } });
  });
  await open(page);
  await expect(page.getByText('Loading study progress…')).toBeVisible();
  await checkpoint('f01-loading.png');
  releaseOutcome?.();
  await expect(page.getByRole('heading', { name: 'You said you’ve started' })).toBeVisible();
  let releaseFeedback: (() => void) | undefined;
  const feedbackReady = new Promise<void>((resolve) => {
    releaseFeedback = resolve;
  });
  await page.route(`**${base}/feedback`, async (route: Readonly<Route>) => {
    await feedbackReady;
    await route.fulfill({ json: ownFeedback });
  });
  await page.getByRole('button', { name: 'Give feedback', exact: true }).click();
  await expect(page.getByText('Loading your feedback…')).toBeVisible();
  await checkpoint('f02-loading.png', { fullPage: false });
  releaseFeedback?.();
  await expect(page.getByText('Would you study together again?')).toBeVisible();
  expect(writes().filter((value: Readonly<Request>) => value.method() === 'PUT')).toHaveLength(0);
  await checkpoint('f02-loaded-no-write.png', { fullPage: false });
});

test('F01 manual read, dismiss and reopen never write an answer', async ({
  page,
  checkpoint,
}: Scenario) => {
  const writes = await setup(page);
  await open(page);
  await expect(page.getByRole('heading', { name: 'You said you’ve started' })).toBeVisible();
  await checkpoint('f01-manual-current.png');
  await page.getByRole('button', { name: 'Dismiss', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Study progress', exact: true })).toHaveCount(0);
  await checkpoint('f01-dismissed.png');
  await page.getByRole('button', { name: 'Study progress', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'You said you’ve started' })).toBeVisible();
  expect(
    writes().filter((value: Readonly<Request>) => !value.url().endsWith('/study-prompt-visits')),
  ).toHaveLength(0);
  await checkpoint('f01-manual-reopen.png');
});

test('F01 offered inline check-in does not take composer focus and records each own answer', async ({
  page,
  checkpoint,
}: Scenario) => {
  let messageWrites = 0;
  page.on('request', (request: Readonly<Request>) => {
    if (request.method() === 'POST' && request.url().endsWith(`${base}/messages`))
      messageWrites += 1;
  });
  await setup(page, { ...ownFeedback, current: null, outcome: null });
  let release: (() => void) | undefined;
  const admission = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(`**${base}/study-prompt-visits`, async (route: Readonly<Route>) => {
    await admission;
    await route.fulfill({ json: offered });
  });
  await page.goto(`/chats?conversation=${conversation.conversation_id}`);
  const composer = page.getByRole('textbox', { name: 'Message', exact: true });
  await composer.focus();
  release?.();
  const region = page.getByRole('region', { name: 'Study progress', exact: true });
  await expect(region.getByText('Have you started working on your goal together?')).toBeVisible();
  await expect(composer).toBeFocused();
  await expect(region.getByRole('button', { name: 'Yes', exact: true })).not.toBeFocused();
  await checkpoint('f01-offered.png');
  for (const answer of ['Not yet', 'It didn’t work out', 'Yes']) {
    await region.getByRole('button', { name: answer, exact: true }).click();
    await expect(
      region.getByRole('heading', {
        name:
          answer === 'Yes'
            ? 'You said you’ve started'
            : answer === 'Not yet'
              ? 'Got it'
              : 'Thanks for letting us know',
      }),
    ).toBeVisible();
    await expect(page.getByRole('region', { name: 'Message composer' })).not.toContainText(
      'Enter a message.',
    );
    await checkpoint(
      `f01-answer-${answer === 'Yes' ? 'yes' : answer === 'Not yet' ? 'not-yet' : 'did-not-work-out'}.png`,
    );
  }
  expect(messageWrites).toBe(0);
});

test('F02 current feedback draft updates one record and displays eligible saved receipt', async ({
  page,
  checkpoint,
}: Scenario) => {
  const writes = await setup(page);
  await feedback(page);
  await expect(page.getByRole('radio', { name: 'Maybe', exact: true })).toBeChecked();
  await expect(page.getByRole('textbox', { name: 'Note for the team · optional' })).toHaveValue(
    receipt.team_note ?? '',
  );
  await checkpoint('f02-current.png', { fullPage: false });
  await page.getByRole('radio', { name: 'No', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Prepared', exact: true }).check();
  await page
    .getByRole('textbox', { name: 'Note for the team · optional' })
    .fill('Team-only note: met in the library.');
  await checkpoint('f02-edited.png', { fullPage: false });
  await page.getByRole('button', { name: 'Update feedback', exact: true }).click();
  await expect(
    page.getByText('It counts once toward the other person’s summary.', { exact: false }),
  ).toBeVisible();
  expect(
    writes().filter((value: Readonly<Request>) => value.url().endsWith('/feedback')),
  ).toHaveLength(1);
  await checkpoint('f02-saved-eligible.png', { fullPage: false });
});

test('F02 private-only and removed publication stay server-owned', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page, {
    ...ownFeedback,
    current_publication: 'removed',
    submission_publication: 'private_only',
  });
  await feedback(page);
  await expect(
    page.getByText('Your current feedback has been removed from the public summary.'),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'This goes to the team only' })).toBeVisible();
  await checkpoint('f02-removed-private-only.png', { fullPage: false });
  await page.getByRole('button', { name: 'Update feedback', exact: true }).click();
  await expect(
    page.getByText('It goes to the team only and does not count toward the public summary.'),
  ).toBeVisible();
  await checkpoint('f02-saved-private-only.png', { fullPage: false });
});

test('F02 new feedback validates required choice and note without speculative writes', async ({
  page,
  checkpoint,
}: Scenario) => {
  const writes = await setup(page, { ...ownFeedback, current: null, current_publication: null });
  await feedback(page);
  await page.getByRole('button', { name: 'Save feedback', exact: true }).click();
  await expect(page.getByText('Choose Yes, Maybe or No.')).toBeVisible();
  await checkpoint('f02-required.png', { fullPage: false });
  await page.getByRole('radio', { name: 'Yes', exact: true }).check();
  await page.getByRole('textbox', { name: 'Note for the team · optional' }).fill('x'.repeat(1001));
  await page.getByRole('button', { name: 'Save feedback', exact: true }).click();
  await expect(page.getByText('Keep your note within 1,000 characters.')).toBeVisible();
  expect(writes().filter((value: Readonly<Request>) => value.method() === 'PUT')).toHaveLength(0);
  await checkpoint('f02-note-validation.png', { fullPage: false });
});

test('F02 unknown network result preserves immutable intent and explicit retry', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let attempts: readonly Request[] = [];
  await page.route(`**${base}/feedback`, async (route: Readonly<Route>) => {
    if (route.request().method() === 'GET') return route.fallback();
    attempts = [...attempts, route.request()];
    if (attempts.length === 1) return route.abort('failed');
    return route.fulfill({ json: receipt });
  });
  await feedback(page);
  await page.getByRole('button', { name: 'Update feedback', exact: true }).click();
  await expect(
    page.getByText('We couldn’t confirm whether this action was saved.', { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Note for the team · optional' })).toHaveAttribute(
    'readonly',
    '',
  );
  await checkpoint('f02-unknown.png', { fullPage: false });
  await page.getByRole('button', { name: 'Retry same action', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Thanks, your feedback is saved' })).toBeVisible();
  expect(attempts).toHaveLength(2);
  expect(attempts[0]?.postData()).toBe(attempts[1]?.postData());
  expect(attempts[0]?.headers()['idempotency-key']).toBe(attempts[1]?.headers()['idempotency-key']);
  await checkpoint('f02-unknown-retried.png', { fullPage: false });
});

for (const code of ['feedback_version_conflict', 'worked_confirmation_required']) {
  test(`F02 ${code} retains draft until explicit recovery`, async ({
    page,
    checkpoint,
  }: Scenario) => {
    await setup(page);
    await page.route(`**${base}/feedback`, (route: Readonly<Route>) =>
      route.request().method() === 'GET'
        ? route.fallback()
        : route.fulfill({ status: 409, json: { code } }),
    );
    await feedback(page);
    await page
      .getByRole('textbox', { name: 'Note for the team · optional' })
      .fill('Keep this private draft');
    await page.getByRole('button', { name: 'Update feedback', exact: true }).click();
    await expect(page.getByText('Your draft is kept.', { exact: false })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Update feedback', exact: true })).toBeDisabled();
    await checkpoint(`f02-${code}.png`, { fullPage: false });
    await page.getByRole('button', { name: 'Reload current record', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Update feedback', exact: true })).toBeEnabled();
    await expect(page.getByRole('textbox', { name: 'Note for the team · optional' })).toHaveValue(
      'Keep this private draft',
    );
    await checkpoint(`f02-${code}-recovered.png`, { fullPage: false });
  });
}

test('F02 real worked confirmation is separate from feedback submission', async ({
  page,
  checkpoint,
}: Scenario) => {
  const writes = await setup(page);
  await open(page);
  await page.route(`**${base}/feedback`, (route: Readonly<Route>) =>
    route.fulfill({ json: { ...ownFeedback, outcome: null, current: null } }),
  );
  await page.getByRole('button', { name: 'Give feedback', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Have you worked on your study goal together?' }),
  ).toBeVisible();
  await checkpoint('f02-confirmation.png', { fullPage: false });
  await page.unroute(`**${base}/feedback`);
  await page.route(`**${base}/feedback`, (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...ownFeedback,
        outcome: { ...outcome, version: 4 },
        current: null,
        current_publication: null,
      },
    }),
  );
  await page.getByRole('button', { name: 'Yes, we worked together', exact: true }).click();
  await expect(page.getByText('Would you study together again?')).toBeVisible();
  expect(writes().filter((value: Readonly<Request>) => value.method() === 'PUT')).toHaveLength(1);
  await checkpoint('f02-confirmed-no-auto-feedback.png', { fullPage: false });
});

test('F01 no_offer leaves the actual chat available without check-in or answer writes', async ({
  page,
  checkpoint,
}: Scenario) => {
  const writes = await setup(page);
  await page.goto(`/chats?conversation=${conversation.conversation_id}`);
  await expect(page.getByRole('button', { name: 'Study progress', exact: true })).toBeEnabled();
  await expect
    .poll(
      () =>
        writes().filter((value: Readonly<Request>) => value.url().endsWith('/study-prompt-visits'))
          .length,
    )
    .toBe(1);
  await expect(page.getByRole('region', { name: 'Study progress', exact: true })).toHaveCount(0);
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toBeVisible();
  expect(writes().filter((value: Readonly<Request>) => value.method() === 'PUT')).toHaveLength(0);
  await checkpoint('f01-no-offer-chat.png');
});

test('F02 can_submit false never renders or submits a rating', async ({
  page,
  checkpoint,
}: Scenario) => {
  const writes = await setup(page, { ...ownFeedback, can_submit: false });
  await feedback(page);
  await expect(
    page.getByText('Feedback is unavailable for this conversation right now.'),
  ).toBeVisible();
  await expect(page.getByRole('radio')).toHaveCount(0);
  expect(writes().filter((value: Readonly<Request>) => value.method() === 'PUT')).toHaveLength(0);
  await checkpoint('f02-submit-unavailable.png', { fullPage: false });
});

for (const status of [401, 403]) {
  test(`F02 ${String(status)} delegates canonical session recovery and retires private answers`, async ({
    page,
    checkpoint,
  }: Scenario) => {
    await setup(page);
    await open(page);
    await page.route('**/api/v1/me', (route: Readonly<Route>) =>
      route.fulfill({ status: 401, json: { code: 'unauthenticated' } }),
    );
    await page.route(`**${base}/feedback`, (route: Readonly<Route>) =>
      route.fulfill({ status, json: { code: 'unavailable' } }),
    );
    await page.getByRole('button', { name: 'Give feedback', exact: true }).click();
    await expect(
      page.getByText('Sign in with an eligible student account to view chats.'),
    ).toBeVisible();
    await expect(page.getByRole('region', { name: 'Study progress', exact: true })).toHaveCount(0);
    await expect(page.getByRole('textbox', { name: 'Note for the team · optional' })).toHaveCount(
      0,
    );
    await checkpoint(`f02-session-${String(status)}-retired.png`, { fullPage: false });
  });
}

for (const status of [404, 422, 503]) {
  test(`F01 actual ${String(status)} read failure and explicit recovery`, async ({
    page,
    checkpoint,
  }: Scenario) => {
    await setup(page);
    await page.route(`**${base}/study-outcome`, (route: Readonly<Route>) =>
      route.fulfill({ status, json: { code: 'unavailable' } }),
    );
    await open(page);
    await expect(
      page.getByRole('region', { name: 'Study progress', exact: true }).getByRole('alert'),
    ).toBeVisible();
    await checkpoint(`f01-read-${String(status)}.png`);
    await page.unroute(`**${base}/study-outcome`);
    await page.route(`**${base}/study-outcome`, (route: Readonly<Route>) =>
      route.fulfill({ json: { outcome } }),
    );
    await page.getByRole('button', { name: 'Reload current record', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'You said you’ve started' })).toBeVisible();
    await checkpoint(`f01-read-${String(status)}-recovered.png`);
  });
}

test('F02 initial 320px / 200% text, reduced motion and keyboard controls remain usable', async ({
  page,
  checkpoint,
}: Scenario) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      document.documentElement.style.setProperty('font-size', '200%');
    });
  });
  await setup(page);
  await feedback(page);
  await page.getByRole('radio', { name: 'Maybe', exact: true }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('radio', { name: 'No', exact: true })).toBeChecked();
  for (const label of ['Easy to communicate', 'Prepared', 'Supportive']) {
    await page.keyboard.press('Tab');
    await expect(page.getByRole('checkbox', { name: label, exact: true })).toBeFocused();
  }
  await page.keyboard.press('Tab');
  await expect(page.getByRole('textbox', { name: 'Note for the team · optional' })).toBeFocused();
  await page.keyboard.press('ControlOrMeta+A');
  await page.keyboard.type('Keyboard draft');
  const note = page.getByRole('textbox', { name: 'Note for the team · optional' });
  await expect(note).toHaveValue('Keyboard draft');
  await expect(note).toBeInViewport({ ratio: 1 });
  const heading = page.getByRole('heading', { name: 'Feedback', exact: true });
  await expect(heading).toBeInViewport({ ratio: 1 });
  await assertNaturalWordWrapping(heading);
  await expect(page.getByRole('dialog', { name: 'Feedback', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Update feedback', exact: true })).toBeInViewport({
    ratio: 1,
  });
  expect(page.viewportSize()?.width).toBe(320);
  const geometry = await page.evaluate(
    (limit: number) => ({
      viewport: innerWidth,
      scrollX,
      width: document.documentElement.scrollWidth,
      overflowing: Array.from(document.querySelectorAll('body *'))
        .map((element: Readonly<Element>) => ({
          tag: element.tagName,
          classes: element.getAttribute('class'),
          left: element.getBoundingClientRect().left + scrollX,
          right: element.getBoundingClientRect().right + scrollX,
        }))
        .filter(
          (element: Readonly<{ readonly left: number; readonly right: number }>) =>
            element.left < 0 || element.right > limit,
        ),
    }),
    320,
  );
  expect(geometry.width, JSON.stringify(geometry)).toBeLessThanOrEqual(320);
  const clippedButtons = await page
    .getByRole('button')
    .evaluateAll((buttons: readonly Readonly<Element>[]) =>
      buttons
        .filter((button: Readonly<Element>) => button.scrollWidth > button.clientWidth)
        .map((button: Readonly<Element>) => ({
          label: button.textContent.trim(),
          width: button.clientWidth,
          content: button.scrollWidth,
        })),
    );
  expect(clippedButtons).toEqual([]);
  await checkpoint('f02-initial320-text200-keyboard.png', { fullPage: false });
});

test('F01/F02 Close keeps late outcome, feedback and admission receipts from reopening UI', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  const region = page.getByRole('region', { name: 'Study progress', exact: true });
  const drain = async (): Promise<void> => {
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() =>
            requestAnimationFrame(() => {
              resolve();
            }),
          ),
        ),
    );
  };
  let releaseOutcome: (() => void) | undefined;
  const outcomeReady = new Promise<void>((resolve) => {
    releaseOutcome = resolve;
  });
  await page.route(`**${base}/study-outcome`, async (route: Readonly<Route>) => {
    if (route.request().method() === 'PUT') await outcomeReady;
    await route.fallback();
  });
  await open(page);
  const outcomeResponse = page.waitForResponse(
    (value) => value.url().endsWith('/study-outcome') && value.request().method() === 'PUT',
  );
  await region.getByRole('button', { name: 'Not yet', exact: true }).click();
  await expect(region.getByText('Saving study progress…')).toBeVisible();
  await checkpoint('f01-saving-before-close.png');
  await region.getByRole('button', { name: 'Close', exact: true }).click();
  releaseOutcome?.();
  expect((await outcomeResponse).status()).toBe(200);
  await drain();
  await expect(region).toHaveCount(0);
  await checkpoint('f01-closed-after-late-outcome.png');

  await page.getByRole('button', { name: 'Study progress', exact: true }).click();
  await expect(region.getByRole('heading', { name: 'Got it' })).toBeVisible();
  await region.getByRole('button', { name: 'Yes', exact: true }).click();
  await expect(region.getByRole('heading', { name: 'You said you’ve started' })).toBeVisible();
  await region.getByRole('button', { name: 'Give feedback', exact: true }).click();
  await expect(region.getByRole('button', { name: 'Update feedback', exact: true })).toBeVisible();
  let releaseFeedback: (() => void) | undefined;
  const feedbackReady = new Promise<void>((resolve) => {
    releaseFeedback = resolve;
  });
  await page.route(`**${base}/feedback`, async (route: Readonly<Route>) => {
    if (route.request().method() === 'PUT') await feedbackReady;
    await route.fallback();
  });
  const feedbackResponse = page.waitForResponse(
    (value) => value.url().endsWith('/feedback') && value.request().method() === 'PUT',
  );
  await region.getByRole('button', { name: 'Update feedback', exact: true }).click();
  await expect(region.getByText('Saving study progress…')).toBeVisible();
  await checkpoint('f02-saving-before-close.png', { fullPage: false });
  await region.getByRole('button', { name: 'Close', exact: true }).click();
  releaseFeedback?.();
  expect((await feedbackResponse).status()).toBe(200);
  await drain();
  await expect(region).toHaveCount(0);
  await checkpoint('f02-closed-after-late-feedback.png', { fullPage: false });

  let releaseOffer: (() => void) | undefined;
  const offerReady = new Promise<void>((resolve) => {
    releaseOffer = resolve;
  });
  await page.route(`**${base}/study-prompt-visits`, async (route: Readonly<Route>) => {
    await offerReady;
    await route.fulfill({ json: offered });
  });
  const offerResponse = page.waitForResponse((value) =>
    value.url().endsWith('/study-prompt-visits'),
  );
  await page.reload();
  await page.getByRole('button', { name: 'Study progress', exact: true }).click();
  await expect(region.getByRole('button', { name: 'Dismiss', exact: true })).toBeVisible();
  await region.getByRole('button', { name: 'Dismiss', exact: true }).click();
  releaseOffer?.();
  expect((await offerResponse).status()).toBe(200);
  await drain();
  await expect(region).toHaveCount(0);
  await checkpoint('f01-dismissed-after-late-offer.png');
});

for (const decision of ['keep', 'load'] as const) {
  test(`F02 protocol background change requires explicit ${decision} of reviewed answers`, async ({
    page,
    checkpoint,
  }: Scenario, info: Readonly<TestInfo>) => {
    const writes = await setup(page);
    let projection = ownFeedback;
    let submitted: readonly Request[] = [];
    let release: (() => void) | undefined;
    const changed = new Promise<void>((resolve) => {
      release = resolve;
    });
    let connections = 0;
    await page.route('**/api/v1/events', async (route: Readonly<Route>) => {
      connections += 1;
      if (connections === 1) await changed;
      await route.fulfill({
        contentType: 'text/event-stream',
        body:
          connections === 1
            ? `id: 42\nevent: resource.changed\ndata: ${JSON.stringify({ resource_type: 'account', resource_id: identity.account_id, version: null })}\n\n`
            : ': heartbeat\n\n',
      });
    });
    await page.route(`**${base}/feedback`, async (route: Readonly<Route>) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ json: projection });
        return;
      }
      submitted = [...submitted, route.request()];
      const body: unknown = route.request().postDataJSON();
      if (typeof body !== 'object' || body === null) throw new Error('Invalid review write');
      const saved: unknown = { ...receipt, ...body, version: 9 };
      if (!isReceipt(saved)) throw new Error('Invalid reviewed receipt');
      projection = { ...projection, current: saved };
      await route.fulfill({ json: saved });
    });
    await feedback(page);
    await page
      .getByRole('textbox', { name: 'Note for the team · optional' })
      .fill('My unsaved answers');
    projection = {
      ...ownFeedback,
      current: {
        ...receipt,
        version: 8,
        again: 'no',
        descriptors: ['prepared'],
        team_note: 'Newer saved answers from another device.',
      },
    };
    const reauthorized = page.waitForResponse('**/api/v1/me');
    release?.();
    expect((await reauthorized).status()).toBe(200);
    const review = page.getByRole('region', { name: 'Latest saved feedback', exact: true });
    await expect(review.getByText('Newer saved answers from another device.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Update feedback', exact: true })).toBeDisabled();
    await expect(page.getByRole('textbox', { name: 'Note for the team · optional' })).toHaveValue(
      'My unsaved answers',
    );
    expect(submitted).toHaveLength(0);
    await checkpointStudy({ page, checkpoint }, info, `f02-background-${decision}-review.png`);
    await page
      .getByRole('button', {
        name: decision === 'keep' ? 'Keep my answers' : 'Load saved answers',
        exact: true,
      })
      .click();
    await expect(review).toHaveCount(0);
    await expect(page.getByRole('textbox', { name: 'Note for the team · optional' })).toHaveValue(
      decision === 'keep' ? 'My unsaved answers' : 'Newer saved answers from another device.',
    );
    await expect(
      page.getByRole('radio', { name: decision === 'keep' ? 'Maybe' : 'No', exact: true }),
    ).toBeChecked();
    await checkpointStudy({ page, checkpoint }, info, `f02-background-${decision}-chosen.png`);
    await page.getByRole('button', { name: 'Update feedback', exact: true }).click();
    await expect(
      page.getByRole('heading', { name: 'Thanks, your feedback is saved' }),
    ).toBeVisible();
    expect(submitted).toHaveLength(1);
    expect(submitted[0]?.postDataJSON()).toEqual(
      expect.objectContaining({
        expected_version: 8,
        team_note:
          decision === 'keep' ? 'My unsaved answers' : 'Newer saved answers from another device.',
      }),
    );
    expect(
      writes().filter((value: Readonly<Request>) => value.url().endsWith('/study-prompt-visits')),
    ).toHaveLength(1);
    await checkpointStudy({ page, checkpoint }, info, `f02-background-${decision}-saved.png`);
  });
}

test('F01 protocol old idempotent replay cannot replace a newer canonical outcome', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  await setup(page);
  const old = { ...outcome, version: 4, answer: 'not_yet' as const };
  const newer = { ...outcome, version: 5, answer: 'did_not_work_out' as const };
  let canonical = outcome;
  let attempts: readonly Request[] = [];
  let release: (() => void) | undefined;
  const changed = new Promise<void>((resolve) => {
    release = resolve;
  });
  let connections = 0;
  await page.route('**/api/v1/events', async (route: Readonly<Route>) => {
    connections += 1;
    if (connections === 1) await changed;
    await route.fulfill({
      contentType: 'text/event-stream',
      body:
        connections === 1
          ? `id: 43\nevent: resource.changed\ndata: ${JSON.stringify({ resource_type: 'conversation', resource_id: conversation.conversation_id, version: null })}\n\n`
          : ': heartbeat\n\n',
    });
  });
  await page.route(`**${base}/study-outcome`, async (route: Readonly<Route>) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: { outcome: canonical } });
      return;
    }
    attempts = [...attempts, route.request()];
    if (attempts.length === 1) {
      canonical = old;
      await route.fulfill({ status: 503, json: { code: 'temporarily_unavailable' } });
    } else await route.fulfill({ json: old });
  });
  await open(page);
  await page
    .getByRole('region', { name: 'Study progress', exact: true })
    .getByRole('button', { name: 'Not yet', exact: true })
    .click();
  await expect(
    page.getByText('We couldn’t confirm whether this action was saved.', { exact: false }),
  ).toBeVisible();
  canonical = newer;
  release?.();
  await expect(page.getByRole('heading', { name: 'Thanks for letting us know' })).toBeVisible();
  await checkpointStudy({ page, checkpoint }, info, 'f01-replay-newer-canonical-before.png');
  await page.getByRole('button', { name: 'Retry same action', exact: true }).click();
  await expect(
    page.getByText('We couldn’t confirm whether this action was saved.', { exact: false }),
  ).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Thanks for letting us know' })).toBeVisible();
  expect(attempts).toHaveLength(2);
  expect(attempts[0]?.headers()['idempotency-key']).toBe(attempts[1]?.headers()['idempotency-key']);
  expect(attempts[0]?.postData()).toBe(attempts[1]?.postData());
  await checkpointStudy({ page, checkpoint }, info, 'f01-replay-newer-canonical-after.png');
});

test('F02 own-account revalidation reads committed feedback without resubmitting', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let projection = ownFeedback;
  let submitted: readonly Request[] = [];
  let reauthorized = false;
  let canonicalVersions: readonly number[] = [];
  const savedNote = 'Saved while checking the account.';
  let releaseHint: (() => void) | undefined;
  const hint = new Promise<void>((resolve) => {
    releaseHint = resolve;
  });
  let releaseIdentity: (() => void) | undefined;
  const identityReady = new Promise<void>((resolve) => {
    releaseIdentity = resolve;
  });
  let releaseReceipt: (() => void) | undefined;
  const receiptReady = new Promise<void>((resolve) => {
    releaseReceipt = resolve;
  });
  let connections = 0;
  await page.route('**/api/v1/events', async (route: Readonly<Route>) => {
    connections += 1;
    if (connections === 1) await hint;
    await route.fulfill({
      contentType: 'text/event-stream',
      body:
        connections === 1
          ? `id: 44\nevent: resource.changed\ndata: ${JSON.stringify({ resource_type: 'account', resource_id: identity.account_id, version: null })}\n\n`
          : ': heartbeat\n\n',
    });
  });
  await page.route(`**${base}/feedback`, async (route: Readonly<Route>) => {
    if (route.request().method() === 'GET') {
      if (reauthorized && projection.current !== null)
        canonicalVersions = [...canonicalVersions, projection.current.version];
      return route.fulfill({ json: projection });
    }
    submitted = [...submitted, route.request()];
    projection = { ...ownFeedback, current: { ...receipt, version: 8, team_note: savedNote } };
    releaseHint?.();
    await receiptReady;
    return route.fulfill({ json: projection.current });
  });
  await feedback(page);
  await page.getByRole('textbox', { name: 'Note for the team · optional' }).fill(savedNote);
  await page.route('**/api/v1/me', async (route: Readonly<Route>) => {
    await identityReady;
    reauthorized = true;
    await route.fulfill({ json: identity });
  });
  const recheck = page.waitForRequest('**/api/v1/me');
  const savedResponse = page.waitForResponse(
    (value) => value.url().endsWith('/feedback') && value.request().method() === 'PUT',
  );
  await page.getByRole('button', { name: 'Update feedback', exact: true }).click();
  await recheck;
  releaseReceipt?.();
  expect((await savedResponse).status()).toBe(200);
  await expect(page.getByText('Saving study progress…')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Update feedback', exact: true })).toBeDisabled();
  await checkpoint('f02-known-save-awaiting-identity.png', { fullPage: false });
  releaseIdentity?.();
  await expect(page.getByRole('button', { name: 'Study progress', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Study progress', exact: true }).click();
  await page.getByRole('button', { name: 'Give feedback', exact: true }).click();
  await expect.poll(() => canonicalVersions).toContain(8);
  await expect(page.getByRole('textbox', { name: 'Note for the team · optional' })).toHaveValue(
    savedNote,
  );
  await expect(page.getByRole('button', { name: 'Update feedback', exact: true })).toBeEnabled();
  expect(submitted).toHaveLength(1);
  await checkpoint('f02-known-save-reauthorized.png', { fullPage: false });
});

test('F02 Escape closes the explicit native dialog while a late save cannot reopen or duplicate it', async ({
  page,
  checkpoint,
}: Scenario) => {
  const writes = await setup(page);
  await feedback(page);
  const dialog = page.getByRole('dialog');
  await expect(dialog).toHaveCount(1);
  await expect(dialog.getByRole('heading', { name: 'Feedback', exact: true })).toBeVisible();
  await dialog
    .getByRole('textbox', { name: 'Note for the team · optional', exact: true })
    .fill('Synthetic draft retained only in its owning form');
  let release: (() => void) | undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(`**${base}/feedback`, async (route: Readonly<Route>) => {
    if (route.request().method() === 'PUT') await gate;
    await route.fallback();
  });
  const response = page.waitForResponse(
    (value) => value.url().endsWith('/feedback') && value.request().method() === 'PUT',
  );
  await dialog.getByRole('button', { name: 'Update feedback', exact: true }).click();
  await expect(dialog.getByText('Saving study progress…', { exact: true })).toBeVisible();
  await checkpoint('f02-native-dialog-saving.png', { fullPage: false });
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Study progress', exact: true })).toBeFocused();
  releaseHeldFeedback(release);
  expect((await response).status()).toBe(200);
  await expect(page.getByRole('region', { name: 'Study progress', exact: true })).toHaveCount(0);
  await expect(page.locator('#study-team-note')).toHaveCount(0);
  expect(
    writes().filter(
      (request) =>
        request.method() === 'PUT' && new URL(request.url()).pathname.endsWith('/feedback'),
    ),
  ).toHaveLength(1);
  await checkpoint('f02-native-dialog-closed-late-save.png', { fullPage: true });
});

test('F02 browser Back retires the open feedback owner before a late save returns', async ({
  page,
  checkpoint,
}: Scenario) => {
  const writes = await setup(page);
  await page.goto('/chats');
  await page.getByRole('link', { name: 'Maya Lim', exact: true }).click();
  await page.getByRole('button', { name: 'Study progress', exact: true }).click();
  await page.getByRole('button', { name: 'Give feedback', exact: true }).click();
  await page
    .getByRole('textbox', { name: 'Note for the team · optional', exact: true })
    .fill('Private feedback owned by the previous conversation screen');
  let release: (() => void) | undefined;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(`**${base}/feedback`, async (route: Readonly<Route>) => {
    if (route.request().method() === 'PUT') await pending;
    await route.fallback();
  });
  const response = page.waitForResponse(
    (value) => value.url().endsWith('/feedback') && value.request().method() === 'PUT',
  );
  await page.getByRole('button', { name: 'Update feedback', exact: true }).click();
  await expect(page.getByText('Saving study progress…', { exact: true })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/chats$/u);
  await expect(page.getByRole('heading', { name: 'Chats', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Study progress', exact: true })).toHaveCount(0);
  await expect(page.locator('#study-team-note')).toHaveCount(0);
  await expect(
    page.getByText('Private feedback owned by the previous conversation screen', { exact: true }),
  ).toHaveCount(0);
  releaseHeldFeedback(release);
  expect((await response).status()).toBe(200);
  await expect(page.getByRole('region', { name: 'Study progress', exact: true })).toHaveCount(0);
  await expect(page.locator('#study-team-note')).toHaveCount(0);
  expect(
    writes().filter(
      (request) =>
        request.method() === 'PUT' && new URL(request.url()).pathname.endsWith('/feedback'),
    ),
  ).toHaveLength(1);
  await checkpoint('f02-route-retired-private-feedback.png', { fullPage: false });
});
