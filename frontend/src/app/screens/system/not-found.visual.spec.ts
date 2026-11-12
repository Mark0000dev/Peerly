import { test, expect } from '../../../../testing/visual';
import type { Page } from '@playwright/test';

interface Context {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}

test('unknown public link keeps an honest not-found state and recovers to Peerly', async ({
  page,
  checkpoint,
}: Context) => {
  await page.goto('/this-page-does-not-exist');
  await expect(page).toHaveURL(/\/this-page-does-not-exist$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Page not found');
  await expect(page.getByRole('link', { name: 'Back to Peerly', exact: true })).toHaveAttribute(
    'href',
    '/',
  );
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    .toBe(true);
  await checkpoint('public-not-found.png');
  await page.getByRole('link', { name: 'Back to Peerly', exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Find someone to study with.');
  await checkpoint('public-not-found-recovered.png');
});
