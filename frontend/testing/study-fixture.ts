import type { Page } from '@playwright/test';
import { expect } from './visual';

export type StudyCohort = Readonly<{
  readonly actorId: string;
  readonly peerId: string;
  readonly conversationId: string;
  readonly requestId: string;
  readonly messageCount: number;
  readonly readPeerFeedback: () => Promise<unknown>;
}>;
export async function prepareStudyFixture(
  page: Readonly<Page>,
  scenario: 'offered' | 'eligible' | 'private' | 'current',
  project: string,
): Promise<StudyCohort> {
  if (!/^(chromium-mobile|webkit-mobile|chromium-desktop)$/.test(project))
    throw new Error('Invalid controlled study project');
  const response = await page.request.post('http://127.0.0.1:8768/__fixture/study', {
    data: { namespace: `study/${scenario}/${project}` },
  });
  expect(response.status()).toBe(201);
  const value: unknown = await response.json();
  if (
    typeof value !== 'object' ||
    value === null ||
    !('viewer_id' in value) ||
    !id(value.viewer_id) ||
    !('peer_id' in value) ||
    !id(value.peer_id) ||
    !('conversation_id' in value) ||
    !id(value.conversation_id) ||
    !('conversation_request_id' in value) ||
    !id(value.conversation_request_id) ||
    !('message_count' in value) ||
    typeof value.message_count !== 'string' ||
    !/^(1|2)$/.test(value.message_count) ||
    !('browser_time' in value) ||
    typeof value.browser_time !== 'string' ||
    !Number.isFinite(Date.parse(value.browser_time)) ||
    !('viewer_session' in value) ||
    typeof value.viewer_session !== 'string' ||
    !/^[A-Za-z0-9_-]{43}$/.test(value.viewer_session) ||
    !('peer_session' in value) ||
    typeof value.peer_session !== 'string' ||
    !/^[A-Za-z0-9_-]{43}$/.test(value.peer_session) ||
    !('cookie_name' in value) ||
    typeof value.cookie_name !== 'string' ||
    !/^__Host-[A-Za-z0-9_-]{1,48}$/.test(value.cookie_name) ||
    !('origin' in value) ||
    typeof value.origin !== 'string' ||
    !/^https:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(value.origin)
  )
    throw new Error('Invalid controlled study cohort');
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
  // Coherent real/historical source instants remain unchanged. Only age-aware
  // client presentation is pinned to the source's next Kuala Lumpur noon.
  await page.clock.setFixedTime(new Date(value.browser_time));
  const peer = value.peer_session;
  const cookie = value.cookie_name;
  const origin = value.origin;
  const conversation = value.conversation_id;
  return {
    actorId: value.viewer_id,
    peerId: value.peer_id,
    conversationId: conversation,
    requestId: value.conversation_request_id,
    messageCount: Number(value.message_count),
    readPeerFeedback: async () => {
      // Only this synthetic participant; credentials stay in Node, never page JS.
      const own = await page.request.get(
        `${origin}/api/v1/conversations/${conversation}/feedback`,
        { headers: { cookie: `${cookie}=${peer}` } },
      );
      expect(own.status()).toBe(200);
      return (await own.json()) as unknown;
    },
  };
}
export async function readStudyFixtureState(
  page: Readonly<Page>,
  conversationId: string,
): Promise<
  Readonly<{
    readonly outcomeVersions: number;
    readonly feedbackVersions: number;
    readonly feedbackCurrent: number;
    readonly promptReceipts: number;
    readonly canonicalEvents: number;
  }>
> {
  if (!id(conversationId)) throw new Error('Invalid controlled study conversation');
  const response = await page.request.get(
    `http://127.0.0.1:8768/__fixture/study/${conversationId}/state`,
  );
  expect(response.status()).toBe(200);
  const value: unknown = await response.json();
  if (
    typeof value !== 'object' ||
    value === null ||
    !('outcome_versions' in value) ||
    !count(value.outcome_versions) ||
    !('feedback_versions' in value) ||
    !count(value.feedback_versions) ||
    !('feedback_current' in value) ||
    !count(value.feedback_current) ||
    !('prompt_receipts' in value) ||
    !count(value.prompt_receipts) ||
    !('canonical_events' in value) ||
    !count(value.canonical_events)
  )
    throw new Error('Invalid controlled study state');
  return {
    outcomeVersions: value.outcome_versions,
    feedbackVersions: value.feedback_versions,
    feedbackCurrent: value.feedback_current,
    promptReceipts: value.prompt_receipts,
    canonicalEvents: value.canonical_events,
  };
}
function id(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value)
  );
}
function count(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}
