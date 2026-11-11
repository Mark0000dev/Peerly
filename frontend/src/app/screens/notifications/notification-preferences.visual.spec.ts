import type { Locator, Page, Route } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import {
  defaultPreference,
  notificationActorFixture,
  savedPreference,
} from './notification-test-data';

interface Scenario {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
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
  await checkpoint('notifications-default-unchosen.png');
  await page.getByRole('radio', { name: 'All updates', exact: false }).check();
  await page.getByRole('button', { name: 'Save preference', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Your choice was saved');
  await checkpoint('notifications-choice-saved.png');
  await page.getByRole('button', { name: 'Use current saved preference' }).click();
  await expect(page.getByRole('button', { name: 'Save preference', exact: true })).toBeEnabled();
  await expect(page.getByRole('radio', { name: 'All updates', exact: false })).toBeChecked();
  await checkpoint('notifications-current.png');
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
  await expect(page.getByRole('radio', { name: 'All updates', exact: false })).toBeDisabled();
  await checkpoint('notifications-save-unknown.png');
  await page.getByRole('button', { name: 'Retry identical save' }).click();
  await expect(page.getByRole('status')).toContainText('Your choice was saved');
  expect(writes).toBe(2);
  await checkpoint('notifications-replayed.png');
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
  await checkpoint('notifications-conflict.png');
  await page.getByRole('button', { name: 'Use current saved preference' }).click();
  await expect(page.getByRole('button', { name: 'Save preference', exact: true })).toBeEnabled();
  expect(writes).toBe(1);
  await checkpoint('notifications-conflict-current.png');
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
  await checkpoint('notifications-load-error.png');
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
  });
  await page.reload();
  await expect(page.getByRole('button', { name: 'Check sign-in state' })).toBeVisible();
  await checkpoint('notifications-session-required.png');
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
  await page.getByRole('radio', { name: 'Messages and requests', exact: false }).focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('radio', { name: 'All updates', exact: false })).toBeChecked();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await expect(page.getByRole('button', { name: 'Enable notifications' })).toHaveCount(0);
  const save = page.getByRole('button', { name: 'Save preference', exact: true });
  await expect(save).toHaveText('Save preference');
  await expect(save).toHaveAccessibleName('Save preference');
  await assertFullTextFits(save);
  await checkpoint('notifications-narrow-keyboard-200.png');
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
  await checkpoint('notifications-saving.png');
  await page.getByRole('link', { name: 'Back to profile', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Leave before the save is confirmed?' }),
  ).toBeVisible();
  await checkpoint('notifications-unconfirmed-leave.png');
  await page.getByRole('button', { name: 'Keep editing', exact: true }).click();
  await fulfillPending(pending);
  await expect(page.getByRole('status')).toContainText('Your choice was saved');
});

async function fulfillPending(route: Readonly<Route> | undefined): Promise<void> {
  if (route === undefined) throw new Error('Missing held preference request');
  await route.fulfill({ json: savedPreference });
}

async function assertFullTextFits(locator: Readonly<Locator>): Promise<void> {
  const fit = await locator.evaluate((element: Readonly<HTMLElement>) => {
    const box = element.getBoundingClientRect();
    const range = document.createRange();
    range.selectNodeContents(element);
    return {
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
      allTextRectsInside: Array.from(range.getClientRects()).every(
        (rect: Readonly<DOMRect>) =>
          rect.left >= box.left &&
          rect.right <= box.right &&
          rect.top >= box.top &&
          rect.bottom <= box.bottom,
      ),
    };
  });
  expect(fit.scrollWidth).toBeLessThanOrEqual(fit.clientWidth);
  expect(fit.scrollHeight).toBeLessThanOrEqual(fit.clientHeight);
  expect(fit.allTextRectsInside).toBe(true);
}
