import { test, expect } from '../../../../testing/visual';
import type { Page } from '@playwright/test';

interface Context {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}

test('public Help embeds real support and preserves an unsent draft when navigation is kept', async ({ page, checkpoint }: Context) => {
  let writes = 0;
  await page.route('**/api/v1/**', async (route) => {
    if (route.request().method() !== 'GET') writes += 1;
    if (new URL(route.request().url()).pathname === '/api/v1/me') {
      await route.fulfill({ status: 401, json: { code: 'session_required' } });
    } else await route.fallback();
  });
  await page.goto('/help');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Help and contact');
  const message = page.getByRole('textbox', { name: 'What’s happening?', exact: true });
  await expect(message).toBeEditable();
  await message.fill('An unsent support question');
  await expect(page.getByRole('link', { name: 'Microsoft quarantine', exact: true })).toHaveAttribute('href', 'https://security.microsoft.com/quarantine');
  await page.getByRole('banner').getByRole('link', { name: 'Open the app', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('Discard unsaved changes?');
  await checkpoint('public-help-unsent-navigation.png');
  await page.getByRole('button', { name: 'Keep editing', exact: true }).click();
  await expect(page).toHaveURL(/\/help$/);
  await expect(message).toHaveValue('An unsent support question');
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(writes).toBe(0);
  await checkpoint('public-help-draft-kept.png');
});
