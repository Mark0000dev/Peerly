import type { Page } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';

async function assertRecoveryActions(page: Readonly<Page>): Promise<void> {
  const navigation = page.getByRole('navigation', { name: 'Access recovery', exact: true });
  const links = navigation.getByRole('link');
  await expect(links).toHaveCount(3);
  const geometry = await links.evaluateAll((elements: readonly Readonly<Element>[]) =>
    elements.map((element) => {
      const bounds = element.getBoundingClientRect();
      const range = document.createRange();
      range.selectNodeContents(element);
      const text = Array.from(range.getClientRects()).map((rect: Readonly<DOMRect>) => ({
        left: rect.left,
        right: rect.right,
        top: rect.top,
        bottom: rect.bottom,
      }));
      return {
        left: bounds.left,
        right: bounds.right,
        top: bounds.top,
        bottom: bounds.bottom,
        width: element.clientWidth,
        scrollWidth: element.scrollWidth,
        text,
      };
    }),
  );
  for (const [index, bounds] of geometry.entries()) {
    expect(bounds.left).toBeGreaterThanOrEqual(0);
    expect(bounds.scrollWidth).toBeLessThanOrEqual(bounds.width);
    for (const text of bounds.text) {
      expect(text.left).toBeGreaterThanOrEqual(bounds.left);
      expect(text.right).toBeLessThanOrEqual(bounds.right);
      expect(text.top).toBeGreaterThanOrEqual(bounds.top);
      expect(text.bottom).toBeLessThanOrEqual(bounds.bottom);
    }
    for (const other of geometry.slice(index + 1))
      expect(
        bounds.right <= other.left ||
          other.right <= bounds.left ||
          bounds.bottom <= other.top ||
          other.bottom <= bounds.top,
      ).toBe(true);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

test('public help offers real recovery links without fake support submission', async ({
  page,
  checkpoint,
}: {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}) => {
  await page.goto('/help');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Help and contact');
  await expect(page.getByRole('heading', { name: 'My APU email is already in use' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Back to sign-in' })).toHaveAttribute(
    'href',
    '/onboarding',
  );
  await expect(page.locator('form')).toHaveCount(0);
  await assertRecoveryActions(page);
  await checkpoint('help.png');
});

test('real Taiga font watcher scales text and restores it without viewport overflow', async ({
  page,
  checkpoint,
}: {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}) => {
  await page.goto('/help');
  const title = page.getByRole('heading', { level: 1 });
  await expect(title).toHaveCSS('font-size', '36px');
  await expect(page.locator('iframe')).toHaveCSS('border-top-width', '0px');
  // Controlled OS text-measurement input. The real observer/provider/theme remain active.
  await page
    .frameLocator('iframe')
    .locator('body')
    .evaluate((body: Readonly<HTMLElement | SVGElement>) => {
      body.replaceChildren(document.createTextNode('.'));
      body.style.setProperty('font-size', '28px');
      body.style.setProperty('line-height', '28px');
      return body.getBoundingClientRect().height;
    });
  await expect
    .poll(() =>
      page
        .frameLocator('iframe')
        .locator('body')
        .evaluate(
          (body: Readonly<HTMLElement | SVGElement>) => body.getBoundingClientRect().height,
        ),
    )
    .toBe(28);
  // Like restoration below, synthetic hidden-frame input needs a rendering turn;
  // native OS text changes schedule one. This is not application scheduling.
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => {
          resolve();
        }),
      ),
  );
  await expect(title).toHaveCSS('font-size', '47px');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await assertRecoveryActions(page);
  await checkpoint('font-scaling-enlarged.png');
  await page
    .frameLocator('iframe')
    .locator('body')
    .evaluate((body: Readonly<HTMLElement | SVGElement>) => {
      body.style.setProperty('font-size', '17px');
      body.style.setProperty('line-height', '17px');
    });
  await expect
    .poll(() =>
      page
        .frameLocator('iframe')
        .locator('body')
        .evaluate(
          (body: Readonly<HTMLElement | SVGElement>) => body.getBoundingClientRect().height,
        ),
    )
    .toBe(17);
  // A synthetic change inside a hidden measurement frame needs a rendering turn.
  // Native OS text-size changes already schedule one; do not use a timed sleep.
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => {
          resolve();
        }),
      ),
  );
  await expect(title).toHaveCSS('font-size', '36px');
  await assertRecoveryActions(page);
  await checkpoint('font-scaling-restored.png');
});

test('public recovery actions remain fully readable and separate at320 and200percent', async ({
  page,
  checkpoint,
}: {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto('/help');
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  await assertRecoveryActions(page);
  const support = page.getByRole('link', { name: 'Contact support', exact: true });
  await support.focus();
  await expect(support).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('link', { name: 'Check a support request', exact: true }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Back to sign-in', exact: true })).toBeFocused();
  await checkpoint('help-recovery-actions320-text200.png');
});
