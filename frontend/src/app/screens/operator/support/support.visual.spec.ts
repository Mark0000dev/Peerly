import type { Page, Route, Locator } from '@playwright/test';
import { test, expect } from '../../../../../testing/visual';
import type { Api } from '../../../api.generated';
import {
  supportActor,
  supportCase,
  supportHistory,
  supportInbox,
  supportReceipt,
} from './support.fixtures';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?:
      Readonly<{ readonly fullPage: boolean }> | Readonly<{ readonly target: Readonly<Locator> }>,
  ) => Promise<void>;
}>;
const listPattern = /\/api\/v1\/operator\/cases(?:\?.*)?$/;
const base = `/api/v1/operator/cases/${supportReceipt.case_id}`;
const historyPattern = new RegExp(`${base}/history(?:\\?.*)?$`);
async function setup(page: Readonly<Page>): Promise<void> {
  await page.clock.setFixedTime(new Date('2026-11-10T06:20:00Z'));
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({ json: supportActor }),
  );
  await page.route(listPattern, (route: Readonly<Route>) => route.fulfill({ json: supportInbox }));
  await page.route(`**${base}`, (route: Readonly<Route>) => route.fulfill({ json: supportCase }));
  await page.route(historyPattern, (route: Readonly<Route>) =>
    route.fulfill({ json: supportHistory }),
  );
}
async function open(page: Readonly<Page>, selected = false, extra = ''): Promise<void> {
  await page.goto(
    '/operator/support' + (selected ? '?case=' + supportReceipt.case_id : '') + extra,
  );
  await expect(
    page.getByRole('heading', { name: 'Operator · student support', exact: true }),
  ).toBeVisible();
}
async function prepare(page: Readonly<Page>): Promise<void> {
  await page
    .getByRole('combobox', { name: 'New case status', exact: true })
    .selectOption({ label: 'in_review' });
  await page.getByRole('button', { name: 'Review status change', exact: true }).click();
  await expect(
    page.getByText('Confirm this status request. It sends no reply to the address above.', {
      exact: true,
    }),
  ).toBeVisible();
}
function release(value: (() => void) | undefined): void {
  if (value === undefined) throw new Error('Missing controlled source release');
  value();
}

test('support inbox metadata does not prefetch private content and explicit detail/history preserve literal source', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let detailReads = 0;
  let historyReads = 0;
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (path === base) detailReads += 1;
    if (path === base + '/history') historyReads += 1;
  });
  await open(page);
  const inbox = page.getByRole('region', { name: 'Support inbox', exact: true });
  await expect(inbox).toContainText('Code not arriving');
  await expect(inbox).not.toContainText(supportCase.reply_address);
  expect(detailReads).toBe(0);
  expect(historyReads).toBe(0);
  await checkpoint('support-inbox-metadata.png');
  await page
    .getByRole('button', { name: `Open support case ${supportReceipt.case_id}`, exact: true })
    .click();
  const detail = page.getByRole('region', { name: 'Selected support case', exact: true });
  await expect(detail).toContainText(supportCase.message);
  await expect(detail.locator('dd b')).toHaveCount(0);
  await expect(detail).toContainText('Not recorded');
  expect(historyReads).toBe(0);
  await checkpoint('support-private-detail.png');
  await page.getByRole('button', { name: 'Open retained status history', exact: true }).click();
  const history = page.getByRole('region', { name: 'Support status history', exact: true });
  await expect(history.getByRole('heading', { level: 3 })).toHaveText([
    'Version 3',
    'Version 2',
    'Version 1',
  ]);
  await expect(history).toContainText('Not recorded');
  await checkpoint('support-retained-history.png');
  await page.getByRole('button', { name: 'Close status history', exact: true }).click();
  await expect(history).toHaveCount(0);
  await expect(page).not.toHaveURL(/history=open/);
});

test('support filters are explicit and paging has no fabricated totals or private search fields', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let reads = 0;
  page.on('request', (request) => {
    if (listPattern.test(request.url())) reads += 1;
  });
  await page.route(listPattern, (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...supportInbox,
        next_cursor: new URL(route.request().url()).searchParams.has('cursor')
          ? null
          : 'signed-inbox-page',
      },
    }),
  );
  await open(page);
  await expect(page.getByRole('button', { name: 'Next support cases', exact: true })).toBeVisible();
  const initial = reads;
  await page
    .getByRole('textbox', { name: 'Account ID', exact: true })
    .fill(supportActor.account_id);
  expect(reads).toBe(initial);
  await page
    .getByRole('combobox', { name: 'No linked account', exact: true })
    .selectOption({ label: 'true' });
  await page.getByRole('button', { name: 'Search support cases', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText(
    'An anonymous case filter cannot specify an account',
  );
  expect(reads).toBe(initial);
  await checkpoint('support-filter-invalid.png');
  await page.getByRole('textbox', { name: 'Account ID', exact: true }).fill('');
  await page.getByRole('button', { name: 'Search support cases', exact: true }).click();
  await expect(page).toHaveURL(/anonymous=true/);
  await expect(page.getByRole('button', { name: 'Next support cases', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Next support cases', exact: true }).click();
  await expect(page).toHaveURL(/cursor=signed-inbox-page/);
  await expect(page.getByRole('button', { name: 'Next support cases', exact: true })).toHaveCount(
    0,
  );
  await checkpoint('support-inbox-older.png');
  await page.getByRole('combobox', { name: 'Topic', exact: true }).selectOption({ label: 'other' });
  await page.getByRole('button', { name: 'Search support cases', exact: true }).click();
  await expect(page).not.toHaveURL(/cursor=/);
  await expect(page).toHaveURL(/topic=other/);
  await checkpoint('support-filter-reset-page.png');
});

test('support valid empty inbox and registered versus anonymous references stay literal', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(listPattern, (route: Readonly<Route>) =>
    route.fulfill({ json: { ...supportInbox, cases: [] } }),
  );
  await open(page);
  await expect(page.getByRole('region', { name: 'Support inbox', exact: true })).toContainText(
    'No support cases match these filters.',
  );
  await checkpoint('support-inbox-empty.png');
  await page.route(`**${base}`, (route: Readonly<Route>) =>
    route.fulfill({ json: { ...supportCase, actor_id: supportActor.account_id, details: '' } }),
  );
  await open(page, true);
  const selected = page.getByRole('region', { name: 'Selected support case', exact: true });
  await expect(
    selected.getByRole('link', { name: supportActor.account_id, exact: true }),
  ).toHaveAttribute('href', `/operator/accounts?account=${supportActor.account_id}`);
  await expect(selected).toContainText('Empty string');
  await checkpoint('support-linked-account.png');
});

test('support source loading and local503 do not invent missing cases or block other panels', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let unblock: (() => void) | undefined;
  const gate = new Promise<void>((resolve) => {
    unblock = resolve;
  });
  await page.route(`**${base}`, async (route: Readonly<Route>) => {
    await gate;
    await route.fulfill({ status: 503, json: { code: 'storage_unavailable' } });
  });
  try {
    await open(page, true);
    await expect(
      page.getByRole('region', { name: 'Selected support case', exact: true }).getByRole('status'),
    ).toContainText('Loading support case');
    await expect(page.getByRole('region', { name: 'Support inbox', exact: true })).toContainText(
      'Code not arriving',
    );
    await checkpoint('support-case-loading.png');
    release(unblock);
    await expect(
      page.getByRole('region', { name: 'Selected support case', exact: true }).getByRole('alert'),
    ).toContainText('This support record could not be loaded');
    await checkpoint('support-case-local503.png');
  } finally {
    unblock?.();
  }
  await page.route(`**${base}`, (route: Readonly<Route>) => route.fulfill({ json: supportCase }));
  await page.getByRole('button', { name: 'Retry case', exact: true }).click();
  await expect(page.getByText(supportCase.message, { exact: true })).toBeVisible();
  await checkpoint('support-case-retry.png');
});

test('support history50 continuation and explicit first page422 preserve current record', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(historyPattern, (route: Readonly<Route>) =>
    route.fulfill(
      new URL(route.request().url()).searchParams.has('cursor')
        ? { status: 422, json: { code: 'invalid_cursor' } }
        : {
            json: {
              ...supportHistory,
              anchor_version: 53,
              revisions: Array.from({ length: 50 }, (_, index) => ({
                version: 53 - index,
                status: 'in_review',
                changed_at: '2026-11-02T06:00:00Z',
                changed_by_id: supportActor.account_id,
                operator_access_version: 1,
              })),
            },
          },
    ),
  );
  await open(page, true);
  await page.getByRole('button', { name: 'Open retained status history', exact: true }).click();
  const history = page.getByRole('region', { name: 'Support status history', exact: true });
  await expect(history.locator('article')).toHaveCount(50);
  await history
    .getByRole('heading', { name: 'Retained status history', exact: true })
    .scrollIntoViewIfNeeded();
  await checkpoint('support-history-fifty-start.png', { fullPage: false });
  await history.getByRole('heading', { name: 'Version 4', exact: true }).scrollIntoViewIfNeeded();
  await checkpoint('support-history-fifty-end.png', { fullPage: false });
  await history.getByRole('button', { name: 'Older status revisions', exact: true }).click();
  await expect(history.getByRole('alert')).toContainText(
    'These filters or this page cursor could not be used',
  );
  await expect(page.getByText(supportCase.message, { exact: true })).toBeVisible();
  await checkpoint('support-history-cursor422.png');
  await history.getByRole('button', { name: 'First history page', exact: true }).click();
  await expect(history.locator('article')).toHaveCount(50);
  await expect(page).not.toHaveURL(/history_cursor=/);
  await history
    .getByRole('heading', { name: 'Retained status history', exact: true })
    .scrollIntoViewIfNeeded();
  await checkpoint('support-history-first-page-start.png', { fullPage: false });
  await history.getByRole('heading', { name: 'Version 4', exact: true }).scrollIntoViewIfNeeded();
  await checkpoint('support-history-first-page-end.png', { fullPage: false });
});

test('support status requires explicit confirmation and uses the exact current version with no account proof action', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let writes = 0;
  let canonical: Api['schemas']['OperatorSupportResponse'] = supportCase;
  await page.route(`**${base}`, (route: Readonly<Route>) => route.fulfill({ json: canonical }));
  await page.route(`**${base}/status`, async (route: Readonly<Route>) => {
    writes += 1;
    const body: unknown = route.request().postDataJSON();
    expect(body).toEqual({ status: 'in_review', expected_version: 3 });
    expect(route.request().headers()['x-csrf-token']).toBe(supportActor.csrf_token);
    canonical = {
      ...supportCase,
      receipt: {
        ...supportReceipt,
        status: 'in_review',
        version: 4,
        changed_at: '2026-11-02T07:00:00Z',
      },
    };
    await route.fulfill({ json: canonical.receipt });
  });
  await open(page, true);
  await expect(page.getByText(supportCase.message, { exact: true })).toBeVisible();
  await prepare(page);
  expect(writes).toBe(0);
  await checkpoint('support-status-confirmation.png');
  await page.getByRole('button', { name: 'Confirm status change', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Recorded result for your request', exact: true }),
  ).toBeVisible();
  expect(writes).toBe(1);
  await expect(page.getByRole('button', { name: /verify.*email/i })).toHaveCount(0);
  await checkpoint('support-status-receipt.png');
});

test('support unknown status replay keeps original key/body and never replaces newer canonical data with its old receipt', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let canonical: Api['schemas']['OperatorSupportResponse'] = supportCase;
  let writes: readonly Readonly<{ readonly body: unknown; readonly key: string | undefined }>[] =
    [];
  await page.route(`**${base}`, (route: Readonly<Route>) => route.fulfill({ json: canonical }));
  await page.route(`**${base}/status`, async (route: Readonly<Route>) => {
    const body: unknown = route.request().postDataJSON();
    writes = [...writes, { body, key: route.request().headers()['idempotency-key'] }];
    canonical = {
      ...supportCase,
      receipt: {
        ...supportReceipt,
        status: 'in_review',
        version: 4,
        changed_at: '2026-11-02T07:00:00Z',
      },
    };
    if (writes.length === 1) {
      await route.fulfill({ status: 503, json: { code: 'storage_unavailable' } });
      return;
    }
    const original = canonical.receipt;
    canonical = {
      ...supportCase,
      receipt: {
        ...supportReceipt,
        status: 'resolved',
        version: 5,
        changed_at: '2026-11-02T08:00:00Z',
      },
    };
    await route.fulfill({ json: original });
  });
  await open(page, true);
  await expect(page.getByText(supportCase.message, { exact: true })).toBeVisible();
  await prepare(page);
  await page.getByRole('button', { name: 'Confirm status change', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('We could not confirm the result');
  await checkpoint('support-status-unknown.png');
  await page.getByRole('button', { name: 'Check current case', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('We could not confirm the result');
  await expect(
    page.getByRole('heading', { name: 'Recorded result for your request', exact: true }),
  ).toHaveCount(0);
  await checkpoint('support-status-matching-current-not-proof.png');
  await page.getByRole('button', { name: 'Retry the same status change', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Recorded result for your request', exact: true }),
  ).toBeVisible();
  expect(writes).toHaveLength(2);
  expect(writes[1]).toEqual(writes[0]);
  await expect(
    page.getByRole('region', { name: 'Selected support case', exact: true }),
  ).toContainText('This receipt records the original result');
  await checkpoint('support-status-original-receipt-newer-current.png');
});

test('support status CAS409 requires fresh explicit reconcile instead of silently reissuing a new command', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${base}/status`, (route: Readonly<Route>) =>
    route.fulfill({ status: 409, json: { code: 'support_version_conflict' } }),
  );
  await open(page, true);
  await expect(page.getByText(supportCase.message, { exact: true })).toBeVisible();
  await prepare(page);
  await page.getByRole('button', { name: 'Confirm status change', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('This request conflicts');
  await checkpoint('support-status-conflict.png');
  await page
    .getByRole('button', { name: 'Use current case for a new change', exact: true })
    .click();
  await expect(page.getByRole('dialog')).toContainText('Use the current case for a new change?');
  await checkpoint('support-status-reconcile-confirmation.png');
  await page.getByRole('button', { name: 'Use current case', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Review status change', exact: true }),
  ).toBeEnabled();
  await checkpoint('support-status-reconciled.png');
});

test('support settled status403 hides all private records until explicit authority recheck', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${base}/status`, (route: Readonly<Route>) =>
    route.fulfill({ status: 403, json: { code: 'operator_access_denied' } }),
  );
  await open(page, true);
  await expect(page.getByText(supportCase.message, { exact: true })).toBeVisible();
  await prepare(page);
  await page.getByRole('button', { name: 'Confirm status change', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Operator access denied', exact: true }),
  ).toBeVisible();
  await expect(page.getByText(supportCase.reply_address, { exact: true })).toHaveCount(0);
  await checkpoint('support-write-denied403.png');
  await page.getByRole('button', { name: 'Check access again', exact: true }).click();
  await expect(page.getByText(supportCase.message, { exact: true })).toBeVisible();
  await checkpoint('support-access-rechecked.png');
});

test('support case404 and canonical401 guest never invent access or reveal private content', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${base}`, (route: Readonly<Route>) =>
    route.fulfill({ status: 404, json: { code: 'support_unavailable' } }),
  );
  await open(page, true);
  await expect(
    page.getByRole('region', { name: 'Selected support case', exact: true }).getByRole('alert'),
  ).toContainText('This support case or history is unavailable');
  await checkpoint('support-case-missing404.png');
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({ status: 401, json: { code: 'unauthenticated' } }),
  );
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Sign in with your operator Google account', exact: true }),
  ).toBeVisible();
  await expect(page.getByText(supportCase.reply_address, { exact: true })).toHaveCount(0);
  await checkpoint('support-session401.png');
});

test('support320text200 preserves complete labels raw content and keyboard status confirmation', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(listPattern, (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...supportInbox,
        cases: supportInbox.cases.map((row) => ({ ...row, actor_id: supportActor.account_id })),
      },
    }),
  );
  await page.setViewportSize({ width: 320, height: 800 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await open(page, true);
  await expect(page.getByText(supportCase.message, { exact: true })).toBeVisible();
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  const linkedRows = page
    .getByRole('region', { name: 'Support inbox', exact: true })
    .locator('li a');
  expect(await linkedRows.count()).toBeGreaterThan(0);
  expect(
    await linkedRows.evaluateAll((links: readonly Readonly<HTMLAnchorElement>[]) =>
      links.every((link) => {
        const button = link.closest('li')?.querySelector('button');
        if (button === null || button === undefined) return false;
        const bounds = button.getBoundingClientRect();
        const text = document.createRange();
        text.selectNodeContents(link);
        return Array.from(text.getClientRects()).every(
          (rect: Readonly<DOMRect>) =>
            rect.bottom <= bounds.top ||
            rect.top >= bounds.bottom ||
            rect.right <= bounds.left ||
            rect.left >= bounds.right,
        );
      }),
    ),
  ).toBe(true);

  await page.getByRole('combobox', { name: 'New case status', exact: true }).focus();
  await page
    .getByRole('combobox', { name: 'New case status', exact: true })
    .selectOption({ label: 'in_review' });
  await page.getByRole('button', { name: 'Review status change', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('button', { name: 'Confirm status change', exact: true }),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 320)).toBe(true);
  expect(
    await page
      .locator('main button,main label,main dt,main dd,main h1,main h2')
      .evaluateAll((nodes: readonly Readonly<HTMLElement>[]) =>
        nodes.every((node: Readonly<HTMLElement>) => {
          const bounds = node.getBoundingClientRect();
          const range = document.createRange();
          range.selectNodeContents(node);
          return (
            node.scrollWidth <= node.clientWidth &&
            node.scrollHeight <= node.clientHeight &&
            Array.from(range.getClientRects()).every(
              (rect: Readonly<DOMRect>) =>
                rect.left >= Math.max(0, bounds.left) && rect.right <= Math.min(320, bounds.right),
            )
          );
        }),
      ),
  ).toBe(true);
  await checkpoint('support320-text200-confirmation.png');
});

test('support unknown write guards real Account records navigation with Keep and Leave choices', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let writes = 0;
  await page.route(`**${base}/status`, (route: Readonly<Route>) => {
    writes += 1;
    return route.fulfill({ status: 503, json: { code: 'storage_unavailable' } });
  });
  await open(page, true);
  await expect(page.getByText(supportCase.message, { exact: true })).toBeVisible();
  await prepare(page);
  await page.getByRole('button', { name: 'Confirm status change', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('We could not confirm the result');
  await page.getByRole('link', { name: 'Account records', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Leave before the save is confirmed?', exact: true }),
  ).toBeVisible();
  await checkpoint('support-unknown-leave-confirmation.png');
  await page.getByRole('button', { name: 'Keep editing', exact: true }).click();
  await expect(page).toHaveURL(/operator\/support/);
  await expect(
    page.getByRole('button', { name: 'Retry the same status change', exact: true }),
  ).toBeVisible();
  await checkpoint('support-unknown-keep-editor.png');
  await page.getByRole('link', { name: 'Account records', exact: true }).click();
  await page.getByRole('button', { name: 'Leave editor', exact: true }).click();
  await expect(page).toHaveURL(/operator\/accounts/);
  expect(writes).toBe(1);
  await checkpoint('support-unknown-left-editor.png');
});

test('support browser Back preserves unknown intent until explicit source departure', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let writes = 0;
  await page.route(`**${base}/status`, (route: Readonly<Route>) => {
    writes += 1;
    return route.fulfill({ status: 503, json: { code: 'storage_unavailable' } });
  });
  await open(page);
  await page
    .getByRole('button', { name: `Open support case ${supportReceipt.case_id}`, exact: true })
    .click();
  await expect(page.getByText(supportCase.message, { exact: true })).toBeVisible();
  await prepare(page);
  await page.getByRole('button', { name: 'Confirm status change', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('We could not confirm the result');
  await page.evaluate(() => {
    window.history.back();
  });
  await expect(
    page.getByRole('heading', { name: 'Leave before the save is confirmed?', exact: true }),
  ).toBeVisible();
  await checkpoint('support-unknown-back-confirmation.png');
  await page.getByRole('button', { name: 'Keep editing', exact: true }).click();
  await expect(page).toHaveURL(/case=/);
  await expect(
    page.getByRole('button', { name: 'Retry the same status change', exact: true }),
  ).toBeVisible();
  await checkpoint('support-unknown-back-kept.png');
  await page.evaluate(() => {
    window.history.back();
  });
  await page.getByRole('button', { name: 'Leave editor', exact: true }).click();
  await expect(page).not.toHaveURL(/case=/);
  await expect(
    page.getByRole('region', { name: 'Selected support case', exact: true }),
  ).toHaveCount(0);
  expect(writes).toBe(1);
  await checkpoint('support-unknown-back-left.png');
});
