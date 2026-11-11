import type { Page, Response, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import {
  prepareOperatorFixture,
  changeOperatorFixtureGrant,
  readOperatorFixtureAudit,
} from '../../../../testing/operator-fixture';
import { isAccounts, isDetail } from './operator-contract';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}>;
async function actual(response: Readonly<Response>): Promise<unknown> {
  expect(response.status()).toBe(200);
  expect(response.headers()['cache-control']).toContain('no-store');
  return await response.json();
}
async function searchAccount(page: Readonly<Page>, id: string): Promise<void> {
  const loaded = page.waitForResponse(
    (response) => new URL(response.url()).pathname === '/api/v1/operator/accounts',
  );
  await page.goto(`/operator/accounts?lifecycle=all&account_id=${id}`);
  const value = await actual(await loaded);
  if (!isAccounts(value)) throw new Error('Malformed actual operator search');
  expect(value.accounts.map((item) => item.account_id)).toEqual([id]);
  await expect(
    page.getByRole('link', { name: `Inspect account ${id}`, exact: true }),
  ).toBeVisible();
}
async function inspect(page: Readonly<Page>, id: string): Promise<void> {
  const loaded = page.waitForResponse(
    (response) => new URL(response.url()).pathname === `/api/v1/operator/accounts/${id}`,
  );
  await page.getByRole('link', { name: `Inspect account ${id}`, exact: true }).click();
  const value = await actual(await loaded);
  if (!isDetail(value)) throw new Error('Malformed actual operator overview');
  expect(value.account.account_id).toBe(id);
  await expect(page.getByRole('region', { name: 'Account overview', exact: true })).toBeVisible();
}

test('real M03 M04 live granted incomplete operator inspects all retained lifecycle and nullable records with audited GETs', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'authorized', info.project.name);
  const identity = await page.request.get('/api/v1/me');
  expect(identity.status()).toBe(200);
  const value: unknown = await identity.json();
  expect(value).toMatchObject({
    account_id: seed.operatorId,
    capabilities: { can_use_student_features: false },
  });
  for (const [state, id] of Object.entries(seed.targets)) {
    await searchAccount(page, id);
    await inspect(page, id);
    await expect(page.locator('img')).toHaveCount(0);
    await checkpoint(`real-operator-${state}.png`);
  }
  const audit = await readOperatorFixtureAudit(page, seed.operatorId);
  expect(audit.audits).toBeGreaterThanOrEqual(10);
  expect(audit.linkedEvents).toBe(audit.audits);
});

test('real M03 ordinary Google session has no operator record authority', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'denied', info.project.name);
  const denied = page.waitForResponse(
    (response) => new URL(response.url()).pathname === '/api/v1/operator/accounts',
  );
  await page.goto(`/operator/accounts?lifecycle=all&account_id=${seed.targets.active}`);
  expect((await denied).status()).toBe(403);
  await expect(page.getByRole('alert')).toContainText('Operator access denied');
  await expect(page.getByRole('region', { name: 'Account results' })).toHaveCount(0);
  await checkpoint('real-operator-denied.png');
  expect((await readOperatorFixtureAudit(page, seed.operatorId)).audits).toBe(0);
});

test('real M04 revoked grant retires prior search and explicit recheck reads after restored grant', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'revocation', info.project.name);
  await searchAccount(page, seed.targets.active);
  const before = await readOperatorFixtureAudit(page, seed.operatorId);
  await changeOperatorFixtureGrant(page, seed.operatorId, false);
  const denied = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `/api/v1/operator/accounts/${seed.targets.active}`,
  );
  await page
    .getByRole('link', { name: `Inspect account ${seed.targets.active}`, exact: true })
    .click();
  expect((await denied).status()).toBe(403);
  await expect(page.getByRole('alert')).toContainText('Operator access denied');
  await expect(page.getByRole('region', { name: 'Account results' })).toHaveCount(0);
  await checkpoint('real-operator-revoked.png');
  expect((await readOperatorFixtureAudit(page, seed.operatorId)).audits).toBe(before.audits);
  await changeOperatorFixtureGrant(page, seed.operatorId, true);
  await page.getByRole('button', { name: 'Check access again' }).click();
  await expect(page.getByRole('region', { name: 'Account overview', exact: true })).toBeVisible();
  await checkpoint('real-operator-grant-restored.png');
  expect((await readOperatorFixtureAudit(page, seed.operatorId)).audits).toBeGreaterThan(
    before.audits,
  );
});

test('real M03 replacement Google actor rechecks actual grant and records its own inspection audit', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'replacement', info.project.name);
  await searchAccount(page, seed.targets.active);
  await changeOperatorFixtureGrant(page, seed.operatorId, false);
  await page
    .getByRole('link', { name: `Inspect account ${seed.targets.active}`, exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText('Operator access denied');
  const old = await readOperatorFixtureAudit(page, seed.operatorId);
  await seed.replaceActor();
  await page.getByRole('button', { name: 'Check access again' }).click();
  await expect(page.getByRole('region', { name: 'Account overview', exact: true })).toBeVisible();
  await checkpoint('real-operator-replacement.png');
  const replacement = await readOperatorFixtureAudit(page, seed.replacementId);
  expect(replacement.audits).toBeGreaterThanOrEqual(2);
  expect((await readOperatorFixtureAudit(page, seed.operatorId)).audits).toBe(old.audits);
});
