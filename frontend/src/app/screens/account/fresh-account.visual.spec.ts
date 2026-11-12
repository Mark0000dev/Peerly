import { test, expect } from '../../../../testing/visual';
import type { Page } from '@playwright/test';
import type { Api } from '../../api.generated';

interface Context {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}
const fresh = {
  account_status: 'active',
  membership_status: 'unverified',
  verified_at: null,
  registration: null,
  email_challenge_id: null,
  capabilities: {
    can_verify_student_email: true,
    can_begin_onboarding: false,
    can_use_student_features: false,
  },
  account_id: '00000000-0000-4000-8000-000000000091',
  csrf_token: 'synthetic-fresh-actor-csrf',
} as const satisfies Api['schemas']['IdentityResponse'];
const receipt = {
  workflow_id: '00000000-0000-4000-8000-000000000090',
  source_version: 1,
  deleted_at: '2026-11-10T11:00:00Z',
  state: 'deleted',
} as const satisfies Api['schemas']['ConfirmedDeletionResponse'];

test('confirmed old deletion offers a fresh sign-in entry without restoring an identity', async ({
  page,
  checkpoint,
}: Context) => {
  let writes: readonly string[] = [];
  page.on('request', (request) => {
    if (request.method() !== 'GET' && new URL(request.url()).pathname.startsWith('/api/v1/'))
      writes = [...writes, request.method()];
  });
  await page.route('**/api/v1/me/deletion-status', (route) => route.fulfill({ json: receipt }));
  await page.route('**/api/v1/me', (route) =>
    route.fulfill({ status: 401, json: { code: 'unauthenticated' } }),
  );
  await page.goto('/account/deletion-status');
  await expect(page.getByRole('heading', { name: 'Deletion confirmed' })).toBeVisible();
  await expect(
    page.getByText('the deleted account cannot be restored', { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Start a new account', exact: true }),
  ).toHaveAttribute('href', '/onboarding');
  await page.setViewportSize({ width: 320, height: 800 });
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  const start = page.getByRole('link', { name: 'Start a new account', exact: true });
  await start.focus();
  await expect(start).toBeFocused();
  await expect(start).toBeInViewport({ ratio: 1 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await checkpoint('old-deletion-new-account-entry.png');
  await page.evaluate(() => {
    document.documentElement.style.removeProperty('font-size');
  });
  await page.getByRole('link', { name: 'Start a new account', exact: true }).click();
  await expect(page).toHaveURL('/onboarding');
  await expect(
    page.getByRole('link', { name: 'Continue with Google', exact: true }),
  ).toHaveAttribute('href', '/api/v1/auth/google/start?return_to=/onboarding');
  expect(writes).toEqual([]);
  await checkpoint('fresh-entry-still-requires-google.png');
});

test('a server-confirmed fresh actor requires new institutional verification before private student flows', async ({
  page,
  checkpoint,
}: Context) => {
  let privateReads: readonly string[] = [];
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (
      path === '/api/v1/me/profile' ||
      path === '/api/v1/me/photo-review' ||
      path === '/api/v1/conversations'
    )
      privateReads = [...privateReads, path];
  });
  await page.route('**/api/v1/me', (route) => route.fulfill({ json: fresh }));
  await page.goto('/onboarding');
  await expect(
    page.getByRole('heading', { name: 'Confirm your APU email', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'APU email', exact: true })).toHaveValue('');
  await expect(page.getByRole('button', { name: 'Send code', exact: true })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Verification code', exact: true })).toHaveCount(
    0,
  );
  await expect(page.getByText('Your APU email is confirmed', { exact: true })).toHaveCount(0);
  expect(privateReads).toEqual([]);
  await checkpoint('fresh-actor-unverified-no-restored-student-data.png');
});
