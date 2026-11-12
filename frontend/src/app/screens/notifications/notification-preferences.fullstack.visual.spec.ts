import type { Api } from '../../api.generated';
import type { Page, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { verifyFixtureStudent } from '../../../../testing/verified-student';
import { isPreference } from './notification-contract';

interface Scenario {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}
function preferenceResponse(value: unknown): Api['schemas']['PreferenceResponse'] {
  if (!isPreference(value)) throw new Error('Invalid actual notification preference');
  return value;
}

function otherMode(mode: Api['schemas']['NotificationMode']): Api['schemas']['NotificationMode'] {
  return mode === 'all_updates' ? 'messages_and_requests' : 'all_updates';
}

test('P02 real verified preactivation student explicit preference CAS survives reload', async ({
  page,
  checkpoint,
}: Readonly<Scenario>, testInfo: Readonly<TestInfo>) => {
  await verifyFixtureStudent(page, testInfo.project.name, 'notification-pref');
  const originalResponse = await page.request.get('/api/v1/me/notification-preference');
  expect(originalResponse.status()).toBe(200);
  const original = preferenceResponse(await originalResponse.json());
  const mode = otherMode(original.mode);
  await page.goto('/profile/notifications');
  await expect(page.getByRole('button', { name: 'Save preference', exact: true })).toBeEnabled();
  await checkpoint('pg-notifications-current.png');
  await page
    .getByRole('radio', {
      name: mode === 'all_updates' ? 'All updates' : 'Messages and requests',
      exact: false,
    })
    .check();
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' &&
      response.url().endsWith('/api/v1/me/notification-preference'),
  );
  await page.getByRole('button', { name: 'Save preference', exact: true }).click();
  const response = await saved;
  expect(response.status()).toBe(200);
  const receipt = preferenceResponse(await response.json());
  expect(receipt.mode).toBe(mode);
  expect(receipt.version).toBe(original.version + 1);
  expect(receipt.changed_at).not.toBeNull();
  await expect(page.getByText('Checking your saved preference…', { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Use saved preference', exact: true }),
  ).toBeEnabled();
  await expect(page.getByRole('status').filter({ hasText: 'Your choice was saved' })).toBeVisible();
  await checkpoint('pg-notifications-saved.png');
  await page.reload();
  await expect(
    page.getByRole('radio', {
      name: mode === 'all_updates' ? 'All updates' : 'Messages and requests',
      exact: false,
    }),
  ).toBeChecked();
  await checkpoint('pg-notifications-reloaded.png');
  const canonicalResponse = await page.request.get('/api/v1/me/notification-preference');
  expect(canonicalResponse.status()).toBe(200);
  expect(await canonicalResponse.json()).toEqual(receipt);
});
