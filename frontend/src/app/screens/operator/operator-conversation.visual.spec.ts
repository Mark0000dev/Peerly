import type { Page, Route } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { operatorIdentity } from './operator.fixtures';
import {
  conversationId,
  otherConversationId,
  messagePage,
  storedMessage,
} from './operator-conversation.fixtures';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}>;
function releaseHeld(value: (() => void) | undefined): void {
  if (value === undefined) throw new Error('Missing release');
  value();
}
const endpoint = /\/api\/v1\/operator\/conversations\/[^/]+\/messages(?:\?.*)?$/;
async function setup(page: Readonly<Page>): Promise<void> {
  await page.clock.setFixedTime(new Date('2026-11-08T06:20:00Z'));
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({ json: operatorIdentity }),
  );
  await page.route(endpoint, (route: Readonly<Route>) => route.fulfill({ json: messagePage }));
}
async function open(page: Readonly<Page>, query = `conversation=${conversationId}`): Promise<void> {
  await page.goto(`/operator/conversations?${query}`);
  await expect(
    page.getByRole('heading', { name: 'Operator · conversation', exact: true }),
  ).toBeVisible();
}
const region = (page: Readonly<Page>) =>
  page.getByRole('region', { name: 'Retained conversation', exact: true });

test('M05 explicit valid UUID selection owns URL; literal stored text and actual source IDs', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let reads = 0;
  page.on('request', (r) => {
    if (endpoint.test(r.url())) reads += 1;
  });
  await open(page, '');
  await expect(
    page.getByText('Select a stored conversation ID to inspect its retained messages.'),
  ).toBeVisible();
  expect(reads).toBe(0);
  await checkpoint('conversation-unselected.png');
  await page.goto('/operator/conversations?conversation=bad');
  await expect(page.getByRole('alert')).toContainText('Conversation ID must be a UUID.');
  expect(reads).toBe(0);
  await checkpoint('conversation-invalid-route.png');
  await page.getByRole('textbox', { name: 'Conversation ID', exact: true }).fill('bad');
  await page.getByRole('button', { name: 'Open retained conversation', exact: true }).click();
  await expect(
    page.getByRole('form', { name: 'Conversation selection' }).getByRole('alert'),
  ).toContainText('must be a UUID');
  expect(reads).toBe(0);
  await checkpoint('conversation-invalid-form.png');
  await page.getByRole('textbox', { name: 'Conversation ID', exact: true }).fill(conversationId);
  await page.getByRole('button', { name: 'Open retained conversation', exact: true }).click();
  await expect(region(page)).toContainText(
    "Stored literal <script>alert('not executable')</script>\n  Original spacing",
  );
  await expect(region(page).locator('script')).toHaveCount(0);
  await expect(region(page)).toContainText(messagePage.relationship_id);
  await expect(region(page)).toContainText(messagePage.request_id);
  await expect(page).toHaveURL(new RegExp(`conversation=${conversationId}`));
  expect(reads).toBe(1);
  await expect(page.getByRole('textbox')).toHaveCount(1);
  await checkpoint('conversation-literal-sources.png');
});

test('M05 source50plus older page and first-page refresh preserve server sequence', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(endpoint, (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...messagePage,
        messages: new URL(route.request().url()).searchParams.has('cursor')
          ? [storedMessage(1), storedMessage(2), storedMessage(3)]
          : Array.from({ length: 50 }, (_, i) => storedMessage(i + 4)),
        next_cursor: new URL(route.request().url()).searchParams.has('cursor')
          ? null
          : 'signed-older-page',
      },
    }),
  );
  await open(page);
  await expect(region(page).getByRole('article')).toHaveCount(50);
  await expect(region(page).getByRole('article').first()).toHaveAccessibleName(
    'Message sequence 4',
  );
  await expect(region(page).getByRole('article').last()).toHaveAccessibleName(
    'Message sequence 53',
  );
  await page.getByRole('button', { name: 'Older message page' }).click();
  await expect(region(page).getByRole('article')).toHaveCount(3);
  await expect(page).toHaveURL(/cursor=signed-older-page/);
  await checkpoint('conversation-older3.png');
  await page.getByRole('button', { name: 'First page', exact: true }).click();
  await expect(region(page).getByRole('article')).toHaveCount(50);
  await expect(page).not.toHaveURL(/cursor=/);
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(region(page).getByRole('article')).toHaveCount(50);
  await checkpoint('conversation-latest50.png');
});

test('M05 retained empty container has real metadata and no invented greeting', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let attempt = 0;
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/me', async (route: Readonly<Route>) => {
    attempt += 1;
    if (attempt === 1) await held;
    await route.fulfill(
      attempt === 1
        ? { status: 503, json: { code: 'unavailable' } }
        : attempt === 2
          ? { status: 401, json: { code: 'unauthenticated' } }
          : { json: operatorIdentity },
    );
  });
  await page.route(endpoint, (route: Readonly<Route>) =>
    route.fulfill({
      json: { ...messagePage, messages: [], anchor_sequence: 0, next_cursor: null },
    }),
  );
  await open(page);
  await expect(page.getByRole('status')).toHaveText('Checking your Google session…');
  await checkpoint('conversation-session-loading.png');
  releaseHeld(release);
  await expect(
    page.getByRole('heading', { name: 'Your session could not be checked' }),
  ).toBeVisible();
  await checkpoint('conversation-session-failed.png');
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Sign in with your operator Google account' }),
  ).toBeVisible();
  await checkpoint('conversation-guest.png');
  await page.reload();
  await expect(region(page)).toContainText('No retained messages on this page.');
  await expect(region(page).getByRole('article')).toHaveCount(0);
  await checkpoint('conversation-empty.png');
});

for (const status of [404, 422, 503])
  test(`M05 actual ${String(status)} remains local with explicit recovery`, async ({
    page,
    checkpoint,
  }: Scenario) => {
    await setup(page);
    let failed = true;
    await page.route(endpoint, (route: Readonly<Route>) =>
      route.fulfill(
        failed
          ? {
              status,
              json: {
                code:
                  status === 404
                    ? 'operator_resource_unavailable'
                    : status === 422
                      ? 'invalid_operator_cursor'
                      : 'unavailable',
              },
            }
          : { json: messagePage },
      ),
    );
    await open(page, `conversation=${conversationId}&cursor=old`);
    await expect(page.getByRole('alert')).toContainText(
      status === 404
        ? 'unavailable'
        : status === 422
          ? 'cursor could not be used'
          : 'Messages could not be loaded',
    );
    await checkpoint(`conversation-${String(status)}.png`);
    failed = false;
    await page
      .getByRole('button', { name: status === 422 ? 'First page' : 'Retry', exact: true })
      .click();
    await expect(region(page)).toContainText('Stored literal');
    await checkpoint(`conversation-${String(status)}-recovered.png`);
  });

test('M05 loading request and conversation replacement retire late old source', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(endpoint, async (route: Readonly<Route>) => {
    if (route.request().url().includes(conversationId)) {
      await held;
      await route.fulfill({ json: messagePage });
    } else
      await route.fulfill({
        json: {
          ...messagePage,
          conversation_id: otherConversationId,
          messages: [],
          next_cursor: null,
        },
      });
  });
  await open(page);
  await expect(page.getByRole('status')).toHaveText('Loading retained messages…');
  await checkpoint('conversation-loading.png');
  await page
    .getByRole('textbox', { name: 'Conversation ID', exact: true })
    .fill(otherConversationId);
  await page.getByRole('button', { name: 'Open retained conversation', exact: true }).click();
  await expect(region(page)).toContainText('No retained messages');
  releaseHeld(release);
  await expect(region(page)).not.toContainText('Stored literal');
  await expect(page).not.toHaveURL(/cursor=/);
  await checkpoint('conversation-switched.png');
});

test('M05 grant403 retires all private records until real recheck', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let denied = false;
  await page.route(endpoint, (route: Readonly<Route>) =>
    route.fulfill(
      denied ? { status: 403, json: { code: 'operator_access_denied' } } : { json: messagePage },
    ),
  );
  await open(page);
  await expect(region(page)).toContainText('Stored literal');
  denied = true;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Operator access denied', exact: true }),
  ).toBeVisible();
  await expect(region(page)).toHaveCount(0);
  await checkpoint('conversation-grant-revoked.png');
  denied = false;
  await page.getByRole('button', { name: 'Check operator access again' }).click();
  await expect(region(page)).toContainText('Stored literal');
  await checkpoint('conversation-grant-restored.png');
});

test('M05 child401 rechecks canonical session and removes private content', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let expired = false;
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill(
      expired ? { status: 401, json: { code: 'unauthenticated' } } : { json: operatorIdentity },
    ),
  );
  await page.route(endpoint, (route: Readonly<Route>) =>
    route.fulfill(
      expired ? { status: 401, json: { code: 'unauthenticated' } } : { json: messagePage },
    ),
  );
  await open(page);
  await expect(region(page)).toContainText('Stored literal');
  expired = true;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Sign in with your operator Google account' }),
  ).toBeVisible();
  await expect(region(page)).toHaveCount(0);
  await checkpoint('conversation-child401.png');
});

test('M05 actor replacement resets signed cursor before new owner reads', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let replaced = false;
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...operatorIdentity,
        account_id: replaced ? otherConversationId : operatorIdentity.account_id,
      },
    }),
  );
  let denied = false;
  let newCursors: readonly (string | null)[] = [];
  await page.route(endpoint, (route: Readonly<Route>) => {
    if (replaced)
      newCursors = [...newCursors, new URL(route.request().url()).searchParams.get('cursor')];
    return route.fulfill(
      denied && !replaced
        ? { status: 403, json: { code: 'operator_access_denied' } }
        : {
            json: replaced
              ? { ...messagePage, messages: [], next_cursor: null }
              : {
                  ...messagePage,
                  next_cursor: new URL(route.request().url()).searchParams.has('cursor')
                    ? 'signed-next-page'
                    : 'signed-older-page',
                },
          },
    );
  });
  await open(page);
  await expect(region(page)).toContainText('Stored literal');
  await page.getByRole('button', { name: 'Older message page' }).click();
  await expect(page).toHaveURL(/cursor=/);
  denied = true;
  await page.getByRole('button', { name: 'Older message page', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Operator access denied' })).toBeVisible();
  replaced = true;
  await page.getByRole('button', { name: 'Check operator access again' }).click();
  await expect(region(page)).toContainText('No retained messages');
  expect(newCursors).toEqual([null]);
  await expect(page).not.toHaveURL(/cursor=/);
  await checkpoint('conversation-actor-replaced.png');
});

test('M05 MX initial320 text200 control and stored text containment plus keyboard', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.setViewportSize({ width: 320, height: 760 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      document.documentElement.style.setProperty('font-size', '200%');
    });
  });
  await open(page);
  await expect(region(page)).toContainText('Stored literal');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const clipped = await page
    .locator('h1,h2,h3,p,dt,dd,a,button')
    .evaluateAll((elements: readonly Element[]) =>
      elements
        .filter((e: Readonly<Element>) => {
          const r = e.getBoundingClientRect();
          return r.width > 0 && (r.left < 0 || r.right > innerWidth + 1);
        })
        .map((e: Readonly<Element>) => e.textContent),
    );
  expect(clipped).toEqual([]);
  await checkpoint('conversation320-text200.png');
  await page.getByRole('textbox', { name: 'Conversation ID', exact: true }).focus();
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('button', { name: 'Open retained conversation', exact: true }),
  ).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(region(page)).toContainText('Stored literal');
  await checkpoint('conversation320-keyboard.png');
});
