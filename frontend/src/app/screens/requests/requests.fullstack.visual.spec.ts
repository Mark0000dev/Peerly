import type { APIResponse, Page, Route, Response } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { prepareRequestsFixture } from '../../../../testing/requests-fixture';

type Context = Readonly<{
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}>;
async function stored(response: Readonly<APIResponse | Response>): Promise<unknown> {
  expect(response.status()).toBe(200);
  expect(response.headers()['cache-control']).toContain('no-store');
  return await response.json();
}
function conversationId(value: unknown): string {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('conversation_id' in value) ||
    typeof value.conversation_id !== 'string'
  )
    throw new Error('Actual acceptance omitted its conversation');
  return value.conversation_id;
}
function equalReceipt(actual: unknown, receipt: unknown): void {
  expect(actual).toEqual(receipt);
}
function sameIntent(
  route: Readonly<Route>,
  original: string | null,
  key: string | undefined,
): void {
  expect(route.request().postData()).toBe(original);
  expect(route.request().headers()['idempotency-key']).toBe(key);
}
function field(value: unknown, key: string): string {
  if (typeof value !== 'object' || value === null || !(key in value))
    throw new Error('Missing actual response field');
  const item: unknown = Reflect.get(value, key);
  if (typeof item !== 'string') throw new Error('Malformed actual response field');
  return item;
}

test('real received disclosure remains unread until explicit owned ACK then accepts without first message', async ({
  page,
  checkpoint,
}: Context) => {
  const seed = await prepareRequestsFixture(page, 'received');
  await page.goto(`/requests?request=${seed.requestId}`);
  await expect(page.getByRole('heading', { name: 'Academic context when sent' })).toBeVisible();
  await expect(page.getByText(seed.text, { exact: true })).toBeVisible();
  await expect(page.getByText('1 unread received requests')).toBeVisible();
  await checkpoint('real-received-unread.png');
  const ack = page.waitForResponse(
    (response) => new URL(response.url()).pathname === `/api/v1/requests/${seed.requestId}/viewed`,
  );
  await page.getByRole('button', { name: 'Mark as viewed' }).click();
  expect(await stored(await ack)).toMatchObject({ request_id: seed.requestId, stored_version: 1 });
  await expect(page.getByText('0 unread received requests')).toBeVisible();
  await checkpoint('real-acknowledged.png');
  const accept = page.waitForResponse(
    (response) => new URL(response.url()).pathname === `/api/v1/requests/${seed.requestId}/accept`,
  );
  await page.getByRole('button', { name: 'Accept request' }).click();
  const receipt = await stored(await accept);
  expect(receipt).toMatchObject({ request_id: seed.requestId, outcome: 'accepted', version: 2 });
  const conversation = await page.request.get(`/api/v1/conversations/${conversationId(receipt)}`);
  expect(await stored(conversation)).toMatchObject({
    request_id: seed.requestId,
    last_confirmed_sequence: 0,
    unread_count: 0,
  });
  await expect(page.getByText('Connected. No message was sent by accepting.')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open chat' })).toHaveCount(0);
  await checkpoint('real-accepted.png');
});

test('real decline stays reachable in recently declined and server Undo restores the same request', async ({
  page,
  checkpoint,
}: Context) => {
  const seed = await prepareRequestsFixture(page, 'received');
  await page.goto('/requests');
  await expect(page.getByText(seed.text, { exact: true })).toBeVisible();
  const decline = page.waitForResponse(
    (response) => new URL(response.url()).pathname === `/api/v1/requests/${seed.requestId}/decline`,
  );
  await page.getByRole('button', { name: 'Decline', exact: true }).click();
  expect(await stored(await decline)).toMatchObject({
    request_id: seed.requestId,
    outcome: 'declined',
    version: 2,
  });
  await page.getByRole('button', { name: 'Recently declined', exact: true }).click();
  await expect(page).toHaveURL(/view=recently_declined/);
  await expect(page.getByRole('button', { name: 'Undo decline' })).toBeEnabled();
  const undo = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `/api/v1/requests/${seed.requestId}/undo-decline`,
  );
  await page.getByRole('button', { name: 'Undo decline' }).click();
  expect(await stored(await undo)).toMatchObject({
    request_id: seed.requestId,
    outcome: 'undo_decline',
    version: 3,
  });
  await expect(page.getByRole('heading', { name: 'No recently declined requests' })).toBeVisible();
  await checkpoint('real-recently-declined-after-undo.png');
  await page.getByRole('button', { name: 'Active', exact: true }).click();
  await expect(page.getByText(seed.text, { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Accept request' })).toBeEnabled();
  await checkpoint('real-undo-restored.png');
});

test('real withdrawal confirms consequences and survives reload in sent history without refund', async ({
  page,
  checkpoint,
}: Context) => {
  const seed = await prepareRequestsFixture(page, 'sent');
  await page.goto('/requests?box=sent');
  await expect(page.getByText(seed.text, { exact: true })).toBeVisible();
  await expect(page.getByText('1 of 5 pending · 1 of 10 sent today')).toBeVisible();
  await checkpoint('real-sent-pending.png');
  await page.getByRole('button', { name: 'Withdraw', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Withdraw this request?' })).toBeVisible();
  await checkpoint('real-withdraw-confirmation.png');
  const withdraw = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `/api/v1/requests/${seed.requestId}/withdraw`,
  );
  await page.getByRole('button', { name: 'Withdraw request', exact: true }).click();
  expect(await stored(await withdraw)).toMatchObject({
    request_id: seed.requestId,
    outcome: 'withdrawn',
    version: 2,
  });
  await expect(page.getByText('0 of 5 pending · 1 of 10 sent today')).toBeVisible();
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await page.reload();
  await expect(page.getByText(seed.text, { exact: true })).toBeVisible();
  await expect(page.getByText('Withdrawn', { exact: true })).toBeVisible();
  await checkpoint('real-withdrawn-history.png');
});

test('real accepted command commits before reply loss and exact replay returns the original receipt', async ({
  page,
  checkpoint,
}: Context) => {
  const seed = await prepareRequestsFixture(page, 'received');
  let original: string | null = null;
  let key: string | undefined;
  let receipt: unknown;
  let sends = 0;
  await page.route(
    `**/api/v1/requests/${seed.requestId}/accept`,
    async (route: Readonly<Route>) => {
      sends += 1;
      if (sends === 1) {
        original = route.request().postData();
        key = route.request().headers()['idempotency-key'];
        receipt = await stored(await route.fetch());
        await route.abort('failed');
      } else {
        sameIntent(route, original, key);
        const response = await route.fetch();
        equalReceipt(await stored(response), receipt);
        await route.fulfill({ response });
      }
    },
  );
  await page.goto('/requests');
  await page.getByRole('button', { name: 'Accept request' }).click();
  await expect(page.getByRole('button', { name: 'Retry same decision' })).toBeVisible();
  await checkpoint('real-accepted-reply-lost.png');
  await page.getByRole('button', { name: 'Retry same decision' }).click();
  await expect(page.getByText('Connected. No message was sent by accepting.')).toBeVisible();
  expect(sends).toBe(2);
  await page.reload();
  await expect(page.getByText('Connected. No message was sent by accepting.')).toBeVisible();
  await checkpoint('real-accepted-replayed.png');
});

test('real decline deadline expires without client finalization and cannot be undone after reload', async ({
  page,
  checkpoint,
}: Context) => {
  const seed = await prepareRequestsFixture(page, 'received');
  await page.goto('/requests');
  const decline = page.waitForResponse(
    (response) => new URL(response.url()).pathname === `/api/v1/requests/${seed.requestId}/decline`,
  );
  await page.getByRole('button', { name: 'Decline', exact: true }).click();
  expect(await stored(await decline)).toMatchObject({
    request_id: seed.requestId,
    outcome: 'declined',
  });
  await page.getByRole('button', { name: 'Recently declined', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Undo decline' })).toBeEnabled();
  // This waits for the actual fixed ten-second server window, not a test sleep or altered clock.
  await expect(page.getByRole('heading', { name: 'No recently declined requests' })).toBeVisible({
    timeout: 15000,
  });
  await checkpoint('real-decline-deadline-elapsed.png');
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await page.reload();
  await expect(page.getByText(seed.text, { exact: true })).toBeVisible();
  await expect(page.getByText('Declined', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Undo decline' })).toHaveCount(0);
  await checkpoint('real-final-decline-history.png');
});

test('real repeated disclosure ACK retains first receipt for the same stored revision', async ({
  page,
  checkpoint,
}: Context) => {
  const seed = await prepareRequestsFixture(page, 'received');
  await page.goto(`/requests?request=${seed.requestId}`);
  await expect(page.getByRole('button', { name: 'Mark as viewed' })).toBeEnabled();
  // A second participant-owned read/ACK simulates another device before this stale UI acts.
  const secondDisclosure = await stored(
    await page.request.get(`/api/v1/requests/${seed.requestId}`),
  );
  const identityResponse = await stored(await page.request.get('/api/v1/me'));
  const first = await stored(
    await page.request.post(`/api/v1/requests/${seed.requestId}/viewed`, {
      headers: {
        Origin: new URL(page.url()).origin,
        'X-CSRF-Token': field(identityResponse, 'csrf_token'),
        'Idempotency-Key': crypto.randomUUID(),
      },
      data: { disclosure_id: field(secondDisclosure, 'disclosure_id') },
    }),
  );
  const acknowledgement = page.waitForResponse(
    (response) => new URL(response.url()).pathname === `/api/v1/requests/${seed.requestId}/viewed`,
  );
  await page.getByRole('button', { name: 'Mark as viewed' }).click();
  equalReceipt(await stored(await acknowledgement), first);
  await expect(page.getByText('0 unread received requests')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry same acknowledgement' })).toHaveCount(0);
  await checkpoint('real-first-ack-receipt-retained.png');
});
