import type { APIResponse, Page, Response, Route, TestInfo } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { test, expect } from '../../../../../testing/visual';
import { prepareChatsFixture } from '../../../../../testing/chats-fixture';
import { isHistory } from '../chats-contract';
import { isTerminalOperation } from '../message-contract';
import {
  isImagePreparation,
  isImageReceipt,
  isImageReportContext,
  isImageReportReceipt,
} from './image-contract';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}>;
const source = readFileSync('testing/fixtures/chat-study-image.png');

interface CommitWitness {
  readonly imageId: string;
  readonly clientMessageId: string;
}
interface StartWitness extends CommitWitness {
  readonly key: string | undefined;
  readonly body: string | null;
}
function witness<T>(value: T | undefined): T {
  if (value === undefined) throw new Error('Missing actual upstream commit witness');
  return value;
}
function gate() {
  let release: () => void = () => undefined;
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { promise, release } as const;
}
async function choose(page: Readonly<Page>, caption: string): Promise<void> {
  await page.getByRole('textbox', { name: 'Message', exact: true }).fill(caption);
  await expect(page.getByLabel('Attach an image', { exact: true })).toBeEnabled();
  await page.getByLabel('Attach an image', { exact: true }).setInputFiles({
    name: 'controlled-study.png',
    mimeType: 'image/png',
    buffer: source,
  });
  await expect(page.getByAltText('Selected image attachment')).toHaveJSProperty(
    'naturalWidth',
    640,
  );
}

async function actual(response: Readonly<APIResponse | Response>, status = 200): Promise<unknown> {
  expect(response.status()).toBe(status);
  expect(response.headers()['cache-control']).toContain('no-store');
  const value: unknown = await response.json();
  return value;
}
function checked<T>(value: unknown, guard: (value: unknown) => value is T): T {
  if (!guard(value)) throw new Error('Invalid actual image response');
  return value;
}
function confirmed(value: unknown) {
  const operation = checked(value, isTerminalOperation);
  if (!('message' in operation)) throw new Error('Image operation was not confirmed');
  return operation;
}
async function imageDecoded(page: Readonly<Page>): Promise<void> {
  const image = page.getByAltText('Image shared in this conversation', { exact: true });
  await expect(image).toBeVisible();
  await expect(image).toHaveJSProperty('naturalWidth', 640);
  await expect(image).toHaveJSProperty('naturalHeight', 480);
}

async function enterAfterInitialRevalidation(
  page: Readonly<Page>,
  conversationId: string,
): Promise<void> {
  let connected = false;
  const revalidated = page.waitForResponse((response) => {
    const path = new URL(response.url()).pathname;
    if (path === '/api/v1/events' && response.status() === 200) connected = true;
    return connected && path === '/api/v1/me' && response.status() === 200;
  });
  await page.goto(`/chats?conversation=${conversationId}`);
  expect(await (await revalidated).finished()).toBeNull();
  await expect(page.getByRole('button', { name: 'Send message', exact: true })).toBeEnabled();
}

async function processReady(page: Readonly<Page>, imageTarget: string): Promise<void> {
  const queued = checked(await actual(await page.request.get(imageTarget)), isImagePreparation);
  expect(queued.state).toBe('queued');
  expect(queued.message_outcome).toBeNull();
  expect(queued.failure).toBeNull();
  let ticks = 0;
  let status = 0;
  let outcome: unknown;
  let transportFailure: unknown;
  await expect
    .poll(
      async () => {
        if (ticks === 20) return true;
        ticks += 1;
        try {
          const response = await page.request.post(
            'http://127.0.0.1:8768/__fixture/chat-images/process',
          );
          status = response.status();
          const body = await response.text();
          try {
            outcome = JSON.parse(body);
          } catch {
            outcome = body;
          }
        } catch (error: unknown) {
          transportFailure = error;
          return true;
        }
        return (
          status !== 200 ||
          !(
            typeof outcome === 'object' &&
            outcome !== null &&
            'outcome' in outcome &&
            outcome.outcome === 'idle'
          )
        );
      },
      { timeout: 5000 },
    )
    .toBe(true);
  if (transportFailure !== undefined)
    throw new Error('Actual worker tick transport failed', { cause: transportFailure });
  expect(ticks).toBeLessThanOrEqual(20);
  expect(status).toBe(200);
  expect(outcome).toEqual({ outcome: 'ready' });
  const ready = checked(await actual(await page.request.get(imageTarget)), isImagePreparation);
  expect(ready.state).toBe('ready');
}

async function prepareQueued(page: Readonly<Page>, conversationId: string) {
  const target = `/api/v1/conversations/${conversationId}`;
  await enterAfterInitialRevalidation(page, conversationId);
  await page.getByRole('textbox', { name: 'Message', exact: true }).fill('Original local caption');
  await expect(page.getByLabel('Attach an image', { exact: true })).toBeEnabled();
  await page.getByLabel('Attach an image', { exact: true }).setInputFiles({
    name: 'controlled-study.png',
    mimeType: 'image/png',
    buffer: source,
  });
  const startResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `${target}/image-preparations` &&
      response.request().method() === 'POST',
  );
  const finalizeResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.startsWith(`${target}/image-preparations/`) &&
      new URL(response.url()).pathname.endsWith('/finalize') &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  const started = checked(await actual(await startResponse, 202), isImageReceipt);
  const finalized = checked(await actual(await finalizeResponse, 202), isImageReceipt);
  expect(finalized.image_id).toBe(started.image_id);
  const preparation = checked(
    await actual(await page.request.get(`${target}/image-preparations/${started.image_id}`)),
    isImagePreparation,
  );
  expect(preparation.state).toBe('queued');
  return preparation;
}

// Real controlled storage/codec/PostgreSQL. No route interception or SQL READY shortcut.
test('C03 real PNG transfer worker and explicit Send store one participant JPEG with peer report evidence', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareChatsFixture(page, 'image-pipeline', info.project.name);
  const target = `/api/v1/conversations/${seed.conversationId}`;
  expect(seed.history.messages).toHaveLength(0);
  let starts = 0;
  let transfers = 0;
  let sends = 0;
  page.on('request', (request) => {
    if (request.method() !== 'POST') return;
    const url = new URL(request.url());
    if (url.pathname === `${target}/image-preparations`) starts += 1;
    if (url.pathname === `${target}/messages`) sends += 1;
    if (url.hostname === '127.0.0.1' && url.port === '8769') {
      transfers += 1;
    }
  });
  await enterAfterInitialRevalidation(page, seed.conversationId);
  const caption = page.getByRole('textbox', { name: 'Message', exact: true });
  await caption.fill('A sketch for our JOIN example');
  await expect(page.getByLabel('Attach an image', { exact: true })).toBeEnabled();
  await page.getByLabel('Attach an image', { exact: true }).setInputFiles({
    name: 'controlled-study.png',
    mimeType: 'image/png',
    buffer: source,
  });
  await expect(page.getByAltText('Selected image attachment')).toHaveJSProperty(
    'naturalWidth',
    640,
  );
  expect(starts).toBe(0);
  expect(transfers).toBe(0);
  expect(sends).toBe(0);
  await checkpoint('real-image-selected-unsent.png');

  const transferRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === 'POST' && url.hostname === '127.0.0.1' && url.port === '8769';
  });
  const startedResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `${target}/image-preparations` &&
      response.request().method() === 'POST',
  );
  const finalizedResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.startsWith(`${target}/image-preparations/`) &&
      new URL(response.url()).pathname.endsWith('/finalize') &&
      response.request().method() === 'POST',
  );
  const storedResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `${target}/messages` &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  const started = checked(await actual(await startedResponse, 202), isImageReceipt);
  expect(started.conversation_id).toBe(seed.conversationId);
  const imageTarget = `${target}/image-preparations/${started.image_id}`;
  const finalized = checked(await actual(await finalizedResponse, 202), isImageReceipt);
  expect(finalized.image_id).toBe(started.image_id);
  const transferHeaders = await (await transferRequest).allHeaders();
  for (const name of ['cookie', 'x-csrf-token', 'authorization', 'referer']) {
    // Compare booleans: a failed assertion must never print a credential value.
    expect(transferHeaders[name] === undefined).toBe(true);
  }
  const queued = checked(await actual(await page.request.get(imageTarget)), isImagePreparation);
  expect(queued.state).toBe('queued');
  expect(queued.expected_source).toEqual({
    content_type: 'image/png',
    size: source.length,
    sha256: createHash('sha256').update(source).digest('hex'),
  });
  expect(starts).toBe(1);
  expect(transfers).toBe(1);
  expect(sends).toBe(0);
  const beforeWorker = checked(
    await actual(await page.request.get(`${target}/messages`)),
    isHistory,
  );
  expect(beforeWorker.messages).toHaveLength(0);
  await expect(
    page.getByRole('status').filter({ hasText: 'Preparing and sending your image' }),
  ).toBeVisible();
  await expect(caption).toHaveValue('A sketch for our JOIN example');
  await checkpoint('real-image-queued-not-stored.png');

  await processReady(page, imageTarget);
  const stored = confirmed(await actual(await storedResponse));
  expect(stored.client_message_id).toBe(started.client_message_id);
  expect(stored.message.image_id).toBe(started.image_id);
  expect(stored.message.author_id).toBe(seed.viewerId);
  expect(stored.message.text).toBe('A sketch for our JOIN example');
  expect(stored.message.sequence).toBe(1);
  expect(sends).toBe(1);
  await expect(caption).toHaveValue('');
  await expect(page.getByText('A sketch for our JOIN example', { exact: true })).toBeVisible();
  await imageDecoded(page);
  await expect(page.getByRole('button', { name: 'Report image', exact: true })).toHaveCount(0);
  const rendition = await page.request.get(`${target}/messages/${stored.message.message_id}/image`);
  expect(rendition.status()).toBe(200);
  expect(rendition.headers()['content-type']).toContain('image/jpeg');
  expect(rendition.headers()['cache-control']).toContain('no-store');
  const jpeg = await rendition.body();
  expect(Array.from(jpeg.subarray(0, 3))).toEqual([255, 216, 255]);
  expect(createHash('sha256').update(jpeg).digest('hex')).not.toBe(
    createHash('sha256').update(source).digest('hex'),
  );
  const storedHistory = checked(
    await actual(await page.request.get(`${target}/messages`)),
    isHistory,
  );
  expect(storedHistory.messages).toEqual([stored.message]);
  await checkpoint('real-image-confirmed-owner.png');

  await seed.usePeer();
  // The real initial stream reset revalidates identity. Finish that bootstrap
  // before opening a new private report, which correctly closes on auth checks.
  const resumed = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname === '/api/v1/events' &&
      request.headers()['last-event-id'] !== undefined,
  );
  await page.reload();
  await resumed;
  await imageDecoded(page);
  const deniedPreparation = await page.request.get(`${imageTarget}/display`);
  expect(deniedPreparation.status()).toBe(404);
  const contextResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        `${target}/messages/${stored.message.message_id}/report-contexts` &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Report image', exact: true }).click();
  const context = checked(await actual(await contextResponse, 201), isImageReportContext);
  expect(context.conversation_id).toBe(seed.conversationId);
  expect(context.message_id).toBe(stored.message.message_id);
  expect(context.image_id).toBe(started.image_id);
  await page.getByRole('radio', { name: 'Other', exact: true }).check();
  await page
    .getByRole('textbox', { name: 'Private explanation (required for Other)', exact: true })
    .fill('This controlled test image contains private study material.');
  const reportResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === '/api/v1/reports' &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Submit report', exact: true }).click();
  const report = checked(await actual(await reportResponse, 201), isImageReportReceipt);
  expect(report.context_id).toBe(context.id);
  await expect(
    page.getByRole('status').filter({ hasText: 'Report submitted. Thank you.' }),
  ).toBeVisible();
  await checkpoint('real-image-peer-report-submitted.png');
});

test('C03 real owner reload retires the original Send and READY requires a new explicit Send', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareChatsFixture(page, 'image-recovery', info.project.name);
  const target = `/api/v1/conversations/${seed.conversationId}`;
  let sends = 0;
  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === `${target}/messages`)
      sends += 1;
  });
  const preparation = await prepareQueued(page, seed.conversationId);
  await page.reload();
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toHaveValue('');
  await expect(page.getByAltText('Selected image attachment')).toHaveCount(0);
  expect(sends).toBe(0);
  await processReady(page, `${target}/image-preparations/${preparation.image_id}`);
  const resumed = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname === '/api/v1/events' &&
      request.headers()['last-event-id'] !== undefined,
  );
  await page.reload();
  await resumed;
  const current = checked(
    await actual(await page.request.get(`${target}/image-preparations/${preparation.image_id}`)),
    isImagePreparation,
  );
  expect(current.state).toBe('ready');
  expect(current.message_outcome).toBeNull();
  const unsent = checked(await actual(await page.request.get(`${target}/messages`)), isHistory);
  expect(unsent.messages).toHaveLength(0);
  await expect(
    page
      .getByRole('region', { name: 'Selected conversation', exact: true })
      .getByRole('heading', { name: 'Aiko Tan', exact: true }),
  ).toBeVisible();
  await expect(page.getByText('Checking your image preparations…', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toBeEnabled();
  expect(sends).toBe(0);
  await checkpoint('real-image-reload-ready-unsent.png');
  await page.getByText('Your recent image preparations', { exact: true }).click();
  await expect(page.locator(`time[datetime="${preparation.created_at}"]`)).toBeVisible();
  await page.getByRole('button', { name: 'Select preparation', exact: true }).click();
  await expect(page.getByAltText('Preview of your selected prepared image')).toHaveJSProperty(
    'naturalWidth',
    640,
  );
  await expect(
    page.getByText('The image is prepared. Press Send to publish it with your current caption.'),
  ).toBeVisible();
  expect(sends).toBe(0);
  const confirmedResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `${target}/messages` &&
      response.request().method() === 'POST',
  );
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Explicit recovered caption');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  const result = confirmed(await actual(await confirmedResponse));
  expect(result.client_message_id).toBe(preparation.client_message_id);
  expect(result.message.image_id).toBe(preparation.image_id);
  expect(result.message.text).toBe('Explicit recovered caption');
  expect(sends).toBe(1);
  await imageDecoded(page);
  await expect(page.getByText('Explicit recovered caption', { exact: true })).toBeVisible();
  // Collapse the already-asserted owner collection through its normal disclosure.
  // Its actual server instant is checked above, never rewritten or masked.
  await page.getByText('Your recent image preparations', { exact: true }).click();
  await checkpoint('real-image-recovered-explicit-confirmed.png');
});

test('C03 real queued image cancellation wins without storing a message', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareChatsFixture(page, 'image-cancel', info.project.name);
  const target = `/api/v1/conversations/${seed.conversationId}`;
  const preparation = await prepareQueued(page, seed.conversationId);
  const cancelResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        `${target}/message-operations/${preparation.client_message_id}/cancel` &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Cancel image send', exact: true }).click();
  const cancelled = checked(await actual(await cancelResponse), isTerminalOperation);
  expect(cancelled.outcome).toBe('cancelled');
  expect(cancelled.client_message_id).toBe(preparation.client_message_id);
  const history = checked(await actual(await page.request.get(`${target}/messages`)), isHistory);
  expect(history.messages).toHaveLength(0);
  const current = checked(
    await actual(await page.request.get(`${target}/image-preparations/${preparation.image_id}`)),
    isImagePreparation,
  );
  expect(current.state).toBe('cancelled');
  expect(current.message_outcome).toEqual(expect.objectContaining({ outcome: 'cancelled' }));
  await expect(
    page.getByRole('status').filter({ hasText: 'The message operation was cancelled.' }),
  ).toBeVisible();
  await expect(page.getByAltText('Image shared in this conversation')).toHaveCount(0);
  await checkpoint('real-image-cancellation-won.png');
});

test('C03 real lost finalize response commits queued state but reload never publishes it', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareChatsFixture(page, 'image-finalize-unknown', info.project.name);
  const target = `/api/v1/conversations/${seed.conversationId}`;
  let committed: CommitWitness | undefined;
  let sends = 0;
  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === `${target}/messages`)
      sends += 1;
  });
  const loseFinalize = async (route: Readonly<Route>): Promise<void> => {
    const upstream = await route.fetch();
    const receipt = checked(await actual(upstream, 202), isImageReceipt);
    expect(receipt.conversation_id).toBe(seed.conversationId);
    committed = { imageId: receipt.image_id, clientMessageId: receipt.client_message_id };
    await route.abort('failed');
  };
  await page.route(`**${target}/image-preparations/*/finalize`, loseFinalize);
  await enterAfterInitialRevalidation(page, seed.conversationId);
  await choose(page, 'Original caption before lost finalization');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry image send', exact: true })).toBeVisible();
  const original = witness<CommitWitness>(committed);
  const imageTarget = `${target}/image-preparations/${original.imageId}`;
  const queued = checked(await actual(await page.request.get(imageTarget)), isImagePreparation);
  expect(queued.state).toBe('queued');
  expect(queued.message_outcome).toBeNull();
  expect(queued.client_message_id).toBe(original.clientMessageId);
  expect(sends).toBe(0);
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toHaveValue(
    'Original caption before lost finalization',
  );
  await expect(page.getByAltText('Selected image attachment')).toHaveJSProperty(
    'naturalWidth',
    640,
  );
  await checkpoint('real-image-finalize-committed-response-lost.png');
  await page.unroute(`**${target}/image-preparations/*/finalize`, loseFinalize);
  await page.reload();
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toHaveValue('');
  await expect(page.getByAltText('Selected image attachment')).toHaveCount(0);
  await processReady(page, imageTarget);
  await page.reload();
  const unsent = checked(await actual(await page.request.get(`${target}/messages`)), isHistory);
  expect(unsent.messages).toHaveLength(0);
  expect(sends).toBe(0);
  await checkpoint('real-image-lost-finalize-reload-ready-unsent.png');
  await page.getByText('Your recent image preparations', { exact: true }).click();
  await page.getByRole('button', { name: 'Select preparation', exact: true }).click();
  await expect(page.getByAltText('Preview of your selected prepared image')).toHaveJSProperty(
    'naturalWidth',
    640,
  );
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('New explicit caption after reload');
  const storedResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `${target}/messages` &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  const stored = confirmed(await actual(await storedResponse));
  expect(stored.client_message_id).toBe(original.clientMessageId);
  expect(stored.message.image_id).toBe(original.imageId);
  expect(stored.message.text).toBe('New explicit caption after reload');
  expect(sends).toBe(1);
  await imageDecoded(page);
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toHaveValue('');
  await page.getByText('Your recent image preparations', { exact: true }).click();
  await checkpoint('real-image-lost-finalize-explicit-confirmed.png');
});

test('C03 real authority pause preserves the original File caption and Start identity until explicit retry', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareChatsFixture(page, 'image-auth-pause', info.project.name);
  const target = `/api/v1/conversations/${seed.conversationId}`;
  const stream = gate();
  const session = gate();
  const sessionStarted = gate();
  let holdSession = false;
  let original: StartWitness | undefined;
  let starts = 0;
  let sends = 0;
  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === `${target}/messages`)
      sends += 1;
  });
  await page.route('**/api/v1/events', async (route) => {
    await stream.promise;
    await route.continue();
  });
  await page.route('**/api/v1/me', async (route) => {
    if (holdSession) {
      sessionStarted.release();
      await session.promise;
    }
    await route.continue();
  });
  await page.route(`**${target}/image-preparations`, async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    starts += 1;
    const request = route.request();
    const upstream = await route.fetch();
    const receipt = checked(await actual(upstream, 202), isImageReceipt);
    if (original === undefined) {
      original = {
        imageId: receipt.image_id,
        clientMessageId: receipt.client_message_id,
        key: request.headers()['idempotency-key'],
        body: request.postData(),
      };
      await route.abort('failed');
      return;
    }
    expect(request.headers()['idempotency-key']).toBe(original.key);
    expect(request.postData()).toBe(original.body);
    expect(receipt.image_id).toBe(original.imageId);
    expect(receipt.client_message_id).toBe(original.clientMessageId);
    await route.fulfill({ response: upstream });
  });
  try {
    await page.goto(`/chats?conversation=${seed.conversationId}`);
    await choose(page, 'Original immutable caption through authentication pause');
    await page.getByRole('button', { name: 'Send message', exact: true }).click();
    const retry = page.getByRole('button', { name: 'Retry image send', exact: true });
    await expect(retry).toBeVisible();
    const initial = witness<StartWitness>(original);
    expect(starts).toBe(1);
    expect(sends).toBe(0);
    holdSession = true;
    stream.release();
    await sessionStarted.promise;
    await expect(retry).toBeDisabled();
    await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toHaveValue(
      'Original immutable caption through authentication pause',
    );
    await expect(page.getByAltText('Selected image attachment')).toHaveJSProperty(
      'naturalWidth',
      640,
    );
    expect(starts).toBe(1);
    expect(sends).toBe(0);
    await checkpoint('real-image-auth-pause-preserves-immutable-intent.png');
    const refreshed = page.waitForResponse(
      (response) => new URL(response.url()).pathname === '/api/v1/me' && response.status() === 200,
    );
    holdSession = false;
    session.release();
    expect(await (await refreshed).finished()).toBeNull();
    await expect(retry).toBeEnabled();
    expect(starts).toBe(1);
    const finalized = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname ===
          `${target}/image-preparations/${initial.imageId}/finalize` &&
        response.request().method() === 'POST',
    );
    await retry.click();
    const receipt = checked(await actual(await finalized, 202), isImageReceipt);
    expect(receipt.image_id).toBe(initial.imageId);
    expect(receipt.client_message_id).toBe(initial.clientMessageId);
    expect(starts).toBe(2);
    const storedResponse = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === `${target}/messages` &&
        response.request().method() === 'POST',
    );
    await processReady(page, `${target}/image-preparations/${initial.imageId}`);
    const stored = confirmed(await actual(await storedResponse));
    expect(stored.client_message_id).toBe(initial.clientMessageId);
    expect(stored.message.image_id).toBe(initial.imageId);
    expect(stored.message.text).toBe('Original immutable caption through authentication pause');
    expect(sends).toBe(1);
    await imageDecoded(page);
    await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toHaveValue('');
    await checkpoint('real-image-auth-pause-explicit-identical-retry-confirmed.png');
  } finally {
    stream.release();
    session.release();
    await page.unrouteAll({ behavior: 'wait' });
  }
});
