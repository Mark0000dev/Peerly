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
  const question = page
    .locator('details')
    .filter({ has: page.locator('summary', { hasText: 'Can I delete my account?' }) });
  await expect(question).not.toHaveAttribute('open');
  await question.locator('summary').click();
  await expect(question).toHaveAttribute('open', '');
  await expect(question.getByRole('link', { name: 'Delete your account' })).toHaveAttribute(
    'href',
    '/account/delete',
  );
  await checkpoint('landing-no-js-question-open.png');
});
