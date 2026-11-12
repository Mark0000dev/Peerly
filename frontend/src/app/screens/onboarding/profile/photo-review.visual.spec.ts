import type { Page } from '@playwright/test';
import { test, expect } from '../../../../../testing/visual';
import { verifiedActor } from '../onboarding.fixtures';
import { ownProfile, profileReference } from './profile.fixtures';

interface Context {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}
for (const [state, title] of [
  ['replacement_required', 'A different profile photo is needed'],
  ['awaiting_human_review', 'Your replacement is awaiting review'],
] as const) {
  test(`owner photo review: ${state} is authoritative without approval or automatic uploads`, async ({
    page,
    checkpoint,
  }: Context) => {
    await page.route('**/api/v1/me', (route) => route.fulfill({ json: verifiedActor }));
    await page.route('**/api/v1/me/profile', (route) => route.fulfill({ json: ownProfile }));
    await page.route('**/api/v1/profile-reference-data', (route) =>
      route.fulfill({ json: profileReference }),
    );
    await page.route('**/api/v1/me/photo-review', (route) =>
      route.fulfill({ json: { version: 1, state } }),
    );
    let uploads = 0;
    await page.route('**/api/v1/media/uploads', async (route) => {
      uploads += 1;
      await route.abort();
    });
    await page.goto('/profile/edit');
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Check photo review status', exact: true }),
    ).toBeEnabled();
    expect(uploads).toBe(0);
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      .toBe(true);
    await checkpoint(`photo-review-${state}.png`);
  });
}
