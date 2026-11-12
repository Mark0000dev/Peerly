import { verifyFixtureStudent } from '../../../../../testing/verified-student';
import type { Page, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../../testing/visual';

test('real verified actor saves a profile draft and reloads the PostgreSQL revision', async ({
  page,
  checkpoint,
}: {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}, info: Readonly<TestInfo>) => {
  await verifyFixtureStudent(page, info.project.name, 'profile');
  await page.getByRole('button', { name: 'Your profile', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Display name' })).toHaveValue('');
  await checkpoint('real-profile-empty.png');
  await page.getByRole('textbox', { name: 'Display name' }).fill('Maya Lee');
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/me/profile') && response.request().method() === 'PUT',
  );
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  const response = await saved;
  expect(response.status()).toBe(200);
  const body: unknown = await response.json();
  expect(body).toMatchObject({ display_name: 'Maya Lee', version: 1, task: 'find_help' });
  await expect(page.getByText('Profile saved.', { exact: true })).toBeVisible();
  await checkpoint('real-profile-saved.png');
  await page.reload();
  await page.getByRole('button', { name: 'Your profile', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Display name' })).toHaveValue('Maya Lee');
  await checkpoint('real-profile-reloaded.png');
});
