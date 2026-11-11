import type { Page } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';

test.use({ javaScriptEnabled: false });

test('built landing remains complete without JavaScript', async ({
  page,
  checkpoint,
}: {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}) => {
  await page.goto('/');
  await expect(page).toHaveTitle('Peerly · Find someone to study with');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Find someone to study with.');
  await expect(
    page.getByRole('heading', { name: 'Three steps, no awkward cold messages' }),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open the app' }).first()).toHaveAttribute(
    'href',
    '/onboarding',
  );
  await expect(page.getByRole('link', { name: 'Privacy Policy' })).toHaveAttribute(
    'href',
    '/privacy',
  );
  await checkpoint('landing-no-js.png');
});
