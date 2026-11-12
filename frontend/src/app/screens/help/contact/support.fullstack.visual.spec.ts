import type { Page, TestInfo } from '@playwright/test';
import type { Api } from '../../../api.generated';
import { test, expect } from '../../../../../testing/visual';
import { formatDate } from '@angular/common';
import { verifyFixtureStudent } from '../../../../../testing/verified-student';
import { isRecentSupport, isSupportReceipt } from './support-contract';

interface Scenario {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}
function receiptResponse(value: unknown): Api['schemas']['SupportReceiptResponse'] {
  if (!isSupportReceipt(value)) throw new Error('Invalid actual support receipt');
  return value;
}
function recentResponse(value: unknown): Api['schemas']['RecentSupportCasesResponse'] {
  if (!isRecentSupport(value)) throw new Error('Invalid actual recent support receipts');
  return value;
}

// Run only in fresh Alembic-head cohort A, all three browser projects.
test('[support-cohort-a] A04 actual anonymous proof receipt and reload recovery without remembered case ID', async ({
  page,
  checkpoint,
}: Readonly<Scenario>, testInfo: Readonly<TestInfo>) => {
  // Real API/cookies/Postgres. No API interception, artificial case seed or provider promise.
  await page.goto('/help/contact');
  await expect(page.getByRole('button', { name: 'Send to the team' })).toBeEnabled();
  await page
    .getByRole('textbox', { name: 'Where we can reply' })
    .fill('support-fixture@example.invalid');
  await page
    .getByRole('textbox', { name: 'What’s happening?', exact: true })
    .fill('Controlled internal acceptance: cannot access the university inbox.');
  await checkpoint('pg-support-manual-form.png');
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' && response.url().endsWith('/api/v1/support-cases'),
  );
  await page.getByRole('button', { name: 'Send to the team' }).click();
  const response = await saved;
  expect(response.status()).toBe(201);
  const receipt = receiptResponse(await response.json());
  expect(receipt.status).toBe('received');
  expect(receipt.version).toBe(1);
  await expect(page.getByRole('heading', { name: 'Request received' })).toBeVisible();
  await expect(page.getByRole('status', { name: 'Support receipt' })).toContainText(
    `Reference: ${receipt.case_id}`,
  );
  await rawReceiptAttachment(page, testInfo, 'pg-support-received');
  await page.goto('/help/contact/status');
  await expect(page.getByText(`Reference: ${receipt.case_id}`, { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText(`Reference: ${receipt.case_id}`, { exact: true })).toBeVisible();
  await assertRecoveryReceipt(page, receipt);
  await rawReceiptAttachment(page, testInfo, 'pg-support-recovered-after-reload');
  const canonical = await page.request.get('/api/v1/support-cases');
  expect(canonical.status()).toBe(200);
  const recent = recentResponse(await canonical.json());
  expect(recent.cases.some((item) => item.case_id === receipt.case_id)).toBe(true);
  expect(
    await page.evaluate(() => ({
      // Taiga's public colour-scheme preference is the only allowed native key.
      // Application drafts, receipts, credentials and actor data must stay absent.
      local: Object.keys(localStorage).filter((key) => key !== 'tuiDark'),
      session: Object.keys(sessionStorage),
    })),
  ).toEqual({ local: [], session: [] });
});

// Run only in fresh Alembic-head cohort B; anonymous cohort A has its own schema.
test('[support-cohort-b] A04 real committed response loss recovers actor-owned status without proof or RAM ID', async ({
  page,
  checkpoint,
}: Readonly<Scenario>, testInfo: Readonly<TestInfo>) => {
  await verifyFixtureStudent(page, testInfo.project.name, 'support-auth');
  let committedWrites = 0;
  // Transport fault only: fetch the genuine server command to completion, then
  // discard its response. No fabricated DTO/status, SQL seed or quota bypass.
  await page.route('**/api/v1/me/support-cases', async (route) => {
    const response = await route.fetch();
    expect(response.status()).toBe(201);
    expect(receiptResponse(await response.json()).status).toBe('received');
    committedWrites += 1;
    await route.abort('failed');
  });
  await page.goto('/help/contact');
  await page
    .getByRole('textbox', { name: 'Where we can reply' })
    .fill('support-fixture@example.invalid');
  await page
    .getByRole('textbox', { name: 'What’s happening?', exact: true })
    .fill('Controlled internal acceptance: account-bound support request.');
  await page.getByRole('button', { name: 'Send to the team' }).click();
  await expect(page.getByRole('alert')).toContainText('whether your request was received');
  await checkpoint('pg-support-account-committed-response-lost.png');
  expect(committedWrites).toBe(1);
  await page.unroute('**/api/v1/me/support-cases');
  await page.context().clearCookies({ name: '__Host-peerly_support' });
  // Full navigation discards the form intent/key; recovery discovers its own ID.
  await page.goto('/help/contact/status');
  await expect(page.getByRole('heading', { name: 'Received', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Received', exact: true })).toBeVisible();
  const listed = await page.request.get('/api/v1/me/support-cases');
  expect(listed.status()).toBe(200);
  const receipt = singleReceipt(await listed.json());
  expect(receipt.status).toBe('received');
  expect(receipt.version).toBe(1);
  await assertRecoveryReceipt(page, receipt);
  await rawReceiptAttachment(
    page,
    testInfo,
    'pg-support-account-lost-response-recovered-without-proof',
  );
  const anonymous = await page.request.get('/api/v1/support-cases');
  expect(anonymous.status()).toBe(404);
  const owned = await page.request.get(`/api/v1/me/support-cases/${receipt.case_id}`);
  expect(owned.status()).toBe(200);
  expect(await owned.json()).toEqual(receipt);
  expect(committedWrites).toBe(1);
});

function singleReceipt(value: unknown): Api['schemas']['SupportReceiptResponse'] {
  const recent = recentResponse(value);
  expect(recent.cases).toHaveLength(1);
  const receipt = recent.cases[0];
  if (receipt === undefined) throw new Error('Missing actual account support receipt');
  return receipt;
}

async function assertRecoveryReceipt(
  page: Readonly<Page>,
  receipt: Api['schemas']['SupportReceiptResponse'],
): Promise<void> {
  // The production section has an accessible label, not an invented test ID.
  const section = page.locator('section[aria-label="Support request"]').filter({
    has: page.getByText(`Reference: ${receipt.case_id}`, { exact: true }),
  });
  const labels: Readonly<Record<Api['schemas']['SupportStatus'], string>> = {
    received: 'Received',
    in_review: 'In review',
    resolved: 'Resolved',
  };
  await expect(section).toHaveCount(1);
  await expect(section.getByRole('heading')).toHaveText(labels[receipt.status]);
  await expect(section.locator('p').nth(0)).toHaveText(`Reference: ${receipt.case_id}`);
  // Angular DatePipe's default en-US medium projection; all pinned projects use
  // Asia/Kuala_Lumpur (+0800). Values come only from the genuine API receipt.
  await expect(section.locator('p').nth(1)).toHaveText(
    `Received: ${formatDate(receipt.received_at, 'medium', 'en-US', '+0800')}`,
  );
  await expect(section.locator('p').nth(2)).toHaveText(
    `Updated: ${formatDate(receipt.changed_at, 'medium', 'en-US', '+0800')}`,
  );
}
async function rawReceiptAttachment(
  page: Readonly<Page>,
  info: Readonly<TestInfo>,
  name: string,
): Promise<void> {
  const viewport = page.viewportSize();
  if (viewport === null) throw new Error('Support PG requires the pinned browser viewport');
  const layout = await page.evaluate(() => ({
    width: window.innerWidth,
    height: window.innerHeight,
    contentWidth: document.documentElement.scrollWidth,
  }));
  expect(layout.width).toBe(viewport.width);
  expect(layout.height).toBe(viewport.height);
  expect(layout.contentWidth).toBeLessThanOrEqual(layout.width);
  // FULL raw page attachment only: NOT a golden comparison. UUIDs/times/content
  // remain visible; no masks/crop/style injection/clock or UUID substitution.
  await info.attach(`${name}-FULL-RAW-UNCOMPARED.png`, {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  });
}
