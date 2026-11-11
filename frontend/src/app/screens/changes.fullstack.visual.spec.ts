import type { Page, Request, TestInfo } from '@playwright/test';
import { test, expect } from '../../../testing/visual';
import { prepareChatsFixture } from '../../../testing/chats-fixture';
import { isConversation, isHistory } from './chats/chats-contract';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}>;
async function drainPublication(page: Readonly<Page>): Promise<void> {
  for (let batch = 0; batch < 25; batch += 1) {
    const response = await page.request.post('http://127.0.0.1:8768/__fixture/changes/publish');
    expect(response.status()).toBe(200);
    const value: unknown = await response.json();
    if (
      typeof value !== 'object' ||
      value === null ||
      !('published' in value) ||
      typeof value.published !== 'number' ||
      !Number.isInteger(value.published) ||
      value.published < 0 ||
      value.published > 100
    )
      throw new Error('Invalid real publisher result');
    if (value.published === 0) return;
  }
  throw new Error('Controlled publication backlog exceeds bounded fixture drain');
}

function checked<T>(value: unknown, guard: (value: unknown) => value is T): T {
  if (!guard(value)) throw new Error('Invalid actual source response');
  return value;
}
function required<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error('Actual source value missing');
  return value;
}
function incomingId(value: unknown): string {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('message_id' in value) ||
    typeof value.message_id !== 'string'
  )
    throw new Error('Invalid actual incoming source');
  return value.message_id;
}

test('real publisher and authorized SSE refresh incoming confirmed chat without automatic ACK/send', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const cohort = await prepareChatsFixture(page, 'stream', info.project.name);
  await drainPublication(page);
  const resumed = page.waitForRequest(
    (request: Readonly<Request>) =>
      new URL(request.url()).pathname === '/api/v1/events' &&
      request.headers()['last-event-id'] !== undefined,
  );
  let writes: readonly Readonly<{
    readonly method: string;
    readonly path: string;
    readonly body: unknown;
  }>[] = [];
  page.on('request', (request: Readonly<Request>) => {
    const path = new URL(request.url()).pathname;
    if (request.method() !== 'GET' && path.startsWith('/api/v1/'))
      writes = [...writes, { method: request.method(), path, body: request.postDataJSON() }];
  });
  await page.goto('/chats?conversation=' + cohort.conversationId);
  await resumed;
  await expect(
    page.getByText('No messages yet. Your accepted request is context, not a human message.', {
      exact: true,
    }),
  ).toBeVisible();
  // No route interception of API/stream: this is actual FastAPI + PostgreSQL and
  // the same canonical application paths as the message API and publisher worker.
  const incomingResponse = await page.request.post(
    'http://127.0.0.1:8768/__fixture/chats/' + cohort.conversationId + '/incoming',
  );
  expect(incomingResponse.status()).toBe(200);
  const messageId = incomingId(await incomingResponse.json());
  const target = '/api/v1/conversations/' + cohort.conversationId;
  const sourceResponse = await page.request.get(target + '/messages');
  expect(sourceResponse.status()).toBe(200);
  const history = checked(await sourceResponse.json(), isHistory);
  const message = required(history.messages.find((item) => item.message_id === messageId));
  const text = required(message.text);
  expect(message.sequence).toBe(1);
  expect(message.author_id).toBe(cohort.personId);
  expect(message.conversation_id).toBe(cohort.conversationId);
  const klDay = (instant: number): number =>
    Math.floor((instant + 8 * 60 * 60 * 1000) / 86_400_000);
  expect(klDay(Date.parse(message.sent_at))).toBe(
    klDay(Date.parse(cohort.conversation.accepted_at)),
  );
  await drainPublication(page);
  const confirmed = page.getByRole('list', { name: 'Confirmed messages' });
  await expect(confirmed.getByText(text, { exact: true })).toBeVisible();
  // Mobile selection intentionally hides the list; verify its canonical DOM projection
  // without requiring a desktop-only region to be visible.
  await expect(
    page.getByLabel('Conversations', { exact: true }).getByText(text, { exact: true }),
  ).toHaveCount(1);
  const displayed = confirmed.locator('time');
  await expect(displayed).toHaveAttribute('datetime', message.sent_at);
  await expect(displayed).toHaveText('Yesterday');
  await expect(displayed).toHaveAttribute(
    'title',
    new RegExp(String(new Date(Date.parse(message.sent_at) + 8 * 60 * 60 * 1000).getUTCFullYear())),
  );
  const detailResponse = await page.request.get(target);
  expect(detailResponse.status()).toBe(200);
  const details = checked(await detailResponse.json(), isConversation);
  expect(details.last_confirmed_sequence).toBe(1);
  expect(details.unread_count).toBe(1);
  expect(details.read_position).toBeNull();
  // This foreground entry records the actual study-prompt visit. It is not a
  // message or a read ACK; reject every additional/misaddressed/malformed write.
  expect(writes).toEqual([{ method: 'POST', path: target + '/study-prompt-visits', body: {} }]);
  await checkpoint('real-incoming-published-without-auto-ack.png');
});
