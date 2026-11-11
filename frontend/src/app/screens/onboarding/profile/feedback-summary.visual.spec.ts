import type { Page } from '@playwright/test';
import { expect, test } from '../../../../../testing/visual';
import { verifiedActor } from '../onboarding.fixtures';
import { ownProfile } from './profile.fixtures';

interface Context {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}
const actor = {
  ...verifiedActor,
  capabilities: { ...verifiedActor.capabilities, can_use_student_features: true },
} as const;
async function profile(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: actor });
  });
  await page.route('**/api/v1/me/profile', async (route) => {
    await route.fulfill({ json: ownProfile });
  });
}
async function open(page: Readonly<Page>): Promise<void> {
  await page.goto('/onboarding');
  await page.getByRole('button', { name: 'Your profile', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your profile', exact: true })).toBeVisible();
}

async function readableExplanation(page: Readonly<Page>): Promise<void> {
  const button = await page.getByRole('button', { name: 'How peer feedback works' }).boundingBox();
  if (button === null) throw new Error('Missing feedback explanation action');
  expect(button.x).toBeGreaterThanOrEqual(0);
  expect(button.x + button.width).toBeLessThanOrEqual(320);
}

for (const responses of [0, 2]) {
  test(`F03 own summary protects the threshold at ${String(responses)} responses`, async ({
    page,
    checkpoint,
  }: Context) => {
    await profile(page);
    await page.route('**/feedback-summary', async (route) => {
      await route.fulfill({ json: { state: 'building', responses, publicly_visible: true } });
    });
    await open(page);
    const summary = page.getByRole('region', { name: 'Your peer feedback', exact: true });
    await expect(
      summary.getByRole('heading', { name: 'Feedback is still building' }),
    ).toBeVisible();
    await expect(
      summary.getByText(
        `${String(responses)} partners have responded. A summary appears after three.`,
      ),
    ).toBeVisible();
    await expect(summary.getByRole('definition')).toHaveCount(0);
    await checkpoint(`own-feedback-building-${String(responses)}.png`);
  });
}

test('F03 own exact counts and functional explanation', async ({ page, checkpoint }: Context) => {
  await profile(page);
  await page.route('**/feedback-summary', async (route) => {
    await route.fulfill({
      json: { state: 'available', responses: 4, yes: 2, maybe: 1, no: 1, publicly_visible: true },
    });
  });
  await open(page);
  const summary = page.getByRole('region', { name: 'Your peer feedback', exact: true });
  await expect(summary.getByText('2 of 4 partners would study together again.')).toBeVisible();
  await expect(summary.getByRole('definition')).toHaveText(['2', '1', '1']);
  await checkpoint('own-feedback-available.png');
  await summary.getByRole('button', { name: 'How peer feedback works' }).click();
  await expect(summary.getByText(/Names and notes are never shown/)).toBeVisible();
  await expect(summary.getByRole('button', { name: 'How peer feedback works' })).toHaveAttribute(
    'aria-expanded',
    'true',
  );
  await checkpoint('own-feedback-explanation.png');
});

test('F03 failed read retries explicitly and never writes', async ({
  page,
  checkpoint,
}: Context) => {
  await profile(page);
  let reads = 0;
  await page.route('**/feedback-summary', async (route) => {
    expect(route.request().method()).toBe('GET');
    reads += 1;
    if (reads === 1)
      await route.fulfill({
        status: 503,
        json: { code: 'temporarily_unavailable', message: 'Unavailable' },
      });
    else await route.fulfill({ json: { state: 'building', responses: 1, publicly_visible: true } });
  });
  await open(page);
  const summary = page.getByRole('region', { name: 'Your peer feedback', exact: true });
  await expect(summary.getByRole('alert')).toHaveText('We couldn’t load peer feedback.');
  expect(reads).toBe(1);
  await checkpoint('own-feedback-read-failed.png');
  await summary.getByRole('button', { name: 'Retry feedback' }).click();
  await expect(
    summary.getByText('1 partner has responded. A summary appears after three.'),
  ).toBeVisible();
  expect(reads).toBe(2);
  await checkpoint('own-feedback-retried.png');
});

test('F03 own non-public response renders no counts', async ({ page, checkpoint }: Context) => {
  await profile(page);
  await page.route('**/feedback-summary', async (route) => {
    await route.fulfill({
      json: { state: 'available', responses: 4, yes: 2, maybe: 1, no: 1, publicly_visible: false },
    });
  });
  await open(page);
  const summary = page.getByRole('region', { name: 'Your peer feedback', exact: true });
  await expect(summary.getByText('Your feedback summary isn’t public right now.')).toBeVisible();
  await expect(summary.getByRole('definition')).toHaveCount(0);
  await expect(summary.getByText(/of 4 partners/)).toHaveCount(0);
  await checkpoint('own-feedback-not-public.png');
});

test('F03 own-summary remains readable at320px and200 percent text', async ({
  page,
  checkpoint,
}: Context) => {
  await profile(page);
  await page.route('**/feedback-summary', async (route) => {
    await route.fulfill({
      json: { state: 'available', responses: 4, yes: 2, maybe: 1, no: 1, publicly_visible: true },
    });
  });
  await page.setViewportSize({ width: 320, height: 800 });
  await open(page);
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  const summary = page.getByRole('region', { name: 'Your peer feedback', exact: true });
  const about = summary.getByRole('button', { name: 'How peer feedback works' });
  await about.scrollIntoViewIfNeeded();
  await about.focus();
  await page.keyboard.press('Enter');
  await expect(about).toBeFocused();
  await expect(summary.getByText(/Names and notes are never shown/)).toBeVisible();
  await expect(summary.getByRole('definition')).toHaveText(['2', '1', '1']);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  await readableExplanation(page);
  await checkpoint('own-feedback-reflow-200.png');
});
