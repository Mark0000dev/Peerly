import type { Locator, Page, Response, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import {
  prepareOperatorFixture,
  changeOperatorFixtureGrant,
  readOperatorFixtureAudit,
} from '../../../../testing/operator-fixture';
import { isAudit, isEvent, isEvents, isReport, isReports } from './operator-reports-contract';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly target: Locator }>,
  ) => Promise<void>;
}>;
function required<T>(value: T | null | undefined): T {
  if (value === null || value === undefined)
    throw new Error('Missing actual retained report source');
  return value;
}
function response(page: Readonly<Page>, path: string): Promise<Response> {
  return page.waitForResponse((value) => new URL(value.url()).pathname === path);
}
async function actual<T>(
  value: Readonly<Response>,
  guard: (body: unknown) => body is T,
): Promise<T> {
  expect(value.status()).toBe(200);
  expect(value.headers()['cache-control']).toBe('no-store');
  const body: unknown = await value.json();
  if (!guard(body)) throw new Error('Invalid actual retained report response');
  return body;
}

test('real M02 M06 reports50plus pagination and private legacy/rich facts preserve actual provenance', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'reports', info.project.name);
  const refs = required(seed.reports);
  const firstResponse = response(page, '/api/v1/operator/reports');
  await page.goto(`/operator/reports?reporter_id=${refs.reporterId}`);
  const first = await actual(await firstResponse, isReports);
  expect(first.reports).toHaveLength(50);
  expect(first.reports.every((row) => row.reporter_id === refs.reporterId)).toBe(true);
  expect(first.next_cursor).not.toBeNull();
  expect(first.reports.every((row) => !('comment' in row))).toBe(true);
  await expect(page.getByRole('button', { name: /^Inspect report / })).toHaveCount(50);
  const nextResponse = response(page, '/api/v1/operator/reports');
  await page.getByRole('button', { name: 'Next report page', exact: true }).click();
  const second = await actual(await nextResponse, isReports);
  expect(second.reports).toHaveLength(3);
  expect(new Set([...first.reports, ...second.reports].map((row) => row.id)).size).toBe(53);
  await expect(page.getByRole('button', { name: /^Inspect report / })).toHaveCount(3);
  await checkpoint('real-reports-older3.png');
  const legacyResponse = response(page, `/api/v1/operator/reports/${refs.legacyReportId}`);
  await page
    .getByRole('button', { name: `Inspect report ${refs.legacyReportId}`, exact: true })
    .click();
  const legacy = await actual(await legacyResponse, isReport);
  expect(legacy.comment).toBeNull();
  expect(legacy.submission).toBeNull();
  expect(legacy.context.origin.http_request_id).not.toBeNull();
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toContainText(
    'Submission event and origin were not recorded',
  );
  await checkpoint('real-report-legacy.png');
  const filteredResponse = response(page, '/api/v1/operator/reports');
  await page
    .getByRole('textbox', { name: 'Disclosure context ID', exact: true })
    .fill(refs.contextId);
  await page.getByRole('button', { name: 'Search retained reports', exact: true }).click();
  const filtered = await actual(await filteredResponse, isReports);
  expect(filtered.reports.map((row) => row.id)).toEqual([refs.reportId]);
  await expect(page).not.toHaveURL(/reports_cursor=/);
  const richResponse = response(page, `/api/v1/operator/reports/${refs.reportId}`);
  await page.getByRole('button', { name: `Inspect report ${refs.reportId}`, exact: true }).click();
  const rich = await actual(await richResponse, isReport);
  const comment = required(rich.comment);
  expect(comment).toContain('<script>');
  expect(rich.context.id).toBe(refs.contextId);
  expect(rich.context.target_id).toBe(seed.targets.deleted);
  expect(rich.submission?.event_id).toBe(refs.reportEventId);
  expect(rich.context.origin.http_request_id).not.toBe(rich.submission?.origin.http_request_id);
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toContainText(
    comment,
  );
  await checkpoint('real-report-literal.png');
  const eventResponse = response(page, `/api/v1/operator/events/${refs.reportEventId}`);
  await page.getByRole('button', { name: 'Open submission event', exact: true }).click();
  const event = await actual(await eventResponse, isEvent);
  expect(event.kind).toBe('report.created');
  expect(
    event.sources.some((source) => source.kind === 'profile_report' && source.id === refs.reportId),
  ).toBe(true);
  await expect(page.getByRole('region', { name: 'Canonical event', exact: true })).toContainText(
    refs.reportId,
  );
  await checkpoint('real-report-submission-source.png');
});

test('real M07 canonical pages and actual access source lead to retained audited inspection', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'reports-events', info.project.name);
  const refs = required(seed.reports);
  const firstResponse = response(page, '/api/v1/operator/events');
  await page.goto(
    `/operator/reports?context_id=${refs.contextId}&report=${refs.reportId}&timeline=1&event_subject_account_id=${refs.reporterId}&event_kind=report.created`,
  );
  const first = await actual(await firstResponse, isEvents);
  expect(first.events).toHaveLength(50);
  expect(first.events.every((row) => row.subject_account_id === refs.reporterId)).toBe(true);
  const nextResponse = response(page, '/api/v1/operator/events');
  await page.getByRole('button', { name: 'Next event page', exact: true }).click();
  const next = await actual(await nextResponse, isEvents);
  expect(next.events).toHaveLength(2);
  expect(new Set([...first.events, ...next.events].map((row) => row.id)).size).toBe(52);
  await expect(page.getByRole('button', { name: /^Inspect event / })).toHaveCount(2);
  await checkpoint('real-canonical-older2.png');
  const operatorResponse = response(page, '/api/v1/operator/events');
  const form = page.getByRole('form', { name: 'Event search', exact: true });
  await form
    .getByRole('textbox', { name: 'Subject account ID', exact: true })
    .fill(seed.operatorId);
  await form
    .getByRole('combobox', { name: 'Kind', exact: true })
    .selectOption({ label: 'operator.inspected' });
  await form.getByRole('button', { name: 'Search canonical events', exact: true }).click();
  const operatorEvents = await actual(await operatorResponse, isEvents);
  const linked = required(
    operatorEvents.events.find((event) =>
      event.sources.some((source) => source.kind === 'operator_audit'),
    ),
  );
  const source = required(linked.sources.find((source) => source.kind === 'operator_audit'));
  const eventResponse = response(page, `/api/v1/operator/events/${linked.id}`);
  await page.getByRole('button', { name: `Inspect event ${linked.id}`, exact: true }).click();
  expect((await actual(await eventResponse, isEvent)).sources).toContainEqual(source);
  const auditResponse = response(page, `/api/v1/operator/audits/${source.id}`);
  await page.getByRole('button', { name: `Inspect audit ${source.id}`, exact: true }).click();
  const audit = await actual(await auditResponse, isAudit);
  expect(audit.operator_id).toBe(seed.operatorId);
  expect(audit.id).toBe(source.id);
  const region = page.getByRole('region', { name: 'Access audit', exact: true });
  for (const value of [
    audit.id,
    audit.operator_id,
    audit.action,
    audit.outcome,
    audit.occurred_at,
    audit.operator_access_changed_at,
    String(audit.operator_access_version),
    ...Object.values(audit.origin).filter((value) => value !== null),
  ]) {
    await expect(region).toContainText(value);
  }
  await expect(page.getByRole('region', { name: 'Canonical event', exact: true })).toContainText(
    source.id,
  );
  await info.attach('real-audit-full-page-UNCOMPARED.png', {
    body: await page.screenshot({ fullPage: true, animations: 'disabled', caret: 'hide' }),
    contentType: 'image/png',
  });
  // Live audit UUIDs/origins/times stay visible and exact above. This baseline
  // compares the COMPLETE retained report, while the audit remains open.
  const reportRegion = page.getByRole('region', { name: 'Retained report', exact: true });
  await expect(reportRegion).toContainText(refs.reportId);
  await checkpoint('real-retained-report-during-audit-COMPARED.png', { target: reportRegion });
  const counts = await readOperatorFixtureAudit(page, seed.operatorId);
  expect(counts.audits).toBeGreaterThanOrEqual(6);
  expect(counts.linkedEvents).toBe(counts.audits);
});

test('real M06 empty retained report namespace and unlinked audit URL remain honest', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'reports-empty', info.project.name);
  const firstResponse = response(page, '/api/v1/operator/reports');
  await page.goto(
    `/operator/reports?reporter_id=${seed.targets.active}&audit=${seed.targets.nullable}`,
  );
  expect((await actual(await firstResponse, isReports)).reports).toEqual([]);
  await expect(page.getByRole('region', { name: 'Report results', exact: true })).toContainText(
    'No retained reports',
  );
  await expect(page.getByRole('region', { name: 'Access audit', exact: true })).toContainText(
    'Open an event with this stored operator-audit',
  );
  await checkpoint('real-reports-empty-unlinked.png');
  const missingResponse = response(page, `/api/v1/operator/reports/${seed.targets.nullable}`);
  await page.goto(
    `/operator/reports?reporter_id=${seed.targets.active}&report=${seed.targets.nullable}`,
  );
  expect((await missingResponse).status()).toBe(404);
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toContainText(
    'This retained report is unavailable',
  );
  await checkpoint('real-report404.png');
});

test('real M06 revoked operator grant retires reports and restores only after real recheck', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'reports-revocation', info.project.name);
  const refs = required(seed.reports);
  await page.goto(`/operator/reports?context_id=${refs.contextId}&report=${refs.reportId}`);
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toContainText(
    'Stored comment',
  );
  await changeOperatorFixtureGrant(page, seed.operatorId, false);
  const deniedResponse = response(page, `/api/v1/operator/events/${refs.reportEventId}`);
  await page.getByRole('button', { name: 'Open submission event', exact: true }).click();
  expect((await deniedResponse).status()).toBe(403);
  await expect(
    page.getByRole('heading', { name: 'Operator access denied', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toHaveCount(0);
  await checkpoint('real-reports-grant-revoked.png');
  await changeOperatorFixtureGrant(page, seed.operatorId, true);
  await page.getByRole('button', { name: 'Check operator access again', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Canonical event', exact: true })).toContainText(
    refs.reportEventId,
  );
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toContainText(
    '<script>',
  );
  await checkpoint('real-reports-grant-restored.png');
});

test('real M06 actor replacement resets signed report cursor and cannot reuse first operator grants', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'reports-replacement', info.project.name);
  const refs = required(seed.reports);
  await page.goto(`/operator/reports?reporter_id=${refs.reporterId}`);
  await page.getByRole('button', { name: 'Next report page', exact: true }).click();
  await expect(page).toHaveURL(/reports_cursor=/);
  await expect(page.getByRole('button', { name: /^Inspect report / })).toHaveCount(3);
  await changeOperatorFixtureGrant(page, seed.operatorId, false);
  await page
    .getByRole('button', { name: `Inspect report ${refs.legacyReportId}`, exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Operator access denied', exact: true }),
  ).toBeVisible();
  await checkpoint('real-reports-replacement-before.png');
  await seed.replaceActor();
  const listResponse = response(page, '/api/v1/operator/reports');
  await page.getByRole('button', { name: 'Check operator access again', exact: true }).click();
  const value = await listResponse;
  expect(new URL(value.url()).searchParams.get('cursor')).toBeNull();
  expect((await actual(value, isReports)).reports).toHaveLength(50);
  await expect(page).not.toHaveURL(/reports_cursor=/);
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toContainText(
    'Submission event and origin were not recorded',
  );
  await checkpoint('real-reports-replacement-after.png');
  expect((await readOperatorFixtureAudit(page, seed.replacementId)).audits).toBeGreaterThanOrEqual(
    2,
  );
});

test('real MX retained report initial320 text200 remains readable and keyboard opens stored submission', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'reports-reflow', info.project.name);
  const refs = required(seed.reports);
  await page.setViewportSize({ width: 320, height: 800 });
  await page.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      document.documentElement.style.setProperty('font-size', '200%');
    });
  });
  await page.goto(`/operator/reports?context_id=${refs.contextId}&report=${refs.reportId}`);
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toContainText(
    '<script>',
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 320)).toBe(true);
  await checkpoint('real-reports320-text200.png');
  const open = page.getByRole('button', { name: 'Open submission event', exact: true });
  await open.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('region', { name: 'Canonical event', exact: true })).toContainText(
    refs.reportId,
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 320)).toBe(true);
  await checkpoint('real-reports320-keyboard-event.png');
});
