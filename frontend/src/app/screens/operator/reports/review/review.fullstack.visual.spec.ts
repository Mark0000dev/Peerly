import type { Locator, Page, Response, Route, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../../../testing/visual';
import {
  prepareOperatorFixture,
  changeOperatorFixtureGrant,
  readOperatorFixtureAudit,
} from '../../../../../../testing/operator-fixture';
import type { Api } from '../../../../api.generated';
import { isReview, isReviewHistory } from './review-contract';

type Review = Api['schemas']['ReportReviewResponse'];
type Body = Api['schemas']['ReviewReportBody'];
type History = Api['schemas']['ReportReviewHistoryResponse'];
type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly target: Readonly<Locator> }>,
  ) => Promise<void>;
}>;
function required<T>(value: T | null | undefined): T {
  if (value === null || value === undefined)
    throw new Error('Missing actual review fixture evidence');
  return value;
}
function response(page: Readonly<Page>, path: string, method = 'GET'): Promise<Response> {
  return page.waitForResponse(
    (value) => new URL(value.url()).pathname === path && value.request().method() === method,
  );
}
async function actual<T>(
  value: Readonly<Response>,
  guard: (body: unknown) => body is T,
): Promise<T> {
  expect(value.status()).toBe(200);
  expect(value.headers()['cache-control']).toBe('no-store');
  const body: unknown = await value.json();
  if (!guard(body)) throw new Error('Invalid actual report review response');
  return body;
}
async function wireReview(value: Readonly<Awaited<ReturnType<Route['fetch']>>>): Promise<Review> {
  expect(value.status()).toBe(200);
  expect(value.headers()['cache-control']).toBe('no-store');
  const body: unknown = await value.json();
  if (!isReview(body)) throw new Error('Invalid actual committed review receipt');
  return body;
}
async function prepare(
  page: Readonly<Page>,
  action: Body['action'],
  reason: string,
): Promise<void> {
  await page
    .getByRole('radio', {
      name: action === 'dismiss' ? 'Dismiss with a reason' : 'Escalate',
      exact: true,
    })
    .check();
  await page.getByRole('textbox', { name: 'Documented private reason', exact: true }).fill(reason);
  await page.getByRole('button', { name: 'Review decision', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Record reviewed decision', exact: true }),
  ).toBeEnabled();
}
async function proof(region: Readonly<Locator>, receipt: Review): Promise<void> {
  await expect(region.locator('app-operator-report-review-proof .reason')).toHaveJSProperty(
    'textContent',
    receipt.reason,
  );
  const fields = [
    ['Review ID', receipt.id],
    ['Report ID', receipt.report_id],
    [
      'Previous version',
      receipt.previous_version === null ? 'No previous decision' : String(receipt.previous_version),
    ],
    ['Operator account ID', receipt.operator_id],
    ['Stored grant version', String(receipt.operator_access_version)],
    ['Stored actor session ID', receipt.actor_session_id],
    ['Reviewed at', receipt.reviewed_at],
    ['Event ID', receipt.event_id],
    ['HTTP request ID', receipt.http_request_id ?? 'Not recorded'],
    ['Action ID', receipt.action_id ?? 'Not recorded'],
    ['Trace ID', receipt.trace_id ?? 'Not recorded'],
    ['Span ID', receipt.span_id ?? 'Not recorded'],
  ] as const;
  for (const [label, value] of fields) {
    await expect(region.getByText(label, { exact: true }).locator('..').locator('dd')).toHaveText(
      value,
    );
  }
  await expect(region.getByRole('heading', { level: 4 })).toHaveText(
    `${receipt.action === 'dismiss' ? 'Dismiss' : 'Escalate'} · version ${String(receipt.version)}`,
  );
  await expect(region.locator('script')).toHaveCount(0);
  await expect(region.locator('time')).toHaveAttribute('datetime', receipt.reviewed_at);
}
async function stored(page: Readonly<Page>, receipt: Review, current: Review): Promise<void> {
  const operation = page.getByRole('region', { name: 'Stored review operation', exact: true });
  await expect(operation).toBeVisible();
  await operation
    .getByRole('button', {
      name: `Original operation receipt · version ${String(receipt.version)}`,
      exact: true,
    })
    .click();
  await proof(operation, receipt);
  const head = page.getByRole('region', { name: 'Current recorded review', exact: true });
  await proof(head, current);
}
async function evidence(
  page: Readonly<Page>,
  info: Readonly<TestInfo>,
  checkpoint: Scenario['checkpoint'],
  name: string,
): Promise<void> {
  await expect(page.getByText('Checking human review history…', { exact: true })).toHaveCount(0);
  await info.attach(`${name}-full-runtime-UNCOMPARED.png`, {
    body: await page.screenshot({ fullPage: true, animations: 'disabled', caret: 'hide' }),
    contentType: 'image/png',
  });
  // Original live UUIDs/timestamps/provenance remain in the complete raw artifact
  // and exact DOM assertions. Compare the COMPLETE native input form, as with the
  // existing operator support command evidence boundary; never mask or replace data.
  await checkpoint(`${name}-native-form-COMPARED.png`, {
    target: page
      .getByRole('region', { name: 'Document a human decision', exact: true })
      .locator('form'),
  });
}
async function nextDecision(page: Readonly<Page>, path: string): Promise<History> {
  const read = response(page, path);
  await page
    .getByRole('button', { name: 'Read current state for another decision', exact: true })
    .click();
  const head = await actual(await read, isReviewHistory);
  await expect(page.getByRole('button', { name: 'Review decision', exact: true })).toBeEnabled();
  return head;
}
async function linkedEvent(page: Readonly<Page>, receipt: Review): Promise<void> {
  const read = await page.request.get(`/api/v1/operator/events/${receipt.event_id}`);
  expect(read.status()).toBe(200);
  expect(read.headers()['cache-control']).toBe('no-store');
  const event: unknown = await read.json();
  expect(event).toMatchObject({
    id: receipt.event_id,
    kind: 'report.reviewed',
    occurred_at: receipt.reviewed_at,
    subject_account_id: receipt.operator_id,
    initiator_account_id: null,
    sources: expect.arrayContaining([
      expect.objectContaining({
        kind: 'report_review_revision',
        id: receipt.id,
        version: receipt.version,
      }),
    ]),
  });
}
function committedLoss() {
  let original: Review | null = null;
  let newer: Review | null = null;
  let requests: readonly Readonly<{ readonly body: unknown; readonly key: string | undefined }>[] =
    [];
  return {
    original: () => required(original),
    newer: () => required(newer),
    requests: () => requests,
    handle: async (route: Readonly<Route>) => {
      if (route.request().method() !== 'POST') {
        await route.continue();
        return;
      }
      expect(route.request().headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/u);
      requests = [
        ...requests,
        { body: route.request().postDataJSON(), key: route.request().headers()['idempotency-key'] },
      ];
      const wire = await route.fetch();
      const receipt = await wireReview(wire);
      if (original === null) {
        original = receipt;
        // Genuine competing application POST advances current after the committed
        // original operation. Nothing is seeded or fabricated at this boundary.
        const competing: Body = {
          action: 'escalate',
          expected_version: receipt.version,
          reason: 'Concurrent retained decision after the original committed operation.',
        };
        newer = await wireReview(
          await route.fetch({
            headers: { ...route.request().headers(), 'idempotency-key': crypto.randomUUID() },
            postData: JSON.stringify(competing),
          }),
        );
        expect(newer.version).toBe(receipt.version + 1);
        await route.abort('failed');
        return;
      }
      expect(receipt).toEqual(original);
      await route.fulfill({ response: wire });
    },
  };
}

// One lead-owned reports-review cohort per project reuses the genuine reports
// seed and stays distinct from the parent reports cohort in the combined matrix.
// The existing fixture rejects namespace reuse; no helper/seed is invented here.
// All bodies/statuses below are genuine application/PostgreSQL results. Only a
// committed response is dropped, or an actual competing POST is issued.
test('real M02 stored human review, canonical audit lineage, CAS recovery, original idempotent replay and grant retirement', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'reports-review', info.project.name);
  const refs = required(seed.reports);
  const path = `/api/v1/operator/reports/${refs.reportId}/reviews`;
  let reviewReads = 0;
  let writes = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname !== path) return;
    if (request.method() === 'POST') writes += 1;
    if (request.method() === 'GET') reviewReads += 1;
  });
  await page.goto(`/operator/reports?context_id=${refs.contextId}&report=${refs.reportId}`);
  await expect(page.getByRole('button', { name: 'Human review', exact: true })).toBeEnabled();
  expect(reviewReads).toBe(0);
  const initialRead = response(page, path);
  await page.getByRole('button', { name: 'Human review', exact: true }).click();
  const initial = await actual(await initialRead, isReviewHistory);
  expect(initial.report_id).toBe(refs.reportId);
  expect(initial.context_id).toBe(refs.contextId);
  expect(initial.target_id).toBe(refs.targetId);
  expect(initial.reporter_id).toBe(refs.reporterId);
  expect(initial.current).toBeNull();
  expect(initial.revisions).toEqual([]);
  const beforeAudit = await readOperatorFixtureAudit(page, seed.operatorId);
  const reason = '  Actual operator reason <b>literal</b>\nOriginal second line  ';
  await prepare(page, 'dismiss', reason);
  expect(writes).toBe(0);
  await evidence(page, info, checkpoint, 'real-review-explicit-prepared');
  const firstWrite = response(page, path, 'POST');
  const firstHead = response(page, path);
  await page.getByRole('button', { name: 'Record reviewed decision', exact: true }).click();
  const write = await firstWrite;
  expect(write.request().postDataJSON()).toEqual({
    action: 'dismiss',
    expected_version: 0,
    reason,
  });
  expect(write.request().headers()['origin']).toBe(new URL(page.url()).origin);
  expect(write.request().headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/u);
  const first = await actual(write, isReview);
  expect(first.report_id).toBe(refs.reportId);
  expect(first.operator_id).toBe(seed.operatorId);
  expect(first.reason).toBe(reason);
  expect(first.version).toBe(1);
  expect(first.previous_version).toBeNull();
  expect((await actual(await firstHead, isReviewHistory)).current).toEqual(first);
  await stored(page, first, first);
  await linkedEvent(page, first);
  await evidence(page, info, checkpoint, 'real-review-stored-exact-proof');

  const beforeConflict = await nextDecision(page, path);
  const conflictReason = '  Original CAS draft\nPreserved after conflict  ';
  await prepare(page, 'escalate', conflictReason);
  let competing: Review | null = null;
  await page.route(
    `**${path}`,
    async (route: Readonly<Route>) => {
      expect(route.request().method()).toBe('POST');
      const body: Body = {
        action: 'dismiss',
        expected_version: required(beforeConflict.current).version,
        reason: 'A genuine concurrent operator decision.',
      };
      competing = await wireReview(
        await route.fetch({
          headers: { ...route.request().headers(), 'idempotency-key': crypto.randomUUID() },
          postData: JSON.stringify(body),
        }),
      );
      await route.continue();
    },
    { times: 1 },
  );
  const conflictResponse = response(page, path, 'POST');
  await page.getByRole('button', { name: 'Record reviewed decision', exact: true }).click();
  const conflict = await conflictResponse;
  expect(conflict.status()).toBe(409);
  expect(await conflict.json()).toMatchObject({ code: 'report_review_version_conflict' });
  await expect(
    page.getByRole('region', { name: 'Report review recovery', exact: true }),
  ).toContainText('Read the current state');
  await evidence(page, info, checkpoint, 'real-review-cas-conflict');
  const refresh = response(page, path);
  await page.getByRole('button', { name: 'Read current review state', exact: true }).click();
  const fresh = await actual(await refresh, isReviewHistory);
  expect(fresh.current).toEqual(required(competing));
  await expect(
    page.getByRole('textbox', { name: 'Documented private reason', exact: true }),
  ).toHaveValue(conflictReason);
  await prepare(page, 'escalate', conflictReason);
  const resolvedWrite = response(page, path, 'POST');
  const resolvedHead = response(page, path);
  await page.getByRole('button', { name: 'Record reviewed decision', exact: true }).click();
  const resolvedResponse = await resolvedWrite;
  expect(resolvedResponse.request().headers()['idempotency-key']).not.toBe(
    conflict.request().headers()['idempotency-key'],
  );
  expect(resolvedResponse.request().postDataJSON()).toEqual({
    action: 'escalate',
    expected_version: required(fresh.current).version,
    reason: conflictReason,
  });
  const resolved = await actual(resolvedResponse, isReview);
  expect(resolved.version).toBe(required(fresh.current).version + 1);
  expect((await actual(await resolvedHead, isReviewHistory)).current).toEqual(resolved);
  await stored(page, resolved, resolved);
  await evidence(page, info, checkpoint, 'real-review-cas-fresh-intent');

  await nextDecision(page, path);
  const lost = committedLoss();
  await page.route(`**${path}`, lost.handle);
  const unknownReason = '  Original unknown-outcome reason\nUnchanged on replay  ';
  await prepare(page, 'dismiss', unknownReason);
  await page.getByRole('button', { name: 'Record reviewed decision', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Retry identical decision', exact: true }),
  ).toBeVisible();
  const committed = lost.original();
  const advanced = lost.newer();
  expect(committed.reason).toBe(unknownReason);
  expect(lost.requests()[0]?.body).toEqual({
    action: 'dismiss',
    expected_version: resolved.version,
    reason: unknownReason,
  });
  expect(committed.version).toBe(resolved.version + 1);
  const unknownRead = response(page, path);
  await page.getByRole('button', { name: 'Read current review state', exact: true }).click();
  expect((await actual(await unknownRead, isReviewHistory)).current).toEqual(advanced);
  await expect(
    page.getByRole('region', { name: 'Stored review operation', exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Retry identical decision', exact: true }),
  ).toBeVisible();
  await evidence(page, info, checkpoint, 'real-review-current-is-not-original-proof');
  const replayHead = response(page, path);
  await page.getByRole('button', { name: 'Retry identical decision', exact: true }).click();
  const canonical = await actual(await replayHead, isReviewHistory);
  expect(lost.requests()).toHaveLength(2);
  expect(lost.requests()[1]).toEqual(lost.requests()[0]);
  expect(canonical.current).toEqual(advanced);
  expect(canonical.revisions.filter((row) => row.id === committed.id)).toHaveLength(1);
  expect(canonical.revisions).toHaveLength(advanced.version);
  await stored(page, committed, advanced);
  await linkedEvent(page, committed);
  await evidence(page, info, checkpoint, 'real-review-replayed-original-newer-canonical');
  await page.unroute(`**${path}`, lost.handle);

  await nextDecision(page, path);
  await prepare(page, 'escalate', 'This forbidden draft must never become a stored decision.');
  await changeOperatorFixtureGrant(page, seed.operatorId, false);
  const deniedWrite = response(page, path, 'POST');
  await page.getByRole('button', { name: 'Record reviewed decision', exact: true }).click();
  expect((await deniedWrite).status()).toBe(403);
  await expect(
    page.getByRole('heading', { name: 'Operator access denied', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toHaveCount(0);
  await expect(
    page.getByRole('textbox', { name: 'Documented private reason', exact: true }),
  ).toHaveCount(0);
  await expect(page.locator('app-operator-report-review textarea')).toHaveCount(0);
  await checkpoint('real-review-write403-retired.png');
  await changeOperatorFixtureGrant(page, seed.operatorId, true);
  const restoredRead = response(page, path);
  await page.getByRole('button', { name: 'Check operator access again', exact: true }).click();
  const restored = await actual(await restoredRead, isReviewHistory);
  expect(restored.current).toEqual(advanced);
  expect(restored.revisions).toHaveLength(advanced.version);
  await expect(
    page.getByRole('textbox', { name: 'Documented private reason', exact: true }),
  ).toHaveValue('');
  await evidence(page, info, checkpoint, 'real-review-restored-no-forbidden-write');
  const counts = await readOperatorFixtureAudit(page, seed.operatorId);
  expect(counts.audits).toBeGreaterThan(beforeAudit.audits);
  expect(counts.linkedEvents).toBe(counts.audits);
});
