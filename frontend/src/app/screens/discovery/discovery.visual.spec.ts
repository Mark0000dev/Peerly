import { jpegBase64 } from '../../../../testing/image-fixture';
import type { Page, Route } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { identity, card, deck, pass } from './discovery.fixtures';

type Context = Readonly<{
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}>;
async function account(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/me', async (route: Readonly<Route>) =>
    route.fulfill({ json: identity }),
  );
  await page.route('**/api/v1/people/*/photo/*', async (route: Readonly<Route>) =>
    route.fulfill({
      status: 200,
      contentType: 'image/jpeg',
      body: Buffer.from(jpegBase64, 'base64'),
    }),
  );
}
async function open(page: Readonly<Page>, query = ''): Promise<void> {
  await page.goto(`/discover${query}`);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/^(Discover|Passed profiles)$/);
}

function releaseRead(release: (() => void) | undefined): void {
  if (release === undefined) throw new Error('Missing release');
  release();
}
function replayMatches(
  route: Readonly<Route>,
  original: string | null,
  key: string | undefined,
): void {
  expect(route.request().postData()).toBe(original);
  expect(route.request().headers()['idempotency-key']).toBe(key);
}

test('D01 grounded card offers actual request review without sending on entry', async ({
  page,
  checkpoint,
}: Context) => {
  let contactWrites = 0;
  page.on('request', (request) => {
    if (
      request.method() === 'POST' &&
      ['/api/v1/requests', '/api/v1/requests/preview'].includes(new URL(request.url()).pathname)
    )
      contactWrites += 1;
  });
  await account(page);
  await page.route('**/api/v1/discovery?*', async (route: Readonly<Route>) =>
    route.fulfill({ json: deck }),
  );
  await open(page);
  await expect(page.getByRole('heading', { name: card.display_name, exact: true })).toBeVisible();
  await expect(page.getByText('Can help with SQL · JOINs', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'View profile' })).toHaveAttribute(
    'href',
    `/people/${card.id}`,
  );
  await expect(page.getByRole('button', { name: 'Review request', exact: true })).toBeEnabled();
  await expect(page.getByRole('img', { name: `Photo of ${card.display_name}` })).toBeVisible();
  expect(contactWrites).toBe(0);
  await checkpoint('grounded-card.png');
  await page.getByRole('button', { name: 'Deck options', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Deck options' })).toBeVisible();
  await checkpoint('deck-options.png');
});

for (const [mode, reason, copy] of [
  ['find_help', 'context_required', 'Choose your learning goal'],
  ['offer_help', 'context_required', 'What can you help with?'],
  ['study_together', 'context_required', 'Choose your learning goal'],
  ['find_help', 'no_relevant_people', 'No relevant people yet'],
  ['find_help', 'exhausted', 'You have seen everyone for now'],
  ['find_help', 'no_available_passed_people', 'No available passed profiles'],
] as const)
  test(`D04 ${mode} ${reason} keeps explicit mode and honest recovery`, async ({
    page,
    checkpoint,
  }: Context) => {
    await account(page);
    await page.route('**/api/v1/discovery?*', async (route: Readonly<Route>) =>
      route.fulfill({
        json: {
          ...deck,
          context: reason === 'context_required' ? null : deck.context,
          people: [],
          empty_reason: reason,
        },
      }),
    );
    await open(
      page,
      `?mode=${mode}${reason === 'no_available_passed_people' ? '&view=passed' : ''}`,
    );
    await expect(page.getByRole('heading', { name: copy, exact: true })).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`mode=${mode}`));
    await checkpoint(`${mode}-${reason}.png`);
  });

test('D04 loading then safe failed read and retry with broader subject reason', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  let release: (() => void) | undefined;
  const hold = new Promise<void>((resolve) => {
    release = resolve;
  });
  let reads = 0;
  await page.route('**/api/v1/discovery?*', async (route: Readonly<Route>) => {
    reads += 1;
    if (reads === 1) {
      await hold;
      await route.fulfill({ status: 503, json: { code: 'unavailable', title: 'PRIVATE' } });
    } else
      await route.fulfill({
        json: {
          ...deck,
          people: [{ ...card, relevance: { ...card.relevance, same_topic: false } }],
        },
      });
  });
  await open(page);
  await expect(page.getByText('Loading people…', { exact: true })).toBeVisible();
  await checkpoint('loading.png');
  releaseRead(release);
  await expect(page.getByRole('alert')).toContainText('We couldn’t load people');
  await expect(page.getByText('PRIVATE', { exact: true })).toHaveCount(0);
  await checkpoint('read-failed.png');
  await page.getByRole('button', { name: 'Refresh current people', exact: true }).click();
  await expect(page.getByText('Can help with SQL', { exact: true })).toBeVisible();
  await checkpoint('broader-subject.png');
});

test('D01 private pass, server Undo, D05 retained pass and explicit reconsideration', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  let passed = false;
  let revision = 0;
  await page.route('**/api/v1/discovery?*', async (route: Readonly<Route>) => {
    const view = new URL(route.request().url()).searchParams.get('view');
    await route.fulfill({
      json: {
        ...deck,
        people:
          passed === (view === 'passed')
            ? [{ ...card, own_pass: { ...pass, passed, version: revision } }]
            : [],
        empty_reason:
          view === 'passed'
            ? passed
              ? null
              : 'no_available_passed_people'
            : passed
              ? 'exhausted'
              : null,
        undo_pass: passed ? { ...pass, version: revision } : null,
      },
    });
  });
  await page.route('**/api/v1/discovery/passes/*', async (route: Readonly<Route>) => {
    const body: unknown = route.request().postDataJSON();
    if (
      typeof body !== 'object' ||
      body === null ||
      !('passed' in body) ||
      typeof body.passed !== 'boolean'
    )
      throw new Error('Invalid pass body');
    passed = body.passed;
    revision += 1;
    await route.fulfill({ json: { ...pass, passed, version: revision } });
  });
  await open(page);
  await page.getByRole('button', { name: 'Pass', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'You have seen everyone for now' })).toBeVisible();
  await checkpoint('passed-and-undo.png');
  await page.getByRole('button', { name: 'Undo pass', exact: true }).click();
  await expect(page.getByRole('heading', { name: card.display_name, exact: true })).toBeVisible();
  await checkpoint('undo-canonical.png');
  await page.getByRole('button', { name: 'Pass', exact: true }).click();
  await page.getByRole('button', { name: 'Review passed profiles', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Passed profiles', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Review again', exact: true })).toBeVisible();
  await checkpoint('passed-review.png');
  await page.getByRole('button', { name: 'Review again', exact: true }).click();
  await expect(page.getByRole('heading', { name: card.display_name, exact: true })).toHaveCount(0);
  await checkpoint('reconsidered-canonical.png');
});

test('unknown pass repeats original body and key; conflict requires explicit refresh', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  await page.route('**/api/v1/discovery?*', async (route: Readonly<Route>) =>
    route.fulfill({ json: deck }),
  );
  let original: string | null = null;
  let key: string | undefined;
  let writes = 0;
  await page.route('**/api/v1/discovery/passes/*', async (route: Readonly<Route>) => {
    writes += 1;
    if (writes === 1) {
      original = route.request().postData();
      key = route.request().headers()['idempotency-key'];
      await route.abort();
    } else {
      replayMatches(route, original, key);
      await route.fulfill({ status: 409, json: { code: 'pass_version_conflict' } });
    }
  });
  await open(page);
  await page.getByRole('button', { name: 'Pass', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Decision not yet confirmed');
  await checkpoint('unknown-pass.png');
  await page.getByRole('button', { name: 'Retry same decision', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Your saved context or pass changed');
  await checkpoint('pass-conflict.png');
  await page.getByRole('button', { name: 'Refresh current people', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await checkpoint('conflict-refreshed.png');
});

for (const [mode, reason, copy] of [
  ['offer_help', 'you_can_help', 'You can help with their SQL · JOINs goal'],
  ['study_together', 'shared_goal', 'Open to studying SQL · JOINs together'],
] as const)
  test(`D01 actual ${mode} reason never silently changes saved context`, async ({
    page,
    checkpoint,
  }: Context) => {
    await account(page);
    await page.route('**/api/v1/discovery?*', async (route: Readonly<Route>) =>
      route.fulfill({
        json: {
          ...deck,
          context: mode === 'offer_help' ? { mode, help_version: 1 } : { ...deck.context, mode },
          people: [{ ...card, relevance: { ...card.relevance, reason } }],
        },
      }),
    );
    await open(page, `?mode=${mode}`);
    await expect(page.getByText(copy, { exact: true })).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`mode=${mode}`));
    await checkpoint(`${mode}-grounded-card.png`);
  });

test('D04 invalid opaque cursor recovers from first page explicitly', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  await page.route('**/api/v1/discovery?*', async (route: Readonly<Route>) => {
    if (new URL(route.request().url()).searchParams.has('cursor'))
      await route.fulfill({ status: 422, json: { code: 'invalid_cursor' } });
    else await route.fulfill({ json: deck });
  });
  await open(page, '?mode=find_help&cursor=stale');
  await expect(page.getByRole('alert')).toContainText('This page is no longer available');
  await checkpoint('stale-cursor.png');
  await page.getByRole('button', { name: 'Refresh current people', exact: true }).click();
  await expect(page.getByRole('heading', { name: card.display_name, exact: true })).toBeVisible();
  await expect(page).not.toHaveURL(/cursor=/);
  await checkpoint('cursor-recovered.png');
});

test('current photo404 refreshes deck version before reading newly authorized bytes', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  let reads = 0;
  await page.route('**/api/v1/discovery?*', async (route: Readonly<Route>) => {
    reads += 1;
    await route.fulfill({
      json: { ...deck, people: [{ ...card, photo: { ...card.photo, version: reads } }] },
    });
  });
  await page.route('**/api/v1/people/*/photo/1', async (route: Readonly<Route>) =>
    route.fulfill({ status: 404, json: { code: 'person_unavailable' } }),
  );
  await open(page);
  await expect(page.getByRole('button', { name: 'Retry photo', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Pass', exact: true })).toBeEnabled();
  await checkpoint('photo-version-unavailable.png');
  await page.getByRole('button', { name: 'Retry photo', exact: true }).click();
  await expect(page.getByRole('img', { name: `Photo of ${card.display_name}` })).toBeVisible();
  expect(reads).toBe(2);
  await checkpoint('current-photo-recovered.png');
});

test('private401 clears card and requires a fresh trusted session', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  let expired = false;
  await page.route('**/api/v1/me', async (route: Readonly<Route>) => {
    if (expired) await route.fulfill({ status: 401, json: { code: 'authentication_required' } });
    else await route.fulfill({ json: identity });
  });
  await page.route('**/api/v1/discovery?*', async (route: Readonly<Route>) =>
    route.fulfill({ json: deck }),
  );
  await page.route('**/api/v1/discovery/passes/*', async (route: Readonly<Route>) => {
    expired = true;
    await route.fulfill({ status: 401, json: { code: 'authentication_required' } });
  });
  await open(page);
  await page.getByRole('button', { name: 'Pass', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Sign in with your verified APU account', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: card.display_name, exact: true })).toHaveCount(0);
  await checkpoint('session-expired.png');
});

async function reflow(page: Readonly<Page>): Promise<void> {
  const geometry = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(geometry.scroll).toBeLessThanOrEqual(geometry.width);
  const name = await page
    .getByRole('heading', { name: card.display_name, exact: true })
    .boundingBox();
  expect(name?.width).toBeGreaterThanOrEqual(geometry.width / 2);
}

test('D01 320px 200percent text keeps mode, card and keyboard actions reachable', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  await page.setViewportSize({ width: 320, height: 720 });
  await page.route('**/api/v1/discovery?*', async (route: Readonly<Route>) =>
    route.fulfill({ json: deck }),
  );
  await open(page);
  await page.addStyleTag({ content: ':root { font-size: 200%; }' });
  await expect(page.getByRole('heading', { name: card.display_name, exact: true })).toBeVisible();
  await reflow(page);
  await checkpoint('narrow-large-text.png');
  const passButton = page.getByRole('button', { name: 'Pass', exact: true });
  await passButton.focus();
  await expect(passButton).toBeFocused();
  await checkpoint('narrow-keyboard-action.png');
});

test('D01 private JPEG503 retries independently without changing the candidate', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  await page.route('**/api/v1/discovery?*', async (route: Readonly<Route>) =>
    route.fulfill({ json: deck }),
  );
  let failed = true;
  await page.route('**/api/v1/people/*/photo/*', async (route: Readonly<Route>) => {
    if (failed) {
      failed = false;
      await route.fulfill({ status: 503, json: { code: 'unavailable' } });
    } else
      await route.fulfill({
        status: 200,
        contentType: 'image/jpeg',
        body: Buffer.from(jpegBase64, 'base64'),
      });
  });
  await open(page);
  await expect(page.getByRole('button', { name: 'Retry photo', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Pass', exact: true })).toBeEnabled();
  await checkpoint('photo-transfer-failed.png');
  await page.getByRole('button', { name: 'Retry photo', exact: true }).click();
  await expect(page.getByRole('img', { name: `Photo of ${card.display_name}` })).toBeVisible();
  await checkpoint('photo-transfer-retried.png');
});

test('D01 session failure and explicit guest recovery never become an empty deck', async ({
  page,
  checkpoint,
}: Context) => {
  let reads = 0;
  await page.route('**/api/v1/me', async (route: Readonly<Route>) => {
    reads += 1;
    await route.fulfill({ status: reads === 1 ? 503 : 401, json: { code: 'unavailable' } });
  });
  await open(page);
  await expect(
    page.getByRole('heading', { name: 'We couldn’t check your account', exact: true }),
  ).toBeVisible();
  await checkpoint('session-check-failed.png');
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Sign in with your verified APU account', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Continue to setup', exact: true })).toHaveAttribute(
    'href',
    '/onboarding',
  );
  await checkpoint('guest-recovery.png');
});

test('D01 paged URL selection survives Person navigation and canonical eligibility is rechecked on back', async ({
  page,
  checkpoint,
}: Context) => {
  await account(page);
  const second = {
    ...card,
    id: '10000000-0000-0000-0000-000000000009',
    display_name: 'Maya Lim',
    own_pass: { ...card.own_pass, person_id: '10000000-0000-0000-0000-000000000009' },
  };
  let returned = false;
  await page.route('**/api/v1/discovery?*', async (route: Readonly<Route>) =>
    route.fulfill({
      json: { ...deck, people: returned ? [card] : [card, second], next_cursor: 'opaque+/=' },
    }),
  );
  await page.route('**/api/v1/me/blocks*', async (route: Readonly<Route>) =>
    route.fulfill({ json: { people: [], next_cursor: null } }),
  );
  await page.route(`**/api/v1/people/${second.id}`, async (route: Readonly<Route>) => {
    returned = true;
    await route.fulfill({ status: 404, json: { code: 'person_unavailable' } });
  });
  await open(page, `?mode=find_help&cursor=opaque&person=${second.id}`);
  await expect(page.getByRole('heading', { name: second.display_name, exact: true })).toBeVisible();
  await checkpoint('paged-selected-person.png');
  await page.getByRole('link', { name: 'View profile', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/people/${second.id}$`));
  await expect(page.getByRole('alert')).toContainText('This profile is unavailable.');
  await checkpoint('person-unavailable.png');
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`cursor=opaque.*person=${second.id}`));
  await expect(page.getByRole('heading', { name: card.display_name, exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: second.display_name, exact: true })).toHaveCount(
    0,
  );
  await checkpoint('back-revalidated.png');
});
