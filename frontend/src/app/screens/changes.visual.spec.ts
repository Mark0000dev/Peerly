import type { Page, Route } from '@playwright/test';
import { test, expect } from '../../../testing/visual';
import { jpegBase64 } from '../../../testing/image-fixture';
import { identity, card, deck } from './discovery/discovery.fixtures';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}>;

function hint(id: string, owner: string): string {
  return (
    'id: ' +
    id +
    '\nevent: resource.changed\ndata: ' +
    JSON.stringify({ resource_type: 'account', resource_id: owner, version: 2 }) +
    '\n\n'
  );
}
async function fixtures(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/me', (route: Readonly<Route>) => route.fulfill({ json: identity }));
  await page.route('**/api/v1/discovery?*', (route: Readonly<Route>) =>
    route.fulfill({ json: deck }),
  );
  await page.route('**/api/v1/people/*/photo/*', (route: Readonly<Route>) =>
    route.fulfill({
      status: 200,
      contentType: 'image/jpeg',
      body: Buffer.from(jpegBase64, 'base64'),
    }),
  );
}
function releaseGate(release: (() => void) | undefined): void {
  if (release === undefined) throw new Error('Missing stream gate');
  release();
}

test('SSE peer hint refetches canonical visible data and resumes exact cursor without commands', async ({
  page,
  checkpoint,
}: Scenario) => {
  await fixtures(page);
  let changed = false;
  let reads = 0;
  let writes = 0;
  let cursors: readonly (string | null)[] = [];
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  page.on('request', (request) => {
    if (request.method() !== 'GET') writes += 1;
  });
  await page.route('**/api/v1/discovery?*', (route: Readonly<Route>) => {
    reads += 1;
    return route.fulfill({
      json: changed
        ? { ...deck, people: [{ ...card, display_name: 'Aiko Tan', version: 2 }] }
        : deck,
    });
  });
  await page.route('**/api/v1/events', async (route: Readonly<Route>) => {
    cursors = [...cursors, route.request().headers()['last-event-id'] ?? null];
    if (cursors.length === 1) await held;
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: hint('9223372036854775807', card.id),
    });
  });
  try {
    await page.goto('/discover');
    await expect(page.getByRole('heading', { name: card.display_name, exact: true })).toBeVisible();
    changed = true;
    releaseGate(release);
    await expect(page.getByRole('heading', { name: 'Aiko Tan', exact: true })).toBeVisible();
    await expect.poll(() => cursors).toContain('9223372036854775807');
    expect(cursors[0]).toBeNull();
    expect(reads).toBeGreaterThanOrEqual(2);
    expect(writes).toBe(0);
    await expect(page.getByRole('img', { name: 'Photo of Aiko Tan' })).toHaveJSProperty(
      'complete',
      true,
    );
    await checkpoint('peer-hint-canonical-refresh.png');
  } finally {
    releaseGate(release);
  }
});

test('SSE own-account change confirms session revocation through actual me and retires private view', async ({
  page,
  checkpoint,
}: Scenario) => {
  await fixtures(page);
  let expired = false;
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill(
      expired
        ? {
            status: 401,
            json: { code: 'unauthenticated', request_id: '10000000-0000-0000-0000-000000000009' },
          }
        : { json: identity },
    ),
  );
  await page.route('**/api/v1/events', async (route: Readonly<Route>) => {
    await held;
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: hint('42', identity.account_id),
    });
  });
  try {
    await page.goto('/discover');
    await expect(page.getByRole('heading', { name: card.display_name, exact: true })).toBeVisible();
    expired = true;
    releaseGate(release);
    await expect(
      page.getByRole('heading', { name: 'Sign in with your verified APU account' }),
    ).toBeVisible();
    await expect(page.getByRole('heading', { name: card.display_name, exact: true })).toHaveCount(
      0,
    );
    await expect(page.getByRole('link', { name: 'Continue to setup' })).toHaveAttribute(
      'href',
      '/onboarding',
    );
    await checkpoint('own-hint-revalidated-private-retirement.png');
  } finally {
    releaseGate(release);
  }
});

test('SSE unavailable transport retries only its safe GET while canonical screen remains usable', async ({
  page,
  checkpoint,
}: Scenario) => {
  await fixtures(page);
  let streams = 0;
  let writes = 0;
  page.on('request', (request) => {
    if (request.method() !== 'GET') writes += 1;
  });
  await page.route('**/api/v1/events', (route: Readonly<Route>) => {
    streams += 1;
    return route.fulfill(
      streams === 1
        ? {
            status: 503,
            headers: { 'Retry-After': '1' },
            json: { code: 'temporarily_unavailable' },
          }
        : { status: 200, contentType: 'text/event-stream', body: ': heartbeat\n\n' },
    );
  });
  await page.goto('/discover');
  await expect(page.getByRole('heading', { name: card.display_name, exact: true })).toBeVisible();
  await expect.poll(() => streams).toBeGreaterThanOrEqual(2);
  expect(writes).toBe(0);
  await expect(page.getByRole('button', { name: 'Review request', exact: true })).toBeEnabled();
  await checkpoint('safe-stream-retry-keeps-canonical-view.png');
});
