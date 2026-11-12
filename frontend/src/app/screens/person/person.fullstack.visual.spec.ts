import type { Page } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { preparePersonFixture } from '../../../../testing/people-fixture';

interface Context {
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}
async function open(page: Readonly<Page>, personId: string): Promise<void> {
  await page.goto(`/people/${personId}`);
  await expect(page.getByRole('heading', { name: 'Aiko Tan', exact: true })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Photo of Aiko Tan', exact: true })).toBeVisible();
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
}
async function options(page: Readonly<Page>): Promise<void> {
  await page.getByRole('button', { name: 'More options', exact: true }).click();
}
async function report(page: Readonly<Page>): Promise<void> {
  await options(page);
  await page.getByRole('button', { name: 'Report profile', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Submit report', exact: true })).toBeVisible();
}

test('actual person projection and current authorized JPEG use real activated student records', async ({
  page,
  checkpoint,
}: Context) => {
  const seed = await preparePersonFixture(page);
  const json = page.waitForResponse((response) =>
    response.url().endsWith(`/api/v1/people/${seed.personId}`),
  );
  const jpeg = page.waitForResponse((response) =>
    response.url().includes(`/api/v1/people/${seed.personId}/photo/`),
  );
  await open(page, seed.personId);
  const profileResponse = await json;
  expect(profileResponse.status()).toBe(200);
  const profile: unknown = await profileResponse.json();
  expect(profile).toMatchObject({ id: seed.personId, own_block: { blocked: false } });
  const photoResponse = await jpeg;
  expect(photoResponse.status()).toBe(200);
  expect(photoResponse.headers()['content-type']).toContain('image/jpeg');
  expect(photoResponse.headers()['cache-control']).toContain('no-store');
  expect(photoResponse.headers()['x-content-type-options']).toBe('nosniff');
  expect((await photoResponse.body()).byteLength).toBeGreaterThan(0);
  expect(
    await page
      .getByRole('img', { name: 'Photo of Aiko Tan' })
      .evaluate(
        (image: Readonly<HTMLElement | SVGElement>) =>
          image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0,
      ),
  ).toBe(true);
  await expect(page.getByText('Happy to practise SQL together.', { exact: true })).toBeVisible();
  await expect(page.getByText('Computing Year 1', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: /request|chat/i })).toHaveCount(0);
  await checkpoint('actual-person-and-private-jpeg.png');
});

test('actual own block rereads canonical state, disclosed profile remains reportable, and own unblock restores read', async ({
  page,
  checkpoint,
}: Context) => {
  const seed = await preparePersonFixture(page);
  await open(page, seed.personId);
  await options(page);
  await page.getByRole('button', { name: 'Block person', exact: true }).click();
  await checkpoint('actual-block-confirmation.png', { fullPage: false });
  const blockedResponse = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' &&
      response.url().endsWith(`/api/v1/me/blocks/${seed.personId}`),
  );
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  expect((await blockedResponse).status()).toBe(200);
  await expect(page.getByRole('alert')).toContainText('This profile is unavailable');
  await expect(page.getByRole('heading', { name: 'Aiko Tan', exact: true })).toHaveCount(0);
  await checkpoint('actual-own-block-canonical.png');
  await report(page);
  await page.getByRole('radio', { name: 'Other', exact: true }).check();
  await page
    .getByLabel('Comment (up to 1000 characters)')
    .fill('Controlled fixture profile report after own block.');
  const submitted = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' && response.url().endsWith('/api/v1/reports'),
  );
  await page.getByRole('button', { name: 'Submit report', exact: true }).click();
  expect((await submitted).status()).toBe(201);
  await expect(page.getByRole('status')).toContainText('Report stored');
  await checkpoint('actual-owned-context-report-after-block.png', { fullPage: false });
  await page
    .getByRole('region', { name: 'Report profile', exact: true })
    .getByRole('button', { name: 'Close', exact: true })
    .click();
  // Initial real SSE reset revalidates /me and legitimately closes private
  // sheets. Wait for its actual cursor-bearing reconnect before opening a new one.
  const resumed = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname === '/api/v1/events' &&
      request.headers()['last-event-id'] !== undefined,
  );
  await page.reload();
  await resumed;
  await expect(page.getByRole('alert')).toContainText('This profile is unavailable');
  await options(page);
  await expect(page.getByRole('button', { name: 'Report profile', exact: true })).toHaveCount(0);
  await checkpoint('actual-reloaded-own-block.png');
  await page.getByRole('button', { name: 'Unblock person', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Unblock this person?', exact: true }),
  ).toBeVisible();
  await checkpoint('actual-unblock-confirmation.png', { fullPage: false });
  const unblockedResponse = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' &&
      response.url().endsWith(`/api/v1/me/blocks/${seed.personId}`),
  );
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  expect((await unblockedResponse).status()).toBe(200);
  await expect(page.getByRole('heading', { name: 'Aiko Tan', exact: true })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Photo of Aiko Tan', exact: true })).toBeVisible();
  await checkpoint('actual-unblocked-profile.png');
});

test('actual stored report lost response remains uncertain until the same intent replays its durable receipt', async ({
  page,
  checkpoint,
}: Context) => {
  const seed = await preparePersonFixture(page);
  await open(page, seed.personId);
  await report(page);
  let originalKey: string | undefined;
  let replayKey: string | undefined;
  let originalBody: string | null = null;
  let replayBody: string | null = null;
  let originalReceipt: unknown;
  let replayReceipt: unknown;
  let attempts = 0;
  await page.route('**/api/v1/reports', async (route) => {
    const response = await route.fetch();
    expect(response.status()).toBe(201);
    const receipt: unknown = await response.json();
    expect(receipt).toHaveProperty('id');
    expect(receipt).toHaveProperty('context_id');
    expect(receipt).toHaveProperty('submitted_at');
    attempts += 1;
    if (attempts === 1) {
      originalKey = route.request().headers()['idempotency-key'];
      originalBody = route.request().postData();
      originalReceipt = receipt;
      await route.abort('failed');
    } else {
      replayKey = route.request().headers()['idempotency-key'];
      replayBody = route.request().postData();
      replayReceipt = receipt;
      await route.fulfill({ response });
    }
  });
  await page
    .getByLabel('Comment (up to 1000 characters)')
    .fill('Controlled fixture durable unknown outcome.');
  await page.getByRole('button', { name: 'Submit report', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry same report' })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('couldn’t confirm the result');
  await checkpoint('actual-report-reply-lost.png', { fullPage: false });
  await page.getByRole('button', { name: 'Retry same report', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Report stored');
  expect(replayKey).toBe(originalKey);
  expect(replayBody).toBe(originalBody);
  expect(replayReceipt).toEqual(originalReceipt);
  await checkpoint('actual-report-durable-replay.png', { fullPage: false });
});
