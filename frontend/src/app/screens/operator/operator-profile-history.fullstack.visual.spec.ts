import type { Page, Response, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import {
  prepareOperatorFixture,
  changeOperatorFixtureGrant,
  readOperatorFixtureAudit,
} from '../../../../testing/operator-fixture';
import { isProfileHistory } from './operator-profile-history-contract';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}>;

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

function response(page: Readonly<Page>, path: string): Promise<Response> {
  return page.waitForResponse((value) => new URL(value.url()).pathname === path);
}
async function actual(value: Readonly<Response>) {
  expect(value.status()).toBe(200);
  expect(value.headers()['cache-control']).toContain('no-store');
  const body: unknown = await value.json();
  if (!isProfileHistory(body)) throw new Error('Malformed actual retained profile history');
  return body;
}
async function open(page: Readonly<Page>, account: string) {
  const path = `/api/v1/operator/accounts/${account}/profile-history`;
  await page.goto(`/operator/accounts?account=${account}`);
  const button = page.getByRole('button', { name: 'Open retained profile history', exact: true });
  await expect(button).toBeVisible();
  const loaded = response(page, path);
  await button.click();
  const body = await actual(await loaded);
  await expect(
    page.getByRole('region', { name: 'Retained profile history', exact: true }),
  ).toBeVisible();
  return body;
}

test('real M06 retained53 history pages source versions beyond unchanged current pointer and audited unavailable owners', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'history', info.project.name);
  let successful = 0;
  page.on('response', (r) => {
    if (new URL(r.url()).pathname.startsWith('/api/v1/operator/') && r.status() === 200)
      successful += 1;
  });
  const overview = response(page, `/api/v1/operator/accounts/${seed.targets.active}`);
  const head = await open(page, seed.targets.active);
  const before: unknown = await (await overview).json();
  expect(before).toMatchObject({ account: { profile_version: 1 }, profile: { version: 1 } });
  expect(head.revisions.map((row) => row.version)).toEqual(
    Array.from({ length: 50 }, (_, i) => 53 - i),
  );
  expect(head.anchor_version).toBe(53);
  const latest = head.revisions.find((row) => row.version === 53);
  expect(latest).toMatchObject({
    task: 'offer_help',
    about: 'Literal <b>revision 53</b>\nOriginal spacing',
    languages: ['zh', 'en'],
  });
  expect(head.revisions.find((row) => row.version === 52)).toMatchObject({
    about: null,
    year_label: null,
  });
  expect(head.revisions.find((row) => row.version === 51)).toMatchObject({
    display_name: null,
    languages: [],
  });
  const panel = page.getByRole('region', { name: 'Retained profile history', exact: true });
  await expect(panel.locator('article')).toHaveCount(50);
  await expect(panel.locator('b')).toHaveCount(0);
  await captureLongHistory(page, checkpoint, 'real-profile-history-head');
  const older = response(page, `/api/v1/operator/accounts/${seed.targets.active}/profile-history`);
  await panel.getByRole('button', { name: 'Older revisions', exact: true }).click();
  const tail = await actual(await older);
  expect(tail.revisions.map((row) => row.version)).toEqual([3, 2, 1]);
  expect(tail.next_cursor).toBeNull();
  await expect(panel.getByRole('heading', { level: 3 })).toHaveText([
    'Version 3',
    'Version 2',
    'Version 1',
  ]);
  await checkpoint('real-profile-history-older.png');
  for (const [state, id] of [
    ['hidden', seed.targets.hidden],
    ['banned', seed.targets.banned],
    ['deleted', seed.targets.deleted],
  ] as const) {
    const value = await open(page, id);
    expect(value.account_id).toBe(id);
    expect(value.revisions).toHaveLength(50);
    await expect(panel.getByRole('heading', { name: 'Version 53', exact: true })).toBeVisible();
    await captureLongHistory(page, checkpoint, `real-profile-history-${state}`);
  }
  const unchanged = response(page, `/api/v1/operator/accounts/${seed.targets.active}`);
  await page.goto(`/operator/accounts?account=${seed.targets.active}`);
  const after: unknown = await (await unchanged).json();
  expect(after).toMatchObject({ account: { profile_version: 1 }, profile: { version: 1 } });
  await expect(
    page.getByRole('button', { name: 'Open retained profile history', exact: true }),
  ).toBeVisible();
  const audit = await readOperatorFixtureAudit(page, seed.operatorId);
  expect(audit.audits).toBe(successful);
  expect(audit.linkedEvents).toBe(audit.audits);
});

test('real M06 empty owner missing account and invalid cursor are distinct', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'history-empty', info.project.name);
  const empty = await open(page, seed.targets.nullable);
  expect(empty).toMatchObject({ anchor_version: 0, revisions: [], next_cursor: null });
  await expect(
    page.getByRole('region', { name: 'Retained profile history', exact: true }),
  ).toContainText('No retained profile revisions on this page.');
  await checkpoint('real-profile-history-empty.png');
  const badPath = `/api/v1/operator/accounts/${seed.targets.active}/profile-history`;
  const bad = response(page, badPath);
  await page.goto(
    `/operator/accounts?account=${seed.targets.active}&profile_history=open&profile_cursor=invalid-signed-cursor`,
  );
  expect((await bad).status()).toBe(422);
  await expect(page.getByRole('alert')).toContainText(
    'This profile history cursor could not be used',
  );
  await checkpoint('real-profile-history-invalid-cursor.png');
  const recovered = response(page, badPath);
  await page.getByRole('button', { name: 'First page', exact: true }).click();
  await actual(await recovered);
  await expect(page.getByRole('heading', { name: 'Version 1', exact: true })).toBeVisible();
  await checkpoint('real-profile-history-first-page.png');
  const missing = '00000000-0000-4000-8000-000000000099';
  const miss = response(page, `/api/v1/operator/accounts/${missing}/profile-history`);
  await page.goto(`/operator/accounts?account=${missing}&profile_history=open`);
  expect((await miss).status()).toBe(404);
  await expect(
    page.getByRole('region', { name: 'Retained profile history', exact: true }).getByRole('alert'),
  ).toContainText('This account profile history is unavailable');
  await checkpoint('real-profile-history-missing.png');
  const audit = await readOperatorFixtureAudit(page, seed.operatorId);
  expect(audit.audits).toBeGreaterThan(0);
  expect(audit.linkedEvents).toBe(audit.audits);
});

test('real M06 grant revoke retires history and overview until explicit current authority restore', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'history-revocation', info.project.name);
  const id = seed.targets.active;
  await open(page, id);
  const before = await readOperatorFixtureAudit(page, seed.operatorId);
  await changeOperatorFixtureGrant(page, seed.operatorId, false);
  const denied = response(page, `/api/v1/operator/accounts/${id}/profile-history`);
  await page.getByRole('button', { name: 'Refresh history', exact: true }).click();
  expect((await denied).status()).toBe(403);
  await expect(
    page.getByRole('heading', { name: 'Operator access denied', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'Retained profile history', exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('heading', { name: 'Account and identity', exact: true }),
  ).toHaveCount(0);
  expect((await readOperatorFixtureAudit(page, seed.operatorId)).audits).toBe(before.audits);
  await checkpoint('real-profile-history-revoked.png');
  await changeOperatorFixtureGrant(page, seed.operatorId, true);
  const restored = response(page, `/api/v1/operator/accounts/${id}/profile-history`);
  await page.getByRole('button', { name: 'Check access again', exact: true }).click();
  await actual(await restored);
  await expect(page.getByRole('heading', { name: 'Version 53', exact: true })).toBeVisible();
  await captureLongHistory(page, checkpoint, 'real-profile-history-restored');
  const after = await readOperatorFixtureAudit(page, seed.operatorId);
  expect(after.audits).toBeGreaterThan(before.audits);
  expect(after.linkedEvents).toBe(after.audits);
});

test('real M06 replacement resets previous actor cursor and320text200 keyboard preserves retained source', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'history-replacement', info.project.name);
  const id = seed.targets.active;
  const path = `/api/v1/operator/accounts/${id}/profile-history`;
  await open(page, id);
  const older = response(page, path);
  await page.getByRole('button', { name: 'Older revisions', exact: true }).click();
  await actual(await older);
  await expect(page).toHaveURL(/profile_cursor=/);
  await changeOperatorFixtureGrant(page, seed.operatorId, false);
  const denied = response(page, path);
  await page.getByRole('button', { name: 'Refresh history', exact: true }).click();
  expect((await denied).status()).toBe(403);
  await expect(
    page.getByRole('heading', { name: 'Operator access denied', exact: true }),
  ).toBeVisible();
  const old = await readOperatorFixtureAudit(page, seed.operatorId);
  await seed.replaceActor();
  const identity = response(page, '/api/v1/me');
  const next = response(page, path);
  await page.getByRole('button', { name: 'Check access again', exact: true }).click();
  const actor: unknown = await (await identity).json();
  expect(actor).toMatchObject({ account_id: seed.replacementId });
  const fresh = await next;
  expect(new URL(fresh.url()).searchParams.has('cursor')).toBe(false);
  await actual(fresh);
  await expect(page).not.toHaveURL(/profile_cursor=/);
  await expect(page.getByRole('heading', { name: 'Version 53', exact: true })).toBeVisible();
  await captureLongHistory(page, checkpoint, 'real-profile-history-replacement');
  await page.setViewportSize({ width: 320, height: 800 });
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  await page.getByRole('button', { name: 'Close retained profile history', exact: true }).focus();
  await page.keyboard.press('Enter');
  const button = page.getByRole('button', { name: 'Open retained profile history', exact: true });
  await expect(button).toBeVisible();
  await button.focus();
  const reopened = response(page, path);
  await page.keyboard.press('Enter');
  await actual(await reopened);
  await expect(page.getByRole('heading', { name: 'Version 53', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 320)).toBe(true);
  await captureLongHistory(page, checkpoint, 'real-profile-history320-keyboard');
  const current = await readOperatorFixtureAudit(page, seed.replacementId);
  expect(current.audits).toBeGreaterThanOrEqual(3);
  expect(current.linkedEvents).toBe(current.audits);
  expect((await readOperatorFixtureAudit(page, seed.operatorId)).audits).toBe(old.audits);
});
