import type { Page, Route } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { account, accounts, detail, operatorIdentity } from './operator.fixtures';
import { profilePage, storedProfile } from './operator-profile-history.fixtures';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}>;
const target = `/api/v1/operator/accounts/${account.account_id}`;
const history = `${target}/profile-history`;
const panelName = 'Retained profile history';

// WebKit cannot capture a dimension above32767px. This retained50-record page
// uses real viewport start/end comparisons; all50 source rows/order remain asserted.
// Other scenarios keep full-page comparisons. No masks, scaling or data omission.
async function captureLongHistory(
  page: Readonly<Page>,
  checkpoint: Scenario['checkpoint'],
  name: string,
): Promise<void> {
  const panel = page.getByRole('region', { name: 'Retained profile history', exact: true });
  await expect(panel.locator('article')).toHaveCount(50);
  await expect(page.getByText('Loading account…', { exact: true })).toHaveCount(0);
  const first = panel.getByRole('heading', { name: 'Version 53', exact: true });
  await first.scrollIntoViewIfNeeded();
  await expect(first).toBeInViewport({ ratio: 1 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await checkpoint(`${name}-start.png`, { fullPage: false });
  const older = panel.getByRole('button', { name: 'Older revisions', exact: true });
  await older.scrollIntoViewIfNeeded();
  await expect(older).toBeInViewport({ ratio: 1 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await checkpoint(`${name}-end.png`, { fullPage: false });
}

function releaseSource(value: (() => void) | undefined): void {
  if (value === undefined) throw new Error('Missing source release');
  value();
}
async function setup(page: Readonly<Page>): Promise<void> {
  await page.clock.setFixedTime(new Date('2026-11-10T06:20:00Z'));
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({ json: operatorIdentity }),
  );
  await page.route('**/api/v1/operator/accounts?*', (route: Readonly<Route>) =>
    route.fulfill({ json: accounts }),
  );
  await page.route(`**${target}`, (route: Readonly<Route>) => route.fulfill({ json: detail }));
  await page.route(`**${history}*`, (route: Readonly<Route>) =>
    route.fulfill({ json: profilePage }),
  );
}
async function open(page: Readonly<Page>, extra = ''): Promise<void> {
  await page.goto(`/operator/accounts?account=${account.account_id}${extra}`);
  await expect(
    page.getByRole('button', { name: 'Open retained profile history', exact: true }),
  ).toBeVisible();
}

test('M06 history requires explicit open and preserves raw source facts without markup', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let reads = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === history) reads += 1;
  });
  await open(page);
  await expect(
    page.getByRole('heading', { name: 'Account and identity', exact: true }),
  ).toBeVisible();
  expect(reads).toBe(0);
  await checkpoint('profile-history-closed.png');
  await page.getByRole('button', { name: 'Open retained profile history', exact: true }).click();
  const panel = page.getByRole('region', { name: panelName, exact: true });
  await expect(panel.getByRole('heading', { name: 'Version 53', exact: true })).toBeVisible();
  await expect(panel).toContainText('<b>Stored raw history</b>');
  await expect(panel.locator('b')).toHaveCount(0);
  await expect(panel).toContainText('Not recorded');
  await expect(panel).toContainText('Empty string');
  await expect(panel.locator('article').first().locator('dd > ol > li')).toHaveText([
    'zz-Legacy',
    'Empty string',
    'zz-Legacy',
    'EN',
  ]);
  await expect(panel).toContainText('offer_help');
  await expect(panel).toContainText('find_help');
  expect(reads).toBe(1);
  await checkpoint('profile-history-literal.png');
  await page.getByRole('button', { name: 'Close retained profile history', exact: true }).click();
  await expect(panel).toHaveCount(0);
  await expect(page).not.toHaveURL(/profile_history=/);
  await page.getByRole('button', { name: 'Open retained profile history', exact: true }).click();
  await expect(panel.getByRole('heading', { name: 'Version 53', exact: true })).toBeVisible();
  expect(reads).toBe(2);
  await checkpoint('profile-history-reopened.png');
});

test('M06 history loading is independent of unavailable overview', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${target}`, (route: Readonly<Route>) =>
    route.fulfill({ status: 503, json: { code: 'operator_source_unavailable' } }),
  );
  let release: (() => void) | undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(`**${history}*`, async (route: Readonly<Route>) => {
    await gate;
    await route.fulfill({ json: profilePage });
  });
  try {
    await page.goto(`/operator/accounts?account=${account.account_id}&profile_history=open`);
    await expect(
      page.getByRole('region', { name: panelName, exact: true }).getByRole('status'),
    ).toContainText('Loading profile history');
    await expect(page.getByRole('alert')).toContainText('The inspection could not be completed');
    await checkpoint('profile-history-loading-overview-unavailable.png');
    releaseSource(release);
    await expect(page.getByRole('heading', { name: 'Version 53', exact: true })).toBeVisible();
    await checkpoint('profile-history-overview-independent.png');
  } finally {
    release?.();
  }
});

test('M06 history pages 50 retained versions and valid anchor zero empty', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${history}*`, (route: Readonly<Route>) =>
    route.fulfill({
      json: new URL(route.request().url()).searchParams.has('cursor')
        ? {
            ...profilePage,
            revisions: [storedProfile(3), storedProfile(2), storedProfile(1)],
            next_cursor: null,
          }
        : {
            ...profilePage,
            revisions: Array.from({ length: 50 }, (_, i) => storedProfile(53 - i)),
          },
    }),
  );
  await open(page);
  await page.getByRole('button', { name: 'Open retained profile history', exact: true }).click();
  const panel = page.getByRole('region', { name: panelName, exact: true });
  await expect(panel.locator('article')).toHaveCount(50);
  await captureLongHistory(page, checkpoint, 'profile-history-fifty');
  await panel.getByRole('button', { name: 'Older revisions', exact: true }).click();
  await expect(panel.getByRole('heading', { level: 3 })).toHaveText([
    'Version 3',
    'Version 2',
    'Version 1',
  ]);
  await checkpoint('profile-history-older.png');
  await page.route(`**${history}*`, (route: Readonly<Route>) =>
    route.fulfill({
      json: { ...profilePage, anchor_version: 0, revisions: [], next_cursor: null },
    }),
  );
  await panel.getByRole('button', { name: 'First page', exact: true }).click();
  await expect(panel).toContainText('No retained profile revisions on this page.');
  await expect(panel).toContainText('Page anchor version 0');
  await checkpoint('profile-history-empty.png');
});

test('M06 history local503 retry404 and422 first page including same URL retry', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let status = 503;
  await page.route(`**${history}*`, (route: Readonly<Route>) =>
    route.fulfill(
      status === 200
        ? { json: profilePage }
        : { status, json: { code: 'controlled_history_failure' } },
    ),
  );
  await open(page);
  await page.getByRole('button', { name: 'Open retained profile history', exact: true }).click();
  const panel = page.getByRole('region', { name: panelName, exact: true });
  await expect(panel.getByRole('alert')).toContainText('Profile history could not be loaded');
  await checkpoint('profile-history-local503.png');
  status = 404;
  await panel.getByRole('button', { name: 'Retry history', exact: true }).click();
  await expect(panel.getByRole('alert')).toContainText(
    'This account profile history is unavailable',
  );
  await checkpoint('profile-history-missing404.png');
  status = 422;
  await panel.getByRole('button', { name: 'Retry history', exact: true }).click();
  await expect(panel.getByRole('alert')).toContainText(
    'This profile history cursor could not be used',
  );
  await checkpoint('profile-history-cursor422.png');
  status = 200;
  await panel.getByRole('button', { name: 'First page', exact: true }).click();
  await expect(panel.getByRole('heading', { name: 'Version 53', exact: true })).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Account and identity', exact: true }),
  ).toBeVisible();
  await checkpoint('profile-history-first-page-recovered.png');
});

test('M06 child403 retires private siblings and actor replacement resets signed cursor', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let denied = false;
  let replacement = false;
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({
      json: replacement
        ? { ...operatorIdentity, account_id: '00000000-0000-4000-8000-000000000099' }
        : operatorIdentity,
    }),
  );
  await page.route(`**${history}*`, (route: Readonly<Route>) =>
    route.fulfill(
      denied ? { status: 403, json: { code: 'operator_access_denied' } } : { json: profilePage },
    ),
  );
  await page.goto(
    `/operator/accounts?account=${account.account_id}&profile_history=open&profile_cursor=old-actor`,
  );
  await expect(page.getByRole('heading', { name: 'Version 53', exact: true })).toBeVisible();
  denied = true;
  await page.getByRole('button', { name: 'Refresh history', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Operator access denied', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('region', { name: panelName, exact: true })).toHaveCount(0);
  await expect(
    page.getByRole('heading', { name: 'Account and identity', exact: true }),
  ).toHaveCount(0);
  await checkpoint('profile-history-denied403.png');
  replacement = true;
  denied = false;
  const loaded = page.waitForResponse((r) => new URL(r.url()).pathname === history);
  await page.getByRole('button', { name: 'Check access again', exact: true }).click();
  expect(new URL((await loaded).url()).searchParams.has('cursor')).toBe(false);
  await expect(page).not.toHaveURL(/profile_cursor=/);
  await expect(page.getByRole('heading', { name: 'Version 53', exact: true })).toBeVisible();
  await checkpoint('profile-history-replacement-owner.png');
});

test('M06 child401 retires history before canonical guest session', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let guest = false;
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill(
      guest ? { status: 401, json: { code: 'unauthenticated' } } : { json: operatorIdentity },
    ),
  );
  await page.route(`**${history}*`, (route: Readonly<Route>) => {
    guest = true;
    return route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
  });
  await page.goto(`/operator/accounts?account=${account.account_id}&profile_history=open`);
  await expect(
    page.getByRole('heading', { name: 'Sign in with your operator Google account', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('region', { name: panelName, exact: true })).toHaveCount(0);
  await checkpoint('profile-history-session401.png');
});

test('MX history320 text200 preserves captions raw fields and keyboard close reopen', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.setViewportSize({ width: 320, height: 800 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await open(page);
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  const button = page.getByRole('button', { name: 'Open retained profile history', exact: true });
  await button.focus();
  await page.keyboard.press('Enter');
  const panel = page.getByRole('region', { name: panelName, exact: true });
  await expect(panel.getByRole('heading', { name: 'Version 53', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 320)).toBe(true);
  expect(
    await panel
      .locator('button,dt,dd,h2,h3')
      .evaluateAll((elements: readonly Readonly<HTMLElement>[]) =>
        elements.every((element: Readonly<HTMLElement>) => {
          if (!(element instanceof HTMLElement))
            throw new Error('Missing semantic history element');
          const bounds = element.getBoundingClientRect();
          const range = document.createRange();
          range.selectNodeContents(element);
          return (
            element.scrollWidth <= element.clientWidth &&
            element.scrollHeight <= element.clientHeight &&
            Array.from(range.getClientRects()).every(
              (rect: Readonly<DOMRect>) =>
                rect.left >= Math.max(0, bounds.left) && rect.right <= Math.min(320, bounds.right),
            )
          );
        }),
      ),
  ).toBe(true);
  await checkpoint('profile-history320-text200.png');
  await panel.getByRole('button', { name: 'Close retained profile history', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(panel).toHaveCount(0);
  await button.focus();
  await page.keyboard.press('Enter');
  await expect(panel.getByRole('heading', { name: 'Version 53', exact: true })).toBeVisible();
  await checkpoint('profile-history-keyboard-reopened.png');
});
