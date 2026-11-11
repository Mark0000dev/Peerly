import { isOwnGoal } from '../study/goal-contract';
import { isPhotoUpload } from '../profile/photo/photo-contract';
import { Buffer } from 'node:buffer';
import type { Page, TestInfo } from '@playwright/test';
import { verifyFixtureStudent } from '../../../../../testing/verified-student';
import { test, expect } from '../../../../../testing/visual';

async function profilePhoto(page: Readonly<Page>): Promise<void> {
  const bytes = await page.evaluate(async () => {
    const canvas = new OffscreenCanvas(32, 32);
    const context = canvas.getContext('2d');
    if (context === null) throw new Error('Missing real canvas');
    context.putImageData(
      new ImageData(
        Uint8ClampedArray.from({ length: 32 * 32 * 4 }, (_, index) =>
          index % 4 === 3 ? 255 : 180,
        ),
        32,
        32,
      ),
      0,
      0,
    );
    return Array.from(
      new Uint8Array(await (await canvas.convertToBlob({ type: 'image/png' })).arrayBuffer()),
    );
  });
  await page.getByRole('button', { name: 'Add photo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Choose photo', exact: true })).toBeEnabled();
  await page
    .locator('input[type=file]')
    .first()
    .setInputFiles({ name: 'fixture.png', mimeType: 'image/png', buffer: Buffer.from(bytes) });
  const finalized = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      /\/api\/v1\/media\/uploads\/[^/]+\/finalize$/.test(new URL(response.url()).pathname),
  );
  await page
    .getByRole('button', { name: 'Use the original without cropping', exact: true })
    .click();
  const creation = await finalized;
  expect(creation.status()).toBe(202);
  const upload: unknown = await creation.json();
  if (!isPhotoUpload(upload)) throw new Error('Missing actual queued photo receipt');
  expect(upload.state).toBe('queued');
  await expect(
    page.getByText('Your photo is waiting for processing.', { exact: true }),
  ).toBeVisible();
  // Other scenarios intentionally retain queued uploads. Run the genuine
  // global worker until THIS receipt is READY, using the same finite ten-step
  // fixture drain as people seeding. Never rewrite/delete rows or assume that
  // one worker claim belongs to the last browser upload.
  for (let step = 0; step < 10; step += 1) {
    const response = await page.request.get(`/api/v1/media/${upload.id}`);
    expect(response.status()).toBe(200);
    const current: unknown = await response.json();
    if (!isPhotoUpload(current) || current.id !== upload.id)
      throw new Error('Invalid actual photo status');
    if (current.state === 'ready') break;
    expect(current.state).toBe('queued');
    const processed = await page.request.post('http://127.0.0.1:8768/__fixture/photo/process');
    expect(processed.status()).toBe(200);
    expect(await processed.json()).toEqual({ outcome: 'ready' });
  }
  const finalResponse = await page.request.get(`/api/v1/media/${upload.id}`);
  expect(finalResponse.status()).toBe(200);
  expect(await finalResponse.json()).toMatchObject({ id: upload.id, state: 'ready' });
  await page.getByRole('button', { name: 'Check photo status', exact: true }).click();
  await expect(page.getByText('Your photo is saved.', { exact: true })).toBeVisible();
}
async function setup(
  page: Readonly<Page>,
  project: string,
  scope: 'setup' | 'setup-replay' | 'setup-visibility-replay' | 'setup-profile',
): Promise<void> {
  await verifyFixtureStudent(page, project, scope);
  await page.getByRole('button', { name: 'Your profile', exact: true }).click();
  await page.getByRole('textbox', { name: 'Display name', exact: true }).fill('Maya Lee');
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  await expect(page.getByText('Profile saved.', { exact: true })).toBeVisible();
  await profilePhoto(page);
  await page.getByRole('button', { name: 'Back to setup', exact: true }).click();
  await page.getByRole('button', { name: 'Your study goal', exact: true }).click();
  await page.getByLabel('Knowledge area', { exact: true }).fill('Databases');
  await page.getByRole('option', { name: /SQL/ }).click();
  await page.getByLabel('Task or topic · optional', { exact: true }).fill('JOINs');
  await page.getByRole('button', { name: 'Save goal', exact: true }).click();
  await expect(
    page.getByText('Goal saved. New requests will use this goal.', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Back to setup', exact: true }).click();
  await page.getByRole('button', { name: 'Your study setup', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeEnabled();
}

for (const scenario of [
  { name: 'normal', scope: 'setup' },
  { name: 'lost completion', scope: 'setup-replay' },
] as const) {
  test(`real prerequisites and ${scenario.name} registration activate before canonical visibility commands`, async ({
    page,
    checkpoint,
  }: {
    readonly page: Page;
    readonly checkpoint: (name: string) => Promise<void>;
  }, info: Readonly<TestInfo>) => {
    await setup(page, info.project.name, scenario.scope);
    const region = page.getByRole('region', { name: 'Your study setup', exact: true });
    await expect(region.getByRole('link', { name: 'Terms of Use', exact: true })).toHaveAttribute(
      'href',
      '/terms?version=fixture-v1',
    );
    await expect(region.getByRole('checkbox')).toHaveCount(0);
    await checkpoint(`real-${scenario.scope}-issued-context.png`);
    await completeRegistration(page, scenario.scope);
    await expect(page).toHaveURL(/\/discover\?mode=find_help$/);
    const identity = await page.request.get('/api/v1/me');
    expect(identity.status()).toBe(200);
    const actor: unknown = await identity.json();
    expect(actor).toMatchObject({
      capabilities: { can_use_student_features: true },
      registration: { surface: 'onboarding_completion' },
    });
    await page.goto('/onboarding');
    await page.getByRole('button', { name: 'Your study setup', exact: true }).click();
    await expect(page.getByText('Your setup is saved.', { exact: true })).toBeVisible();
    await checkpoint(`real-${scenario.scope}-activated.png`);
    await page.getByRole('button', { name: 'Hide my profile', exact: true }).click();
    await expect(
      page.getByText('Your profile is hidden from Discover.', { exact: true }),
    ).toBeVisible();
    await expect(page.getByText('Existing chats continue to work.', { exact: true })).toBeVisible();
    await checkpoint(`real-${scenario.scope}-hidden.png`);
    await page.getByRole('button', { name: 'Show my profile', exact: true }).click();
    await expect(
      page.getByText('Your profile can appear in Discover.', { exact: true }),
    ).toBeVisible();
    await checkpoint(`real-${scenario.scope}-restored.png`);
  });
}
async function readActivatedGoal(page: Readonly<Page>) {
  const source = await page.request.get('/api/v1/me/goal');
  expect(source.status()).toBe(200);
  const saved: unknown = await source.json();
  if (!isOwnGoal(saved) || saved.goal === null) throw new Error('Missing real activated goal');
  return saved.goal;
}

test('real P01 overview and explicit goal completion use the activated actor canonical state', async ({
  page,
  checkpoint,
}: {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}, info: Readonly<TestInfo>) => {
  await setup(page, info.project.name, 'setup-profile');
  await completeRegistration(page, 'setup-profile');
  await expect(page).toHaveURL(/\/discover\?mode=find_help$/);
  const saved = await readActivatedGoal(page);
  await page.goto('/profile');
  await expect(page.getByRole('heading', { name: 'Maya Lee', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Your study goal' })).toContainText(
    saved.subject.label,
  );
  await expect(page.getByRole('img', { name: 'Your current profile photo' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Notifications', exact: true })).toHaveAttribute(
    'href',
    '/profile/notifications',
  );
  await checkpoint('real-own-profile-overview.png');
  await page.getByRole('button', { name: 'Mark goal done', exact: true }).click();
  const response = page.waitForResponse(
    (value) =>
      value.url().endsWith('/api/v1/me/goal/complete') && value.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Mark done', exact: true }).click();
  const completed = await response;
  expect(completed.status()).toBe(200);
  expect(completed.request().postDataJSON()).toEqual({
    goal_id: saved.id,
    expected_version: saved.version,
  });
  expect(await completed.json()).toMatchObject({
    id: saved.id,
    version: saved.version + 1,
  });
  await expect(page.getByText('No active study goal yet.', { exact: true })).toBeVisible();
  await checkpoint('real-own-goal-completed.png');
});

async function completeRegistration(
  page: Readonly<Page>,
  scope: 'setup' | 'setup-replay' | 'setup-visibility-replay' | 'setup-profile',
): Promise<void> {
  if (scope !== 'setup-replay') {
    await page.getByRole('button', { name: 'Continue', exact: true }).click();
    return;
  }
  let key: string | undefined;
  let body: unknown;
  let writes = 0;
  await page.route('**/api/v1/me/registration', async (route) => {
    writes += 1;
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    if (writes === 1) {
      key = route.request().headers()['idempotency-key'];
      body = route.request().postDataJSON();
      await route.abort('failed');
      return;
    }
    expect(route.request().headers()['idempotency-key']).toBe(key);
    expect(route.request().postDataJSON()).toEqual(body);
    await route.fulfill({ response });
  });
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(
    page.getByText(
      'We couldn’t confirm completion. Retry the same action or check your saved setup.',
      { exact: true },
    ),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Retry same completion', exact: true }).click();
}

test('real saved help and explicit first-task change prepare registration without a goal', async ({
  page,
  checkpoint,
}: {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}, info: Readonly<TestInfo>) => {
  await verifyFixtureStudent(page, info.project.name, 'setup-offer');
  await page.getByRole('button', { name: 'Your profile', exact: true }).click();
  await page.getByRole('textbox', { name: 'Display name', exact: true }).fill('Maya Lee');
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  await expect(page.getByText('Profile saved.', { exact: true })).toBeVisible();
  await profilePhoto(page);
  await page.getByRole('button', { name: 'Back to setup', exact: true }).click();
  await page.getByRole('button', { name: 'Your help areas', exact: true }).click();
  await page.getByRole('button', { name: 'Add an area', exact: true }).click();
  await page.getByLabel('Search areas', { exact: true }).fill('Databases');
  await page.getByRole('button', { name: 'SQL Databases', exact: true }).click();
  await page.getByLabel('Note for SQL · optional', { exact: true }).fill('JOINs');
  await page.getByRole('button', { name: 'Save help areas', exact: true }).click();
  await expect(page.getByText('Help areas saved.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Back to setup', exact: true }).click();
  await page.getByRole('button', { name: 'Your study setup', exact: true }).click();
  await expect(page.getByText('Save your study goal.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeDisabled();
  await checkpoint('real-offer-before-task-change.png');
  await page.getByRole('radio', { name: 'Offer help', exact: true }).check();
  await page.getByRole('button', { name: 'Save task', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeEnabled();
  await expect(
    page
      .getByRole('region', { name: 'Your study setup', exact: true })
      .getByRole('link', { name: 'Terms of Use', exact: true }),
  ).toHaveAttribute('href', '/terms?version=fixture-v1');
  await checkpoint('real-offer-ready-context.png');
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(page).toHaveURL(/\/discover\?mode=offer_help$/);
  await page.goto('/onboarding');
  await page.getByRole('button', { name: 'Your study setup', exact: true }).click();
  await expect(page.getByText('Your setup is saved.', { exact: true })).toBeVisible();
  await expect(page.getByRole('radio', { name: 'Offer help', exact: true })).toBeChecked();
  await expect(
    page.getByRole('link', { name: 'Continue to Discover', exact: true }),
  ).toHaveAttribute('href', '/discover?mode=offer_help');
  await checkpoint('real-offer-activated.png');
});

test('real committed visibility loss replays the original immutable outcome before explicit restoration', async ({
  page,
  checkpoint,
}: {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}, info: Readonly<TestInfo>) => {
  await setup(page, info.project.name, 'setup-visibility-replay');
  await completeRegistration(page, 'setup-visibility-replay');
  await expect(page).toHaveURL(/\/discover\?mode=find_help$/);
  await page.goto('/onboarding');
  await page.getByRole('button', { name: 'Your study setup', exact: true }).click();
  await expect(page.getByText('Your setup is saved.', { exact: true })).toBeVisible();
  await hideWithLostReply(page, checkpoint);
  await expect(page.getByText('Existing chats continue to work.', { exact: true })).toBeVisible();
  await checkpoint('real-setup-visibility-replayed-hidden.png');
  await page.getByRole('button', { name: 'Show my profile', exact: true }).click();
  await expect(
    page.getByText('Your profile can appear in Discover.', { exact: true }),
  ).toBeVisible();
  await checkpoint('real-setup-visibility-replayed-restored.png');
});

async function hideWithLostReply(
  page: Readonly<Page>,
  checkpoint: (name: string) => Promise<void>,
): Promise<void> {
  let writes = 0;
  let key: string | undefined;
  let body: unknown;
  let receipt: unknown;
  await page.route('**/api/v1/me/visibility', async (route) => {
    writes += 1;
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    if (writes === 1) {
      key = route.request().headers()['idempotency-key'];
      expect(typeof key).toBe('string');
      body = route.request().postDataJSON();
      expect(body).toMatchObject({ hidden: true });
      receipt = await response.json();
      await route.abort('failed');
      return;
    }
    expect(route.request().headers()['idempotency-key']).toBe(key);
    expect(route.request().postDataJSON()).toEqual(body);
    expect(await response.json()).toEqual(receipt);
    await route.fulfill({ response });
  });
  await page.getByRole('button', { name: 'Hide my profile', exact: true }).click();
  await expect(
    page.getByText(
      'We couldn’t confirm the visibility change. Retry the same change or reload the saved setup.',
      { exact: true },
    ),
  ).toBeVisible();
  expect(writes).toBe(1);
  const saved = await page.request.get('/api/v1/me/onboarding');
  expect(saved.status()).toBe(200);
  expect(await saved.json()).toMatchObject({ visibility: receipt });
  await checkpoint('real-setup-visibility-unknown.png');
  await page.getByRole('button', { name: 'Retry same change', exact: true }).click();
  await expect(
    page.getByText('Your profile is hidden from Discover.', { exact: true }),
  ).toBeVisible();
  expect(writes).toBe(2);
  await page.unroute('**/api/v1/me/visibility');
}
