import type { Page, Response, Route, TestInfo, Locator } from '@playwright/test';
import { test, expect } from '../../../../../testing/visual';
import {
  prepareOperatorFixture,
  changeOperatorFixtureGrant,
  readOperatorFixtureAudit,
} from '../../../../../testing/operator-fixture';
import type { Api } from '../../../api.generated';
import {
  isSupportInbox,
  isSupportCase,
  isSupportHistory,
  isSupportReceipt,
  statusText,
} from './support-contract';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?:
      Readonly<{ readonly fullPage: boolean }> | Readonly<{ readonly target: Readonly<Locator> }>,
  ) => Promise<void>;
}>;
const root = '/api/v1/operator/cases';
const selected = (page: Readonly<Page>) =>
  page.getByRole('region', { name: 'Selected support case', exact: true });
const history = (page: Readonly<Page>) =>
  page.getByRole('region', { name: 'Support status history', exact: true });
const inbox = (page: Readonly<Page>) =>
  page.getByRole('region', { name: 'Support inbox', exact: true });
function required<T>(value: T | null): T {
  if (value === null) throw new Error('Missing actual controlled support sources');
  return value;
}
function response(page: Readonly<Page>, path: string, method = 'GET'): Promise<Response> {
  return page.waitForResponse(
    (r) => new URL(r.url()).pathname === path && r.request().method() === method,
  );
}
async function actual<T>(
  response: Readonly<Response>,
  guard: (value: unknown) => value is T,
): Promise<T> {
  expect(response.status()).toBe(200);
  expect(response.headers()['cache-control']).toBe('no-store');
  const body: unknown = await response.json();
  if (!guard(body)) throw new Error('Invalid actual support response');
  return body;
}
async function audit(page: Readonly<Page>, actor: string): Promise<void> {
  const value = await readOperatorFixtureAudit(page, actor);
  expect(value.audits).toBeGreaterThan(0);
  expect(value.linkedEvents).toBe(value.audits);
}
async function openCase(
  page: Readonly<Page>,
  id: string,
): Promise<Api['schemas']['OperatorSupportResponse']> {
  const read = response(page, `${root}/${id}`);
  await page.goto(`/operator/support?case_id=${id}&case=${id}`);
  const value = await actual(await read, isSupportCase);
  await expect(selected(page)).toContainText(value.message);
  return value;
}
async function prepare(page: Readonly<Page>): Promise<void> {
  await page
    .getByRole('combobox', { name: 'New case status', exact: true })
    .selectOption({ label: 'in_review' });
  await page.getByRole('button', { name: 'Review status change', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Confirm status change', exact: true }),
  ).toBeEnabled();
}
async function receiptDom(
  page: Readonly<Page>,
  value: Api['schemas']['SupportReceiptResponse'],
): Promise<void> {
  const result = selected(page)
    .getByRole('status')
    .filter({
      has: page.getByRole('heading', { name: 'Recorded result for your request', exact: true }),
    });
  await expect(
    result.getByRole('heading', { name: 'Recorded result for your request', exact: true }),
  ).toBeVisible();
  await expect(result).toContainText(
    `${statusText(value.status)} · version ${String(value.version)}`,
  );
  await expect(result).toContainText(value.received_at);
  await expect(result).toContainText(value.changed_at);
  await expect(selected(page)).toContainText(value.case_id);
}
async function raw(page: Readonly<Page>, info: Readonly<TestInfo>, name: string): Promise<void> {
  await info.attach(name, {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  });
}
async function commandEvidence(
  page: Readonly<Page>,
  info: Readonly<TestInfo>,
  checkpoint: Scenario['checkpoint'],
  name: string,
): Promise<void> {
  await expect(page.getByText('Loading support case…', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Loading support cases…', { exact: true })).toHaveCount(0);
  await raw(page, info, `${name}-full-runtime.png`);
  await checkpoint(`${name}-choice.png`, {
    target: page.getByRole('form', { name: 'Support status choice', exact: true }),
  });
}

// Every HTTP response below is the genuine local application + PostgreSQL fixture.
// Transport interception only loses an actual committed response or issues a genuine
// concurrent PUT via route.fetch; no application response/DTO is fabricated.
test('real support metadata53 keyset source order private lazy content and audited history53', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'support', info.project.name);
  const refs = required(seed.support);
  let privateReads = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith(`${root}/`)) privateReads += 1;
  });
  const read = response(page, root);
  await page.goto(
    '/operator/support?' +
      new URLSearchParams({
        received_from: refs.receivedFrom,
        received_before: refs.receivedBefore,
      }).toString(),
  );
  const first = await actual(await read, isSupportInbox);
  expect(first.cases).toHaveLength(50);
  expect(first.cases[0]?.case_id).toBe(refs.caseId);
  expect(first.next_cursor).not.toBeNull();
  expect(privateReads).toBe(0);
  await expect(inbox(page).locator('li')).toHaveCount(50);
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

  await expect(inbox(page).locator('li')).toContainText(first.cases.map((row) => row.case_id));
  await expect(inbox(page)).not.toContainText('synthetic-support-0@example.test');
  expect(
    first.cases.every((row, index) => {
      const previous = first.cases[index - 1];
      return (
        previous === undefined || Date.parse(previous.received_at) >= Date.parse(row.received_at)
      );
    }),
  ).toBe(true);
  const firstRow = inbox(page).locator('li').first();
  await firstRow.scrollIntoViewIfNeeded();
  await expect(firstRow).toBeInViewport();
  await checkpoint('real-support-inbox50-start.png', { fullPage: false });
  await inbox(page)
    .getByRole('button', {
      name: `Open support case ${required(first.cases.at(-1) ?? null).case_id}`,
      exact: true,
    })
    .scrollIntoViewIfNeeded();
  await checkpoint('real-support-inbox50-end.png', { fullPage: false });
  const olderRead = response(page, root);
  await page.getByRole('button', { name: 'Next support cases', exact: true }).click();
  const older = await actual(await olderRead, isSupportInbox);
  expect(older.cases).toHaveLength(3);
  expect(older.next_cursor).toBeNull();
  expect(new Set([...first.cases, ...older.cases].map((row) => row.case_id)).size).toBe(53);
  await expect(inbox(page).locator('li')).toHaveCount(3);
  await checkpoint('real-support-inbox-older3.png');
  const detail = await openCase(page, refs.caseId);
  expect(detail.actor_id).toBe(seed.targets.active);
  expect(detail.message).toBe('Literal <b>support 0</b>\nOriginal second line');
  await expect(selected(page).locator('dd b')).toHaveCount(0);
  await checkpoint('real-support-literal-detail.png');
  const firstHistoryRead = response(page, `${root}/${refs.caseId}/history`);
  await page.getByRole('button', { name: 'Open retained status history', exact: true }).click();
  const revisions = await actual(await firstHistoryRead, isSupportHistory);
  expect(revisions.anchor_version).toBe(53);
  expect(revisions.revisions.map((row) => row.version)).toEqual(
    Array.from({ length: 50 }, (_, i) => 53 - i),
  );
  await expect(history(page).locator('article')).toHaveCount(50);
  await expect(history(page).getByRole('heading', { level: 3 })).toHaveText(
    revisions.revisions.map((row) => `Version ${String(row.version)}`),
  );
  await history(page)
    .getByRole('heading', { name: 'Retained status history', exact: true })
    .scrollIntoViewIfNeeded();
  await checkpoint('real-support-history50-start.png', { fullPage: false });
  await history(page)
    .getByRole('heading', { name: 'Version 4', exact: true })
    .scrollIntoViewIfNeeded();
  await checkpoint('real-support-history50-end.png', { fullPage: false });
  const olderHistoryRead = response(page, `${root}/${refs.caseId}/history`);
  await page.getByRole('button', { name: 'Older status revisions', exact: true }).click();
  const olderRevisions = await actual(await olderHistoryRead, isSupportHistory);
  expect(olderRevisions.revisions.map((row) => row.version)).toEqual([3, 2, 1]);
  expect(olderRevisions.anchor_version).toBe(53);
  expect(olderRevisions.revisions.at(-1)?.changed_by_id).toBeNull();
  expect(olderRevisions.revisions.at(-1)?.operator_access_version).toBeNull();
  await expect(history(page).locator('article')).toHaveCount(3);
  await expect(
    history(page).getByRole('article', { name: 'Status revision 1', exact: true }),
  ).toContainText('Not recorded');
  await checkpoint('real-support-history-older3-null-provenance.png');
  await audit(page, seed.operatorId);
});

test('real support anonymous null details and retained deleted actor are genuine stored references', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'support-references', info.project.name);
  const refs = required(seed.support);
  const anonymous = await openCase(page, refs.anonymousId);
  expect(anonymous.actor_id).toBeNull();
  expect(anonymous.details).toBeNull();
  await expect(selected(page)).toContainText('No linked account');
  await expect(selected(page)).toContainText('Not recorded');
  await checkpoint('real-support-anonymous-null.png');
  const retained = await openCase(page, refs.retainedId);
  expect(retained.actor_id).toBe(seed.targets.deleted);
  await expect(
    selected(page).getByRole('link', { name: seed.targets.deleted, exact: true }),
  ).toHaveAttribute('href', `/operator/accounts?account=${seed.targets.deleted}`);
  await expect(selected(page)).toContainText('Synthetic retained details');
  await checkpoint('real-support-deleted-account-reference.png');
  await audit(page, seed.operatorId);
});

test('real support empty metadata and unavailable case do not fabricate content', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'support-empty', info.project.name);
  const refs = required(seed.support);
  const list = response(page, root);
  await page.goto(`/operator/support?case_id=${refs.missingId}`);
  expect((await actual(await list, isSupportInbox)).cases).toEqual([]);
  await expect(inbox(page)).toContainText('No support cases match these filters.');
  await checkpoint('real-support-empty.png');
  const missing = response(page, `${root}/${refs.missingId}`);
  await page.goto(`/operator/support?case_id=${refs.missingId}&case=${refs.missingId}`);
  expect((await missing).status()).toBe(404);
  await expect(selected(page).getByRole('alert')).toContainText(
    'This support case or history is unavailable',
  );
  await checkpoint('real-support404.png');
  await audit(page, seed.operatorId);
});

test('real support explicit status CAS persists exact receipt and subsequent retained revision', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'support-status', info.project.name);
  const refs = required(seed.support);
  const before = await openCase(page, refs.caseId);
  expect(before.receipt.version).toBe(53);
  await prepare(page);
  await checkpoint('real-support-status-confirmation.png');
  const write = response(page, `${root}/${refs.caseId}/status`, 'PUT');
  await page.getByRole('button', { name: 'Confirm status change', exact: true }).click();
  const result = await actual(await write, isSupportReceipt);
  expect(result.case_id).toBe(refs.caseId);
  expect(result.status).toBe('in_review');
  expect(result.version).toBe(54);
  expect(result.received_at).toBe(before.receipt.received_at);
  await receiptDom(page, result);
  await commandEvidence(page, info, checkpoint, 'real-support-status-committed');
  const read = response(page, `${root}/${refs.caseId}/history`);
  await page.getByRole('button', { name: 'Open retained status history', exact: true }).click();
  const retained = await actual(await read, isSupportHistory);
  expect(retained.revisions[0]).toEqual({
    version: result.version,
    status: result.status,
    changed_at: result.changed_at,
    changed_by_id: seed.operatorId,
    operator_access_version: 1,
  });
  await expect(
    history(page).getByRole('article', { name: 'Status revision 54', exact: true }),
  ).toContainText(result.changed_at);
  await info.attach('real-support-new-revision-runtime-start.png', {
    body: await page.screenshot({ fullPage: false }),
    contentType: 'image/png',
  });
  await checkpoint('real-support-history-choice.png', {
    target: page.getByRole('form', { name: 'Support status choice', exact: true }),
  });
  await audit(page, seed.operatorId);
});

// Immutable captured receipt remains native response data, never substituted into GET/history.
function lostResponse(): Readonly<{
  readonly handle: (route: Readonly<Route>) => Promise<void>;
  readonly receipt: () => Api['schemas']['SupportReceiptResponse'] | null;
  readonly requests: () => readonly Readonly<{
    readonly body: unknown;
    readonly key: string | undefined;
  }>[];
}> {
  let result: Api['schemas']['SupportReceiptResponse'] | null = null;
  let requests: readonly Readonly<{ readonly body: unknown; readonly key: string | undefined }>[] =
    [];
  return {
    receipt: () => result,
    requests: () => requests,
    handle: async (route: Readonly<Route>) => {
      requests = [
        ...requests,
        { body: route.request().postDataJSON(), key: route.request().headers()['idempotency-key'] },
      ];
      const wire = await route.fetch();
      expect(wire.status()).toBe(200);
      const body: unknown = await wire.json();
      if (!isSupportReceipt(body)) throw new Error('Invalid committed real support receipt');
      if (result === null) {
        result = body;
        await route.abort('failed');
        return;
      }
      expect(body).toEqual(result);
      await route.fulfill({ response: wire });
    },
  };
}

test('real support committed but lost response manually replays same intent and current matching status is not proof', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'support-unknown', info.project.name);
  const refs = required(seed.support);
  await openCase(page, refs.caseId);
  const lost = lostResponse();
  await page.route(`**${root}/${refs.caseId}/status`, lost.handle);
  await prepare(page);
  await page.getByRole('button', { name: 'Confirm status change', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('We could not confirm the result');
  const committed = required(lost.receipt());
  expect(committed.version).toBe(54);
  await commandEvidence(page, info, checkpoint, 'real-support-status-lost');
  const read = response(page, `${root}/${refs.caseId}`);
  await page.getByRole('button', { name: 'Check current case', exact: true }).click();
  expect((await actual(await read, isSupportCase)).receipt).toEqual(committed);
  await expect(page.getByRole('alert')).toContainText('We could not confirm the result');
  await expect(
    page.getByRole('heading', { name: 'Recorded result for your request', exact: true }),
  ).toHaveCount(0);
  await commandEvidence(page, info, checkpoint, 'real-support-matching-not-proof');
  await page.getByRole('button', { name: 'Retry the same status change', exact: true }).click();
  await receiptDom(page, committed);
  expect(lost.requests()).toHaveLength(2);
  expect(lost.requests()[1]).toEqual(lost.requests()[0]);
  await commandEvidence(page, info, checkpoint, 'real-support-same-intent-receipt');
  await audit(page, seed.operatorId);
});

test('real support revoked write retires private siblings and explicit same-owner grant recheck restores access', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'support-revocation', info.project.name);
  const refs = required(seed.support);
  await openCase(page, refs.caseId);
  await prepare(page);
  await changeOperatorFixtureGrant(page, seed.operatorId, false);
  const denied = response(page, `${root}/${refs.caseId}/status`, 'PUT');
  await page.getByRole('button', { name: 'Confirm status change', exact: true }).click();
  expect((await denied).status()).toBe(403);
  await expect(
    page.getByRole('heading', { name: 'Operator access denied', exact: true }),
  ).toBeVisible();
  await expect(selected(page)).toHaveCount(0);
  await expect(inbox(page)).toHaveCount(0);
  await checkpoint('real-support-write403.png');
  await changeOperatorFixtureGrant(page, seed.operatorId, true);
  await page.getByRole('button', { name: 'Check access again', exact: true }).click();
  await expect(selected(page)).toContainText('Literal <b>support 0</b>');
  await expect(
    page.getByRole('heading', { name: 'Recorded result for your request', exact: true }),
  ).toHaveCount(0);
  await checkpoint('real-support-grant-restored.png');
  await audit(page, seed.operatorId);
});

test('real support actor replacement resets signed history cursor and retires previous-owner content', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'support-replacement', info.project.name);
  const refs = required(seed.support);
  await openCase(page, refs.caseId);
  await page.getByRole('button', { name: 'Open retained status history', exact: true }).click();
  await expect(history(page).locator('article')).toHaveCount(50);
  await page.getByRole('button', { name: 'Older status revisions', exact: true }).click();
  await expect(history(page).locator('article')).toHaveCount(3);
  await expect(page).toHaveURL(/history_cursor=/);
  await checkpoint('real-support-owner-before.png');
  await changeOperatorFixtureGrant(page, seed.operatorId, false);
  await page.getByRole('button', { name: 'Check current case', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Operator access denied', exact: true }),
  ).toBeVisible();
  await seed.replaceActor();
  const fresh = response(page, `${root}/${refs.caseId}/history`);
  await page.getByRole('button', { name: 'Check access again', exact: true }).click();
  const value = await actual(await fresh, isSupportHistory);
  expect(value.revisions).toHaveLength(50);
  expect(new URL((await fresh).url()).searchParams.get('cursor')).toBeNull();
  await expect(page).not.toHaveURL(/history_cursor=/);
  await expect(history(page).locator('article')).toHaveCount(50);
  await history(page)
    .getByRole('heading', { name: 'Retained status history', exact: true })
    .scrollIntoViewIfNeeded();
  await checkpoint('real-support-owner-after-start.png', { fullPage: false });
  await history(page)
    .getByRole('heading', { name: 'Version 4', exact: true })
    .scrollIntoViewIfNeeded();
  await checkpoint('real-support-owner-after-end.png', { fullPage: false });
  await audit(page, seed.replacementId);
});

test('real support concurrent server change yields409 and explicit reconcile uses fresh CAS version with new intent', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'support-conflict', info.project.name);
  const refs = required(seed.support);
  await openCase(page, refs.caseId);
  await prepare(page);
  const path = `${root}/${refs.caseId}/status`;
  const competing: Api['schemas']['SupportStatusBody'] = {
    status: 'received',
    expected_version: 53,
  };
  await page.route(`**${path}`, async (route: Readonly<Route>) => {
    const wire = await route.fetch({
      headers: { ...route.request().headers(), 'idempotency-key': crypto.randomUUID() },
      postData: JSON.stringify(competing),
    });
    expect(wire.status()).toBe(200);
    const value: unknown = await wire.json();
    if (!isSupportReceipt(value)) throw new Error('Invalid real competing support receipt');
    expect(value.version).toBe(54);
    expect(value.status).toBe('received');
    await route.continue();
  });
  const conflict = response(page, path, 'PUT');
  await page.getByRole('button', { name: 'Confirm status change', exact: true }).click();
  const old = await conflict;
  expect(old.status()).toBe(409);
  await expect(page.getByRole('alert')).toContainText('This request conflicts');
  await commandEvidence(page, info, checkpoint, 'real-support-cas409');
  await page.unroute(`**${path}`);
  await page
    .getByRole('button', { name: 'Use current case for a new change', exact: true })
    .click();
  const dialog = page.getByRole('dialog');
  await expect(
    dialog.getByRole('heading', { name: 'Use the current case for a new change?', exact: true }),
  ).toBeVisible();
  await expect(dialog).toContainText(
    'Your prepared or unsaved status choice will be replaced by the current case. The original result remains part of the server’s recorded history.',
  );
  await expect(dialog.getByRole('button', { name: 'Use current case', exact: true })).toBeVisible();
  await expect(
    dialog.getByRole('button', { name: 'Keep current draft', exact: true }),
  ).toBeVisible();
  await raw(page, info, 'real-support-cas-reconcile-dialog-runtime.png');
  await page.getByRole('button', { name: 'Use current case', exact: true }).click();
  await prepare(page);
  const write = response(page, path, 'PUT');
  await page.getByRole('button', { name: 'Confirm status change', exact: true }).click();
  const fresh = await write;
  expect(fresh.request().postDataJSON()).toEqual({ status: 'in_review', expected_version: 54 });
  expect(fresh.request().headers()['idempotency-key']).not.toBe(
    old.request().headers()['idempotency-key'],
  );
  const receipt = await actual(fresh, isSupportReceipt);
  expect(receipt.version).toBe(55);
  await receiptDom(page, receipt);
  await commandEvidence(page, info, checkpoint, 'real-support-cas-reconciled');
  await audit(page, seed.operatorId);
});
