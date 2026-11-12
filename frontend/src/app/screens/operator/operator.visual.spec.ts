import type { Page, Route } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import type { Api } from '../../api.generated';
import { account, accounts, detail, nullableDetail, operatorIdentity } from './operator.fixtures';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}>;
const target = `/api/v1/operator/accounts/${account.account_id}`;
async function setup(
  page: Readonly<Page>,
  list: Api['schemas']['OperatorAccountsResponse'] = accounts,
  record: Api['schemas']['OperatorAccountDetailResponse'] = detail,
): Promise<void> {
  await page.clock.setFixedTime(new Date('2026-11-08T06:20:00Z'));
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({ json: operatorIdentity }),
  );
  await page.route('**/api/v1/operator/accounts?*', (route: Readonly<Route>) =>
    route.fulfill({ json: list }),
  );
  await page.route(`**${target}`, (route: Readonly<Route>) => route.fulfill({ json: record }));
}
async function open(page: Readonly<Page>, query = ''): Promise<void> {
  await page.goto(`/operator/accounts${query}`);
  await expect(
    page.getByRole('heading', { name: 'Operator · accounts', exact: true }),
  ).toBeVisible();
}
async function search(page: Readonly<Page>): Promise<void> {
  await page.getByRole('button', { name: 'Search accounts', exact: true }).click();
}
async function selected(page: Readonly<Page>): Promise<void> {
  await open(page, `?lifecycle=all&account=${account.account_id}`);
  await expect(page.getByRole('region', { name: 'Account overview', exact: true })).toBeVisible();
}
function releaseHeld(release: (() => void) | undefined): void {
  if (release === undefined) throw new Error('Missing held boundary');
  release();
}

function retainedState(
  state: 'active' | 'hidden' | 'banned' | 'deleted',
): Api['schemas']['OperatorAccountResponse'] {
  return {
    ...account,
    hidden_at: state === 'hidden' ? account.created_at : null,
    banned_at: state === 'banned' ? account.created_at : null,
    deleted_at: state === 'deleted' ? account.created_at : null,
  };
}

test('M03 explicit account search accepts operator without student activation', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let reads = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/v1/operator/')) reads += 1;
  });
  await open(page);
  await expect(page.getByRole('form', { name: 'Account search' })).toBeVisible();
  expect(reads).toBe(0);
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill('Maya');
  expect(reads).toBe(0);
  await checkpoint('search-unsent.png');
  await search(page);
  await expect(page).toHaveURL(/name=Maya/);
  await expect(page.getByRole('region', { name: 'Account results' })).toContainText('Maya Lee');
  expect(reads).toBe(1);
  await checkpoint('search-results.png');
});

test('M03 loading and empty remain separate from denied or failed search', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/operator/accounts?*', async (route: Readonly<Route>) => {
    await held;
    await route.fulfill({ json: { accounts: [], next_cursor: null } });
  });
  await open(page, '?lifecycle=all');
  await expect(page.getByRole('status')).toContainText('Loading accounts');
  await checkpoint('search-loading.png');
  releaseHeld(release);
  await expect(page.getByText('No accounts match these filters.')).toBeVisible();
  await checkpoint('search-empty.png');
});

test('M03 filter validation preserves drafts and rejects malformed URL without inspection', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  const requests: readonly string[] = [];
  let reads = requests;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/v1/operator/'))
      reads = [...reads, request.url()];
  });
  await open(page);
  await page.getByRole('textbox', { name: 'Account ID', exact: true }).fill('U-123');
  await search(page);
  await expect(page.getByRole('alert')).toContainText('must be UUIDs');
  expect(reads).toHaveLength(0);
  await checkpoint('search-field-invalid.png');
  await open(page, '?hidden=not-a-boolean');
  await expect(page.getByRole('alert')).toContainText('valid lifecycle and visibility');
  expect(reads).toHaveLength(0);
  await checkpoint('search-url-invalid.png');
});

test('M03 all actual filters include ASCII Google subject and aware dates reset cursor', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route('**/api/v1/operator/accounts?*', (route: Readonly<Route>) => {
    const filters = new URL(route.request().url()).searchParams;
    const matching = {
      ...retainedState('deleted'),
      hidden_at: account.created_at,
      google_link: {
        id: '00000000-0000-4000-8000-000000000003',
        issuer: 'https://accounts.google.com',
        subject: 'subject_alpha-01',
        created_at: account.created_at,
      },
    };
    return route.fulfill({
      json: filters.has('google_subject') ? { accounts: [matching], next_cursor: null } : accounts,
    });
  });
  await open(page, '?lifecycle=all&cursor=old');
  await expect(page.getByText('Maya Lee', { exact: true })).toBeVisible();
  await page.getByRole('textbox', { name: 'Google subject', exact: true }).fill('subject_alpha-01');
  await page
    .getByRole('textbox', { name: 'Created from', exact: true })
    .fill('2026-10-01T00:00:00+08:00');
  await page
    .getByRole('textbox', { name: 'Created before', exact: true })
    .fill('2026-11-01T00:00:00Z');
  await page
    .getByRole('combobox', { name: 'Lifecycle', exact: true })
    .selectOption({ label: 'deleted' });
  await page
    .getByRole('combobox', { name: 'Profile visibility', exact: true })
    .selectOption({ label: 'hidden' });
  const response = page.waitForResponse(
    (item) =>
      new URL(item.url()).pathname === '/api/v1/operator/accounts' &&
      new URL(item.url()).searchParams.has('google_subject'),
  );
  await search(page);
  const url = new URL((await response).url());
  expect(url.searchParams.get('google_subject')).toBe('subject_alpha-01');
  expect(url.searchParams.get('hidden')).toBe('true');
  expect(url.searchParams.get('lifecycle')).toBe('deleted');
  expect(url.searchParams.get('cursor')).toBeNull();
  await expect(page).not.toHaveURL(/cursor=/);
  const results = page.getByRole('region', { name: 'Account results', exact: true });
  await expect(results).toContainText('Google subject: subject_alpha-01');
  await expect(results).toContainText('Deleted:');
  await expect(results).toContainText('Hidden:');
  await checkpoint('search-complete-filters.png');
});

test('M03 opaque paging and invalid cursor recovery keep filters without false totals', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route('**/api/v1/operator/accounts?*', (route: Readonly<Route>) => {
    const cursor = new URL(route.request().url()).searchParams.get('cursor');
    return cursor === null
      ? route.fulfill({ json: { ...accounts, next_cursor: 'opaque+/=' } })
      : route.fulfill({ status: 422, json: { code: 'invalid_cursor' } });
  });
  await open(page, '?name=Maya&lifecycle=all');
  await page.getByRole('button', { name: 'Next results' }).click();
  await expect(page).toHaveURL(/cursor=/);
  await expect(page.getByRole('alert')).toContainText('page cursor');
  await checkpoint('search-cursor-invalid.png');
  await page.getByRole('button', { name: 'First page', exact: true }).click();
  await expect(page).not.toHaveURL(/cursor=/);
  await expect(page.getByRole('region', { name: 'Account results' })).toContainText('Maya Lee');
  await checkpoint('search-cursor-recovered.png');
});

test('M03 safe service failure explicit retry never exposes retained results', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let failed = true;
  await page.route('**/api/v1/operator/accounts?*', (route: Readonly<Route>) =>
    failed
      ? route.fulfill({
          status: 503,
          json: { code: 'unavailable', request_id: 'operator-search-test' },
        })
      : route.fulfill({ json: accounts }),
  );
  await open(page, '?lifecycle=all');
  await expect(page.getByRole('alert')).toContainText('could not be completed');
  await expect(page.getByRole('region', { name: 'Account results' })).not.toContainText('Maya Lee');
  await checkpoint('search-service-error.png');
  failed = false;
  await page.getByRole('button', { name: 'Retry search' }).click();
  await expect(page.getByRole('region', { name: 'Account results' })).toContainText('Maya Lee');
  await checkpoint('search-service-recovered.png');
});

for (const state of ['active', 'hidden', 'banned', 'deleted'] as const)
  test(`M04 retained ${state} account embedded overview uses genuine text and metadata`, async ({
    page,
    checkpoint,
  }: Scenario) => {
    const row = retainedState(state);
    await setup(page, { ...accounts, accounts: [row] }, { ...detail, account: row });
    await selected(page);
    await expect(page.getByRole('region', { name: 'Profile', exact: true })).toContainText(
      'Information Technology',
    );
    await expect(page.getByRole('region', { name: 'Current goal', exact: true })).toContainText(
      'SQL JOINs',
    );
    await expect(page.getByRole('region', { name: 'Help subjects', exact: true })).toContainText(
      'Python',
    );
    await expect(page.locator('img')).toHaveCount(0);
    await expect(
      page.getByRole('region', { name: 'Record references', exact: true }).getByRole('link'),
    ).toHaveCount(0);
    await checkpoint(`overview-${state}.png`);
  });

test('M04 nullable records do not fabricate identity counts capabilities or links', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page, { ...accounts, accounts: [nullableDetail.account] }, nullableDetail);
  await selected(page);
  for (const section of [
    'Profile',
    'Current goal',
    'Help subjects',
    'Photo reference',
    'Profile lifecycle',
    'Discovery exposure',
    'Registration receipt',
  ]) {
    await expect(page.getByRole('region', { name: section, exact: true })).toContainText(
      'No stored record.',
    );
  }
  await expect(page.getByText('No stored references.')).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'Account overview', exact: true }),
  ).not.toContainText('Maya Lee');
  await checkpoint('overview-nullable.png');
});

test('M04 unavailable404 preserves independently authorized search and can retry detail', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let unavailable = true;
  await page.route(`**${target}`, (route: Readonly<Route>) =>
    unavailable
      ? route.fulfill({ status: 404, json: { code: 'operator_resource_unavailable' } })
      : route.fulfill({ json: detail }),
  );
  await open(page, `?lifecycle=all&account=${account.account_id}`);
  await expect(page.getByRole('region', { name: 'Account results' })).toContainText('Maya Lee');
  await expect(page.getByRole('alert')).toContainText('account record is unavailable');
  await checkpoint('overview-unavailable.png');
  unavailable = false;
  await page.getByRole('button', { name: 'Retry account' }).click();
  await expect(page.getByRole('region', { name: 'Account overview', exact: true })).toContainText(
    'SQL JOINs',
  );
  await checkpoint('overview-recovered.png');
});

test('M03 guest401 and ordinary403 are separate actual authority outcomes', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({ status: 401, json: { code: 'unauthenticated' } }),
  );
  await open(page);
  await expect(page.getByRole('link', { name: 'Continue to sign in' })).toHaveAttribute(
    'href',
    '/onboarding',
  );
  await checkpoint('operator-guest.png');
  await page.unroute('**/api/v1/me');
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({ json: operatorIdentity }),
  );
  await page.route('**/api/v1/operator/accounts?*', (route: Readonly<Route>) =>
    route.fulfill({ status: 403, json: { code: 'operator_access_denied' } }),
  );
  await open(page, '?lifecycle=all');
  await expect(page.getByRole('alert')).toContainText('Operator access denied');
  await expect(page.getByRole('form', { name: 'Account search' })).toHaveCount(0);
  await checkpoint('operator-denied.png');
});

test('M04 revocation hides cached sibling list after an explicit detail denial', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await open(page, '?lifecycle=all');
  await expect(page.getByRole('region', { name: 'Account results' })).toContainText('Maya Lee');
  await page.route(`**${target}`, (route: Readonly<Route>) =>
    route.fulfill({ status: 403, json: { code: 'operator_access_denied' } }),
  );
  await page
    .getByRole('link', { name: `Inspect account ${account.account_id}`, exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText('Operator access denied');
  await expect(page.getByText('Maya Lee', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Account results' })).toHaveCount(0);
  await checkpoint('operator-revoked.png');
});

test('M04 parallel denial prevents late sibling data from rendering', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let started: (() => void) | undefined;
  let finished: (() => void) | undefined;
  const entered = new Promise<void>((resolve) => {
    started = resolve;
  });
  const completed = new Promise<void>((resolve) => {
    finished = resolve;
  });
  await page.route(`**${target}`, async (route: Readonly<Route>) => {
    releaseHeld(started);
    await held;
    await route.fulfill({ json: detail });
    releaseHeld(finished);
  });
  await page.route('**/api/v1/operator/accounts?*', async (route: Readonly<Route>) => {
    await entered;
    await route.fulfill({ status: 403, json: { code: 'operator_access_denied' } });
  });
  await open(page, `?lifecycle=all&account=${account.account_id}`);
  await expect(page.getByRole('alert')).toContainText('Operator access denied');
  releaseHeld(release);
  await completed;
  await expect(page.getByRole('region', { name: 'Account overview', exact: true })).toHaveCount(0);
  await checkpoint('operator-denied-sibling.png');
});

test('M03 actor replacement after denied recheck cannot reuse previous operator data', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let replacement = false;
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({
      json: replacement
        ? { ...operatorIdentity, account_id: '00000000-0000-4000-8000-000000000099' }
        : operatorIdentity,
    }),
  );
  await page.route('**/api/v1/operator/accounts?*', (route: Readonly<Route>) =>
    replacement
      ? route.fulfill({ json: { accounts: [], next_cursor: null } })
      : route.fulfill({ status: 403, json: { code: 'operator_access_denied' } }),
  );
  await open(page, '?lifecycle=all');
  await expect(page.getByRole('alert')).toContainText('Operator access denied');
  replacement = true;
  await page.getByRole('button', { name: 'Check access again' }).click();
  await expect(page.getByText('No accounts match these filters.')).toBeVisible();
  await expect(page.getByText('Maya Lee', { exact: true })).toHaveCount(0);
  await checkpoint('operator-replacement.png');
});

test('MX keyboard and 320px text200 retain searchable fields without horizontal overflow', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.setViewportSize({ width: 320, height: 800 });
  await open(page);
  await page.getByRole('textbox', { name: 'Name', exact: true }).focus();
  await page.keyboard.type('Maya');
  await expect(page.getByRole('textbox', { name: 'Name', exact: true })).toBeFocused();
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  await search(page);
  await expect(page.getByRole('region', { name: 'Account results' })).toContainText('Maya Lee');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 320)).toBe(true);
  const labels = page.getByRole('form', { name: 'Account search' }).locator('label');
  await expect(labels).toHaveCount(10);
  expect(
    await labels.evaluateAll((elements: readonly Readonly<HTMLElement>[]) =>
      elements.every(
        (element: Readonly<HTMLElement>) => element.scrollWidth <= element.clientWidth,
      ),
    ),
  ).toBe(true);
  expect(
    await page
      .getByRole('button', { name: 'Search accounts', exact: true })
      .evaluate((button: Readonly<HTMLElement>) => {
        const range = document.createRange();
        range.selectNodeContents(button);
        const text = range.getBoundingClientRect();
        const control = button.getBoundingClientRect();
        return text.left >= control.left && text.right <= control.right;
      }),
  ).toBe(true);
  await checkpoint('operator-320-text200.png');
});

test('M03 session read failure retries without inspecting before live identity', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let failed = true;
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    failed
      ? route.fulfill({ status: 503, json: { code: 'unavailable' } })
      : route.fulfill({ json: operatorIdentity }),
  );
  await open(page, '?lifecycle=all');
  await expect(page.getByRole('alert')).toContainText('Your session could not be checked');
  await expect(page.getByRole('region', { name: 'Account results' })).toHaveCount(0);
  await checkpoint('operator-session-error.png');
  failed = false;
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Account results' })).toContainText('Maya Lee');
  await checkpoint('operator-session-recovered.png');
});

test('M04 expired inspection401 retires private content and rechecks canonical session', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let expired = false;
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    expired
      ? route.fulfill({ status: 401, json: { code: 'unauthenticated' } })
      : route.fulfill({ json: operatorIdentity }),
  );
  await page.route(`**${target}`, (route: Readonly<Route>) => {
    expired = true;
    return route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
  });
  await open(page, `?lifecycle=all&account=${account.account_id}`);
  await expect(page.getByRole('link', { name: 'Continue to sign in' })).toBeVisible();
  await expect(page.getByText('Maya Lee', { exact: true })).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(account.account_id));
  await checkpoint('operator-inspection-expired.png');
});

test('M03 network failure offers explicit retry with preserved filter URL', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let disconnected = true;
  await page.route('**/api/v1/operator/accounts?*', (route: Readonly<Route>) =>
    disconnected ? route.abort('internetdisconnected') : route.fulfill({ json: accounts }),
  );
  await open(page, '?name=Maya&lifecycle=all');
  await expect(page.getByRole('alert')).toContainText('could not be completed');
  await expect(page).toHaveURL(/name=Maya/);
  await checkpoint('operator-network-error.png');
  disconnected = false;
  await page.getByRole('button', { name: 'Retry search' }).click();
  await expect(page.getByRole('region', { name: 'Account results' })).toContainText('Maya Lee');
  await checkpoint('operator-network-recovered.png');
});
