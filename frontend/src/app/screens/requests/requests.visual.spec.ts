import { jpegBase64 } from '../../../../testing/image-fixture';
import { Buffer } from 'node:buffer';
import { assertStudentNavigationInViewport } from '../../../../testing/student-navigation';
import { assertNaturalWordWrapping, assertFullTextFits } from '../../../../testing/readable-text';
import type { Page, Route } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import {
  identity,
  page as requestPage,
  request,
  detail,
  receipt,
  viewed,
  declined,
} from './requests.fixtures';

type Context = Readonly<{
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}>;
async function account(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/people/*/photo/*', async (route: Readonly<Route>) =>
    route.fulfill({ contentType: 'image/jpeg', body: Buffer.from(jpegBase64, 'base64') }),
  );
  await page.route('**/api/v1/me', async (route: Readonly<Route>) =>
    route.fulfill({ json: identity }),
  );
}
async function list(page: Readonly<Page>, data: unknown = requestPage): Promise<void> {
  await page.route('**/api/v1/requests?*', async (route: Readonly<Route>) =>
    route.fulfill({ json: data }),
  );
}
async function open(page: Readonly<Page>, query = ''): Promise<void> {
  await page.goto(`/requests${query}`);
  await expect(
    page.getByRole('heading', { name: /^(Requests|Request details)$/, exact: true }),
  ).toBeVisible();
}
function releaseRead(release: (() => void) | undefined): void {
  if (release === undefined) throw new Error('Missing controlled read');
  release();
}
function replayMatches(route: Readonly<Route>, body: string | null, key: string | undefined): void {
  expect(route.request().postData()).toBe(body);
  expect(route.request().headers()['idempotency-key']).toBe(key);
}

test('R01 actual unread, immutable intent and grounded mode list without invented compose/chat', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  await list(page);
  await open(page);
  await expect(page.locator('app-requests')).toHaveCSS('background-color', 'rgb(250, 246, 239)');
  await expect(page.getByRole('article', { name: 'Request with Maya Lim', exact: true })).toHaveCSS(
    'background-color',
    'rgb(255, 255, 255)',
  );
  await expect(page.getByRole('heading', { name: 'Maya Lim' })).toBeVisible();
  await expect(page.getByText('1 unread received requests')).toBeVisible();
  await expect(page.getByText(request.text, { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'View profile' })).toHaveAttribute(
    'href',
    `/people/${request.peer.person_id}`,
  );
  await expect(page.getByRole('button', { name: 'Send request', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Open chat' })).toHaveCount(0);
  const card = page.getByRole('article', { name: 'Request with Maya Lim', exact: true });
  await expect(card).toHaveAttribute('data-appearance', 'floating');
  await expect(card.locator('header')).toContainText('Would like help with SQL');
  await expect(card.locator('header time')).toHaveAttribute('datetime', request.sent_at);
  await expect(card.locator('blockquote')).toHaveText(request.text);
  await assertStudentNavigationInViewport(page, 'Requests');
  await checkpoint('received-viewport.png', { fullPage: false });
  await checkpoint('received.png');
});

test('R01 received modes distinguish a help request, offer and shared learning without expertise claims', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  await list(page, {
    ...requestPage,
    requests: [
      request,
      {
        ...request,
        request_id: '20000000-0000-4000-8000-000000000002',
        mode: 'offer_help',
        unread: false,
        peer: {
          ...request.peer,
          person_id: '10000000-0000-4000-8000-000000000003',
          display_name: 'Jun Park',
        },
      },
      {
        ...request,
        request_id: '20000000-0000-4000-8000-000000000003',
        mode: 'study_together',
        unread: false,
        peer: {
          ...request.peer,
          person_id: '10000000-0000-4000-8000-000000000004',
          display_name: 'Sofia Reyes',
        },
      },
    ],
  });
  await open(page);
  await expect(page.getByText('Would like help with SQL', { exact: true })).toBeVisible();
  await expect(page.getByText('Offers help with SQL', { exact: true })).toBeVisible();
  await expect(page.getByText('Would like to study SQL together', { exact: true })).toBeVisible();
  await checkpoint('received-three-modes.png');
});

test('R03 disclosure GET is not ACK; explicit foreground action clears canonical unread only', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  let acknowledged = false;
  await page.route('**/api/v1/requests?*', async (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...requestPage,
        unread_received: acknowledged ? 0 : 1,
        requests: [{ ...request, unread: !acknowledged }],
      },
    }),
  );
  await page.route(`**/api/v1/requests/${request.request_id}`, async (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...detail,
        request: { ...request, unread: !acknowledged },
      },
    }),
  );
  await page.route('**/viewed', async (route: Readonly<Route>) => {
    expect(route.request().postDataJSON()).toEqual({ disclosure_id: detail.disclosure_id });
    acknowledged = true;
    await route.fulfill({ json: viewed });
  });
  await open(page, `?request=${request.request_id}`);
  await expect(page.getByRole('heading', { name: 'Academic context when sent' })).toBeVisible();
  expect(acknowledged).toBe(false);
  await checkpoint('detail-not-acknowledged.png');
  await page.getByRole('button', { name: 'Mark as viewed' }).click();
  await expect(page.getByText('0 unread received requests')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Mark as viewed' })).toHaveCount(0);
  await checkpoint('detail-viewed.png');
});

test('R01 loading and failed read require explicit successful recovery', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  let release: (() => void) | undefined;
  const hold = new Promise<void>((resolve) => {
    release = resolve;
  });
  let reads = 0;
  await page.route('**/api/v1/requests?*', async (route: Readonly<Route>) => {
    reads += 1;
    if (reads === 1) {
      await hold;
      await route.fulfill({ status: 503, json: { code: 'unavailable' } });
    } else await route.fulfill({ json: requestPage });
  });
  await open(page);
  await expect(page.getByText('Loading requests…')).toBeVisible();
  await checkpoint('list-loading.png');
  releaseRead(release);
  await expect(page.getByRole('alert')).toContainText('We couldn’t load requests');
  await checkpoint('list-failed.png');
  await page.getByRole('button', { name: 'Refresh requests' }).click();
  await expect(page.getByRole('heading', { name: 'Maya Lim' })).toBeVisible();
  await checkpoint('list-recovered.png');
});

test('R03 detail loading and neutral unavailable recover only by explicit reread', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  await list(page);
  let release: (() => void) | undefined;
  const hold = new Promise<void>((resolve) => {
    release = resolve;
  });
  let reads = 0;
  await page.route(`**/api/v1/requests/${request.request_id}`, async (route: Readonly<Route>) => {
    reads += 1;
    if (reads === 1) {
      await hold;
      await route.fulfill({ status: 404, json: {} });
    } else await route.fulfill({ json: detail });
  });
  await open(page, `?request=${request.request_id}`);
  await expect(page.getByText('Loading requests…')).toBeVisible();
  await checkpoint('detail-loading.png');
  releaseRead(release);
  await expect(page.getByRole('alert')).toHaveText('This request is no longer available.');
  await expect(page.getByRole('button', { name: 'Mark as viewed' })).toHaveCount(0);
  await checkpoint('detail-unavailable.png');
  await page.getByRole('button', { name: 'Refresh requests' }).click();
  await expect(page.getByRole('heading', { name: 'Academic context when sent' })).toBeVisible();
  await checkpoint('detail-recovered.png');
});

for (const view of ['active', 'history', 'recently_declined'] as const)
  test(`R01 empty ${view} stays a separate URL view`, async ({ page, checkpoint }: Context) => {
    await account(page);
    await list(page, { ...requestPage, requests: [], unread_received: 0 });
    await open(page, `?view=${view}`);
    await expect(
      page.getByRole('heading', {
        name:
          view === 'active'
            ? 'No requests for you yet'
            : view === 'history'
              ? 'No closed requests yet'
              : 'No recently declined requests',
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', {
        name: view === 'active' ? 'Active' : view === 'history' ? 'History' : 'Recently declined',
        exact: true,
      }),
    ).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('link', { name: 'Discover people', exact: true })).toHaveCount(
      view === 'active' ? 1 : 0,
    );
    await checkpoint(`${view}-empty.png`);
  });

test('R02 empty active sent view keeps allowance and the genuine discovery entry', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  await list(page, { ...requestPage, requests: [], outgoing_pending: 0 });
  await open(page, '?box=sent');
  await expect(
    page.getByRole('heading', { name: 'No sent requests yet', exact: true }),
  ).toBeVisible();
  await expect(page.locator('.request-allowance')).toContainText('0 of 5 pending');
  await expect(page.getByRole('link', { name: 'Discover people', exact: true })).toHaveAttribute(
    'href',
    '/discover',
  );
  await expect(page.getByRole('button', { name: 'Withdraw', exact: true })).toHaveCount(0);
  await checkpoint('sent-empty.png');
});

test('R01 decline pending then server Undo, with recently declined URL surviving navigation', async ({
  page,
  checkpoint,
}: Context) => {
  await page.clock.setFixedTime(new Date(request.observed_at));
  await account(page);
  let state = request;
  let release: (() => void) | undefined;
  const hold = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/requests?*', async (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...requestPage,
        unread_received: state.unread ? 1 : 0,
        requests:
          new URL(route.request().url()).searchParams.get('view') === 'recently_declined' &&
          state.state !== 'pending_decline'
            ? []
            : [state],
      },
    }),
  );
  await page.route('**/decline', async (route: Readonly<Route>) => {
    expect(route.request().postDataJSON()).toEqual({
      person_id: request.peer.person_id,
      expected_version: 1,
    });
    await hold;
    state = declined;
    await route.fulfill({
      json: {
        ...receipt,
        outcome: 'declined',
        conversation_id: null,
        undo_until: declined.undo_until,
      },
    });
  });
  await page.route('**/undo-decline', async (route: Readonly<Route>) => {
    expect(route.request().postDataJSON()).toEqual({
      person_id: request.peer.person_id,
      expected_version: 2,
    });
    state = { ...request, version: 3 };
    await route.fulfill({
      json: { ...receipt, version: 3, outcome: 'undo_decline', conversation_id: null },
    });
  });
  await open(page);
  await page.getByRole('button', { name: 'Decline', exact: true }).click();
  await expect(page.getByText('Checking with the server…')).toBeVisible();
  await checkpoint('decline-pending.png');
  releaseRead(release);
  await expect(page.getByRole('button', { name: 'Undo decline' })).toBeEnabled();
  await checkpoint('undo-available.png');
  await page.getByRole('button', { name: 'Recently declined', exact: true }).click();
  await expect(page).toHaveURL(/view=recently_declined/);
  await expect(page.getByRole('button', { name: 'Undo decline' })).toBeEnabled();
  await checkpoint('recently-declined.png');
  await page.getByRole('button', { name: 'Undo decline' }).click();
  await expect(
    page.getByRole('heading', { name: 'No recently declined requests', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Active', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Accept request' })).toBeEnabled();
  await checkpoint('undo-confirmed.png');
});

test('R01 expired timer refreshes server capabilities instead of locally finalizing decline', async ({
  page,
  checkpoint,
}: Context) => {
  await page.clock.setFixedTime(new Date(request.observed_at));
  await account(page);
  let reads = 0;
  await page.route('**/api/v1/requests?*', async (route: Readonly<Route>) => {
    reads += 1;
    await route.fulfill({
      json: { ...requestPage, unread_received: 0, requests: reads === 1 ? [declined] : [] },
    });
  });
  await open(page, '?view=recently_declined');
  await expect(page.getByRole('button', { name: 'Undo decline' })).toBeEnabled();
  await checkpoint('expiry-before.png');
  await page.clock.setFixedTime(new Date(Date.parse(request.observed_at) + 11000));
  await expect(
    page.getByRole('heading', { name: 'No recently declined requests', exact: true }),
  ).toBeVisible();
  expect(reads).toBe(2);
  await checkpoint('expiry-canonical.png');
});

test('R03 accept exposes the permitted conversation without creating a first message', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  let accepted = false;
  await page.route('**/api/v1/requests?*', async (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...requestPage,
        unread_received: accepted ? 0 : 1,
        requests: [
          accepted
            ? {
                ...request,
                state: 'accepted',
                unread: false,
                version: 2,
                conversation_id: receipt.conversation_id,
                capabilities: {
                  ...request.capabilities,
                  accept: false,
                  decline: false,
                  open_conversation: true,
                },
              }
            : request,
        ],
      },
    }),
  );
  await page.route('**/accept', async (route: Readonly<Route>) => {
    accepted = true;
    await route.fulfill({ json: receipt });
  });
  await open(page);
  await page.getByRole('button', { name: 'Accept request' }).click();
  await expect(page.getByText('Connected. No message was sent by accepting.')).toBeVisible();
  expect(receipt.conversation_id).not.toBeNull();
  await expect(page.getByRole('link', { name: 'Open chat' })).toHaveAttribute(
    'href',
    `/chats?conversation=${String(receipt.conversation_id)}`,
  );
  await checkpoint('accepted-reference.png');
});

test('R02 sent quota and explicit withdrawal confirmation preserve immutable text', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  let withdrawn = false;
  await page.route('**/api/v1/requests?*', async (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...requestPage,
        outgoing_pending: withdrawn ? 0 : 1,
        successful_today: 4,
        requests:
          withdrawn && new URL(route.request().url()).searchParams.get('view') !== 'history'
            ? []
            : [
                {
                  ...request,
                  unread: false,
                  state: withdrawn ? 'withdrawn' : 'pending',
                  capabilities: {
                    ...request.capabilities,
                    accept: false,
                    decline: false,
                    withdraw: !withdrawn,
                  },
                },
              ],
      },
    }),
  );
  await page.route('**/withdraw', async (route: Readonly<Route>) => {
    withdrawn = true;
    await route.fulfill({ json: { ...receipt, outcome: 'withdrawn', conversation_id: null } });
  });
  await open(page, '?box=sent');
  await expect(page.getByText('1 of 5 pending · 4 of 10 sent today')).toBeVisible();
  await checkpoint('sent-pending.png');
  await page.getByRole('button', { name: 'Withdraw', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Withdraw this request?' })).toBeVisible();
  await checkpoint('withdraw-confirmation.png');
  await page.getByRole('button', { name: 'Keep request' }).click();
  await expect(page.getByRole('heading', { name: 'Withdraw this request?' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Withdraw', exact: true }).click();
  await page.getByRole('button', { name: 'Withdraw request', exact: true }).click();
  await expect(page.getByText('0 of 5 pending · 4 of 10 sent today')).toBeVisible();
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await expect(page.getByText(request.text, { exact: true })).toBeVisible();
  await checkpoint('withdraw-confirmed.png');
});

test('R01 uncertain decision exact replay and stale CAS conflict require honest recovery', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  await list(page);
  let original: string | null = null;
  let key: string | undefined;
  let sends = 0;
  await page.route('**/decline', async (route: Readonly<Route>) => {
    sends += 1;
    if (sends === 1) {
      original = route.request().postData();
      key = route.request().headers()['idempotency-key'];
      await route.abort('failed');
    } else {
      replayMatches(route, original, key);
      await route.fulfill({ status: 409, json: { code: 'request_version_conflict' } });
    }
  });
  await open(page);
  await page.getByRole('button', { name: 'Decline', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry same decision' })).toBeVisible();
  await checkpoint('decision-unknown.png');
  await page.getByRole('button', { name: 'Retry same decision' }).click();
  await expect(page.getByRole('alert')).toContainText('This request changed');
  await checkpoint('decision-conflict.png');
  await page.getByRole('button', { name: 'Refresh requests' }).click();
  await expect(page.getByRole('button', { name: 'Accept request' })).toBeEnabled();
  expect(sends).toBe(2);
  await checkpoint('conflict-refreshed.png');
});

test('R03 unknown acknowledgement retries the same owned disclosure/key', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  let acknowledged = false;
  await page.route('**/api/v1/requests?*', async (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...requestPage,
        unread_received: acknowledged ? 0 : 1,
        requests: [{ ...request, unread: !acknowledged }],
      },
    }),
  );
  await page.route(`**/api/v1/requests/${request.request_id}`, async (route: Readonly<Route>) =>
    route.fulfill({ json: { ...detail, request: { ...request, unread: !acknowledged } } }),
  );
  let original: string | null = null;
  let key: string | undefined;
  let sends = 0;
  await page.route('**/viewed', async (route: Readonly<Route>) => {
    sends += 1;
    if (sends === 1) {
      original = route.request().postData();
      key = route.request().headers()['idempotency-key'];
      await route.abort('failed');
    } else {
      replayMatches(route, original, key);
      acknowledged = true;
      await route.fulfill({ json: viewed });
    }
  });
  await open(page, `?request=${request.request_id}`);
  await page.getByRole('button', { name: 'Mark as viewed' }).click();
  await expect(page.getByRole('button', { name: 'Retry same acknowledgement' })).toBeVisible();
  await checkpoint('acknowledgement-unknown.png');
  await page.getByRole('button', { name: 'Retry same acknowledgement' }).click();
  await expect(page.getByRole('button', { name: 'Mark as viewed' })).toHaveCount(0);
  await expect(page.getByText('0 unread received requests')).toBeVisible();
  expect(sends).toBe(2);
  await checkpoint('acknowledgement-replayed.png');
});

test('R01 pagination uses opaque cursor and invalid continuation refresh clears it', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  await page.route('**/api/v1/requests?*', async (route: Readonly<Route>) => {
    const cursor = new URL(route.request().url()).searchParams.get('cursor');
    await route.fulfill(
      cursor === null
        ? { json: { ...requestPage, next_cursor: 'opaque/value' } }
        : { status: 422, json: { code: 'invalid_request_cursor' } },
    );
  });
  await open(page);
  await page.getByRole('button', { name: 'Next page' }).click();
  await expect(page).toHaveURL(/cursor=opaque%2Fvalue/);
  await expect(page.getByRole('alert')).toContainText('Refresh from the beginning');
  await checkpoint('cursor-invalid.png');
  await page.getByRole('button', { name: 'Refresh requests' }).click();
  await expect(page).not.toHaveURL(/cursor=/);
  await expect(page.getByRole('heading', { name: 'Maya Lim' })).toBeVisible();
  await checkpoint('cursor-first-page.png');
});

for (const state of ['unavailable', 'deleted'] as const)
  test(`R03 retained request with ${state} peer grants no profile`, async ({
    page,
    checkpoint,
  }: Context) => {
    await account(page);
    await list(page, {
      ...requestPage,
      unread_received: 0,
      requests: [
        {
          ...request,
          state: 'closed',
          unread: false,
          peer: { ...request.peer, state, display_name: null, photo_version: null },
          capabilities: {
            ...request.capabilities,
            accept: false,
            decline: false,
            view_profile: false,
          },
        },
      ],
    });
    await open(page, '?view=history');
    await expect(
      page.getByRole('heading', {
        name: state === 'deleted' ? 'Deleted account' : 'Profile unavailable',
      }),
    ).toBeVisible();
    await expect(page.getByText(request.text, { exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'View profile' })).toHaveCount(0);
    await checkpoint(`${state}-retained-request.png`);
  });

test('R01 current session expiry clears private request and pending recovery', async ({
  page,
  checkpoint,
}: Context) => {
  let expired = false;
  await page.route('**/api/v1/me', async (route: Readonly<Route>) =>
    route.fulfill(expired ? { status: 401, json: {} } : { json: identity }),
  );
  await list(page);
  await page.route('**/accept', async (route: Readonly<Route>) => {
    expired = true;
    await route.fulfill({ status: 401, json: {} });
  });
  await open(page);
  await page.getByRole('button', { name: 'Accept request' }).click();
  await expect(
    page.getByRole('heading', { name: 'Complete your profile to use Requests' }),
  ).toBeVisible();
  await expect(page.getByText('Maya Lim')).toHaveCount(0);
  await checkpoint('session-expired.png');
});

test('R01 account failure and guest access never fabricate a private request', async ({
  page,
  checkpoint,
}: Context) => {
  let reads = 0;
  await page.route('**/api/v1/me', async (route: Readonly<Route>) => {
    reads += 1;
    await route.fulfill({ status: reads === 1 ? 503 : 401, json: {} });
  });
  await open(page);
  await expect(page.getByRole('alert')).toContainText('We couldn’t check your account');
  await checkpoint('account-failure.png');
  await page.getByRole('button', { name: 'Retry account check' }).click();
  await expect(
    page.getByRole('heading', { name: 'Complete your profile to use Requests' }),
  ).toBeVisible();
  await checkpoint('guest.png');
});

test('R01 long retained text and keyboard actions reflow at320px and200percent', async ({
  page,
  checkpoint,
}: Context) => {
  await page.setViewportSize({ width: 320, height: 780 });
  await page.addStyleTag({ content: 'html { font-size: 200%; }' });
  await account(page);
  await list(page, {
    ...requestPage,
    requests: [
      {
        ...request,
        peer: {
          ...request.peer,
          display_name: 'Maya-Lim-with-a-long-unbroken-public-display-name',
        },
        text: request.text.repeat(6),
      },
    ],
  });
  await open(page);
  await page.addStyleTag({ content: 'html { font-size: 200%; }' });
  await expect(page.getByRole('heading', { level: 2 })).toBeVisible();
  const overflow = await page.locator('main').evaluate((main: Readonly<HTMLElement>) =>
    Array.from(main.querySelectorAll('header, nav, article, button, a'))
      .map((element: Readonly<Element>) => {
        const rect = element.getBoundingClientRect();
        return {
          text: element.textContent.trim().slice(0, 40),
          left: Math.floor(rect.left),
          right: Math.ceil(rect.right),
        };
      })
      .filter(
        (
          item: Readonly<{ readonly text: string; readonly left: number; readonly right: number }>,
        ) => item.left < 0 || item.right > document.documentElement.clientWidth,
      ),
  );
  expect(overflow, 'Every control must fit the actual enlarged viewport').toEqual([]);
  expect(
    await page
      .getByRole('heading', { level: 2 })
      .evaluate((element: Readonly<Element>) => element.getBoundingClientRect().width),
  ).toBeGreaterThanOrEqual(160);
  await expect(page.locator('html')).toHaveJSProperty('scrollWidth', 320);
  await page.getByRole('button', { name: 'Review request' }).focus();
  await expect(page.getByRole('button', { name: 'Review request' })).toBeFocused();
  await assertNaturalWordWrapping(
    page.getByRole('heading', { name: 'Requests', level: 1, exact: true }),
  );
  await assertFullTextFits(page.getByRole('heading', { name: 'Requests', level: 1, exact: true }));
  for (const name of ['Received', 'Sent', 'Accept request', 'Decline']) {
    const control = page.getByRole('button', { name, exact: true });
    await expect(control).toBeVisible();
    await assertNaturalWordWrapping(control);
    await assertFullTextFits(control);
  }
  await checkpoint('narrow-enlarged-keyboard.png');
});

test('R01 current photo503 retries locally without rereading metadata or sending a decision', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  let metadataReads = 0;
  let photos = 0;
  let writes = 0;
  page.on('request', (item) => {
    if (item.method() !== 'GET' && new URL(item.url()).pathname.startsWith('/api/v1/requests'))
      writes += 1;
  });
  await page.route('**/api/v1/requests?*', async (route) => {
    metadataReads += 1;
    await route.fulfill({ json: requestPage });
  });
  await page.route(`**/api/v1/people/${request.peer.person_id}/photo/1`, async (route) => {
    photos += 1;
    if (photos === 1)
      await route.fulfill({ status: 503, json: { code: 'media_storage_unavailable' } });
    else
      await route.fulfill({ contentType: 'image/jpeg', body: Buffer.from(jpegBase64, 'base64') });
  });
  await open(page);
  await expect(page.getByText('Photo unavailable.', { exact: true })).toBeVisible();
  expect(photos).toBe(1);
  await checkpoint('request-photo-storage-unavailable.png');
  await page.getByRole('button', { name: 'Retry request photo', exact: true }).click();
  await expect(
    page.getByRole('img', { name: 'Current request participant photo', exact: true }),
  ).toBeVisible();
  expect(photos).toBe(2);
  expect(metadataReads).toBe(1);
  expect(writes).toBe(0);
  await checkpoint('request-photo-local-retry.png');
});

test('R01 stale photo404 refreshes canonical metadata and never retries the retired version', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  let metadataReads = 0;
  let oldPhotos = 0;
  let writes = 0;
  let release: (() => void) | undefined;
  const metadata = new Promise<void>((resolve) => {
    release = resolve;
  });
  page.on('request', (item) => {
    if (item.method() !== 'GET' && new URL(item.url()).pathname.startsWith('/api/v1/requests'))
      writes += 1;
  });
  await page.route('**/api/v1/requests?*', async (route) => {
    metadataReads += 1;
    if (metadataReads > 1) await metadata;
    await route.fulfill({
      json: {
        ...requestPage,
        requests: [
          { ...request, peer: { ...request.peer, photo_version: metadataReads === 1 ? 1 : 2 } },
        ],
      },
    });
  });
  await page.route(`**/api/v1/people/${request.peer.person_id}/photo/1`, async (route) => {
    oldPhotos += 1;
    await route.fulfill({ status: 404, json: { code: 'person_unavailable' } });
  });
  await open(page);
  await expect(page.getByText('Photo unavailable.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry request photo', exact: true })).toHaveCount(
    0,
  );
  await checkpoint('request-photo-retired-version.png');
  releaseRead(release);
  await expect(
    page.getByRole('img', { name: 'Current request participant photo', exact: true }),
  ).toBeVisible();
  expect(oldPhotos).toBe(1);
  expect(metadataReads).toBe(2);
  expect(writes).toBe(0);
  await checkpoint('request-photo-canonical-version.png');
});
