import type { Page } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';

interface Context {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}
for (const [kind, title] of [
  ['terms', 'Terms of Use'],
  ['privacy', 'Privacy Policy'],
] as const) {
  test(`published ${kind} renders safe versioned text without agreement controls`, async ({
    page,
    checkpoint,
  }: Context) => {
    await page.route(`**/api/v1/policies/${kind}?version=test-v1`, async (route) => {
      await route.fulfill({
        json: {
          title,
          content: 'Published fixture text.\n<script>private()</script>',
          reference: {
            id: '00000000-0000-0000-0000-000000000010',
            kind,
            version: 'test-v1',
            published_at: '2026-11-07T12:00:00Z',
          },
        },
      });
    });
    await page.goto(`/${kind}?version=test-v1`);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
    await expect(page.getByText('<script>private()</script>', { exact: false })).toBeVisible();
    await expect(page.getByRole('checkbox')).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Open the app' })).toHaveAttribute(
      'href',
      '/onboarding',
    );
    await checkpoint(`${kind}-published.png`);
  });
}

test('publication failure recovers by explicit retry', async ({ page, checkpoint }: Context) => {
  await page.route('**/api/v1/policies/terms', async (route) => {
    await route.fulfill({ status: 503, json: { code: 'policy_unavailable' } });
  });
  await page.goto('/terms');
  await expect(page.getByRole('alert')).toHaveText('This document is not available right now.');
  await checkpoint('publication-unavailable.png');
  await page.unroute('**/api/v1/policies/terms');
  await page.route('**/api/v1/policies/terms', async (route) => {
    await route.fulfill({
      json: {
        title: 'Terms of Use',
        content: 'Published terms fixture.',
        reference: {
          id: '00000000-0000-0000-0000-000000000010',
          kind: 'terms',
          version: 'test-v1',
          published_at: '2026-11-07T12:00:00Z',
        },
      },
    });
  });
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Terms of Use');
  await checkpoint('publication-recovered.png');
});
