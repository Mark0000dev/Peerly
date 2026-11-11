import type { Api } from '../../api.generated';
import { jpegBase64 } from '../../../../testing/image-fixture';
import { Buffer } from 'node:buffer';
import type { Page, Route } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { actor, person, blocked, receipt } from './person.fixtures';

interface Context {
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}
const path = `/people/${person.id}`;
const api = `**/api/v1/people/${person.id}`;
async function base(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: actor });
  });
  await page.route('**/api/v1/me/blocks*', async (route) => {
    await route.fulfill({ json: { people: [], next_cursor: null } });
  });
  // F03 is an actual independent consumer. Give non-summary scenarios an explicit
  // real-shaped neutral response rather than an accidental dev-server HTML error.
  await page.route('**/api/v1/people/*/feedback-summary', async (route) => {
    await route.fulfill({
      json: {
        state: 'building',
        responses: 0,
        publicly_visible: true,
      } satisfies Api['schemas']['BuildingFeedbackSummaryResponse'],
    });
  });
  await page.route(api, async (route) => {
    await route.fulfill({ json: person });
  });
  const photo = Buffer.from(jpegBase64, 'base64');
  await page.route('**/api/v1/people/*/photo/*', async (route) => {
    await route.fulfill({ contentType: 'image/jpeg', body: photo });
  });
}
async function open(page: Readonly<Page>, requirePhoto = true): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole('heading', { name: person.display_name })).toBeVisible();
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
  if (requirePhoto)
    await expect(page.getByRole('img', { name: `Photo of ${person.display_name}` })).toBeVisible();
}
async function report(page: Readonly<Page>): Promise<void> {
  await page.getByRole('button', { name: 'More options' }).click();
  await page.getByRole('button', { name: 'Report profile', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Submit report' })).toBeVisible();
  const dialog = await page.getByRole('dialog').boundingBox();
  const reasons = await page.getByRole('group', { name: 'Reason', exact: true }).boundingBox();
  if (dialog === null || reasons === null) throw new Error('Missing report geometry');
  expect(reasons.x).toBeGreaterThanOrEqual(dialog.x);
  expect(reasons.x + reasons.width).toBeLessThanOrEqual(dialog.x + dialog.width);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
}
async function block(page: Readonly<Page>): Promise<void> {
  await page.getByRole('button', { name: 'More options' }).click();
  await page.getByRole('button', { name: 'Block person', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Block this person?' })).toBeVisible();
}
async function readableReportTitle(page: Readonly<Page>): Promise<void> {
  const title = await page
    .getByRole('heading', { name: 'Report profile', exact: true })
    .boundingBox();
  const viewport = page.viewportSize();
  if (title === null || viewport === null) throw new Error('Missing readable report title');
  expect(title.width).toBeGreaterThanOrEqual(viewport.width / 2);
}
function safetyRequest(route: Readonly<Route>): void {
  expect(route.request().headers()['x-csrf-token']).toBe(actor.csrf_token);
  expect(route.request().headers()['idempotency-key']).toMatch(/^[a-f0-9-]{36}$/);
}

test('D02 real public projection and labelled safety menu', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  await open(page);
  await expect(page.getByText('JOINs and subqueries', { exact: false })).toBeVisible();
  await expect(page.getByText('Integration by parts', { exact: false })).toBeVisible();
  await expect(page.getByText('Provided by this student.')).toBeVisible();
  await expect(page.getByRole('button', { name: /request|chat/i })).toHaveCount(0);
  await checkpoint('person-full-profile.png');
  await page.getByRole('button', { name: 'More options' }).click();
  await expect(page.getByRole('navigation', { name: 'Profile safety' })).toBeVisible();
  await checkpoint('person-safety-menu.png');
});

test('D02 loading resolves to a profile', async ({ page, checkpoint }: Context) => {
  await base(page);
  let release: () => void = () => {
    throw new Error('No pending read');
  };
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  // F03 is an actual independent consumer. Give non-summary scenarios an explicit
  // real-shaped neutral response rather than an accidental dev-server HTML error.
  await page.route('**/api/v1/people/*/feedback-summary', async (route) => {
    await route.fulfill({
      json: {
        state: 'building',
        responses: 0,
        publicly_visible: true,
      } satisfies Api['schemas']['BuildingFeedbackSummaryResponse'],
    });
  });
  await page.route(api, async (route) => {
    await pending;
    await route.fulfill({ json: person });
  });
  await page.goto(path);
  await expect(page.getByRole('status')).toContainText('Loading profile');
  await checkpoint('person-loading.png');
  release();
  await expect(page.getByRole('heading', { name: person.display_name })).toBeVisible();
  await checkpoint('person-loaded.png');
});

test('D02 unavailable remains neutral and has no invented report context', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  // F03 is an actual independent consumer. Give non-summary scenarios an explicit
  // real-shaped neutral response rather than an accidental dev-server HTML error.
  await page.route('**/api/v1/people/*/feedback-summary', async (route) => {
    await route.fulfill({
      json: {
        state: 'building',
        responses: 0,
        publicly_visible: true,
      } satisfies Api['schemas']['BuildingFeedbackSummaryResponse'],
    });
  });
  await page.route(api, async (route) => {
    await route.fulfill({ status: 404, json: { code: 'person_unavailable' } });
  });
  await page.goto(path);
  await expect(page.getByRole('alert')).toContainText('This profile is unavailable');
  await expect(page.getByRole('button', { name: 'More options' })).toHaveCount(0);
  await checkpoint('person-unavailable.png');
});

test('D02 read failure has safe recovery and supports sparse profiles', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  // F03 is an actual independent consumer. Give non-summary scenarios an explicit
  // real-shaped neutral response rather than an accidental dev-server HTML error.
  await page.route('**/api/v1/people/*/feedback-summary', async (route) => {
    await route.fulfill({
      json: {
        state: 'building',
        responses: 0,
        publicly_visible: true,
      } satisfies Api['schemas']['BuildingFeedbackSummaryResponse'],
    });
  });
  await page.route(api, async (route) => {
    await route.fulfill({
      status: 503,
      json: { code: 'unavailable', message: 'PRIVATE STORAGE DETAIL' },
    });
  });
  await page.goto(path);
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByText('PRIVATE STORAGE DETAIL')).toHaveCount(0);
  await checkpoint('person-read-failure.png');
  // F03 is an actual independent consumer. Give non-summary scenarios an explicit
  // real-shaped neutral response rather than an accidental dev-server HTML error.
  await page.route('**/api/v1/people/*/feedback-summary', async (route) => {
    await route.fulfill({
      json: {
        state: 'building',
        responses: 0,
        publicly_visible: true,
      } satisfies Api['schemas']['BuildingFeedbackSummaryResponse'],
    });
  });
  await page.route(api, async (route) => {
    await route.fulfill({
      json: {
        ...person,
        about: null,
        programme: null,
        year_label: null,
        languages: [],
        goal: null,
        help_subjects: null,
      },
    });
  });
  await page.getByRole('button', { name: 'Refresh current status' }).click();
  await expect(page.getByRole('heading', { name: person.display_name })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'About', exact: true })).toHaveCount(0);
  await checkpoint('person-sparse-profile.png');
});

test('D02 session failure and nonstudent access never read private profile', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  let reads = 0;
  // F03 is an actual independent consumer. Give non-summary scenarios an explicit
  // real-shaped neutral response rather than an accidental dev-server HTML error.
  await page.route('**/api/v1/people/*/feedback-summary', async (route) => {
    await route.fulfill({
      json: {
        state: 'building',
        responses: 0,
        publicly_visible: true,
      } satisfies Api['schemas']['BuildingFeedbackSummaryResponse'],
    });
  });
  await page.route(api, async (route) => {
    reads += 1;
    await route.fulfill({ json: person });
  });
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ status: 503, json: { code: 'unavailable' } });
  });
  await page.goto(path);
  await expect(page.getByRole('alert')).toContainText('couldn’t check your session');
  await checkpoint('person-session-failure.png');
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({
      json: { ...actor, capabilities: { ...actor.capabilities, can_use_student_features: false } },
    });
  });
  await page.getByRole('button', { name: 'Check session' }).click();
  await expect(page.getByRole('link', { name: 'Continue', exact: true })).toBeVisible();
  expect(reads).toBe(0);
  await checkpoint('person-verification-required.png');
});

test('S01 report validation uses Unicode codepoints and stores a receipt', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  await open(page);
  await report(page);
  await checkpoint('person-report-reasons.png', { fullPage: false });
  await page.getByRole('radio', { name: 'Other', exact: true }).check();
  await page.getByRole('button', { name: 'Submit report' }).click();
  await expect(page.getByRole('alert')).toContainText('Explain the reason');
  await checkpoint('person-report-other-required.png', { fullPage: false });
  await page.getByLabel('Comment (up to 1000 characters)').fill('😀'.repeat(1001));
  await page.getByRole('button', { name: 'Submit report' }).click();
  await expect(page.getByRole('alert')).toContainText('Use no more than 1000');
  await checkpoint('person-report-length-validation.png', { fullPage: false });
  await page.getByLabel('Comment (up to 1000 characters)').fill('Private explanation');
  await page.route('**/api/v1/reports', async (route) => {
    safetyRequest(route);
    expect(route.request().postDataJSON()).toEqual({
      kind: 'profile',
      context_id: person.access_context_id,
      category: 'other',
      comment: 'Private explanation',
    });
    await route.fulfill({ status: 201, json: receipt });
  });
  await page.getByRole('button', { name: 'Submit report' }).click();
  await expect(page.getByRole('status')).toContainText('Report stored');
  await checkpoint('person-report-stored-receipt.png', { fullPage: false });
});

test('S01 report unknown outcome replays exactly and never claims review', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  await open(page);
  await report(page);
  let key: string | undefined;
  let body: string | null = null;
  let attempts = 0;
  let replayKey: string | undefined;
  let replayBody: string | null = null;
  await page.route('**/api/v1/reports', async (route) => {
    safetyRequest(route);
    attempts += 1;
    if (attempts === 1) {
      key = route.request().headers()['idempotency-key'];
      body = route.request().postData();
      await route.fulfill({ status: 503, json: { code: 'unavailable' } });
    } else {
      replayKey = route.request().headers()['idempotency-key'];
      replayBody = route.request().postData();
      await route.fulfill({ status: 201, json: receipt });
    }
  });
  await page.getByLabel('Comment (up to 1000 characters)').fill('Original private explanation');
  await page.getByRole('button', { name: 'Submit report' }).click();
  await expect(page.getByRole('button', { name: 'Retry same report' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Submit report' })).toBeDisabled();
  await checkpoint('person-report-unknown.png', { fullPage: false });
  await page.getByRole('button', { name: 'Retry same report' }).click();
  await expect(page.getByRole('status')).toContainText('Report stored');
  expect(replayKey).toBe(key);
  expect(replayBody).toBe(body);
  await checkpoint('person-report-replayed.png', { fullPage: false });
});

test('S01 quota exposes only safe retry metadata', async ({ page, checkpoint }: Context) => {
  await base(page);
  await open(page);
  await report(page);
  await page.route('**/api/v1/reports', async (route) => {
    await route.fulfill({
      status: 429,
      json: { code: 'report_rate_limited', recovery: { retry_at: '2026-11-08T00:00:00Z' } },
    });
  });
  await page.getByRole('button', { name: 'Submit report' }).click();
  await page
    .getByRole('region', { name: 'Report profile', exact: true })
    .getByRole('button', { name: 'Close', exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText('Too many attempts');
  await expect(page.getByRole('alert')).toContainText('Try again after');
  await checkpoint('person-report-rate-limit.png');
});

test('S01 block confirmation rechecks canonical state then permits own unblock', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  await open(page);
  await block(page);
  await checkpoint('person-block-confirmation.png', { fullPage: false });
  let active = false;
  await page.route('**/api/v1/me/blocks*', async (route) => {
    await route.fulfill({
      json: {
        people: active
          ? [{ block: blocked, deleted: false, display_name: person.display_name }]
          : [],
        next_cursor: null,
      },
    });
  });
  // F03 is an actual independent consumer. Give non-summary scenarios an explicit
  // real-shaped neutral response rather than an accidental dev-server HTML error.
  await page.route('**/api/v1/people/*/feedback-summary', async (route) => {
    await route.fulfill({
      json: {
        state: 'building',
        responses: 0,
        publicly_visible: true,
      } satisfies Api['schemas']['BuildingFeedbackSummaryResponse'],
    });
  });
  await page.route(api, async (route) => {
    await route.fulfill(
      active
        ? { status: 404, json: { code: 'person_unavailable' } }
        : { json: { ...person, own_block: { ...blocked, blocked: false, version: 2 } } },
    );
  });
  await page.route(`**/api/v1/me/blocks/${person.id}`, async (route) => {
    safetyRequest(route);
    expect(route.request().method()).toBe('PUT');
    expect(route.request().postDataJSON()).toEqual({
      blocked: !active,
      expected_version: active ? 1 : 0,
      context_id: person.access_context_id,
    });
    active = !active;
    await route.fulfill({ json: active ? blocked : { ...blocked, blocked: false, version: 2 } });
  });
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('This profile is unavailable');
  await checkpoint('person-own-block-canonical.png');
  await report(page);
  await page.route('**/api/v1/reports', async (route) => {
    expect(route.request().postDataJSON()).toMatchObject({
      kind: 'profile',
      context_id: person.access_context_id,
    });
    await route.fulfill({ status: 201, json: receipt });
  });
  await page.getByRole('button', { name: 'Submit report' }).click();
  await expect(page.getByRole('status')).toContainText('Report stored');
  await checkpoint('person-unavailable-owned-report.png', { fullPage: false });
  await page
    .getByRole('region', { name: 'Report profile', exact: true })
    .getByRole('button', { name: 'Close', exact: true })
    .click();
  await page.getByRole('button', { name: 'Unblock person', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Unblock this person?' })).toBeVisible();
  await checkpoint('person-unblock-confirmation.png', { fullPage: false });
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByRole('heading', { name: person.display_name })).toBeVisible();
  await checkpoint('person-unblocked-canonical.png');
});

test('S01 block conflict requires refresh and does not silently replay a new intent', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  await open(page);
  await block(page);
  let writes = 0;
  await page.route(`**/api/v1/me/blocks/${person.id}`, async (route) => {
    writes += 1;
    await route.fulfill({ status: 409, json: { code: 'block_version_conflict' } });
  });
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await page
    .getByRole('region', { name: 'Confirm block change', exact: true })
    .getByRole('button', { name: 'Close', exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText('The state changed');
  expect(writes).toBe(1);
  await checkpoint('person-block-conflict.png');
  await page.getByRole('button', { name: 'Refresh current status' }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await checkpoint('person-block-conflict-refreshed.png');
});

test('D02 320px reflow and 200 percent text with keyboard dialog dismissal', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  await page.setViewportSize({ width: 320, height: 800 });
  await open(page);
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await checkpoint('person-narrow-large-text.png');
  await report(page);
  await expect(page.getByRole('dialog')).toBeVisible();
  await readableReportTitle(page);
  await checkpoint('person-narrow-large-text-report.png', { fullPage: false });
  const submit = page.getByRole('button', { name: 'Submit report', exact: true });
  await submit.scrollIntoViewIfNeeded();
  await expect(submit).toBeInViewport();
  await checkpoint('person-narrow-large-text-actions.png', { fullPage: false });
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Report profile', exact: true })).toBeFocused();
  await checkpoint('person-dialog-keyboard-return.png');
});

test('D02 photo failure retries only the current authorized JPEG', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  await page.route('**/api/v1/people/*/photo/*', async (route) => {
    await route.fulfill({ status: 503, json: { code: 'storage_unavailable' } });
  });
  await open(page, false);
  await expect(
    page.getByText('Photo didn’t load. The profile may still be available.'),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: person.display_name })).toBeVisible();
  await checkpoint('person-photo-failure.png');
  const photo = Buffer.from(jpegBase64, 'base64');
  await page.route('**/api/v1/people/*/photo/*', async (route) => {
    expect(route.request().url()).toContain(`/people/${person.id}/photo/1`);
    await route.fulfill({ contentType: 'image/jpeg', body: photo });
  });
  await page.getByRole('button', { name: 'Retry photo' }).click();
  await expect(page.getByRole('img', { name: `Photo of ${person.display_name}` })).toBeVisible();
  await checkpoint('person-photo-retried.png');
});

test('S01 report session expiry removes private profile and draft', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  await open(page);
  await report(page);
  await page.getByLabel('Comment (up to 1000 characters)').fill('Private draft for original actor');
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
  });
  await page.route('**/api/v1/reports', async (route) => {
    await route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
  });
  await page.getByRole('button', { name: 'Submit report' }).click();
  await expect(page.getByRole('link', { name: 'Continue', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: person.display_name })).toHaveCount(0);
  await expect(page.getByLabel('Comment (up to 1000 characters)')).toHaveCount(0);
  await checkpoint('person-expired-session.png');
});

test('S01 paginated own blocks resolve the target beyond the first page', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  await page.route('**/api/v1/me/blocks*', async (route) => {
    await route.fulfill({
      json: route.request().url().includes('?cursor=')
        ? {
            people: [{ block: blocked, deleted: false, display_name: person.display_name }],
            next_cursor: null,
          }
        : { people: [], next_cursor: 'opaque cursor' },
    });
  });
  await open(page);
  await expect(page.getByRole('button', { name: 'Check next blocked people' })).toBeVisible();
  await checkpoint('person-blocks-first-page.png');
  await page.getByRole('button', { name: 'Check next blocked people' }).click();
  await page.getByRole('button', { name: 'More options' }).click();
  await expect(page.getByRole('button', { name: 'Unblock person', exact: true })).toBeVisible();
  await checkpoint('person-blocks-target-page.png');
});

test('S01 block unknown outcome repeats the exact original intent', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  await open(page);
  await block(page);
  let firstKey: string | undefined;
  let secondKey: string | undefined;
  let firstBody: string | null = null;
  let secondBody: string | null = null;
  let attempts = 0;
  await page.route(`**/api/v1/me/blocks/${person.id}`, async (route) => {
    attempts += 1;
    if (attempts === 1) {
      firstKey = route.request().headers()['idempotency-key'];
      firstBody = route.request().postData();
    } else {
      secondKey = route.request().headers()['idempotency-key'];
      secondBody = route.request().postData();
    }
    await route.fulfill({ status: 503, json: { code: 'unavailable' } });
  });
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry same block action' })).toBeVisible();
  await checkpoint('person-block-unknown.png', { fullPage: false });
  await page.getByRole('button', { name: 'Retry same block action' }).click();
  await expect.poll(() => attempts).toBe(2);
  expect(secondKey).toBe(firstKey);
  expect(secondBody).toBe(firstBody);
  await expect(page.getByRole('button', { name: 'Retry same block action' })).toBeVisible();
  await checkpoint('person-block-unknown-retried.png', { fullPage: false });
});

test('S01 deliberate writes show pending status and prevent duplicate clicks', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  await open(page);
  await report(page);
  let releaseReport: () => void = () => {
    throw new Error('Report not pending');
  };
  const reportPending = new Promise<void>((resolve) => {
    releaseReport = resolve;
  });
  let reports = 0;
  await page.route('**/api/v1/reports', async (route) => {
    reports += 1;
    await reportPending;
    await route.fulfill({ status: 201, json: receipt });
  });
  await page.getByRole('button', { name: 'Submit report' }).click();
  await expect(page.getByRole('status')).toContainText('Submitting report');
  await expect(page.getByRole('button', { name: 'Submit report' })).toBeDisabled();
  expect(reports).toBe(1);
  await checkpoint('person-report-pending.png', { fullPage: false });
  releaseReport();
  await expect(page.getByRole('status')).toContainText('Report stored');
  await page
    .getByRole('region', { name: 'Report profile', exact: true })
    .getByRole('button', { name: 'Close', exact: true })
    .click();
  await page.getByRole('button', { name: 'Block person', exact: true }).click();
  let releaseBlock: () => void = () => {
    throw new Error('Block not pending');
  };
  const blockPending = new Promise<void>((resolve) => {
    releaseBlock = resolve;
  });
  let blocks = 0;
  await page.route(`**/api/v1/me/blocks/${person.id}`, async (route) => {
    blocks += 1;
    await blockPending;
    await route.fulfill({ status: 409, json: { code: 'block_version_conflict' } });
  });
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Saving block change');
  await expect(page.getByRole('button', { name: 'Confirm', exact: true })).toBeDisabled();
  expect(blocks).toBe(1);
  await checkpoint('person-block-pending.png', { fullPage: false });
  releaseBlock();
  await page
    .getByRole('region', { name: 'Confirm block change', exact: true })
    .getByRole('button', { name: 'Close', exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText('The state changed');
  await checkpoint('person-pending-resolved.png');
});

test('S01 reload finds an own block on later pages and exposes only its own unblock', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  // F03 is an actual independent consumer. Give non-summary scenarios an explicit
  // real-shaped neutral response rather than an accidental dev-server HTML error.
  await page.route('**/api/v1/people/*/feedback-summary', async (route) => {
    await route.fulfill({
      json: {
        state: 'building',
        responses: 0,
        publicly_visible: true,
      } satisfies Api['schemas']['BuildingFeedbackSummaryResponse'],
    });
  });
  await page.route(api, async (route) => {
    await route.fulfill({ status: 404, json: { code: 'person_unavailable' } });
  });
  await page.route('**/api/v1/me/blocks*', async (route) => {
    await route.fulfill({
      json: route.request().url().includes('?cursor=')
        ? { people: [{ block: blocked, deleted: true, display_name: null }], next_cursor: null }
        : { people: [], next_cursor: 'next' },
    });
  });
  await page.goto(path);
  await expect(page.getByRole('alert')).toContainText('This profile is unavailable');
  await expect(page.getByRole('button', { name: 'More options' })).toHaveCount(0);
  await checkpoint('person-reloaded-block-first-page.png');
  await page.getByRole('button', { name: 'Check next blocked people' }).click();
  await page.getByRole('button', { name: 'More options' }).click();
  await expect(page.getByRole('button', { name: 'Report profile', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Unblock person', exact: true })).toBeVisible();
  await checkpoint('person-reloaded-own-block.png');
  await page.getByRole('button', { name: 'Unblock person', exact: true }).click();
  await page.route(`**/api/v1/me/blocks/${person.id}`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({ blocked: false, expected_version: 1 });
    await route.fulfill({ json: { ...blocked, blocked: false, version: 2 } });
  });
  await page.route('**/api/v1/me/blocks*', async (route) => {
    await route.fulfill({ json: { people: [], next_cursor: null } });
  });
  // F03 is an actual independent consumer. Give non-summary scenarios an explicit
  // real-shaped neutral response rather than an accidental dev-server HTML error.
  await page.route('**/api/v1/people/*/feedback-summary', async (route) => {
    await route.fulfill({
      json: {
        state: 'building',
        responses: 0,
        publicly_visible: true,
      } satisfies Api['schemas']['BuildingFeedbackSummaryResponse'],
    });
  });
  await page.route(api, async (route) => {
    await route.fulfill({
      json: { ...person, own_block: { ...blocked, blocked: false, version: 2 } },
    });
  });
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByRole('heading', { name: person.display_name })).toBeVisible();
  await checkpoint('person-reloaded-unblocked.png');
});

test('S01 malformed successful report response stays uncertain and preserves the immutable intent', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  await open(page);
  await report(page);
  let firstKey: string | undefined;
  let replayKey: string | undefined;
  let firstBody: string | null = null;
  let replayBody: string | null = null;
  let attempts = 0;
  await page.route('**/api/v1/reports', async (route) => {
    attempts += 1;
    if (attempts === 1) {
      firstKey = route.request().headers()['idempotency-key'];
      firstBody = route.request().postData();
      await route.fulfill({ status: 201, contentType: 'application/json', body: '{' });
    } else {
      replayKey = route.request().headers()['idempotency-key'];
      replayBody = route.request().postData();
      await route.fulfill({ status: 201, json: receipt });
    }
  });
  await page
    .getByLabel('Comment (up to 1000 characters)')
    .fill('Original intent after malformed receipt.');
  await page.getByRole('button', { name: 'Submit report', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('couldn’t confirm the result');
  await expect(page.getByRole('button', { name: 'Retry same report', exact: true })).toBeVisible();
  await expect(page.getByText('Report stored.', { exact: false })).toHaveCount(0);
  await checkpoint('person-report-malformed-reply.png', { fullPage: false });
  await page.getByRole('button', { name: 'Retry same report', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Report stored');
  expect(replayKey).toBe(firstKey);
  expect(replayBody).toBe(firstBody);
  await checkpoint('person-report-malformed-reply-replayed.png', { fullPage: false });
});

test('D02 a stale JPEG version refreshes the canonical person before retrying the new current photo', async ({
  page,
  checkpoint,
}: Context) => {
  await base(page);
  await page.route('**/api/v1/people/*/photo/1', async (route) => {
    await route.fulfill({ status: 404, json: { code: 'person_unavailable' } });
  });
  await open(page, false);
  await expect(
    page.getByText('Photo didn’t load. The profile may still be available.'),
  ).toBeVisible();
  await checkpoint('person-photo-version-stale.png');
  // F03 is an actual independent consumer. Give non-summary scenarios an explicit
  // real-shaped neutral response rather than an accidental dev-server HTML error.
  await page.route('**/api/v1/people/*/feedback-summary', async (route) => {
    await route.fulfill({
      json: {
        state: 'building',
        responses: 0,
        publicly_visible: true,
      } satisfies Api['schemas']['BuildingFeedbackSummaryResponse'],
    });
  });
  await page.route(api, async (route) => {
    await route.fulfill({
      json: {
        ...person,
        photo: {
          version: 2,
          display_url: person.photo.display_url.replace('/photo/1', '/photo/2'),
        },
      },
    });
  });
  const canonical = page.waitForResponse((response) =>
    response.url().endsWith(`/api/v1/people/${person.id}`),
  );
  const current = page.waitForRequest((request) =>
    request.url().endsWith(`/api/v1/people/${person.id}/photo/2`),
  );
  await page.getByRole('button', { name: 'Retry photo', exact: true }).click();
  expect((await canonical).status()).toBe(200);
  await current;
  await expect(page.getByRole('img', { name: `Photo of ${person.display_name}` })).toBeVisible();
  await checkpoint('person-photo-version-current.png');
});
