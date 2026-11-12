import {
  assertNaturalWordWrapping,
  assertFullTextFits,
  assertTextPaintNotClipped,
} from '../../../../testing/readable-text';
import type { Page, Route } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import {
  defaultPreference,
  notificationActorFixture,
  savedPreference,
} from './notification-test-data';

interface Scenario {
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean; readonly threshold: 0 }>,
  ) => Promise<void>;
}

function validateWrite(route: Readonly<Route>): void {
  expect(route.request().postDataJSON()).toEqual({ mode: 'all_updates', expected_version: 0 });
  expect(route.request().headers()['x-csrf-token']).toBe(notificationActorFixture.csrf_token);
}
async function replayReceipt(
  route: Readonly<Route>,
  body: unknown,
  key: string | undefined,
): Promise<void> {
  expect(route.request().headers()['idempotency-key']).toBe(key);
  expect(route.request().postDataJSON()).toEqual(body);
  await route.fulfill({ json: savedPreference });
}

async function session(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: notificationActorFixture });
  });
}

test('P02 actual default and explicit saved enum, canonical current read', async ({
  page,
  checkpoint,
}: Readonly<Scenario>) => {
  await session(page);
  let saved = false;
  await page.route('**/api/v1/me/notification-preference', async (route) => {
    if (route.request().method() === 'PUT') {
      validateWrite(route);
      saved = true;
      await route.fulfill({ json: savedPreference });
    } else await route.fulfill({ json: saved ? savedPreference : defaultPreference });
  });
  await page.goto('/profile/notifications');
  await expect(
    page.getByRole('radio', { name: 'Messages and requests', exact: false }),
  ).toBeChecked();
  await assertOrdinaryHeaderRow(page);
  const preference = page.getByRole('region', { name: 'Notification preference', exact: true });
  const device = page.getByRole('region', { name: 'On this device', exact: true });
  await expect(preference.getByRole('radio')).toHaveCount(2);
  await expect(preference.getByRole('region', { name: 'On this device', exact: true })).toHaveCount(
    0,
  );
  await expect(device).toContainText('Device delivery is unavailable in this preview.');
  await expect(device).toContainText('Security messages are unchanged.');
  await expect(
    page.getByRole('button', { name: /enable notifications|open device settings/i }),
  ).toHaveCount(0);

  await checkpoint('notifications-default-unchosen.png', { fullPage: true, threshold: 0 });
  await page.getByRole('radio', { name: 'All updates', exact: false }).check();
  expect(saved).toBe(false);
  await page.getByRole('button', { name: 'Save preference', exact: true }).click();
  await expect(
    page.getByRole('status').filter({ hasText: 'Your choice was saved.' }),
  ).toContainText('Your choice was saved');
  await checkpoint('notifications-choice-saved.png', { fullPage: true, threshold: 0 });
  await page.getByRole('button', { name: 'Use saved preference' }).click();
  await expect(page.getByRole('button', { name: 'Save preference', exact: true })).toBeEnabled();
  await expect(page.getByRole('radio', { name: 'All updates', exact: false })).toBeChecked();
  await checkpoint('notifications-current.png', { fullPage: true, threshold: 0 });
});

test('P02 unknown save requires identical replay and never requests OS permission', async ({
  page,
  checkpoint,
}: Readonly<Scenario>) => {
  await session(page);
  let writes = 0;
  let key: string | undefined;
  let body: unknown = null;
  await page.route('**/api/v1/me/notification-preference', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: writes > 1 ? savedPreference : defaultPreference });
      return;
    }
    writes += 1;
    if (writes === 1) {
      key = route.request().headers()['idempotency-key'];
      body = route.request().postDataJSON();
      await route.abort('failed');
    } else {
      await replayReceipt(route, body, key);
    }
  });
  await page.goto('/profile/notifications');
  await page.getByRole('radio', { name: 'All updates', exact: false }).check();
  await page.getByRole('button', { name: 'Save preference', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('save outcome is unknown');
  await expect(
    page.getByText('Your last check found the default: Messages and requests.', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('You haven’t saved an explicit choice yet.', { exact: false }),
  ).toHaveCount(0);
  await expect(page.getByRole('radio', { name: 'All updates', exact: false })).toBeDisabled();
  await page.setViewportSize({ width: 320, height: 800 });
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  for (const label of ['Retry this save', 'Check saved preference']) {
    const action = page.getByRole('button', { name: label, exact: true });
    await assertNaturalWordWrapping(action);
    await assertFullTextFits(action);
  }

  await checkpoint('notifications-save-unknown.png', { fullPage: true, threshold: 0 });
  await page.getByRole('button', { name: 'Retry this save' }).click();
  await expect(
    page.getByRole('status').filter({ hasText: 'Your choice was saved.' }),
  ).toContainText('Your choice was saved');
  expect(writes).toBe(2);
  await checkpoint('notifications-replayed.png', { fullPage: true, threshold: 0 });
});

test('P02 conflict fresh read permits a new explicit choice without automatic PUT', async ({
  page,
  checkpoint,
}: Readonly<Scenario>) => {
  await session(page);
  let writes = 0;
  await page.route('**/api/v1/me/notification-preference', async (route) => {
    if (route.request().method() === 'PUT') {
      writes += 1;
      await route.fulfill({
        status: 409,
        json: { code: 'notification_preference_version_conflict' },
      });
    } else
      await route.fulfill({
        json: writes > 0 ? { ...savedPreference, version: 2 } : defaultPreference,
      });
  });
  await page.goto('/profile/notifications');
  await page.getByRole('radio', { name: 'All updates', exact: false }).check();
  await page.getByRole('button', { name: 'Save preference', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('changed elsewhere');
  await checkpoint('notifications-conflict.png', { fullPage: true, threshold: 0 });
  await page.getByRole('button', { name: 'Use saved preference' }).click();
  await expect(page.getByRole('button', { name: 'Save preference', exact: true })).toBeEnabled();
  expect(writes).toBe(1);
  await checkpoint('notifications-conflict-current.png', { fullPage: true, threshold: 0 });
});

test('P02 session denied and canonical read failure have explicit actual recovery', async ({
  page,
  checkpoint,
}: Readonly<Scenario>) => {
  await session(page);
  await page.route('**/api/v1/me/notification-preference', async (route) => {
    await route.fulfill({ status: 503, json: { code: 'storage_unavailable' } });
  });
  await page.goto('/profile/notifications');
  await expect(page.getByRole('alert')).toContainText('could not be loaded');
  await checkpoint('notifications-load-error.png', { fullPage: true, threshold: 0 });
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
  });
  await page.reload();
  await expect(page.getByRole('button', { name: 'Check sign-in state' })).toBeVisible();
  await checkpoint('notifications-session-required.png', { fullPage: true, threshold: 0 });
});

test('P02 320px 200 percent keyboard selection and no fake device enable control', async ({
  page,
  checkpoint,
}: Readonly<Scenario>) => {
  await session(page);
  await page.route('**/api/v1/me/notification-preference', async (route) => {
    await route.fulfill({ json: defaultPreference });
  });
  await page.setViewportSize({ width: 320, height: 800 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/profile/notifications');
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  const pageHeading = page.getByRole('heading', { name: 'Notifications', level: 1, exact: true });
  await expect(pageHeading).toBeVisible();
  await assertNaturalWordWrapping(pageHeading);
  await assertFullTextFits(pageHeading);
  await page.getByRole('radio', { name: 'Messages and requests', exact: false }).focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('radio', { name: 'All updates', exact: false })).toBeChecked();
  for (const description of [
    'New messages, requests for you and accepted connections',
    'Also new partner suggestions, product news and promotions',
  ]) {
    const caption = page.getByText(description, { exact: true });
    await expect(caption).toBeVisible();
    await assertTextPaintNotClipped(caption);
  }
  await assertNaturalWordWrapping(
    page.getByRole('group', { name: 'What to notify you about', exact: true }),
  );
  await assertNaturalWordWrapping(
    page.getByRole('region', { name: 'On this device', exact: true }),
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await expect(page.getByRole('button', { name: 'Enable notifications' })).toHaveCount(0);
  const save = page.getByRole('button', { name: 'Save preference', exact: true });
  await expect(save).toHaveText('Save preference');
  await expect(save).toHaveAccessibleName('Save preference');
  await assertFullTextFits(save);
  await checkpoint('notifications-narrow-keyboard-200.png', { fullPage: true, threshold: 0 });
});

test('P02 pending save and leave confirmation do not enable another write', async ({
  page,
  checkpoint,
}: Readonly<Scenario>) => {
  await session(page);
  let pending: Readonly<Route> | undefined;
  await page.route('**/api/v1/me/notification-preference', async (route) => {
    if (route.request().method() === 'PUT') {
      pending = route;
      return;
    }
    await route.fulfill({ json: defaultPreference });
  });
  await page.goto('/profile/notifications');
  await page.getByRole('radio', { name: 'All updates', exact: false }).check();
  await page.getByRole('button', { name: 'Save preference', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Saving your preference');
  await checkpoint('notifications-saving.png', { fullPage: true, threshold: 0 });
  await page.getByRole('link', { name: 'Back to profile', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Leave before the save is confirmed?' }),
  ).toBeVisible();
  await checkpoint('notifications-unconfirmed-leave.png', { fullPage: true, threshold: 0 });
  await page.getByRole('button', { name: 'Keep editing', exact: true }).click();
  await fulfillPending(pending);
  await expect(
    page.getByRole('status').filter({ hasText: 'Your choice was saved.' }),
  ).toContainText('Your choice was saved');
});

async function fulfillPending(route: Readonly<Route> | undefined): Promise<void> {
  if (route === undefined) throw new Error('Missing held preference request');
  await route.fulfill({ json: savedPreference });
}

async function assertOrdinaryHeaderRow(page: Readonly<Page>): Promise<void> {
  const headingBox = await page
    .getByRole('heading', { name: 'Notifications', exact: true })
    .boundingBox();
  const backBox = await page
    .getByRole('link', { name: 'Back to profile', exact: true })
    .boundingBox();
  if (headingBox === null || backBox === null) throw new Error('Missing visible settings heading');
  expect(
    Math.min(headingBox.y + headingBox.height, backBox.y + backBox.height) -
      Math.max(headingBox.y, backBox.y),
  ).toBeGreaterThan(0);
}
