import type { Page } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';

for (const [kind, title] of [
  ['terms', 'Terms of Use'],
  ['privacy', 'Privacy Policy'],
] as const) {
  test(`real published ${kind} is read from PostgreSQL by version`, async ({
    page,
    checkpoint,
  }: {
    readonly page: Page;
    readonly checkpoint: (name: string) => Promise<void>;
  }) => {
    const published = page.waitForResponse(`**/api/v1/policies/${kind}?version=fixture-v1`);
    await page.goto(`/${kind}?version=fixture-v1`);
    const response = await published;
    expect(response.status()).toBe(200);
    const value: unknown = await response.json();
    expect(value).toMatchObject({
      reference: { kind, version: 'fixture-v1' },
      content: `Published ${kind} fixture from PostgreSQL.`,
    });
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
    await expect(page.getByText(`Published ${kind} fixture from PostgreSQL.`)).toBeVisible();
    await expect(page.getByRole('checkbox')).toHaveCount(0);
    await checkpoint(`${kind}-published-postgres.png`);
  });
}
