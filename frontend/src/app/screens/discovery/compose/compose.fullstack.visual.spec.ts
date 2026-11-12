import type { APIResponse, Page, Request, Response, Route, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../../testing/visual';
import { prepareComposerFixture } from '../../../../../testing/composer-fixture';
import type { Api } from '../../../api.generated';
import { isPreview, isSendResult } from './compose-contract';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}>;

async function actual(response: Readonly<APIResponse | Response>): Promise<unknown> {
  expect(response.status()).toBe(200);
  expect(response.headers()['cache-control']).toContain('no-store');
  return await response.json();
}

function previewResult(value: unknown): Api['schemas']['PreviewResponse'] {
  if (!isPreview(value)) throw new Error('Actual composer response must be a complete preview');
  return value;
}

function field(value: unknown, name: string): string {
  if (typeof value !== 'object' || value === null) throw new Error('Missing actual response');
  const item: unknown = Reflect.get(value, name);
  if (typeof item !== 'string') throw new Error(`Missing actual ${name}`);
  return item;
}

async function review(
  page: Readonly<Page>,
  personId: string,
  mode: Api['schemas']['DiscoveryMode'],
): Promise<Response> {
  const checked = page.waitForResponse(
    (response) => new URL(response.url()).pathname === '/api/v1/requests/preview',
  );
  await page.goto(`/discover?mode=${mode}&person=${personId}&compose=request`);
  return await checked;
}

function sent(value: unknown): string {
  if (!isSendResult(value) || value.outcome !== 'sent')
    throw new Error('Actual send did not return sent receipt');
  return value.request_id;
}

function sourceGoal(value: unknown): Readonly<{ readonly id: string; readonly version: number }> {
  if (typeof value !== 'object' || value === null || !('goal' in value))
    throw new Error('Missing current real goal');
  const goal = value.goal;
  if (
    typeof goal !== 'object' ||
    goal === null ||
    !('version' in goal) ||
    typeof goal.version !== 'number'
  )
    throw new Error('Missing current real goal revision');
  return { id: field(goal, 'id'), version: goal.version };
}

test('real D03 source revision requires review without replacing draft', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareComposerFixture(page, 'find_help', 'source-change', info.project.name);
  const checked = previewResult(await actual(await review(page, seed.personId, 'find_help')));
  const text = page.getByRole('textbox', { name: 'Request text', exact: true });
  await expect(text).toHaveValue(checked.suggested_text);
  await checkpoint('real-source-original-preview.png', { fullPage: false });
  await text.fill('Keep my edited request through a real goal revision.');
  const identity = await actual(await page.request.get('/api/v1/me'));
  const goal = sourceGoal(await actual(await page.request.get('/api/v1/me/goal')));
  const body: Api['schemas']['SaveGoalRequest'] = {
    expected_goal_id: goal.id,
    expected_version: goal.version,
    subject: { kind: 'canonical', id: seed.subjectId },
    topic: 'Updated worked examples',
    context: 'Review the updated academic source before sending.',
    shared_learning: true,
  };
  expect(
    await actual(
      await page.request.put('/api/v1/me/goal', {
        headers: {
          'X-CSRF-Token': field(identity, 'csrf_token'),
          'Idempotency-Key': crypto.randomUUID(),
          Origin: new URL(page.url()).origin,
        },
        data: body,
      }),
    ),
  ).toMatchObject({ version: goal.version + 1 });
  const response = page.waitForResponse(
    (item) => new URL(item.url()).pathname === '/api/v1/requests/preview',
  );
  await page.getByRole('button', { name: 'Recheck availability', exact: true }).click();
  const revised = previewResult(await actual(await response));
  expect(revised.preview_id).not.toBe(checked.preview_id);
  await expect(
    page.getByRole('region', { name: 'Changed academic context', exact: true }),
  ).toContainText(body.context ?? '');
  await expect(text).toHaveValue('Keep my edited request through a real goal revision.');
  const discard = page.getByRole('button', {
    name: 'Discard draft and use new suggestion',
    exact: true,
  });
  await discard.evaluate((element: Readonly<HTMLElement>) => {
    element.scrollIntoView({ block: 'center' });
  });
  await expect(discard).toBeInViewport({ ratio: 1 });
  await expect(
    page.getByRole('button', { name: 'Use reviewed context and keep my text', exact: true }),
  ).toBeInViewport({ ratio: 1 });
  await checkpoint('real-source-review-required.png', { fullPage: false });
  await page
    .getByRole('button', { name: 'Use reviewed context and keep my text', exact: true })
    .click();
  await expect(
    page.getByRole('region', { name: 'Saved academic context', exact: true }),
  ).toContainText(body.context ?? '');
  await expect(text).toHaveValue('Keep my edited request through a real goal revision.');
  await checkpoint('real-source-reviewed-text-retained.png', { fullPage: false });
  const delivered = page.waitForResponse(
    (item) => new URL(item.url()).pathname === '/api/v1/requests',
  );
  await page.getByRole('button', { name: 'Send request', exact: true }).click();
  const requestId = sent(await actual(await delivered));
  await expect(page.getByRole('heading', { name: 'Requests', exact: true })).toBeVisible();
  expect(await actual(await page.request.get(`/api/v1/requests/${requestId}`))).toMatchObject({
    text: 'Keep my edited request through a real goal revision.',
    context: revised.context,
  });
  await checkpoint('real-source-stored-reviewed-request.png');
});

test('real D03 close retains feature draft and navigation destroys it', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareComposerFixture(page, 'find_help', 'draft', info.project.name);
  const checked = previewResult(await actual(await review(page, seed.personId, 'find_help')));
  const text = page.getByRole('textbox', { name: 'Request text', exact: true });
  await expect(text).toHaveValue(checked.suggested_text);
  await text.fill('This unsent text belongs only to this feature instance.');
  await page.getByRole('button', { name: 'Close without sending', exact: true }).click();
  await expect(text).toHaveCount(0);
  await page.getByRole('button', { name: 'Review request', exact: true }).click();
  await expect(text).toHaveValue('This unsent text belongs only to this feature instance.');
  await text.scrollIntoViewIfNeeded();
  await checkpoint('real-feature-draft-reopened.png', { fullPage: false });
  await page.getByRole('button', { name: 'Close without sending', exact: true }).click();
  await expect(text).toHaveCount(0);
  let documentNavigations = 0;
  page.on('request', (request: Readonly<Request>) => {
    if (request.isNavigationRequest() && request.resourceType() === 'document')
      documentNavigations += 1;
  });
  await page.getByRole('link', { name: 'Edit setup', exact: true }).click();
  await expect(page).toHaveURL((url: Readonly<URL>) => url.pathname === '/onboarding');
  await page.getByRole('button', { name: 'Your study setup', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your study setup', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Continue to Discover', exact: true })).toBeVisible();
  await checkpoint('real-spa-setup-after-leaving-draft.png');
  expect(
    await actual(await page.request.get('/api/v1/requests?box=sent&view=active')),
  ).toMatchObject({ outgoing_pending: 0, successful_today: 0, requests: [] });
  await page.getByRole('link', { name: 'Continue to Discover', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Discover', exact: true })).toBeVisible();
  const response = page.waitForResponse(
    (item) => new URL(item.url()).pathname === '/api/v1/requests/preview',
  );
  await page.getByRole('button', { name: 'Review request', exact: true }).click();
  const fresh = previewResult(await actual(await response));
  await expect(text).toHaveValue(fresh.suggested_text);
  expect(fresh.context).toEqual(checked.context);
  expect(documentNavigations).toBe(0);
  await checkpoint('real-navigation-destroys-unsent-draft.png', { fullPage: false });
});

for (const mode of ['find_help', 'offer_help', 'study_together'] as const)
  test(`real D03 ${mode} edited text and note persist through canonical Requests`, async ({
    page,
    checkpoint,
  }: Scenario, info: Readonly<TestInfo>) => {
    const seed = await prepareComposerFixture(page, mode, 'fresh', info.project.name);
    const checked = previewResult(await actual(await review(page, seed.personId, mode)));
    expect(checked.context.mode).toBe(mode);
    expect(checked.can_send).toBe(true);
    const text = page.getByRole('textbox', { name: 'Request text', exact: true });
    await expect(text).toHaveValue(checked.suggested_text);
    await expect(
      page.getByRole('region', { name: 'Saved academic context', exact: true }),
    ).toContainText(seed.subjectLabel);
    const textfield = page.locator('tui-textfield').filter({ has: text });
    await textfield.evaluate((element: Readonly<HTMLElement>) => {
      element.scrollIntoView({ block: 'center' });
    });
    await expect(textfield).toBeInViewport({ ratio: 1 });
    await checkpoint(`real-${mode}-preview.png`, { fullPage: false });
    const edited = 'Could we compare our worked examples?\nI have tried the lab.';
    const note = ' I can share my attempt. ';
    await text.fill(edited);
    await page.getByRole('button', { name: 'Personal note · optional', exact: true }).click();
    const noteField = page.getByRole('textbox', { name: 'Personal note', exact: true });
    await noteField.fill(note);
    const noteTextfield = page.locator('tui-textfield').filter({ has: noteField });
    await noteTextfield.evaluate((element: Readonly<HTMLElement>) => {
      element.scrollIntoView({ block: 'center' });
    });
    await expect(noteTextfield).toBeInViewport({ ratio: 1 });
    await expect(textfield).toBeInViewport({ ratio: 1 });
    await expect(text).toHaveValue(edited);
    await expect(noteField).toHaveValue(note);
    await checkpoint(`real-${mode}-edited-note.png`, { fullPage: false });
    const response = page.waitForResponse(
      (item) => new URL(item.url()).pathname === '/api/v1/requests',
    );
    await page.getByRole('button', { name: 'Send request', exact: true }).click();
    const requestId = sent(await actual(await response));
    await expect(page.getByRole('heading', { name: 'Requests', exact: true })).toBeVisible();
    await expect(page.getByText(edited, { exact: true })).toBeVisible();
    expect(await actual(await page.request.get(`/api/v1/requests/${requestId}`))).toMatchObject({
      text: edited,
      note,
      context: checked.context,
      request: { request_id: requestId, state: 'pending', mode },
    });
    // Pending requests offer no conversation action. Global student navigation
    // remains available and is not a claim that this pair is already connected.
    await expect(
      page.getByRole('article', { name: /Request with / }).getByRole('link', { name: /chat/i }),
    ).toHaveCount(0);
    await expect(
      page
        .getByRole('navigation', { name: 'Student navigation', exact: true })
        .getByRole('link', { name: 'Chats', exact: true }),
    ).toHaveAttribute('href', '/chats');
    await checkpoint(`real-${mode}-stored-request.png`);
  });

for (const [scenario, outcome] of [
  ['outgoing', 'existing_outgoing'],
  ['incoming', 'incoming'],
  ['connected', 'connected'],
] as const)
  test(`real D03 ${scenario} recovers actual pair without sending or accepting`, async ({
    page,
    checkpoint,
  }: Scenario, info: Readonly<TestInfo>) => {
    const seed = await prepareComposerFixture(page, 'find_help', scenario, info.project.name);
    let sends = 0;
    page.on('request', (request) => {
      if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/requests')
        sends += 1;
    });
    const response = await actual(await review(page, seed.personId, 'find_help'));
    expect(response).toMatchObject({ outcome });
    const requestId = field(response, 'request_id');
    await expect(page.getByRole('region', { name: 'Existing pair', exact: true })).toBeVisible();
    await expect(
      page.getByRole('link', { name: 'Review existing request', exact: true }),
    ).toHaveAttribute('href', new RegExp(`request=${requestId}`));
    await expect(page.getByRole('button', { name: 'Send request', exact: true })).toHaveCount(0);
    expect(sends).toBe(0);
    await checkpoint(`real-${scenario}-recovery.png`, { fullPage: false });
    await page.getByRole('link', { name: 'Review existing request', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Requests', exact: true })).toBeVisible();
    await expect(page).toHaveURL(
      (url: Readonly<URL>) =>
        url.pathname === '/requests' && url.searchParams.get('request') === requestId,
    );
    expect(await actual(await page.request.get(`/api/v1/requests/${requestId}`))).toMatchObject({
      request: { request_id: requestId },
    });
    expect(sends).toBe(0);
    await checkpoint(`real-${scenario}-canonical-recovery.png`);
  });

function sameIntent(route: Readonly<Route>, body: string | null, key: string | undefined): void {
  expect(route.request().postData()).toBe(body);
  expect(route.request().headers()['idempotency-key']).toBe(key);
}

test('real D03 send commits before response loss and exact replay returns original receipt', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareComposerFixture(page, 'find_help', 'lost-reply', info.project.name);
  const checked = previewResult(await actual(await review(page, seed.personId, 'find_help')));
  let original: string | null = null;
  let key: string | undefined;
  let committed: unknown;
  let writes = 0;
  await page.route('**/api/v1/requests', async (route: Readonly<Route>) => {
    writes += 1;
    if (writes === 1) {
      original = route.request().postData();
      key = route.request().headers()['idempotency-key'];
      committed = await actual(await route.fetch());
      await route.abort();
    } else {
      sameIntent(route, original, key);
      const replay = await route.fetch();
      equalReceipt(await actual(replay), committed);
      await route.fulfill({ response: replay });
    }
  });
  const text = page.getByRole('textbox', { name: 'Request text', exact: true });
  await expect(text).toHaveValue(checked.suggested_text);
  await text.fill('Please keep this original committed request.');
  await page.getByRole('button', { name: 'Send request', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry same request', exact: true })).toBeVisible();
  const requestId = sent(committed);
  expect(await actual(await page.request.get(`/api/v1/requests/${requestId}`))).toMatchObject({
    text: 'Please keep this original committed request.',
  });
  await checkpoint('real-send-committed-reply-lost.png', { fullPage: false });
  await page
    .getByRole('region', { name: 'Request recovery', exact: true })
    .scrollIntoViewIfNeeded();
  await expect(
    page.getByRole('button', { name: 'Retry same request', exact: true }),
  ).toBeInViewport({ ratio: 1 });
  await checkpoint('real-send-committed-reply-lost-recovery.png', { fullPage: false });
  await page.getByRole('button', { name: 'Retry same request', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Requests', exact: true })).toBeVisible();
  expect(writes).toBe(2);
  expect(
    await actual(await page.request.get('/api/v1/requests?box=sent&view=active')),
  ).toMatchObject({
    outgoing_pending: 1,
    successful_today: 1,
    requests: [{ request_id: requestId }],
  });
  await checkpoint('real-send-original-receipt-replayed.png');
});

function equalReceipt(value: unknown, original: unknown): void {
  expect(value).toEqual(original);
}
