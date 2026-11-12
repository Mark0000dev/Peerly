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
    await expect(
      page.getByRole('banner').getByRole('link', { name: 'Open the app' }),
    ).toHaveAttribute('href', '/onboarding');
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

for (const [kind, title] of [
  ['terms', 'Terms of Use'],
  ['privacy', 'Privacy Policy'],
] as const) {
  test(`${kind} published history paginates metadata and opens the selected version`, async ({
    page,
    checkpoint,
  }: Context) => {
    await page.route(`**/api/v1/policies/${kind}/versions?*`, async (route) => {
      const older = new URL(route.request().url()).searchParams.has('cursor');
      await route.fulfill({
        json: {
          items: [
            {
              title,
              reference: {
                id: older
                  ? '00000000-0000-0000-0000-000000000011'
                  : '00000000-0000-0000-0000-000000000010',
                kind,
                version: older ? 'test-v1' : 'test-v2',
                published_at: '2026-11-07T12:00:00Z',
              },
            },
          ],
          next_cursor: older ? null : 'opaque-fixture-page',
        },
      });
    });
    await page.route(`**/api/v1/policies/${kind}?version=test-v1`, async (route) =>
      route.fulfill({
        json: {
          title,
          content: 'Exact published older version. <script>not executable</script>',
          reference: {
            id: '00000000-0000-0000-0000-000000000011',
            kind,
            version: 'test-v1',
            published_at: '2026-11-07T12:00:00Z',
          },
        },
      }),
    );
    await page.goto(`/${kind}?view=history`);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(`${title} · Version history`);
    await expect(page.getByRole('link', { name: `${title} · test-v2`, exact: true })).toBeVisible();
    await checkpoint(`${kind}-history-first.png`);
    await page.getByRole('link', { name: 'Older versions', exact: true }).click();
    await expect(page).toHaveURL(`/${kind}?view=history&cursor=opaque-fixture-page`);
    await page.getByRole('link', { name: `${title} · test-v1`, exact: true }).waitFor();
    await expect(page.getByRole('link', { name: 'Older versions', exact: true })).toHaveCount(0);
    await checkpoint(`${kind}-history-older.png`);
    await page.getByRole('link', { name: `${title} · test-v1`, exact: true }).click();
    await expect(page.getByText('Exact published older version.', { exact: false })).toBeVisible();
    await expect(page.getByRole('checkbox')).toHaveCount(0);
    await checkpoint(`${kind}-history-selected-version.png`);
  });
}

test('invalid version-history cursor recovers through the real first-page link', async ({
  page,
  checkpoint,
}: Context) => {
  await page.route('**/api/v1/policies/terms/versions?*', async (route) => {
    const cursor = new URL(route.request().url()).searchParams.get('cursor');
    if (cursor !== null)
      await route.fulfill({
        status: 422,
        json: { code: 'invalid_cursor', message: 'This page cannot be used.' },
      });
    else await route.fulfill({ json: { items: [], next_cursor: null } });
  });
  await page.goto('/terms?view=history&cursor=other-document-page');
  await expect(page.getByRole('alert')).toHaveText('This version-history page link can’t be used.');
  await checkpoint('terms-history-invalid-cursor.png');
  await page.getByRole('link', { name: 'Latest published versions', exact: true }).click();
  await expect(page).toHaveURL('/terms?view=history');
  await expect(
    page.getByText('No published versions are available.', { exact: true }),
  ).toBeVisible();
  await checkpoint('terms-history-first-page-recovered.png');
});
