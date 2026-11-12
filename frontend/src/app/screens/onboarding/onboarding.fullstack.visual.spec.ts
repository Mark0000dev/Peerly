import { verifyFixtureStudent } from '../../../../testing/verified-student';
import type { Page, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';

test('real FastAPI bootstrap and PostgreSQL readiness render real welcome', async ({
  page,
  checkpoint,
}: {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}) => {
  const ready = await page.request.get('/api/ready');
  expect(ready.status()).toBe(200);
  const unauthenticated = page.waitForResponse('**/api/v1/me');
  await page.goto('/onboarding');
  expect((await unauthenticated).status()).toBe(401);
  await expect(
    page.getByRole('heading', { name: 'Find someone to study with', exact: true }),
  ).toBeVisible();
  await checkpoint('guest.png');
});

test('real session bootstrap, CSRF denial and logout revoke the stored session', async ({
  page,
  checkpoint,
  baseURL,
}: {
  readonly baseURL: string | undefined;
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}, info: Readonly<TestInfo>) => {
  const marker = markerFor(info.project.name);
  await page.context().addCookies([
    {
      name: '__Host-studymate_session',
      value: marker.repeat(43),
      url: fixtureOrigin(baseURL),
      secure: true,
      httpOnly: true,
      sameSite: 'Lax',
    },
  ]);
  const bootstrap = page.waitForResponse('**/api/v1/me');
  await page.goto('/onboarding');
  const response = await bootstrap;
  expect(response.status()).toBe(200);
  const value: unknown = await response.json();
  const csrf = csrfToken(value);
  expect(value).toMatchObject({
    account_id: '00000000-0000-0000-0000-000000000001',
    account_status: 'active',
    membership_status: 'unverified',
    email_challenge_id: null,
  });
  await expect(
    page.getByRole('heading', { name: 'Confirm your APU email', exact: true }),
  ).toBeVisible();
  await checkpoint('authenticated.png');
  const denied = await page.request.post('/api/v1/auth/logout', {
    headers: { origin: fixtureOrigin(baseURL) },
  });
  expect(denied.status()).toBe(403);
  expect(csrf.length).toBeGreaterThan(0);
  await page.getByRole('textbox', { name: 'APU email', exact: true }).fill('draft@mail.apu.edu.my');
  const logout = page.waitForResponse('**/api/v1/auth/logout');
  const revoked = page.waitForResponse('**/api/v1/me');
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  expect((await logout).status()).toBe(204);
  expect((await revoked).status()).toBe(401);
  await expect(
    page.getByRole('heading', { name: 'Find someone to study with', exact: true }),
  ).toBeVisible();
  await checkpoint('guest.png');
});

function csrfToken(value: unknown): string {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('csrf_token' in value) ||
    typeof value.csrf_token !== 'string'
  )
    throw new Error('Invalid actual bootstrap');
  return value.csrf_token;
}

function markerFor(project: string): string {
  if (project === 'webkit-mobile') return 'b';
  if (project === 'chromium-desktop') return 'c';
  return 'a';
}

for (const outcome of ['success', 'cancelled', 'unavailable'] as const) {
  test(`real Google-entry state and browser callback ${outcome} with controlled provider`, async ({
    page,
    checkpoint,
  }: {
    readonly page: Page;
    readonly checkpoint: (name: string) => Promise<void>;
  }, info: Readonly<TestInfo>) => {
    await page.route('https://provider.invalid/**', async (route) => {
      await route.fulfill({
        contentType: 'text/plain',
        body: 'Controlled provider fixture. No external request.',
      });
    });
    await page.goto('/onboarding');
    const external = page.waitForRequest('https://provider.invalid/**');
    await page.getByRole('link', { name: 'Continue with Google' }).click();
    const state = new URL((await external).url()).searchParams.get('state');
    expect(state).not.toBeNull();
    const parameters = callbackParameters(outcome, state, info.project.name);
    await page.goto(`/api/v1/auth/google/callback?${parameters.toString()}`);
    await expect(page).toHaveURL('/onboarding');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(
      outcome === 'success' ? 'Confirm your APU email' : 'Find someone to study with',
    );
    await expect(page.getByRole('heading', { level: 2 })).toHaveCount(
      outcome === 'success' ? 0 : 1,
    );
    await checkpoint(`google-${outcome}.png`);
  });
}

function callbackParameters(
  outcome: string,
  state: string | null,
  project: string,
): URLSearchParams {
  if (state === null) throw new Error('Missing actual server state');
  return new URLSearchParams(
    outcome === 'cancelled'
      ? { state, error: 'access_denied' }
      : { state, code: outcome === 'unavailable' ? 'fixture-unavailable' : `fixture-${project}` },
  );
}

test('real email challenge, durable delivery and code verification survive reload', async ({
  page,
  checkpoint,
}: {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}, info: Readonly<TestInfo>) => {
  await verifyFixtureStudent(page, info.project.name, 'email');
  await page.reload();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Your APU email is confirmed');
  await checkpoint('email-verified-reload.png');
});

function fixtureOrigin(value: string | undefined): string {
  if (value === undefined) throw new Error('Missing configured fixture origin');
  return new URL(value).origin;
}
