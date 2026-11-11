import type { Page, Route } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { operatorIdentity } from './operator.fixtures';
import {
  auditId,
  eventId,
  eventPage,
  reportDetail,
  reportId,
  reportPage,
  retainedAudit,
  retainedEvent,
  submissionEvent,
  submissionEventId,
} from './operator-reports.fixtures';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}>;
const reports = /\/api\/v1\/operator\/reports(?:\?.*)?$/;
const events = /\/api\/v1\/operator\/events(?:\?.*)?$/;
const reportPath = `/api/v1/operator/reports/${reportId}`;
const eventPath = `/api/v1/operator/events/${eventId}`;
const auditPath = `/api/v1/operator/audits/${auditId}`;
async function setup(page: Readonly<Page>): Promise<void> {
  await page.clock.setFixedTime(new Date('2026-11-08T06:20:00Z'));
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({ json: operatorIdentity }),
  );
  await page.route(reports, (route: Readonly<Route>) => route.fulfill({ json: reportPage }));
  await page.route(events, (route: Readonly<Route>) => route.fulfill({ json: eventPage }));
  await page.route(`**${reportPath}`, (route: Readonly<Route>) =>
    route.fulfill({ json: reportDetail }),
  );
  await page.route(`**${eventPath}`, (route: Readonly<Route>) =>
    route.fulfill({ json: retainedEvent }),
  );
  await page.route(`**/api/v1/operator/events/${submissionEventId}`, (route: Readonly<Route>) =>
    route.fulfill({ json: submissionEvent }),
  );
  await page.route(`**${auditPath}`, (route: Readonly<Route>) =>
    route.fulfill({ json: retainedAudit }),
  );
}
async function open(page: Readonly<Page>, extra = ''): Promise<void> {
  await page.goto(`/operator/reports${extra}`);
  await expect(
    page.getByRole('heading', { name: 'Operator · reports', exact: true }),
  ).toBeVisible();
}
async function event(page: Readonly<Page>): Promise<void> {
  await page.getByRole('button', { name: 'Open canonical timeline', exact: true }).click();
  await page.getByRole('button', { name: `Inspect event ${eventId}`, exact: true }).click();
  await expect(page.getByRole('region', { name: 'Canonical event', exact: true })).toContainText(
    'Stored source references',
  );
}
function release(value: (() => void) | undefined): void {
  if (value === undefined) throw new Error('Missing controlled release');
  value();
}

test('M02 M06 report metadata excludes private comment and explicit record keeps literal provenance', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let reads: readonly string[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/v1/operator/'))
      reads = [...reads, new URL(request.url()).pathname];
  });
  await open(page);
  await expect(page.getByRole('region', { name: 'Report results' })).toContainText(reportId);
  await expect(page.getByText(reportDetail.comment, { exact: true })).toHaveCount(0);
  expect(reads).toEqual(['/api/v1/operator/reports']);
  await checkpoint('reports-metadata.png');
  await page.getByRole('button', { name: `Inspect report ${reportId}`, exact: true }).click();
  const record = page.getByRole('region', { name: 'Retained report', exact: true });
  await expect(record).toContainText(reportDetail.comment);
  await expect(record.locator('script')).toHaveCount(0);
  await expect(record).toContainText('Not recorded');
  await expect(
    record.getByRole('link', { name: reportDetail.report.target_id, exact: true }),
  ).toHaveAttribute('href', `/operator/accounts?account=${reportDetail.report.target_id}`);
  expect(reads).not.toContain(eventPath);
  await checkpoint('report-literal-context.png');
  await record.getByRole('button', { name: 'Open submission event', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Canonical event', exact: true })).toContainText(
    submissionEventId,
  );
  await expect(page.getByRole('region', { name: 'Canonical event', exact: true })).toContainText(
    'report.created',
  );
  await expect(page.getByRole('region', { name: 'Canonical event', exact: true })).toContainText(
    'profile_report',
  );
  await expect(page.getByRole('region', { name: 'Canonical event', exact: true })).toContainText(
    reportId,
  );
  await expect(page).toHaveURL(new RegExp(`event=${submissionEventId}`));
  await checkpoint('report-submission-event.png');
});

test('M02 legacy report has no comment or submission even when disclosure context has origin', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${reportPath}`, (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...reportDetail,
        report: { ...reportDetail.report, has_comment: false },
        comment: null,
        submission: null,
      },
    }),
  );
  await page.route(reports, (route: Readonly<Route>) =>
    route.fulfill({
      json: { ...reportPage, reports: [{ ...reportDetail.report, has_comment: false }] },
    }),
  );
  await open(page, `?report=${reportId}`);
  const record = page.getByRole('region', { name: 'Retained report', exact: true });
  await expect(record).toContainText('No comment recorded');
  await expect(record).toContainText('Submission event and origin were not recorded');
  await expect(record).toContainText(reportDetail.context.origin.trace_id);
  await expect(
    record.getByRole('button', { name: 'Open submission event', exact: true }),
  ).toHaveCount(0);
  await checkpoint('report-legacy-provenance-absent.png');
});

test('M06 independent report and timeline pagination reset only compatible selections', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(reports, (route: Readonly<Route>) =>
    route.fulfill({
      json: new URL(route.request().url()).searchParams.has('cursor')
        ? { ...reportPage, reports: [], next_cursor: null }
        : reportPage,
    }),
  );
  await open(page);
  await page.getByRole('button', { name: 'Next report page', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Report results' })).toContainText(
    'No retained reports',
  );
  await expect(page).toHaveURL(/reports_cursor=report-next/);
  await checkpoint('reports-next-empty.png');
  await page
    .getByRole('form', { name: 'Report search', exact: true })
    .getByRole('textbox', { name: 'Target ID', exact: true })
    .fill(reportDetail.report.target_id);
  await page.getByRole('button', { name: 'Search retained reports', exact: true }).click();
  await expect(page).not.toHaveURL(/reports_cursor=/);
  await expect(
    page.getByRole('button', { name: `Inspect report ${reportId}`, exact: true }),
  ).toBeVisible();
  await event(page);
  await page.getByRole('button', { name: 'Next event page', exact: true }).click();
  await expect(page).toHaveURL(/events_cursor=event-next/);
  await expect(page).toHaveURL(new RegExp(`target_id=${reportDetail.report.target_id}`));
  await expect(page.getByRole('region', { name: 'Canonical event', exact: true })).toHaveCount(0);
  await checkpoint('reports-timeline-independent-page.png');
});

test('M07 audit requires genuine selected event source and shows only retained access metadata', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let audits = 0;
  page.on('request', (value) => {
    if (new URL(value.url()).pathname === auditPath) audits += 1;
  });
  await open(page, `?audit=${auditId}`);
  await expect(page.getByRole('region', { name: 'Access audit', exact: true })).toContainText(
    'Open an event with this stored operator-audit',
  );
  expect(audits).toBe(0);
  await checkpoint('audit-unlinked-url.png');
  await event(page);
  await page.getByRole('button', { name: `Inspect audit ${auditId}`, exact: true }).click();
  const audit = page.getByRole('region', { name: 'Access audit', exact: true });
  await expect(audit).toContainText('Inspection of this audit is itself recorded');
  await expect(audit).toContainText('read_report');
  await expect(audit).not.toContainText(reportDetail.comment);
  expect(audits).toBe(1);
  await checkpoint('audit-stored-source.png');
});

test('M06 local503 and404 recover independently and empty timeline is not proof of absence', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let unavailable = true;
  await page.route(`**${reportPath}`, (route: Readonly<Route>) =>
    route.fulfill(
      unavailable ? { status: 404, json: { code: 'report_not_found' } } : { json: reportDetail },
    ),
  );
  await page.route(events, (route: Readonly<Route>) =>
    route.fulfill(
      unavailable
        ? { status: 503, json: { code: 'temporarily_unavailable' } }
        : { json: { ...eventPage, events: [], next_cursor: null } },
    ),
  );
  await open(page, `?report=${reportId}&timeline=1`);
  await expect(page.getByRole('region', { name: 'Report results' })).toContainText(reportId);
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toContainText(
    'This retained report is unavailable',
  );
  await expect(page.getByRole('region', { name: 'Event results', exact: true })).toContainText(
    'This investigation record could not be loaded',
  );
  await checkpoint('reports-local-unavailable.png');
  unavailable = false;
  await page.getByRole('button', { name: 'Retry report record', exact: true }).click();
  await page.getByRole('button', { name: 'Retry event search', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toContainText(
    reportDetail.comment,
  );
  await expect(page.getByRole('region', { name: 'Event results', exact: true })).toContainText(
    'This does not prove that nothing happened',
  );
  await checkpoint('reports-retry-empty-timeline.png');
});

test('M06 cursor422 and client filter validation preserve genuine bounded search', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(reports, (route: Readonly<Route>) =>
    route.fulfill(
      new URL(route.request().url()).searchParams.has('cursor')
        ? { status: 422, json: { code: 'validation_error' } }
        : { json: reportPage },
    ),
  );
  await open(page, '?reports_cursor=expired');
  await expect(page.getByRole('region', { name: 'Report results' })).toContainText(
    'These filters or this cursor',
  );
  await checkpoint('reports-cursor422.png');
  await page.getByRole('button', { name: 'First page', exact: true }).click();
  await expect(
    page.getByRole('button', { name: `Inspect report ${reportId}`, exact: true }),
  ).toBeVisible();
  await page.getByRole('textbox', { name: 'Target ID', exact: true }).fill('invalid');
  await page.getByRole('button', { name: 'Search retained reports', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('IDs must be UUIDs');
  await expect(page).not.toHaveURL(/target_id=invalid/);
  await checkpoint('reports-filter-invalid.png');
});

test('M06 child403 retires pending siblings and real access recheck alone permits restored reads', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let denied = true;
  let ready: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    ready = resolve;
  });
  await page.route(reports, async (route: Readonly<Route>) => {
    await held;
    await route.fulfill({ json: reportPage });
  });
  await page.route(`**${eventPath}`, (route: Readonly<Route>) =>
    route.fulfill(
      denied ? { status: 403, json: { code: 'operator_access_denied' } } : { json: retainedEvent },
    ),
  );
  await open(page, `?event=${eventId}&report=${reportId}`);
  await expect(
    page.getByRole('heading', { name: 'Operator access denied', exact: true }),
  ).toBeVisible();
  release(ready);
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toHaveCount(0);
  await checkpoint('reports-child403-retired.png');
  denied = false;
  await page.getByRole('button', { name: 'Check operator access again', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toContainText(
    reportDetail.comment,
  );
  await expect(page.getByRole('region', { name: 'Canonical event', exact: true })).toContainText(
    eventId,
  );
  await checkpoint('reports-grant-rechecked.png');
});

test('M06 child401 rechecks actual session and retires all private records', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let expired = false;
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill(
      expired
        ? { status: 401, json: { code: 'authentication_required' } }
        : { json: operatorIdentity },
    ),
  );
  await page.route(`**${reportPath}`, (route: Readonly<Route>) => {
    expired = true;
    return route.fulfill({ status: 401, json: { code: 'authentication_required' } });
  });
  await open(page, `?report=${reportId}`);
  await expect(
    page.getByRole('heading', { name: 'Sign in with your operator Google account', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('region', { name: 'Report results', exact: true })).toHaveCount(0);
  await checkpoint('reports-child401-session-expired.png');
});

test('M06 loading is explicit for each selected private record and completes to real metadata', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let listReady: (() => void) | undefined;
  const listHeld = new Promise<void>((resolve) => {
    listReady = resolve;
  });
  let detailReady: (() => void) | undefined;
  const detailHeld = new Promise<void>((resolve) => {
    detailReady = resolve;
  });
  let eventReady: (() => void) | undefined;
  const eventHeld = new Promise<void>((resolve) => {
    eventReady = resolve;
  });
  let auditReady: (() => void) | undefined;
  const auditHeld = new Promise<void>((resolve) => {
    auditReady = resolve;
  });
  await page.route(reports, async (route: Readonly<Route>) => {
    await listHeld;
    await route.fulfill({ json: reportPage });
  });
  await page.route(`**${reportPath}`, async (route: Readonly<Route>) => {
    await detailHeld;
    await route.fulfill({ json: reportDetail });
  });
  await page.route(`**${eventPath}`, async (route: Readonly<Route>) => {
    await eventHeld;
    await route.fulfill({ json: retainedEvent });
  });
  await page.route(`**${auditPath}`, async (route: Readonly<Route>) => {
    await auditHeld;
    await route.fulfill({ json: retainedAudit });
  });
  await open(page, `?report=${reportId}`);
  await expect(
    page.getByRole('status', { name: '', exact: true }).filter({ hasText: 'Loading reports…' }),
  ).toBeVisible();
  await checkpoint('reports-list-detail-loading.png');
  release(listReady);
  release(detailReady);
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toContainText(
    reportDetail.comment,
  );
  await page.getByRole('button', { name: 'Open canonical timeline', exact: true }).click();
  await page.getByRole('button', { name: `Inspect event ${eventId}`, exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Loading event…');
  await checkpoint('report-event-loading.png');
  release(eventReady);
  await page.getByRole('button', { name: `Inspect audit ${auditId}`, exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Loading audit…');
  await checkpoint('report-audit-loading.png');
  release(auditReady);
  await expect(page.getByRole('region', { name: 'Access audit', exact: true })).toContainText(
    'Stored result references',
  );
  await checkpoint('report-audit-loaded.png');
});

test('MX reports initial320 text200 keeps literal facts and all control captions visible before focus', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.setViewportSize({ width: 320, height: 800 });
  await page.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      document.documentElement.style.setProperty('font-size', '200%');
    });
  });
  await open(page, `?report=${reportId}&event=${eventId}&audit=${auditId}`);
  await expect(page.getByRole('region', { name: 'Access audit', exact: true })).toContainText(
    'Stored result references',
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 320)).toBe(true);
  await expect
    .poll(() =>
      page.getByRole('button').evaluateAll((buttons: readonly Readonly<HTMLElement>[]) =>
        buttons.flatMap((button) => {
          const bounds = button.getBoundingClientRect();
          if (bounds.width === 0) return [];
          const walk = document.createTreeWalker(button, NodeFilter.SHOW_TEXT);
          let text = walk.nextNode();
          while (text !== null) {
            if ((text.textContent ?? '').trim().length > 0) {
              const range = document.createRange();
              range.selectNodeContents(text);
              if (
                Array.from(range.getClientRects()).some(
                  (rect: Readonly<DOMRect>) =>
                    rect.left < Math.max(0, bounds.left) ||
                    rect.right > Math.min(320, bounds.right),
                )
              )
                return [button.textContent];
            }
            text = walk.nextNode();
          }
          return [];
        }),
      ),
    )
    .toEqual([]);
  await checkpoint('reports-initial320-text200.png');
  const target = page.getByRole('textbox', { name: 'Target ID', exact: true });
  await target.focus();
  await expect(target).toBeFocused();
  await target.fill(reportDetail.report.target_id);
  await page.getByRole('button', { name: 'Search retained reports', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(new RegExp(`target_id=${reportDetail.report.target_id}`));
  await checkpoint('reports-keyboard320-text200.png');
});

test('M06 session loading failure and genuine sign-in recovery never start private reads', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let ready: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    ready = resolve;
  });
  let failure = true;
  await page.route('**/api/v1/me', async (route: Readonly<Route>) => {
    await held;
    await route.fulfill({
      status: failure ? 503 : 401,
      json: { code: failure ? 'temporarily_unavailable' : 'authentication_required' },
    });
  });
  let privateReads = 0;
  page.on('request', (value) => {
    if (new URL(value.url()).pathname.startsWith('/api/v1/operator/')) privateReads += 1;
  });
  await open(page);
  await expect(page.getByRole('status')).toHaveText('Checking your Google session…');
  await checkpoint('reports-session-loading.png');
  release(ready);
  await expect(
    page.getByRole('heading', { name: 'Your session could not be checked', exact: true }),
  ).toBeVisible();
  await checkpoint('reports-session-unavailable.png');
  failure = false;
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Sign in with your operator Google account', exact: true }),
  ).toBeVisible();
  expect(privateReads).toBe(0);
  await checkpoint('reports-session-signin.png');
});

test('M06 actor replacement resets both signed cursors before new actor reads', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let replaced = false;
  let revoked = false;
  let freshCursors: readonly (string | null)[] = [];
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({
      json: replaced ? { ...operatorIdentity, account_id: auditId } : operatorIdentity,
    }),
  );
  await page.route(reports, (route: Readonly<Route>) => {
    if (replaced)
      freshCursors = [...freshCursors, new URL(route.request().url()).searchParams.get('cursor')];
    return route.fulfill(
      revoked && !replaced
        ? { status: 403, json: { code: 'operator_access_denied' } }
        : {
            json: replaced ? { ...reportPage, reports: [], next_cursor: null } : reportPage,
          },
    );
  });
  await page.route(events, (route: Readonly<Route>) => {
    if (replaced)
      freshCursors = [...freshCursors, new URL(route.request().url()).searchParams.get('cursor')];
    return route.fulfill({
      json: replaced ? { ...eventPage, events: [], next_cursor: null } : eventPage,
    });
  });
  await open(page, '?reports_cursor=old-reports&timeline=1&events_cursor=old-events');
  await expect(
    page.getByRole('button', { name: `Inspect event ${eventId}`, exact: true }),
  ).toBeVisible();
  await checkpoint('reports-before-actor-change.png');
  revoked = true;
  await page.getByRole('button', { name: 'Refresh report page', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Operator access denied', exact: true }),
  ).toBeVisible();
  replaced = true;
  await page.getByRole('button', { name: 'Check operator access again', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Report results', exact: true })).toContainText(
    'No retained reports',
  );
  await expect(page.getByRole('region', { name: 'Event results', exact: true })).toContainText(
    'No canonical events',
  );
  await expect(page).not.toHaveURL(/cursor=/);
  expect(freshCursors).toEqual([null, null]);
  await expect(
    page.getByRole('button', { name: `Inspect report ${reportId}`, exact: true }),
  ).toHaveCount(0);
  await checkpoint('reports-after-actor-change.png');
});

test('M07 unavailable audit and missing event retry keep successful report readable', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let missing = true;
  await page.route(`**${eventPath}`, (route: Readonly<Route>) =>
    route.fulfill(
      missing ? { status: 404, json: { code: 'event_not_found' } } : { json: retainedEvent },
    ),
  );
  await open(page, `?report=${reportId}&event=${eventId}`);
  await expect(page.getByRole('region', { name: 'Canonical event', exact: true })).toContainText(
    'This stored investigation record is unavailable',
  );
  await expect(page.getByRole('region', { name: 'Retained report', exact: true })).toContainText(
    reportDetail.comment,
  );
  await checkpoint('report-event404.png');
  missing = false;
  await page.getByRole('button', { name: 'Retry event record', exact: true }).click();
  let unavailable = true;
  await page.route(`**${auditPath}`, (route: Readonly<Route>) =>
    route.fulfill(
      unavailable
        ? { status: 503, json: { code: 'temporarily_unavailable' } }
        : { json: retainedAudit },
    ),
  );
  await page.getByRole('button', { name: `Inspect audit ${auditId}`, exact: true }).click();
  await expect(page.getByRole('region', { name: 'Access audit', exact: true })).toContainText(
    'This investigation record could not be loaded',
  );
  await checkpoint('report-audit503.png');
  unavailable = false;
  await page.getByRole('button', { name: 'Retry access audit', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Access audit', exact: true })).toContainText(
    'Stored result references',
  );
  await checkpoint('report-audit-retry.png');
});
