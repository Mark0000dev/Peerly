import type { APIResponse, Page, Response, Route, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { prepareChatsFixture } from '../../../../testing/chats-fixture';
import type { Api } from '../../api.generated';
import { absoluteChatTime } from './chats-date';
import { isConversation, isHistory, isReadPosition, orderedMessages } from './chats-contract';
import { isOperation, isTerminalOperation } from './message-contract';
import { isOwnGoal, isShareReceipt, isShares } from './goal-share-contract';

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
function checked<T>(value: unknown, guard: (value: unknown) => value is T): T {
  if (!guard(value)) throw new Error('Invalid actual chat response');
  return value;
}
function ownGoal(value: unknown): Api['schemas']['GoalResponse'] {
  if (!isOwnGoal(value) || value.goal === null) throw new Error('Actual current goal missing');
  return value.goal;
}
function latestMessage(
  messages: readonly Api['schemas']['MessageResponse'][],
): Api['schemas']['MessageResponse'] {
  const item = orderedMessages(messages).at(-1);
  if (item === undefined) throw new Error('Expected actual confirmed history');
  return item;
}
function messageText(value: Api['schemas']['MessageResponse']): string {
  if (value.text === null) throw new Error('Expected the actual text-message source');
  return value.text;
}
function confirmed(value: unknown): Api['schemas']['ConfirmedOperationResponse'] {
  if (!isTerminalOperation(value) || !('message' in value))
    throw new Error('Expected actual confirmed message operation');
  return value;
}
function sameKualaLumpurDate(actual: string, reference: string): void {
  const day = (value: string): number =>
    Math.floor((Date.parse(value) + 8 * 60 * 60 * 1000) / 86_400_000);
  expect(day(actual)).toBe(day(reference));
}
async function exactTimes(page: Readonly<Page>, values: readonly string[]): Promise<void> {
  for (const value of values) {
    const time = page
      .locator('time')
      .filter({ hasText: 'Yesterday' })
      .and(page.locator(`time[datetime="${value}"]`));
    await expect(time.first()).toHaveAttribute('datetime', value);
    await expect(time.first()).toHaveAttribute('title', absoluteChatTime(value));
    await expect(time.first()).toHaveText('Yesterday');
  }
}
async function field(page: Readonly<Page>) {
  const text = page.getByRole('textbox', { name: 'Message', exact: true });
  await expect(text).toBeVisible();
  await page
    .locator('tui-textfield')
    .filter({ has: text })
    .evaluate((element: Readonly<HTMLElement>) => {
      element.scrollIntoView({ block: 'center' });
    });
  return text;
}
async function send(
  page: Readonly<Page>,
  text: string,
): Promise<Api['schemas']['ConfirmedOperationResponse']> {
  await (await field(page)).fill(text);
  const response = page.waitForResponse(
    (item) =>
      new URL(item.url()).pathname.endsWith('/messages') && item.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  return confirmed(await actual(await response));
}
async function loseCommittedReply(
  page: Readonly<Page>,
  target: string,
  text: string,
): Promise<Api['schemas']['ConfirmedOperationResponse']> {
  let receipt: Api['schemas']['ConfirmedOperationResponse'] | undefined;
  const pattern = `**${target}/messages`;
  const listener: (route: Readonly<Route>) => Promise<void> = async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    const response = await route.fetch();
    receipt = confirmed(await actual(response));
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ code: 'unavailable' }),
    });
    await page.unroute(pattern, listener);
  };
  await page.route(pattern, listener);
  await (await field(page)).fill(text);
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText(
    'We couldn’t confirm whether this message was stored',
  );
  if (receipt === undefined) throw new Error('No committed upstream receipt');
  return receipt;
}

test('real C02 empty accepted thread explicit text lost-reply lookup and cancellation race', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareChatsFixture(page, 'empty', info.project.name);
  const target = `/api/v1/conversations/${seed.conversationId}`;
  await page.goto(`/chats?conversation=${seed.conversationId}`);
  await expect(
    page.getByText('No messages yet. Your accepted request is context, not a human message.'),
  ).toBeVisible();
  await exactTimes(page, [seed.conversation.accepted_at]);
  await checkpoint('real-chat-empty.png');
  const first = await send(
    page,
    ' I tried the LEFT JOIN example.\nCould we compare the ON clause? ',
  );
  expect(first.message.author_id).toBe(seed.viewerId);
  expect(first.message.sequence).toBe(1);
  expect(first.message.text).toBe(
    ' I tried the LEFT JOIN example.\nCould we compare the ON clause? ',
  );
  sameKualaLumpurDate(first.message.sent_at, seed.conversation.accepted_at);
  await expect(
    page.getByRole('list', { name: 'Confirmed messages' }).getByRole('listitem'),
  ).toHaveCount(1);
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toHaveValue('');
  await exactTimes(page, [first.message.sent_at]);
  await checkpoint('real-message-stored.png');
  const lost = await loseCommittedReply(
    page,
    target,
    'This reply commits before the confirmation is lost.',
  );
  sameKualaLumpurDate(lost.message.sent_at, seed.conversation.accepted_at);
  expect(lost.message.sequence).toBe(2);
  await checkpoint('real-message-unknown.png');
  const checkedResponse = page.waitForResponse(
    (item) =>
      new URL(item.url()).pathname === `${target}/message-operations/${lost.client_message_id}`,
  );
  await page.getByRole('button', { name: 'Check message status' }).click();
  const lookup = await actual(await checkedResponse);
  expect(isOperation(lookup)).toBe(true);
  expect(confirmed(lookup).message.message_id).toBe(lost.message.message_id);
  await expect(
    page.getByRole('list', { name: 'Confirmed messages' }).getByRole('listitem'),
  ).toHaveCount(2);
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toHaveValue('');
  await exactTimes(page, [lost.message.sent_at]);
  await checkpoint('real-message-lookup-confirmed.png');
  const racing = await loseCommittedReply(
    page,
    target,
    'Cancellation must not delete an already stored message.',
  );
  expect(racing.message.sequence).toBe(3);
  sameKualaLumpurDate(racing.message.sent_at, seed.conversation.accepted_at);
  const cancelled = page.waitForResponse(
    (item) =>
      new URL(item.url()).pathname ===
      `${target}/message-operations/${racing.client_message_id}/cancel`,
  );
  await page.getByRole('button', { name: 'Cancel message intent' }).click();
  const result = confirmed(await actual(await cancelled));
  expect(result.message.message_id).toBe(racing.message.message_id);
  await expect(
    page.getByRole('list', { name: 'Confirmed messages' }).getByRole('listitem'),
  ).toHaveCount(3);
  await exactTimes(page, [racing.message.sent_at]);
  await checkpoint('real-message-cancel-race-stored.png');
  const stored = checked(await actual(await page.request.get(`${target}/messages`)), isHistory);
  expect(stored.messages).toHaveLength(3);
  expect(new Set(stored.messages.map((item) => item.message_id)).size).toBe(3);
  expect(orderedMessages(stored.messages).map((item) => item.sequence)).toEqual([1, 2, 3]);
});

test('real C01 C02 private displayed read ACK and explicit current-goal share', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareChatsFixture(page, 'messages', info.project.name);
  const target = `/api/v1/conversations/${seed.conversationId}`;
  expect(seed.history.messages).toHaveLength(2);
  expect(new Set(seed.history.messages.map((item) => item.author_id)).size).toBe(2);
  await page.goto('/chats');
  await expect(page.getByRole('heading', { name: 'Chats', exact: true })).toBeVisible();
  await exactTimes(page, [latestMessage(seed.history.messages).sent_at]);
  await checkpoint('real-chat-list-human-messages.png');
  await page
    .getByRole('region', { name: 'Conversations' })
    .locator(`a[href*="conversation=${seed.conversationId}"]`)
    .click();
  await expect(page).toHaveURL(new RegExp(`conversation=${seed.conversationId}`));
  await expect(
    page.getByRole('list', { name: 'Confirmed messages' }).getByRole('listitem'),
  ).toHaveCount(2);
  await exactTimes(page, [
    seed.conversation.accepted_at,
    ...seed.history.messages.map((item) => item.sent_at),
  ]);
  const untouched = checked(await actual(await page.request.get(target)), isConversation);
  expect(untouched.read_position).toEqual(seed.conversation.read_position);
  const latest = latestMessage(seed.history.messages);
  const rendered = page
    .getByRole('list', { name: 'Confirmed messages' })
    .getByRole('listitem')
    .filter({ hasText: messageText(latest) });
  await rendered.scrollIntoViewIfNeeded();
  await checkpoint('real-chat-visible-no-ack.png');
  const ack = page.waitForResponse(
    (item) => new URL(item.url()).pathname === `${target}/read-position`,
  );
  await rendered.getByRole('button', { name: 'Mark read through this message' }).click();
  const position = checked(await actual(await ack), isReadPosition);
  expect(position.through_sequence).toBe(latest.sequence);
  expect(position.conversation_id).toBe(seed.conversationId);
  await expect(rendered.getByRole('button')).toHaveCount(0);
  await checkpoint('real-chat-private-read-position.png');
  await page.getByRole('button', { name: 'View shared goals' }).click();
  const goal = ownGoal(await actual(await page.request.get('/api/v1/me/goal')));
  const source = checked(await actual(await page.request.get(`${target}/goal-shares`)), isShares);
  await page.getByRole('button', { name: 'Review current goal for sharing' }).click();
  await expect(
    page.getByText(
      'Share this goal version as a separate context? The original request stays unchanged.',
    ),
  ).toBeVisible();
  await checkpoint('real-chat-goal-reviewed.png');
  const shared = page.waitForResponse(
    (item) =>
      new URL(item.url()).pathname === `${target}/goal-shares` &&
      item.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Share reviewed goal' }).click();
  const receipt = checked(await actual(await shared), isShareReceipt);
  expect(receipt.source.goal_id).toBe(goal.id);
  expect(receipt.source.version).toBe(goal.version);
  expect(receipt.context_version).toBe(source.current_context_version + 1);
  await expect(page.getByRole('region', { name: 'Latest shared goal' })).toContainText(
    goal.subject.label,
  );
  await checkpoint('real-chat-goal-shared.png');
  const retained = checked(await actual(await page.request.get(target)), isConversation);
  expect(retained.original_context).toEqual(seed.conversation.original_context);
});

interface LostShare {
  readonly receipt: Api['schemas']['ConversationGoalShareReceiptResponse'];
  readonly body: string;
  readonly key: string;
}
async function loseShareReply(page: Readonly<Page>, target: string): Promise<LostShare> {
  let original: LostShare | undefined;
  const pattern = `**${target}/goal-shares`;
  const listener: (route: Readonly<Route>) => Promise<void> = async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    const body = route.request().postData();
    const key = route.request().headers()['idempotency-key'];
    if (body === null || key === undefined) throw new Error('Missing actual share intent');
    const receipt = checked(await actual(await route.fetch()), isShareReceipt);
    original = { receipt, body, key };
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ code: 'unavailable' }),
    });
    await page.unroute(pattern, listener);
  };
  await page.route(pattern, listener);
  await page.getByRole('button', { name: 'Share reviewed goal' }).click();
  await expect(page.getByRole('alert')).toContainText(
    'We couldn’t confirm whether this goal was shared.',
  );
  if (original === undefined) throw new Error('No committed actual share');
  return original;
}
function originalGoal(
  context: Api['schemas']['AcademicContextResponse'],
  owner: string,
): Api['schemas']['GoalContextResponse'] {
  const goal = [context.sender_goal, context.recipient_goal].find(
    (item) => item?.owner_id === owner,
  );
  if (goal === undefined || goal === null) throw new Error('Actual original owned goal missing');
  return goal;
}

test('real C04 newer goal explicit review lost-reply replay preserves immutable accepted baseline', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareChatsFixture(page, 'goal-change', info.project.name);
  const target = `/api/v1/conversations/${seed.conversationId}`;
  const current = ownGoal(await actual(await page.request.get('/api/v1/me/goal')));
  const original = originalGoal(seed.conversation.original_context, seed.viewerId);
  expect(current.id).toBe(original.goal_id);
  expect(current.version).toBeGreaterThan(original.version);
  await page.goto(`/chats?conversation=${seed.conversationId}`);
  await exactTimes(page, [seed.conversation.accepted_at]);
  await page.getByRole('button', { name: 'View shared goals' }).click();
  await expect(page.getByRole('region', { name: 'Your current goal' })).toContainText(
    current.subject.label,
  );
  await checkpoint('real-goal-source-changed.png');
  await page.getByRole('button', { name: 'Review current goal for sharing' }).click();
  await expect(
    page.getByText(
      'Share this goal version as a separate context? The original request stays unchanged.',
    ),
  ).toBeVisible();
  await checkpoint('real-newer-goal-reviewed.png');
  const lost = await loseShareReply(page, target);
  expect(lost.receipt.source.version).toBe(current.version);
  expect(lost.receipt.source.goal_id).toBe(current.id);
  await checkpoint('real-goal-share-unknown.png');
  const replay = page.waitForResponse(
    (item) =>
      new URL(item.url()).pathname === `${target}/goal-shares` &&
      item.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Retry same goal share' }).click();
  const response = await replay;
  expect(response.request().postData()).toBe(lost.body);
  expect(response.request().headers()['idempotency-key']).toBe(lost.key);
  const receipt = checked(await actual(response), isShareReceipt);
  expect(receipt.share_id).toBe(lost.receipt.share_id);
  expect(receipt.context_version).toBe(lost.receipt.context_version);
  await expect(page.getByText('Goal share stored. Original context unchanged.')).toBeVisible();
  await checkpoint('real-goal-share-replayed.png');
  const canonical = checked(
    await actual(await page.request.get(`${target}/goal-shares`)),
    isShares,
  );
  expect(canonical.latest?.share_id).toBe(receipt.share_id);
  expect(canonical.current_context_version).toBe(receipt.context_version);
  const retained = checked(await actual(await page.request.get(target)), isConversation);
  expect(retained.original_context).toEqual(seed.conversation.original_context);
  const messages = checked(await actual(await page.request.get(`${target}/messages`)), isHistory);
  expect(messages.messages).toEqual(seed.history.messages);
});
