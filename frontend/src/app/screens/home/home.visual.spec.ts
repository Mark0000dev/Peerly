import type { Page } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';

interface Context {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}

async function artwork(page: Readonly<Page>): Promise<void> {
  await expect
    .poll(() =>
      page
        .locator('img')
        .evaluateAll((images: readonly (HTMLElement | SVGElement)[]) =>
          images.every(
            (image: Readonly<HTMLElement | SVGElement>) =>
              image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0,
          ),
        ),
    )
    .toBe(true);
}

for (const [scenario, path] of [
  ['home', '/'],
  ['unknown-route', '/unknown-route'],
] as const) {
  test(`${scenario}: public landing without private bootstrap`, async ({
    page,
    checkpoint,
  }: Context) => {
    let requests = 0;
    let errors: readonly string[] = [];
    page.on('pageerror', (error: Readonly<Error>) => {
      errors = [...errors, error.message];
    });
    await page.route('**/api/v1/me', async (route) => {
      requests += 1;
      await route.abort();
    });
    await page.goto(path);
    await expect(page).toHaveURL('/');
    await expect(page).toHaveTitle('Peerly · Find someone to study with');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Find someone to study with.');
    await expect(page.getByRole('link', { name: 'Open the app' }).first()).toHaveAttribute(
      'href',
      '/onboarding',
    );
    await expect(page.getByRole('link', { name: 'Privacy Policy' })).toBeVisible();
    expect(requests).toBe(0);
    expect(errors).toEqual([]);
    await artwork(page);
    await checkpoint(`${scenario}.png`);
  });
}

test('small viewport and enlarged text preserve content', async ({ page, checkpoint }: Context) => {
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto('/');
  await page.addStyleTag({ content: ':root { font-size: 200%; }' });
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Find someone to study with.');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await artwork(page);
  await checkpoint('small-large-text.png');
});
