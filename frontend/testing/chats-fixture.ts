import { expect } from './visual';
import type { Page } from '@playwright/test';
import type { Api } from '../src/app/api.generated';
import { isConversation, isHistory } from '../src/app/screens/chats/chats-contract';
import { isControlledPeople } from './controlled-people';

// Loopback test driver: credentials are installed only as the actual HTTP-only cookie.
export async function prepareChatsFixture(
  page: Readonly<Page>,
  scenario:
    | 'empty'
    | 'messages'
    | 'goal-change'
    | 'deletion-messages'
    | 'deletion-goal-change'
    | 'stream'
    | 'image-pipeline'
    | 'image-recovery'
    | 'image-cancel'
    | 'image-report'
    | 'image-finalize-unknown'
    | 'image-auth-pause',
  project: string,
): Promise<{
  readonly viewerId: string;
  readonly personId: string;
  readonly conversationId: string;
  readonly conversation: Api['schemas']['ConversationDetailsResponse'];
  readonly history: Api['schemas']['MessageHistoryResponse'];
  readonly browserTime: string;
  readonly usePeer: () => Promise<void>;
}> {
  if (!/^(chromium-mobile|webkit-mobile|chromium-desktop)$/.test(project))
    throw new Error('Invalid controlled chat project');
  const response = await page.request.post('http://127.0.0.1:8768/__fixture/chats', {
    data: { namespace: `chats/${scenario}/${project}` },
  });
  expect(response.status()).toBe(201);
  const value: unknown = await response.json();
  if (
    !isControlledPeople(value) ||
    !('conversation_id' in value) ||
    typeof value.conversation_id !== 'string' ||
    !/^[a-f0-9-]{36}$/.test(value.conversation_id)
  )
    throw new Error('Invalid controlled chat cohort');
  await page.context().addCookies([
    {
      name: value.cookie_name,
      value: value.viewer_session,
      url: value.origin,
      httpOnly: true,
      secure: true,
      sameSite: 'Lax',
    },
  ]);
  // Actual API reads do not ACK messages. Keep the authoritative timestamps for
  // exact DOM/sequence assertions independently of the age-aware screenshot label.
  const target = `${value.origin}/api/v1/conversations/${value.conversation_id}`;
  const [detailsResponse, historyResponse] = await Promise.all([
    page.request.get(target),
    page.request.get(`${target}/messages`),
  ]);
  expect(detailsResponse.status()).toBe(200);
  expect(historyResponse.status()).toBe(200);
  const conversation: unknown = await detailsResponse.json();
  const history: unknown = await historyResponse.json();
  if (
    !isConversation(conversation) ||
    !isHistory(history) ||
    conversation.conversation_id !== value.conversation_id ||
    history.messages.some((message) => message.conversation_id !== value.conversation_id)
  )
    throw new Error('Invalid actual chat source');
  const instants = [
    Date.parse(conversation.accepted_at),
    ...history.messages.map((message) => Date.parse(message.sent_at)),
  ];
  const latest = Math.max(...instants);
  // The scenario is specifically yesterday presentation. Assert this fixture
  // prerequisite, including the real KL date, instead of masking divergent dates.
  const sourceDay = Math.floor((latest + 8 * 60 * 60 * 1000) / 86_400_000);
  expect(
    instants.every(
      (instant) =>
        Number.isFinite(instant) &&
        Math.floor((instant + 8 * 60 * 60 * 1000) / 86_400_000) === sourceDay,
    ),
  ).toBe(true);
  const local = new Date(latest + 8 * 60 * 60 * 1000);
  // Noon on the next KL calendar day; only the browser wall clock changes.
  // Server sessions, expiry, freshness, canonical events and SQL remain real-time.
  const browserTime = new Date(
    Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate() + 1, 4),
  ).toISOString();
  await page.clock.setFixedTime(new Date(browserTime));
  return {
    viewerId: value.viewer_id,
    personId: value.peer_id,
    conversationId: value.conversation_id,
    conversation,
    history,
    browserTime,
    // The driver switches only its synthetic participant. Credentials never
    // enter application JavaScript, URLs, query state or persistent storage.
    usePeer: () =>
      page.context().addCookies([
        {
          name: value.cookie_name,
          value: value.peer_session,
          url: value.origin,
          httpOnly: true,
          secure: true,
          sameSite: 'Lax',
        },
      ]),
  };
}
