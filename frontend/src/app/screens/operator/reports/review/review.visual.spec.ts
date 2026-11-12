import type { Page, Route } from '@playwright/test';
import { test, expect } from '../../../../../../testing/visual';
import { operatorIdentity } from '../../operator.fixtures';
import { reportDetail, reportId, reportPage } from '../../operator-reports.fixtures';
import { anchoredHistory, earlierHistory, emptyHistory, revision } from './review.fixtures';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}>;
function releaseHeld(release: (() => void) | undefined): void {
  if (release === undefined) throw new Error('Missing controlled history release');
  release();
}
const path = `/api/v1/operator/reports/${reportId}/reviews`;
async function setup(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({ json: operatorIdentity }),
  );
  await page.route(/\/api\/v1\/operator\/reports(?:\?.*)?$/, (route: Readonly<Route>) =>
    route.fulfill({ json: reportPage }),
  );
  await page.route(`**/api/v1/operator/reports/${reportId}`, (route: Readonly<Route>) =>
    route.fulfill({ json: reportDetail }),
  );
  await page.route(`**${path}`, (route: Readonly<Route>) => route.fulfill({ json: emptyHistory }));
}
async function open(page: Readonly<Page>): Promise<void> {
  await page.goto(`/operator/reports?report=${reportId}`);
  await page.getByRole('button', { name: 'Human review', exact: true }).click();
  await expect(
    page.getByRole('region', { name: 'Human report review', exact: true }),
  ).toBeVisible();
}
async function draft(page: Readonly<Page>): Promise<void> {
  await page.getByRole('radio', { name: 'Dismiss with a reason', exact: true }).check();
  await page
    .getByRole('textbox', { name: 'Documented private reason', exact: true })
    .fill('Private documented reason.');
  await page.getByRole('button', { name: 'Review decision', exact: true }).click();
}

async function visibleDiscardConfirmation(
  page: Readonly<Page>,
  checkpoint: Scenario['checkpoint'],
): Promise<void> {
  // A fixed modal is the visible viewport, not every off-screen document scroll
  // position at once. Keep the retained closed form's full-page comparison below.
  const dialog = page
    .getByRole('dialog')
    .filter({ has: page.getByRole('heading', { name: 'Discard unsaved changes?', exact: true }) });
  await page.evaluate(() => document.fonts.ready);
  await expect
    .poll(() =>
      dialog.evaluate((element: Readonly<HTMLElement | SVGElement>) =>
        element.contains(element.ownerDocument.activeElement),
      ),
    )
    .toBe(true);
  const before = await dialog.boundingBox();
  const viewport = page.viewportSize();
  if (before === null || viewport === null)
    throw new Error('Missing visible confirmation viewport');
  expect(before.x).toBeGreaterThanOrEqual(0);
  expect(before.y).toBeGreaterThanOrEqual(0);
  expect(before.x + before.width).toBeLessThanOrEqual(viewport.width);
  expect(before.y + before.height).toBeLessThanOrEqual(viewport.height);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await checkpoint('review-dirty-leave.png', { fullPage: false });
  expect(await dialog.boundingBox()).toEqual(before);
  expect(
    await dialog.evaluate((element: Readonly<HTMLElement | SVGElement>) =>
      element.contains(element.ownerDocument.activeElement),
    ),
  ).toBe(true);
}

test('M02 review empty state, validation, explicit confirmation and stored canonical head', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let writes = 0;
  await page.route(`**${path}`, (route: Readonly<Route>) => {
    if (route.request().method() === 'GET')
      return route.fulfill({
        json:
          writes === 0
            ? emptyHistory
            : {
                ...emptyHistory,
                current: { ...revision(1), reason: 'Private documented reason.' },
                anchor_version: 1,
                revisions: [{ ...revision(1), reason: 'Private documented reason.' }],
              },
      });
    writes += 1;
    expect(route.request().postDataJSON()).toEqual({
      action: 'dismiss',
      expected_version: 0,
      reason: 'Private documented reason.',
    });
    return route.fulfill({ json: { ...revision(1), reason: 'Private documented reason.' } });
  });
  await open(page);
  await expect(
    page.getByText('No dismiss or escalate decision is recorded.', { exact: true }),
  ).toBeVisible();
  await checkpoint('review-empty.png');
  await page.getByRole('button', { name: 'Review decision', exact: true }).click();
  await expect(page.getByText('Choose Dismiss or Escalate.', { exact: true })).toBeVisible();
  await checkpoint('review-validation.png');
  await draft(page);
  expect(writes).toBe(0);
  await expect(page.getByText('Expected current version 0.', { exact: true })).toBeVisible();
  await checkpoint('review-before-record.png');
  await page.getByRole('button', { name: 'Record reviewed decision', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Stored review operation' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Current recorded review' })).toContainText(
    'Private documented reason.',
  );
  expect(writes).toBe(1);
  await checkpoint('review-stored.png');
});

test('M02 anchored history keeps newer current and draft while paging actual fifty-row slice', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${path}*`, (route: Readonly<Route>) =>
    route.fulfill({
      json: new URL(route.request().url()).searchParams.has('cursor')
        ? earlierHistory
        : anchoredHistory,
    }),
  );
  await open(page);
  await expect(page.getByRole('region', { name: 'Current recorded review' })).toContainText('52');
  await page
    .getByRole('textbox', { name: 'Documented private reason', exact: true })
    .fill('Unsent reason remains on the same report.');
  await checkpoint('review-anchored-history.png');
  await page.getByRole('button', { name: 'Earlier review revisions', exact: true }).click();
  await expect(page).toHaveURL(/report_review_cursor=anchored-review-page-two/u);
  await expect(
    page.getByRole('button', { name: 'Open stored review version 1', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('textbox', { name: 'Documented private reason', exact: true }),
  ).toHaveValue('Unsent reason remains on the same report.');
  await page.getByRole('button', { name: 'Open stored review version 1', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Retained review history' })).toContainText(
    revision(1).actor_session_id,
  );
  await checkpoint('review-earlier-provenance-draft.png');
});

test('M02 unknown result replays identical body and key without duplicate fresh intent', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let originalBody: string | null = null;
  let originalKey: string | undefined;
  let writes = 0;
  await page.route(`**${path}`, (route: Readonly<Route>) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: emptyHistory });
    writes += 1;
    if (writes === 1) {
      originalBody = route.request().postData();
      originalKey = route.request().headers()['idempotency-key'];
      return route.abort('connectionfailed');
    }
    expect(route.request().postData()).toBe(originalBody);
    expect(route.request().headers()['idempotency-key']).toBe(originalKey);
    return route.fulfill({ json: { ...revision(1), reason: 'Private documented reason.' } });
  });
  await open(page);
  await draft(page);
  await page.getByRole('button', { name: 'Record reviewed decision', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Retry identical decision', exact: true }),
  ).toBeVisible();
  await checkpoint('review-unknown.png');
  await page.getByRole('button', { name: 'Retry identical decision', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Stored review operation' })).toBeVisible();
  expect(writes).toBe(2);
  await checkpoint('review-original-receipt.png');
});

test('M02 CAS conflict requires fresh read and preserves reason', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${path}`, (route: Readonly<Route>) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 409, json: { code: 'report_review_version_conflict' } })
      : route.fulfill({ json: emptyHistory }),
  );
  await open(page);
  await draft(page);
  await page.getByRole('button', { name: 'Record reviewed decision', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Report review recovery' })).toContainText(
    'Read the current state',
  );
  await checkpoint('review-conflict.png');
  await page.getByRole('button', { name: 'Read current review state', exact: true }).click();
  await expect(
    page.getByRole('textbox', { name: 'Documented private reason', exact: true }),
  ).toHaveValue('Private documented reason.');
  await expect(page.getByRole('button', { name: 'Review decision', exact: true })).toBeEnabled();
  await checkpoint('review-conflict-fresh-state.png');
});

test('M02 failed read remains recoverable without write and denied authority retires draft', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${path}`, (route: Readonly<Route>) =>
    route.fulfill({ status: 503, json: { code: 'temporarily_unavailable' } }),
  );
  await open(page);
  await expect(page.getByRole('region', { name: 'Report review recovery' })).toBeVisible();
  await checkpoint('review-read-unavailable.png');
  await page.route(`**${path}`, (route: Readonly<Route>) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 403, json: { code: 'operator_access_required' } })
      : route.fulfill({ json: emptyHistory }),
  );
  await page.getByRole('button', { name: 'Read current review state', exact: true }).click();
  await draft(page);
  await page.getByRole('button', { name: 'Record reviewed decision', exact: true }).click();
  await expect(
    page.getByRole('textbox', { name: 'Documented private reason', exact: true }),
  ).toHaveCount(0);
  await checkpoint('review-authority-retired.png');
});

test('M02 history loading cannot submit, and a dirty leave keeps the same report until explicit discard', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(`**${path}`, async (route: Readonly<Route>) => {
    await held;
    await route.fulfill({ json: emptyHistory });
  });
  await open(page);
  await expect(page.getByText('Checking human review history…', { exact: true })).toBeVisible();
  await checkpoint('review-loading.png');
  releaseHeld(release);
  await expect(
    page.getByText('No dismiss or escalate decision is recorded.', { exact: true }),
  ).toBeVisible();
  await draft(page);
  await page.getByRole('link', { name: reportDetail.report.target_id, exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Discard unsaved changes?', exact: true }),
  ).toBeVisible();
  await visibleDiscardConfirmation(page, checkpoint);
  await page.getByRole('button', { name: 'Keep editing', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`report=${reportId}`));
  await expect(
    page.getByRole('region', { name: 'Review decision before recording' }),
  ).toContainText('Private documented reason.');
  await checkpoint('review-kept-draft.png');
});
