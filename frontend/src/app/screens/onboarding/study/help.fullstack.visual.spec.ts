import type { Page, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../../testing/visual';
import { verifyFixtureStudent } from '../../../../../testing/verified-student';

test('real canonical help selection saves notes, reloads and preserves an explicitly empty revision', async ({
  page,
  checkpoint,
}: {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}, info: Readonly<TestInfo>) => {
  await verifyFixtureStudent(page, info.project.name, 'help');
  await page.getByRole('button', { name: 'Your help areas', exact: true }).click();
  await expect(
    page.getByText('0 of 5 areas. Changes apply after you save.', { exact: true }),
  ).toBeVisible();
  await checkpoint('real-help-empty.png');
  await page.getByRole('button', { name: 'Add an area', exact: true }).click();
  await page.getByLabel('Search areas', { exact: true }).fill('Databases');
  await page.getByRole('button', { name: 'SQL Databases', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  await page.getByLabel('Note for SQL · optional', { exact: true }).fill('JOINs');
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/me/help-subjects') && response.request().method() === 'PUT',
  );
  await page.getByRole('button', { name: 'Save help areas', exact: true }).click();
  const response = await saved;
  expect(response.status()).toBe(200);
  const body: unknown = await response.json();
  expect(body).toMatchObject({ version: 1, subjects: [{ label: 'SQL', topic_note: 'JOINs' }] });
  await expect(page.getByText('Help areas saved.', { exact: true })).toBeVisible();
  await checkpoint('real-help-saved.png');
  await page.reload();
  await page.getByRole('button', { name: 'Your help areas', exact: true }).click();
  await expect(page.getByLabel('Note for SQL · optional', { exact: true })).toHaveValue('JOINs');
  await checkpoint('real-help-reloaded.png');
  await page.getByRole('button', { name: 'Remove SQL', exact: true }).click();
  const removed = page.waitForResponse(
    (result) =>
      result.url().endsWith('/api/v1/me/help-subjects') && result.request().method() === 'PUT',
  );
  await page.getByRole('button', { name: 'Save help areas', exact: true }).click();
  const removedResponse = await removed;
  expect(removedResponse.status()).toBe(200);
  const empty: unknown = await removedResponse.json();
  expect(empty).toMatchObject({ version: 2, subjects: [] });
  await expect(page.getByText('Help areas saved.', { exact: true })).toBeVisible();
  await checkpoint('real-help-empty-saved.png');
  await page.reload();
  await page.getByRole('button', { name: 'Your help areas', exact: true }).click();
  await expect(
    page.getByText('0 of 5 areas. Changes apply after you save.', { exact: true }),
  ).toBeVisible();
  await checkpoint('real-help-empty-reloaded.png');
  await page.getByRole('button', { name: 'Back to setup', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Your profile', exact: true })).toBeVisible();
  await checkpoint('real-help-back-to-setup.png');
});
