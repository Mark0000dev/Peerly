import type { Page } from '@playwright/test';
import { expect } from './visual';

// Controlled loopback fixture only. HTTP, sessions, membership and delivery persistence are real;
// provider navigation and the fixture inbox driver never contact Google or a student's mailbox.
export async function verifyFixtureStudent(
  page: Readonly<Page>,
  project: string,
  scope:
    | 'email'
    | 'profile'
    | 'goal'
    | 'goal-ai'
    | 'support-auth'
    | 'notification-pref'
    | 'help'
    | 'photo'
    | 'photo-resume'
    | 'setup-profile'
    | 'setup'
    | 'setup-replay'
    | 'setup-visibility-replay'
    | 'setup-offer',
): Promise<void> {
  await page.route('https://provider.invalid/**', async (route) => {
    await route.fulfill({ contentType: 'text/plain', body: 'Controlled provider fixture.' });
  });
  await page.goto('/onboarding');
  const external = page.waitForRequest('https://provider.invalid/**');
  await page.getByRole('link', { name: 'Continue with Google' }).click();
  const state = new URL((await external).url()).searchParams.get('state');
  const parameters = new URLSearchParams({
    state: requiredState(state),
    code: `fixture-${scope}-${project}`,
  });
  await page.goto(`/api/v1/auth/google/callback?${parameters.toString()}`);
  const email = `${scope}-${project}@mail.apu.edu.my`;
  await page.getByRole('textbox', { name: 'APU email', exact: true }).fill(email);
  await page.getByRole('button', { name: 'Send code', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check your APU email');
  const delivered = await page.request.post(
    `http://127.0.0.1:8768/__fixture/deliver/${encodeURIComponent(email)}`,
  );
  expect(delivered.status()).toBe(200);
  const message: unknown = await delivered.json();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Confirm code' })).toBeEnabled();
  await page.getByRole('textbox', { name: 'Verification code' }).fill(deliveredCode(message));
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Your APU email is confirmed');
}
function requiredState(value: string | null): string {
  if (value === null) throw new Error('Missing actual server state');
  return value;
}
function deliveredCode(value: unknown): string {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('code' in value) ||
    typeof value.code !== 'string' ||
    !/^\d{6}$/.test(value.code)
  )
    throw new Error('Invalid controlled inbox');
  return value.code;
}
