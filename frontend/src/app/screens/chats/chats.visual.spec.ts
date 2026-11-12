import { assertFullTextFits, assertNaturalWordWrapping } from '../../../../testing/readable-text';
import { assertStudentNavigationInViewport } from '../../../../testing/student-navigation';
import { jpegBase64 } from '../../../../testing/image-fixture';
import type { Page, Request, Route, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import type { Api } from '../../api.generated';
import {
  conversation,
  context,
  currentGoal,
  history,
  identity,
  message,
  page as conversations,
  peer,
  shareReceipt,
  shares,
  summary,
} from './chats.fixtures';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}>;
const threadPath = `/api/v1/conversations/${conversation.conversation_id}`;
async function setup(
  page: Readonly<Page>,
  list: Api['schemas']['ConversationListResponse'] = conversations,
  details: Api['schemas']['ConversationDetailsResponse'] = conversation,
  messages: Api['schemas']['MessageHistoryResponse'] = history,
): Promise<void> {
  await page.clock.setFixedTime(new Date('2026-11-08T06:20:00Z'));
  await page.route('**/api/v1/me', (route: Readonly<Route>) => route.fulfill({ json: identity }));
  await page.route('**/api/v1/conversations?*', (route: Readonly<Route>) =>
    route.fulfill({ json: list }),
  );
  await page.route('**/api/v1/conversations', (route: Readonly<Route>) =>
    route.fulfill({ json: list }),
  );
  await page.route(`**${threadPath}`, (route: Readonly<Route>) => route.fulfill({ json: details }));
  await page.route(`**${threadPath}/image-preparations`, (route: Readonly<Route>) =>
    route.fulfill({ json: { preparations: [] } }),
  );
  await page.route(`**${threadPath}/messages*`, (route: Readonly<Route>) =>
    route.fulfill({ json: messages }),
  );
  await page.route(`**${threadPath}/goal-shares*`, (route: Readonly<Route>) =>
    route.fulfill({ json: shares }),
  );
  await page.route('**/api/v1/me/goal', (route: Readonly<Route>) =>
    route.fulfill({ json: { goal: currentGoal } }),
  );
}
async function open(page: Readonly<Page>, selected = false): Promise<void> {
  await page.goto(`/chats${selected ? `?conversation=${conversation.conversation_id}` : ''}`);
  if (selected)
    await expect(
      page.getByRole('region', { name: 'Selected conversation', exact: true }),
    ).toBeVisible();
  else await expect(page.getByRole('heading', { name: 'Chats', exact: true })).toBeVisible();
}
async function composer(page: Readonly<Page>) {
  const field = page.getByRole('textbox', { name: 'Message', exact: true });
  await expect(field).toBeVisible();
  await page
    .locator('tui-textfield')
    .filter({ has: field })
    .evaluate((element: Readonly<HTMLElement>) => {
      element.scrollIntoView({ block: 'center' });
    });
  return field;
}
type TextMessageBody = Api['schemas']['SendMessageBody'] & Readonly<{ readonly text: string }>;
function submitted(value: unknown): value is TextMessageBody {
  return (
    typeof value === 'object' &&
    value !== null &&
    'client_message_id' in value &&
    typeof value.client_message_id === 'string' &&
    'text' in value &&
    typeof value.text === 'string'
  );
}
function confirmed(body: TextMessageBody): Api['schemas']['ConfirmedOperationResponse'] {
  return {
    operation_id: 'operation',
    conversation_id: conversation.conversation_id,
    client_message_id: body.client_message_id,
    message: {
      ...message,
      message_id: '00000000-0000-4000-8000-000000000041',
      sequence: 2,
      author_id: identity.account_id,
      client_message_id: body.client_message_id,
      text: body.text,
    },
  };
}

async function canonicalMessageReads(
  page: Readonly<Page>,
  stored: () => Api['schemas']['ConfirmedOperationResponse'] | undefined,
): Promise<() => Promise<void>> {
  let historySequence = 1;
  let detailsSequence = 1;
  let listMessageId: string = message.message_id;
  await page.route(`**${threadPath}/messages*`, (route: Readonly<Route>) => {
    if (route.request().method() !== 'GET') return route.fallback();
    const receipt = stored();
    const projection: Api['schemas']['MessageHistoryResponse'] =
      receipt === undefined
        ? history
        : {
            ...history,
            anchor_sequence: receipt.message.sequence,
            messages: [message, receipt.message],
          };
    historySequence = projection.anchor_sequence;
    return route.fulfill({ json: projection });
  });
  await page.route(`**${threadPath}`, (route: Readonly<Route>) => {
    const receipt = stored();
    const projection = { ...conversation, last_confirmed_sequence: receipt?.message.sequence ?? 1 };
    detailsSequence = projection.last_confirmed_sequence;
    return route.fulfill({ json: projection });
  });
  await page.route(/\/api\/v1\/conversations(?:\?.*)?$/, (route: Readonly<Route>) => {
    const latest = stored()?.message ?? message;
    listMessageId = latest.message_id;
    return route.fulfill({
      json: {
        ...conversations,
        conversations: [{ ...summary, last_message: latest, activity_at: latest.sent_at }],
      } satisfies Api['schemas']['ConversationListResponse'],
    });
  });
  return async () => {
    const receipt = stored();
    const latest = receipt?.message ?? message;
    await expect
      .poll(() => ({ historySequence, detailsSequence, listMessageId }))
      .toEqual({
        historySequence: latest.sequence,
        detailsSequence: latest.sequence,
        listMessageId: latest.message_id,
      });
    const items = page.getByRole('list', { name: 'Confirmed messages' }).getByRole('listitem');
    await expect(items).toHaveCount(receipt === undefined ? 1 : 2);
    if (latest.text === null) throw new Error('Expected the actual text-message fixture');
    await expect(items.last()).toContainText(latest.text);
  };
}
function sharedProjection(
  receipt: Api['schemas']['ConversationGoalShareReceiptResponse'],
): Api['schemas']['ConversationGoalSharePageResponse'] {
  const latest = { ...receipt, can_complete: true };
  return {
    ...shares,
    current_context_version: receipt.context_version,
    anchor_version: receipt.context_version,
    latest,
    history: [latest],
  };
}

function releaseHeld(release: (() => void) | undefined): void {
  if (release === undefined) throw new Error('Missing controlled request');
  release();
}
function contextForPeer(personId: string): Api['schemas']['AcademicContextResponse'] {
  const help = context.recipient_help;
  if (help === null) throw new Error('Missing actual-mode fixture help source');
  return { ...context, recipient_help: { ...help, owner_id: personId } };
}
function modeContext(
  mode: 'offer_help' | 'study_together',
): Api['schemas']['AcademicContextResponse'] {
  const goal = context.sender_goal;
  const help = context.recipient_help;
  if (goal === null || help === null) throw new Error('Missing fixture context');
  return mode === 'offer_help'
    ? {
        mode,
        sender_goal: null,
        recipient_help: null,
        sender_help: { ...help, owner_id: identity.account_id },
        recipient_goal: { ...goal, owner_id: peer.person_id },
      }
    : {
        mode,
        sender_goal: { ...goal, shared_learning: true },
        recipient_goal: {
          ...goal,
          goal_id: 'other-goal',
          owner_id: peer.person_id,
          shared_learning: true,
        },
        sender_help: null,
        recipient_help: null,
      };
}

test('C01 actual list unread empty accepted and masked peers', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page, {
    conversations: [
      summary,
      {
        ...summary,
        conversation_id: '00000000-0000-4000-8000-000000000022',
        request_id: '00000000-0000-4000-8000-000000000023',
        peer: {
          ...peer,
          person_id: '00000000-0000-4000-8000-000000000003',
          display_name: 'Jun Park',
        },
        original_context: contextForPeer('00000000-0000-4000-8000-000000000003'),
        last_message: null,
        activity_at: summary.accepted_at,
        unread_count: 0,
      },
      {
        ...summary,
        conversation_id: '00000000-0000-4000-8000-000000000024',
        request_id: '00000000-0000-4000-8000-000000000025',
        original_context: contextForPeer('00000000-0000-4000-8000-000000000004'),
        peer: {
          ...peer,
          person_id: '00000000-0000-4000-8000-000000000004',
          state: 'unavailable',
          display_name: null,
        },
        last_message: null,
        activity_at: summary.accepted_at,
        unread_count: 0,
        can_send: false,
      },
    ],
    next_cursor: null,
  });
  await open(page);
  await expect(page.getByText('1 unread', { exact: true })).toBeVisible();
  await expect(page.getByText('Connected · no messages yet')).toHaveCount(2);
  await expect(page.getByRole('heading', { name: 'Profile unavailable' })).toBeVisible();
  await expect(page.getByText('Read-only conversation')).toBeVisible();
  await assertStudentNavigationInViewport(page, 'Chats');
  await expect(page.locator('app-chats')).toHaveCSS('background-color', 'rgb(250, 246, 239)');
  await expect(page.locator('.conversation-rows')).toHaveCSS(
    'background-color',
    'rgb(255, 255, 255)',
  );
  await expect(page.locator('tui-badge-notification')).toHaveText('1 unread');
  await expect(page.locator('.row-metadata time').first()).toHaveAttribute(
    'datetime',
    summary.activity_at,
  );
  await expect(page.getByRole('link', { name: 'Maya Lim', exact: true })).toHaveAttribute(
    'data-appearance',
    'action-grayscale',
  );
  await checkpoint('chat-list-viewport.png', { fullPage: false });
  await checkpoint('chat-list.png');
  await page.setViewportSize({ width: 320, height: 800 });
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  await assertNaturalWordWrapping(page.getByText('Read-only conversation', { exact: true }));
  const unread = page.locator('tui-badge-notification');
  await assertNaturalWordWrapping(unread);
  await assertFullTextFits(unread);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await checkpoint('chat-list-narrow-text200.png');
});

test('C01 loading then actual empty state has real Requests recovery', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/conversations', async (route: Readonly<Route>) => {
    await held;
    await route.fulfill({ json: { conversations: [], next_cursor: null } });
  });
  await open(page);
  await expect(page.getByText('Loading conversations…')).toBeVisible();
  await checkpoint('chat-list-loading.png');
  releaseHeld(release);
  await expect(page.getByRole('heading', { name: 'No chats yet' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'View requests' })).toHaveAttribute(
    'href',
    '/requests',
  );
  await expect(page.locator('.empty-chats .empty-icon')).toHaveAttribute('aria-hidden', 'true');
  await expect(page.getByRole('link', { name: 'View requests', exact: true })).toHaveAttribute(
    'data-appearance',
    'secondary',
  );
  await checkpoint('chat-list-empty.png');
});

test('C01 confirmed read failure retries explicitly and invalid cursor returns to latest', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let reads = 0;
  await page.route('**/api/v1/conversations', (route: Readonly<Route>) => {
    reads += 1;
    return route.fulfill(
      reads === 1 ? { status: 503, json: { code: 'unavailable' } } : { json: conversations },
    );
  });
  await open(page);
  await expect(page.getByRole('alert')).toContainText('We couldn’t load chats');
  expect(reads).toBe(1);
  await checkpoint('chat-list-error.png');
  await page.getByRole('button', { name: 'Retry chats', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Maya Lim' })).toBeVisible();
  await page.route('**/api/v1/conversations?*', (route: Readonly<Route>) =>
    route.fulfill({ status: 422, json: { code: 'invalid_conversation_cursor' } }),
  );
  await page.goto('/chats?cursor=expired');
  await expect(page.getByRole('alert')).toContainText('This page has expired');
  await checkpoint('chat-cursor-expired.png');
  await page.getByRole('link', { name: 'Latest conversations' }).click();
  await expect(page.getByRole('heading', { name: 'Maya Lim' })).toBeVisible();
  await checkpoint('chat-list-recovered.png');
});

test('C01 opaque list pagination preserves server order', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page, { ...conversations, next_cursor: 'next+/=' });
  await page.route('**/api/v1/conversations?*', (route: Readonly<Route>) => {
    expect(new URL(route.request().url()).searchParams.get('cursor')).toBe('next+/=');
    return route.fulfill({
      json: {
        conversations: [
          {
            ...summary,
            conversation_id: '00000000-0000-4000-8000-000000000070',
            request_id: '00000000-0000-4000-8000-000000000071',
            peer: {
              ...peer,
              person_id: '00000000-0000-4000-8000-000000000003',
              display_name: 'Jun Park',
            },
            original_context: contextForPeer('00000000-0000-4000-8000-000000000003'),
            last_message: {
              ...message,
              conversation_id: '00000000-0000-4000-8000-000000000070',
              author_id: '00000000-0000-4000-8000-000000000003',
              message_id: '00000000-0000-4000-8000-000000000072',
              client_message_id: '00000000-0000-4000-8000-000000000073',
            },
          },
        ],
        next_cursor: null,
      },
    });
  });
  await open(page);
  await page.getByRole('link', { name: 'More conversations' }).click();
  await expect(page).toHaveURL(/cursor=next/);
  await expect(page.getByRole('heading', { name: 'Jun Park' })).toBeVisible();
  await checkpoint('chat-list-next.png');
});

test('C02 confirmed sequence order and original context never ACK on GET', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page, conversations, conversation, {
    ...history,
    anchor_sequence: 2,
    messages: [
      {
        ...message,
        message_id: '00000000-0000-4000-8000-000000000042',
        sequence: 2,
        author_id: identity.account_id,
        text: 'My follow-up',
        sent_at: '2026-11-08T06:11:00Z',
      },
      message,
    ],
  });
  let writes: readonly string[] = [];
  page.on('request', (request: Readonly<Request>) => {
    if (request.method() !== 'GET')
      writes = [...writes, `${request.method()} ${new URL(request.url()).pathname}`];
  });
  await open(page, true);
  await expect(page.getByRole('region', { name: 'Original accepted context' })).toContainText(
    'SQL JOINs',
  );
  await page.getByRole('button', { name: 'Original accepted context', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Original accepted context · read only', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('navigation', { name: 'Student navigation', exact: true }),
  ).toHaveCount(0);
  await checkpoint('thread-original-context.png');
  const items = page.getByRole('list', { name: 'Confirmed messages' }).getByRole('listitem');
  await expect(items).toHaveCount(2);
  await expect(items.nth(0)).toContainText(message.text);
  await expect(items.nth(1)).toContainText('My follow-up');
  await items.nth(1).scrollIntoViewIfNeeded();
  // Opening a thread records its study-prompt visit and mandatory telemetry.
  // Neither authorizes a message write or an implicit read-position ACK.
  const permittedVisits = [
    `POST ${threadPath}/study-prompt-visits`,
    'POST /api/v1/telemetry/events',
  ];
  expect(writes.filter((write) => !permittedVisits.includes(write))).toEqual([]);
  await checkpoint('thread-confirmed-sequence.png');
});

test('C02 empty accepted conversation has no invented greeting or capability', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(
    page,
    {
      ...conversations,
      conversations: [
        { ...summary, last_message: null, activity_at: summary.accepted_at, unread_count: 0 },
      ],
    },
    { ...conversation, last_confirmed_sequence: 0, unread_count: 0 },
    { anchor_sequence: 0, messages: [], next_cursor: null },
  );
  await open(page, true);
  await expect(
    page.getByText('No messages yet. Your accepted request is context, not a human message.'),
  ).toBeVisible();
  await expect(
    page.getByRole('list', { name: 'Confirmed messages' }).getByRole('listitem'),
  ).toHaveCount(0);
  await composer(page);
  await expect(page.getByRole('button', { name: 'Send message', exact: true })).toBeEnabled();
  await checkpoint('thread-empty.png');
});

for (const state of ['unavailable', 'deleted'] as const)
  test(`C02 ${state} masks current identity and respects read-only`, async ({
    page,
    checkpoint,
  }: Scenario) => {
    await setup(
      page,
      {
        ...conversations,
        conversations: [
          {
            ...summary,
            peer: { ...peer, state, display_name: null, photo_version: null },
            can_send: false,
          },
        ],
      },
      {
        ...conversation,
        peer: { ...peer, state, display_name: null, photo_version: null },
        can_send: false,
      },
    );
    await open(page, true);
    await expect(
      page
        .getByRole('heading', {
          name: state === 'deleted' ? 'Deleted account' : 'Profile unavailable',
          exact: true,
        })
        .first(),
    ).toBeVisible();
    await composer(page);
    await expect(page.getByRole('button', { name: 'Send message', exact: true })).toBeDisabled();
    await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toHaveAttribute(
      'readonly',
      '',
    );
    await checkpoint(`thread-${state}.png`);
  });

test('C02 earlier history is URL owned without read ACK', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page, conversations, conversation, { ...history, next_cursor: 'older+/=' });
  await page.route(`**${threadPath}/messages?*`, (route: Readonly<Route>) => {
    expect(new URL(route.request().url()).searchParams.get('cursor')).toBe('older+/=');
    return route.fulfill({
      json: {
        anchor_sequence: 1,
        messages: [{ ...message, text: 'Earlier retained example' }],
        next_cursor: null,
      },
    });
  });
  await open(page, true);
  await (await composer(page)).fill('Retain only this active-thread draft');
  await page.getByRole('link', { name: 'Earlier messages' }).click();
  await expect(page).toHaveURL(/history_cursor=older/);
  await expect(page.getByText('Earlier retained example', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Latest messages' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toHaveValue(
    'Retain only this active-thread draft',
  );
  await checkpoint('thread-earlier-history.png');
});

for (const status of [404, 503])
  test(`C02 selected thread ${status.toString()} recovery is explicit`, async ({
    page,
    checkpoint,
  }: Scenario) => {
    await setup(page);
    let failed = true;
    await page.route(`**${threadPath}`, (route: Readonly<Route>) =>
      route.fulfill(
        failed ? { status, json: { code: 'conversation_unavailable' } } : { json: conversation },
      ),
    );
    await open(page, true);
    await expect(page.getByRole('alert')).toContainText(
      status === 404 ? 'This conversation is unavailable.' : 'We couldn’t load chats.',
    );
    await checkpoint(`thread-error-${status.toString()}.png`);
    failed = false;
    await page.getByRole('button', { name: 'Retry conversation' }).click();
    await expect(page.getByRole('region', { name: 'Original accepted context' })).toBeVisible();
    await checkpoint(`thread-recovered-${status.toString()}.png`);
  });

test('C02 explicit Send keeps raw text and confirmed success rereads canonical messages', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let body: TextMessageBody | undefined;
  let stored: Api['schemas']['ConfirmedOperationResponse'] | undefined;
  const canonical = await canonicalMessageReads(page, () => stored);
  await page.route(`**${threadPath}/messages`, (route: Readonly<Route>) => {
    if (route.request().method() === 'GET') return route.fallback();
    const value: unknown = route.request().postDataJSON();
    if (!submitted(value)) throw new Error('Invalid actual send body');
    body = value;
    expect(value.text).toBe(' My SQL attempt.\nCompare the ON clause. ');
    stored = confirmed(value);
    return route.fulfill({ json: stored });
  });
  await open(page, true);
  const text = await composer(page);
  await text.fill(' My SQL attempt.\nCompare the ON clause. ');
  await checkpoint('message-edited-draft.png');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(
    page.getByText('Message stored. This is not a delivery or read receipt.'),
  ).toBeVisible();
  await expect(text).toHaveValue('');
  expect(body).toBeDefined();
  await canonical();
  await checkpoint('message-stored.png');
});

test('C02 pending send locks duplicate transport and exposes stored-only confirmation', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let sends = 0;
  let stored: Api['schemas']['ConfirmedOperationResponse'] | undefined;
  const canonical = await canonicalMessageReads(page, () => stored);
  await page.route(`**${threadPath}/messages`, async (route: Readonly<Route>) => {
    if (route.request().method() === 'GET') {
      await route.fallback();
      return;
    }
    sends += 1;
    const body: unknown = route.request().postDataJSON();
    if (!submitted(body)) throw new Error('Invalid send');
    await held;
    stored = confirmed(body);
    await route.fulfill({ json: stored });
  });
  await open(page, true);
  const text = await composer(page);
  await text.fill('Check this attempt');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(text).toHaveAttribute('readonly', '');
  await expect(page.getByRole('button', { name: 'Send message', exact: true })).toBeDisabled();
  await expect(page.getByText('Checking message operation…')).toBeVisible();
  expect(sends).toBe(1);
  await checkpoint('message-pending.png');
  releaseHeld(release);
  await expect(text).toHaveValue('');
  await expect(
    page.getByText('Message stored. This is not a delivery or read receipt.'),
  ).toBeVisible();
  await canonical();
  await checkpoint('message-confirmed.png');
});

test('C02 unknown send manually checks unobserved then replays exact body and key', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let original: TextMessageBody | undefined;
  let key: string | undefined;
  let sends = 0;
  let stored: Api['schemas']['ConfirmedOperationResponse'] | undefined;
  const canonical = await canonicalMessageReads(page, () => stored);
  await page.route(`**${threadPath}/messages`, (route: Readonly<Route>) => {
    if (route.request().method() === 'GET') return route.fallback();
    const body: unknown = route.request().postDataJSON();
    if (!submitted(body)) throw new Error('Invalid send');
    sends += 1;
    if (original === undefined) {
      original = body;
      key = route.request().headers()['idempotency-key'];
      return route.fulfill({ status: 503, json: { code: 'unavailable' } });
    }
    expect(body).toEqual(original);
    expect(route.request().headers()['idempotency-key']).toBe(key);
    stored = confirmed(body);
    return route.fulfill({ json: stored });
  });
  await page.route(`**${threadPath}/message-operations/*`, (route: Readonly<Route>) => {
    if (original === undefined) throw new Error('No pending intent');
    return route.fulfill({
      json: {
        conversation_id: conversation.conversation_id,
        client_message_id: original.client_message_id,
        outcome: 'unobserved',
      },
    });
  });
  await open(page, true);
  const text = await composer(page);
  await text.fill(' Keep my original text. ');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('We couldn’t confirm');
  await expect(text).toHaveAttribute('readonly', '');
  expect(sends).toBe(1);
  await checkpoint('message-unknown.png');
  await page.getByRole('button', { name: 'Check message status' }).click();
  await expect(page.getByText('Not observed yet.', { exact: false })).toBeVisible();
  expect(sends).toBe(1);
  await checkpoint('message-unobserved.png');
  await page.getByRole('button', { name: 'Retry same message' }).click();
  await expect(text).toHaveValue('');
  expect(sends).toBe(2);
  await canonical();
  await checkpoint('message-replayed.png');
});

for (const outcome of ['confirmed', 'cancelled'] as const)
  test(`C02 manual cancel may return ${outcome} without inventing deletion`, async ({
    page,
    checkpoint,
  }: Scenario) => {
    await setup(page);
    let original: TextMessageBody | undefined;
    let stored: Api['schemas']['ConfirmedOperationResponse'] | undefined;
    const canonical = await canonicalMessageReads(page, () => stored);
    await page.route(`**${threadPath}/messages`, (route: Readonly<Route>) => {
      if (route.request().method() === 'GET') return route.fallback();
      const body: unknown = route.request().postDataJSON();
      if (!submitted(body)) throw new Error('Invalid send');
      original = body;
      return route.fulfill({ status: 503, json: { code: 'unavailable' } });
    });
    await page.route(`**${threadPath}/message-operations/*/cancel`, (route: Readonly<Route>) => {
      if (original === undefined) throw new Error('No intent');
      expect(route.request().method()).toBe('POST');
      stored = outcome === 'confirmed' ? confirmed(original) : undefined;
      return route.fulfill({
        json: stored ?? {
          operation_id: 'operation',
          conversation_id: conversation.conversation_id,
          client_message_id: original.client_message_id,
          cancelled_at: message.sent_at,
        },
      });
    });
    await open(page, true);
    const text = await composer(page);
    await text.fill('Keep this cancelled text');
    await page.getByRole('button', { name: 'Send message', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('We couldn’t confirm');
    await page.getByRole('button', { name: 'Cancel message intent' }).click();
    await expect(
      page.getByText(
        outcome === 'confirmed'
          ? 'Message stored. This is not a delivery or read receipt.'
          : 'Message intent cancelled. Your text remains editable.',
      ),
    ).toBeVisible();
    await expect(text).toHaveValue(outcome === 'confirmed' ? '' : 'Keep this cancelled text');
    await canonical();
    await checkpoint(`message-cancel-${outcome}.png`);
  });

test('C02 validation preserves Unicode raw input and links actual field errors', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await open(page, true);
  const text = await composer(page);
  await text.focus();
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(page.getByText('Enter a message.', { exact: true })).toBeVisible();
  await expect(text).toBeFocused();
  await checkpoint('message-required.png');
  const long = '😀'.repeat(2001);
  await text.fill(long);
  await text.blur();
  await expect(text).toHaveValue(long);
  await expect(page.getByText('Use at most 2000 characters.', { exact: true })).toBeVisible();
  await checkpoint('message-unicode-limit.png');
  await text.fill('Example\u0000');
  await text.blur();
  await expect(
    page.getByText('Remove unsupported control characters.', { exact: true }),
  ).toBeVisible();
  await checkpoint('message-control-rejected.png');
});

test('C02 private read ACK is explicit and binds displayed confirmed sequence', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let acknowledged = false;
  let writes = 0;
  let listUnread = 1;
  await page.route(/\/api\/v1\/conversations(?:\?.*)?$/, (route: Readonly<Route>) => {
    listUnread = acknowledged ? 0 : 1;
    return route.fulfill({
      json: {
        ...conversations,
        conversations: [{ ...summary, unread_count: listUnread }],
      } satisfies Api['schemas']['ConversationListResponse'],
    });
  });
  await page.route(`**${threadPath}`, (route: Readonly<Route>) =>
    route.fulfill({
      json: acknowledged
        ? {
            ...conversation,
            unread_count: 0,
            read_position: {
              conversation_id: conversation.conversation_id,
              through_sequence: 1,
              acknowledged_at: message.sent_at,
              version: 1,
            },
          }
        : conversation,
    }),
  );
  await page.route(`**${threadPath}/read-position`, (route: Readonly<Route>) => {
    writes += 1;
    expect(route.request().method()).toBe('PUT');
    expect(route.request().postDataJSON()).toEqual({ through_sequence: 1 });
    acknowledged = true;
    return route.fulfill({
      json: {
        conversation_id: conversation.conversation_id,
        through_sequence: 1,
        acknowledged_at: message.sent_at,
        version: 1,
      },
    });
  });
  await open(page, true);
  const item = page.getByRole('list', { name: 'Confirmed messages' }).getByRole('listitem');
  await item.scrollIntoViewIfNeeded();
  const ack = page.getByRole('button', { name: 'Mark read through this message' });
  await expect(ack).toBeEnabled();
  expect(writes).toBe(0);
  await checkpoint('message-visible-not-acked.png');
  await ack.click();
  await expect(ack).toHaveCount(0);
  expect(writes).toBe(1);
  await expect.poll(() => listUnread).toBe(0);
  await expect(page.getByLabel('Conversations', { exact: true })).not.toContainText('1 unread');
  await checkpoint('message-own-read-position.png');
});

test('C02 current401 clears draft and private thread without authorizing another actor', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let expired = false;
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill(
      expired ? { status: 401, json: { code: 'unauthenticated' } } : { json: identity },
    ),
  );
  await page.route(`**${threadPath}/messages`, (route: Readonly<Route>) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: history });
    expired = true;
    return route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
  });
  await open(page, true);
  const text = await composer(page);
  await text.fill('Private unsent text');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(
    page.getByText('Sign in with an eligible student account to view chats.'),
  ).toBeVisible();
  await expect(text).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Continue account', exact: true })).toHaveAttribute(
    'href',
    '/onboarding',
  );
  await expect(page.getByText(message.text, { exact: true })).toHaveCount(0);
  await checkpoint('chat-session-expired.png');
});

test('C04 sharing requires explicit current-source review and retains original accepted context', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let shared = false;
  let writes = 0;
  await page.route(`**${threadPath}/goal-shares`, (route: Readonly<Route>) => {
    if (route.request().method() === 'GET')
      return route.fulfill({
        json: shared ? sharedProjection(shareReceipt) : shares,
      });
    writes += 1;
    expect(route.request().postDataJSON()).toEqual({
      goal_id: currentGoal.id,
      expected_goal_version: currentGoal.version,
      expected_context_version: 0,
    });
    shared = true;
    return route.fulfill({ json: shareReceipt });
  });
  await open(page, true);
  await page.getByRole('button', { name: 'View shared goals' }).click();
  await expect(page.getByRole('region', { name: 'Your current goal' })).toContainText(
    'Transactions',
  );
  expect(writes).toBe(0);
  await checkpoint('goal-share-current.png');
  await page.getByRole('button', { name: 'Review current goal for sharing' }).click();
  await expect(
    page.getByText(
      'Share this goal version as a separate context? The original request stays unchanged.',
    ),
  ).toBeVisible();
  expect(writes).toBe(0);
  await checkpoint('goal-share-reviewed.png');
  await page.getByRole('button', { name: 'Share reviewed goal' }).click();
  await expect(page.getByText('Goal share stored. Original context unchanged.')).toBeVisible();
  await expect(page.getByRole('region', { name: 'Latest shared goal' })).toContainText(
    'Transactions',
  );
  await expect(page.getByRole('region', { name: 'Original accepted context' })).toContainText(
    'SQL JOINs',
  );
  expect(writes).toBe(1);
  await checkpoint('goal-share-stored.png');
});

test('C04 unknown share retains exact reviewed intent for explicit replay', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let original: string | null = null;
  let key: string | undefined;
  let writes = 0;
  let readVersion = 0;
  await page.route(`**${threadPath}/goal-shares`, (route: Readonly<Route>) => {
    if (route.request().method() === 'GET') {
      const projection = writes >= 2 ? sharedProjection(shareReceipt) : shares;
      readVersion = projection.current_context_version;
      return route.fulfill({ json: projection });
    }
    writes += 1;
    if (writes === 1) {
      original = route.request().postData();
      key = route.request().headers()['idempotency-key'];
      return route.fulfill({ status: 503, json: { code: 'unavailable' } });
    }
    expect(route.request().postData()).toBe(original);
    expect(route.request().headers()['idempotency-key']).toBe(key);
    return route.fulfill({ json: shareReceipt });
  });
  await open(page, true);
  await page.getByRole('button', { name: 'View shared goals' }).click();
  await page.getByRole('button', { name: 'Review current goal for sharing' }).click();
  await page.getByRole('button', { name: 'Share reviewed goal' }).click();
  await expect(page.getByRole('alert')).toContainText(
    'We couldn’t confirm whether this goal was shared',
  );
  await checkpoint('goal-share-unknown.png');
  await page.getByRole('button', { name: 'Retry same goal share' }).click();
  await expect(page.getByText('Goal share stored. Original context unchanged.')).toBeVisible();
  expect(writes).toBe(2);
  await expect.poll(() => readVersion).toBe(shareReceipt.context_version);
  await expect(page.getByRole('region', { name: 'Latest shared goal' })).toContainText(
    'Transactions',
  );
  await checkpoint('goal-share-replayed.png');
});

test('C02 keyboard and 320px text200 retain usable controls and explicit multiline send', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  await setup(page);
  await page.setViewportSize({ width: 320, height: 800 });
  await open(page, true);
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  const text = await composer(page);
  await text.fill('First line');
  await text.press('Shift+Enter');
  await text.press('End');
  await text.pressSequentially('Second line');
  await expect(text).toHaveValue('First line\nSecond line');
  await expect(page.getByRole('button', { name: 'Send message', exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await checkpoint('chat-320-text200.png', { fullPage: false });
  await page.setViewportSize({ width: 320, height: 420 });
  const field = page.locator('tui-textfield').filter({ has: text });
  const send = page.getByRole('button', { name: 'Send message', exact: true });
  const count = page.getByLabel('Message character count', { exact: true });
  await info.attach('keyboard-layout-before-natural-scroll', {
    body: JSON.stringify({
      viewport: page.viewportSize(),
      field: await field.boundingBox(),
      send: await send.boundingBox(),
      count: await count.boundingBox(),
    }),
    contentType: 'application/json',
  });
  // The optional image controls precede the typing controls. Centreing their
  // entire form can clip the field; normal document scroll can expose the full
  // native typing group without changing production geometry or hiding controls.
  await field.evaluate((element: Readonly<HTMLElement>) => {
    element.scrollIntoView({ block: 'start' });
  });
  await info.attach('keyboard-layout-after-natural-scroll', {
    body: JSON.stringify({
      viewport: page.viewportSize(),
      field: await field.boundingBox(),
      send: await send.boundingBox(),
      count: await count.boundingBox(),
    }),
    contentType: 'application/json',
  });
  await expect(page.locator('tui-textfield').filter({ has: text })).toBeInViewport({ ratio: 1 });
  await expect(page.getByRole('button', { name: 'Send message', exact: true })).toBeInViewport({
    ratio: 1,
  });
  await expect(page.getByLabel('Message character count', { exact: true })).toBeInViewport({
    ratio: 1,
  });
  await expect(text).toBeFocused();
  await expect(text).toHaveValue('First line\nSecond line');
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await checkpoint('chat-keyboard-height.png', { fullPage: false });
});

for (const mode of ['offer_help', 'study_together'] as const)
  test(`C02 ${mode} retained academic context is attributed without teaching claims`, async ({
    page,
    checkpoint,
  }: Scenario) => {
    const source = modeContext(mode);
    await setup(page, conversations, { ...conversation, original_context: source });
    await open(page, true);
    const region = page.getByRole('region', { name: 'Original accepted context' });
    await expect(region).toContainText(
      mode === 'offer_help' ? 'Sender’s help subject' : 'neither person is presented as a teacher',
    );
    await page.getByRole('button', { name: 'Original accepted context', exact: true }).click();
    await expect(
      page.getByRole('heading', { name: 'Original accepted context · read only', exact: true }),
    ).toBeVisible();
    await checkpoint(`thread-${mode}-context.png`);
  });

test('C04 changed source requires explicit refresh and renewed version review', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let changed = false;
  let stored: Api['schemas']['ConversationGoalShareReceiptResponse'] | undefined;
  let readVersion = 0;
  const previous = {
    ...shareReceipt,
    share_id: '00000000-0000-4000-8000-000000000052',
    context_version: 2,
    can_complete: false,
  };
  await page.route('**/api/v1/me/goal', (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        goal: changed
          ? { ...currentGoal, version: 3, topic: 'Newer transactions source' }
          : currentGoal,
      },
    }),
  );
  await page.route(`**${threadPath}/goal-shares`, (route: Readonly<Route>) => {
    if (route.request().method() === 'GET') {
      const projection =
        stored !== undefined
          ? sharedProjection(stored)
          : changed
            ? {
                ...shares,
                current_context_version: 2,
                anchor_version: 2,
                latest: previous,
                history: [previous],
              }
            : shares;
      readVersion = projection.current_context_version;
      return route.fulfill({ json: projection });
    }
    if (!changed) {
      changed = true;
      return route.fulfill({ status: 409, json: { code: 'goal_context_changed' } });
    }
    expect(route.request().postDataJSON()).toEqual({
      goal_id: currentGoal.id,
      expected_goal_version: 3,
      expected_context_version: 2,
    });
    stored = {
      ...shareReceipt,
      context_version: 3,
      source: { ...shareReceipt.source, version: 3, topic: 'Newer transactions source' },
    };
    return route.fulfill({ json: stored });
  });
  await open(page, true);
  await page.getByRole('button', { name: 'View shared goals' }).click();
  await page.getByRole('button', { name: 'Review current goal for sharing' }).click();
  await page.getByRole('button', { name: 'Share reviewed goal' }).click();
  await expect(page.getByRole('alert')).toContainText('The goal or shared context changed.');
  await checkpoint('goal-share-conflict.png');
  await page.getByRole('button', { name: 'Refresh shared goals' }).click();
  await expect(
    page.getByText('The reviewed source changed. Review the current goal again before sharing.'),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Share reviewed goal' })).toHaveCount(0);
  await checkpoint('goal-share-changed-review.png');
  await page.getByRole('button', { name: 'Review current goal for sharing' }).click();
  await page.getByRole('button', { name: 'Share reviewed goal' }).click();
  await expect(page.getByText('Goal share stored. Original context unchanged.')).toBeVisible();
  await expect.poll(() => readVersion).toBe(3);
  await expect(page.getByRole('region', { name: 'Latest shared goal' })).toContainText(
    'Newer transactions source',
  );
  await checkpoint('goal-share-new-version.png');
});

test('C04 historical share cursor and absent current goal do not fabricate completion actions', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route('**/api/v1/me/goal', (route: Readonly<Route>) =>
    route.fulfill({ json: { goal: null } }),
  );
  const latest = {
    ...shareReceipt,
    share_id: '00000000-0000-4000-8000-000000000052',
    context_version: 2,
    can_complete: false,
  };
  const earlier = {
    ...shareReceipt,
    can_complete: false,
    source: { ...shareReceipt.source, version: 1, topic: 'Earlier transaction examples' },
  };
  await page.route(`**${threadPath}/goal-shares*`, (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...shares,
        anchor_version: 2,
        current_context_version: 2,
        latest,
        history: new URL(route.request().url()).searchParams.has('cursor') ? [earlier] : [latest],
        next_cursor: new URL(route.request().url()).searchParams.has('cursor') ? null : 'older+/=',
      },
    }),
  );
  await open(page, true);
  await page.getByRole('button', { name: 'View shared goals' }).click();
  await expect(page.getByText('You have no current goal to share.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Review current goal for sharing' })).toHaveCount(
    0,
  );
  await checkpoint('shared-goals-readonly-history.png');
  await page.getByRole('link', { name: 'Earlier shared goals' }).click();
  await expect(page).toHaveURL(/share_cursor=older/);
  await expect(page.getByRole('link', { name: 'Latest shared goals' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Historical shared goal' })).toContainText(
    'Earlier transaction examples',
  );
  await expect(page.getByRole('region', { name: 'Historical shared goal' })).toContainText(
    'Retained context version 1',
  );
  await expect(page.getByRole('region', { name: 'Latest shared goal' })).toContainText(
    'context version 2',
  );
  await checkpoint('shared-goals-earlier-page.png');
});

test('C02 actual chat avatar grant retries without Discovery/profile requests', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(
    page,
    { ...conversations, conversations: [{ ...summary, peer: { ...peer, photo_version: 1 } }] },
    { ...conversation, peer: { ...peer, photo_version: 1 } },
  );
  let failed = true;
  let foreignRequests = 0;
  page.on('request', (request: Readonly<Request>) => {
    if (new URL(request.url()).pathname.startsWith('/api/v1/people')) foreignRequests += 1;
  });
  await page.route(`**${threadPath}/participant/avatar/1`, (route: Readonly<Route>) =>
    route.fulfill(
      failed
        ? { status: 503, json: { code: 'unavailable' } }
        : { contentType: 'image/jpeg', body: Buffer.from(jpegBase64, 'base64') },
    ),
  );
  await open(page, true);
  const thread = page.getByRole('region', { name: 'Selected conversation' });
  await expect(thread.getByText('Chat photo unavailable.')).toBeVisible();
  await checkpoint('chat-photo-unavailable.png');
  failed = false;
  await thread.getByRole('button', { name: 'Retry chat photo' }).click();
  const image = thread.getByRole('img', { name: 'Current chat participant photo' });
  await expect(image).toBeVisible();
  await expect(image).toHaveJSProperty('naturalWidth', 2);
  expect(foreignRequests).toBe(0);
  await checkpoint('chat-photo-current.png');
});

test('C02 SPA selection navigation destroys its one private draft without a send', async ({
  page,
  checkpoint,
}: Scenario) => {
  const otherId = '00000000-0000-4000-8000-000000000060';
  const otherPeer = {
    ...peer,
    person_id: '00000000-0000-4000-8000-000000000003',
    display_name: 'Jun Park',
  };
  const source = contextForPeer(otherPeer.person_id);
  await setup(page, {
    ...conversations,
    conversations: [
      summary,
      {
        ...summary,
        conversation_id: otherId,
        request_id: '00000000-0000-4000-8000-000000000061',
        peer: otherPeer,
        original_context: source,
        last_message: null,
        activity_at: summary.accepted_at,
        unread_count: 0,
      },
    ],
  });
  await page.route(`**/api/v1/conversations/${otherId}`, (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...conversation,
        conversation_id: otherId,
        request_id: '00000000-0000-4000-8000-000000000061',
        peer: otherPeer,
        original_context: source,
        last_confirmed_sequence: 0,
        unread_count: 0,
      },
    }),
  );
  await page.route(`**/api/v1/conversations/${otherId}/messages`, (route: Readonly<Route>) =>
    route.fulfill({ json: { messages: [], next_cursor: null, anchor_sequence: 0 } }),
  );
  let writes: readonly Readonly<{
    readonly method: string;
    readonly path: string;
    readonly body: unknown;
  }>[] = [];
  let loads = 0;
  page.on('request', (request: Readonly<Request>) => {
    if (request.method() !== 'GET')
      writes = [
        ...writes,
        {
          method: request.method(),
          path: new URL(request.url()).pathname,
          body: request.postDataJSON(),
        },
      ];
  });
  await open(page, true);
  page.on('load', () => {
    loads += 1;
  });
  await (await composer(page)).fill('Private draft for Maya only');
  await checkpoint('thread-private-active-draft.png');
  await page.getByRole('link', { name: 'Back to chats', exact: true }).click();
  await page.getByRole('link', { name: 'Jun Park', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`conversation=${otherId}`));
  await expect(await composer(page)).toHaveValue('');
  await expect(page.getByText('Private draft for Maya only', { exact: true })).toHaveCount(0);
  // A genuine study-prompt visit is not a message send or a read ACK. Account
  // for its exact empty protocol body while rejecting every other mutation.
  expect(writes).toEqual([
    {
      method: 'POST',
      path: `/api/v1/conversations/${conversation.conversation_id}/study-prompt-visits`,
      body: {},
    },
    { method: 'POST', path: `/api/v1/conversations/${otherId}/study-prompt-visits`, body: {} },
  ]);
  expect(loads).toBe(0);
  await checkpoint('thread-selection-draft-cleared.png');
  await page.getByRole('link', { name: 'Back to chats', exact: true }).click();
  await page.getByRole('link', { name: 'Maya Lim', exact: true }).click();
  await expect(await composer(page)).toHaveValue('');
  await expect.poll(() => writes.length).toBe(3);
  expect(writes).toEqual([
    {
      method: 'POST',
      path: `/api/v1/conversations/${conversation.conversation_id}/study-prompt-visits`,
      body: {},
    },
    { method: 'POST', path: `/api/v1/conversations/${otherId}/study-prompt-visits`, body: {} },
    {
      method: 'POST',
      path: `/api/v1/conversations/${conversation.conversation_id}/study-prompt-visits`,
      body: {},
    },
  ]);
  expect(loads).toBe(0);
  await checkpoint('thread-original-draft-not-restored.png');
});

test('C01 image-only preview is truthful and opening the list does not fetch an attachment or ACK it', async ({
  page,
  checkpoint,
}: Scenario) => {
  let privateReads = 0;
  let writes = 0;
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.includes('/images/')) privateReads += 1;
    if (request.method() !== 'GET' && url.pathname.startsWith('/api/')) writes += 1;
  });
  await setup(page, {
    ...conversations,
    conversations: [
      {
        ...summary,
        last_message: { ...message, text: null, image_id: '00000000-0000-4000-8000-000000000080' },
      },
    ],
  });
  await open(page);
  await expect(page.getByText('Image', { exact: true })).toBeVisible();
  await expect(page.getByText('1 unread', { exact: true })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toHaveCount(0);
  expect(privateReads).toBe(0);
  expect(writes).toBe(0);
  await checkpoint('image-only-list-no-private-fetch.png');
});
