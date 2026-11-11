import type { Page, Route } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { actor, pending, challenge } from './onboarding.fixtures';

interface Context {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}

async function bootstrap(route: Route, outcome: string): Promise<void> {
  if (outcome === 'network') {
    await route.abort('failed');
    return;
  }
  await route.fulfill(
    outcome === 'authenticated'
      ? { json: actor }
      : outcome === 'guest'
        ? { status: 401, json: { code: 'unauthenticated' } }
        : { status: 503, json: { code: 'unavailable', title: 'PRIVATE' } },
  );
}

for (const [outcome, title] of [
  ['guest', 'Find someone to study with'],
  ['authenticated', 'Confirm your APU email'],
  ['unavailable', 'We couldn’t check your sign-in'],
  ['network', 'We couldn’t check your sign-in'],
] as const) {
  test(`bootstrap ${outcome}: actual identity boundary and safe recovery`, async ({
    page,
    checkpoint,
  }: Context) => {
    let requests = 0;
    await page.route('**/api/v1/me', async (route) => {
      requests += 1;
      await bootstrap(route, outcome);
    });
    await page.goto('/onboarding');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
    expect(requests).toBe(1);
    await expect(page.getByText('fixture-csrf')).toHaveCount(0);
    await expect(page.getByText('PRIVATE', { exact: true })).toHaveCount(0);
    expect(
      await page.evaluate(() => ({
        local: Object.keys(localStorage).filter((key) => key !== 'tuiDark'),
        session: Object.keys(sessionStorage),
      })),
    ).toEqual({ local: [], session: [] });
    await checkpoint(`${outcome}.png`);
  });
}

for (const code of [
  'login_invalid',
  'login_cancelled',
  'login_provider_unavailable',
  'login_rate_limited',
  'account_unavailable',
  'request_context_invalid',
] as const) {
  test(`callback recovery ${code} is presentation only and strips URL`, async ({
    page,
    checkpoint,
  }: Context) => {
    await page.route('**/api/v1/me', async (route) => {
      await route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
    });
    await page.goto(`/onboarding?auth_error=${code}&auth_ref=00000000-0000-0000-0000-000000000001`);
    await expect(page).toHaveURL('/onboarding');
    await expect(page.getByRole('heading', { level: 2 })).toBeVisible();
    await expect(page.getByText('Reference: 00000000-0000-0000-0000-000000000001')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Continue with Google' })).toHaveAttribute(
      'href',
      '/api/v1/auth/google/start?return_to=/onboarding',
    );
    await checkpoint(`${code}.png`);
  });
}

for (const [name, status] of [
  ['queued', { ...challenge, delivery: 'queued', can_verify: false }],
  ['sending', { ...challenge, delivery: 'sending', can_verify: false }],
  ['cancelled', { ...challenge, delivery: 'cancelled', can_verify: false }],
  ['active', challenge],
  ['locked', { ...challenge, state: 'locked', attempts_remaining: 0, can_verify: false }],
  ['expired', { ...challenge, state: 'expired', can_verify: false, can_resend: true }],
  ['delivery-failed', { ...challenge, delivery: 'failed', can_verify: false, can_resend: true }],
] as const) {
  test(`reload owned challenge ${name} reads server capabilities`, async ({
    page,
    checkpoint,
  }: Context) => {
    await page.route('**/api/v1/me', async (route) => {
      await route.fulfill({ json: pending });
    });
    await page.route(`**/api/v1/auth/email-challenges/${challenge.id}`, async (route) => {
      await route.fulfill({ json: status });
    });
    await page.goto('/onboarding');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check your APU email');
    await expect(page.getByRole('button', { name: 'Confirm code' })).toBeEnabled({
      enabled: status.can_verify,
    });
    await expect(page.getByRole('button', { name: 'Resend code' })).toBeEnabled({
      enabled: status.can_resend,
    });
    await expect(page.getByRole('region', { name: 'Email delivery help' })).toContainText(
      'quarantine',
    );
    await expect(
      page.getByRole('link', { name: 'your university email quarantine (opens in a new tab)' }),
    ).toHaveAttribute('href', 'https://security.microsoft.com/quarantine');
    await expect(
      page.getByRole('link', { name: 'your university email quarantine (opens in a new tab)' }),
    ).toHaveAttribute('rel', 'noopener noreferrer');
    await expect(
      page.getByRole('link', { name: 'Contact support if you still cannot find the code' }),
    ).toHaveAttribute('href', '/help/contact');
    const meaning = {
      sent: 'This does not confirm delivery to your inbox.',
      queued: 'The mail service has not confirmed acceptance yet.',
      sending: 'Acceptance is not confirmed yet.',
      failed: 'We couldn’t confirm that the mail service accepted this email.',
      cancelled: 'We couldn’t confirm that the mail service accepted this email.',
    } as const;
    await expect(page.getByRole('region', { name: 'Email delivery help' })).toContainText(
      meaning[status.delivery],
    );
    await expect(page.getByText('Resend available after', { exact: false })).toHaveCount(
      Number(!status.can_resend),
    );
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await checkpoint(`challenge-${name}.png`);
  });
}

test('email validation preserves editable draft and makes no command request', async ({
  page,
  checkpoint,
}: Context) => {
  let writes = 0;
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: actor });
  });
  await page.route('**/api/v1/auth/email-challenges', async (route) => {
    writes += 1;
    await route.abort();
  });
  await page.goto('/onboarding');
  await page.getByRole('textbox', { name: 'APU email', exact: true }).fill('student@apu.edu.my');
  await page.getByRole('button', { name: 'Send code', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText(
    'Enter a student address ending in @mail.apu.edu.my.',
  );
  await expect(page.getByRole('textbox', { name: 'APU email', exact: true })).toHaveValue(
    'student@apu.edu.my',
  );
  expect(writes).toBe(0);
  await checkpoint('email-invalid.png');
});

test('support-required survives challenge reload', async ({ page, checkpoint }: Context) => {
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: pending });
  });
  await page.route(`**/api/v1/auth/email-challenges/${challenge.id}`, async (route) => {
    await route.fulfill({
      json: {
        ...challenge,
        state: 'consumed',
        verification_outcome: 'support_required',
        can_verify: false,
      },
    });
  });
  await page.goto('/onboarding');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('This address needs support');
  await expect(page.getByRole('button', { name: 'Confirm code' })).toHaveCount(0);
  await checkpoint('challenge-support-required.png');
});

test('session loading resolves to actual welcome', async ({ page, checkpoint }: Context) => {
  let release: () => void = () => {
    throw new Error('Response gate was not initialised');
  };
  const reply = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/me', async (route) => {
    await reply;
    await route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
  });
  await page.goto('/onboarding');
  await expect(page.getByRole('status')).toHaveText('Checking your sign-in…');
  await checkpoint('session-loading.png');
  release();
  await expect(page.getByRole('link', { name: 'Continue with Google' })).toBeVisible();
  await checkpoint('session-loading-resolved.png');
});

test('session check retries only after explicit action', async ({ page, checkpoint }: Context) => {
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ status: 503, json: { code: 'unavailable' } });
  });
  await page.goto('/onboarding');
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible();
  await checkpoint('session-retry-before.png');
  await page.unroute('**/api/v1/me');
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
  });
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByRole('link', { name: 'Continue with Google' })).toBeVisible();
  await checkpoint('session-retry-after.png');
});

test('uncertain send reconciles server challenge instead of claiming nothing sent', async ({
  page,
  checkpoint,
}: Context) => {
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: actor });
  });
  await page.route('**/api/v1/auth/email-challenges', async (route) => {
    await route.abort('failed');
  });
  await page.goto('/onboarding');
  await page.getByRole('textbox', { name: 'APU email', exact: true }).fill(challenge.email);
  await page.unroute('**/api/v1/me');
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: pending });
  });
  await page.route(`**/api/v1/auth/email-challenges/${challenge.id}`, async (route) => {
    await route.fulfill({ json: { ...challenge, delivery: 'queued', can_verify: false } });
  });
  await page.getByRole('button', { name: 'Send code', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Check your APU email');
  await expect(page.getByRole('alert')).toHaveText(
    'We couldn’t confirm the result. Check status before trying again.',
  );
  await expect(page.getByText('Nothing sent', { exact: false })).toHaveCount(0);
  await checkpoint('send-uncertain-reconciled.png');
});

test('wrong pasted code uses actual remaining attempts', async ({ page, checkpoint }: Context) => {
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: pending });
  });
  await page.route(`**/api/v1/auth/email-challenges/${challenge.id}`, async (route) => {
    await route.fulfill({ json: challenge });
  });
  await page.route(`**/api/v1/auth/email-challenges/${challenge.id}/verify`, async (route) => {
    expect(route.request().headers()['x-csrf-token']).toBe(actor.csrf_token);
    expect(route.request().postDataJSON()).toEqual({ code: '123456' });
    await route.fulfill({ status: 422, json: { code: 'verification_wrong' } });
  });
  await page.goto('/onboarding');
  await expect(page.getByRole('button', { name: 'Confirm code' })).toBeEnabled();
  await page.unroute(`**/api/v1/auth/email-challenges/${challenge.id}`);
  await page.route(`**/api/v1/auth/email-challenges/${challenge.id}`, async (route) => {
    await route.fulfill({
      json: { ...challenge, attempts_remaining: 4, verification_outcome: 'wrong' },
    });
  });
  await page.getByRole('textbox', { name: 'Verification code' }).fill('123456');
  await expect(page.getByText('Attempts remaining: 4.', { exact: false })).toBeVisible();
  await checkpoint('code-wrong.png');
});

test('a replaced account never inherits the previous verification draft', async ({
  page,
  checkpoint,
}: Context) => {
  let account: string = actor.account_id;
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: { ...actor, account_id: account } });
  });
  await page.goto('/onboarding');
  const input = page.getByRole('textbox', { name: 'APU email', exact: true });
  await input.fill('private-draft@mail.apu.edu.my');
  await checkpoint('first-account-verification-draft.png');
  account = '00000000-0000-0000-0000-000000000088';
  await page.getByRole('button', { name: 'Check status', exact: true }).click();
  await expect(input).toHaveValue('');
  await expect(page.getByText('private-draft@mail.apu.edu.my', { exact: true })).toHaveCount(0);
  await checkpoint('replacement-account-cleared-draft.png');
});

test('late old-account send rejection cannot sign out the replacement account', async ({
  page,
  checkpoint,
}: Context) => {
  let account: string = actor.account_id;
  let requests = 0;
  let release: () => void = () => {
    throw new Error('Uninitialised old send');
  };
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/me', async (route) => {
    requests += 1;
    await route.fulfill({ json: { ...actor, account_id: account } });
  });
  await page.route('**/api/v1/auth/email-challenges', async (route) => {
    await pending;
    await route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
  });
  await page.goto('/onboarding');
  await page.getByRole('textbox', { name: 'APU email', exact: true }).fill(challenge.email);
  await page.getByRole('button', { name: 'Send code', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sending…', exact: true })).toBeDisabled();
  account = '00000000-0000-0000-0000-000000000088';
  await page.getByRole('button', { name: 'Check status', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'APU email', exact: true })).toHaveValue('');
  await page
    .getByRole('textbox', { name: 'APU email', exact: true })
    .fill('new-draft@mail.apu.edu.my');
  const finished = page.waitForResponse('**/api/v1/auth/email-challenges');
  release();
  await (await finished).finished();
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() =>
          requestAnimationFrame(() => {
            resolve();
          }),
        ),
      ),
  );
  await expect(page.getByRole('textbox', { name: 'APU email', exact: true })).toHaveValue(
    'new-draft@mail.apu.edu.my',
  );
  await expect(page.getByRole('link', { name: 'Continue with Google' })).toHaveCount(0);
  expect(requests).toBe(2);
  await checkpoint('late-old-send-rejected.png');
});

test('verification quarantine guidance remains readable at320 and200percent without automatic resend', async ({
  page,
  checkpoint,
}: Context) => {
  await page.setViewportSize({ width: 320, height: 800 });
  let writes: readonly string[] = [];
  page.on('request', (request) => {
    if (request.method() !== 'GET' && new URL(request.url()).pathname.startsWith('/api/v1/'))
      writes = [...writes, request.method()];
  });
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: pending });
  });
  await page.route(`**/api/v1/auth/email-challenges/${challenge.id}`, async (route) => {
    await route.fulfill({ json: challenge });
  });
  await page.goto('/onboarding');
  await expect(page.getByRole('region', { name: 'Email delivery help' })).toContainText(
    'does not confirm delivery',
  );
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  const help = page.getByRole('link', {
    name: 'Contact support if you still cannot find the code',
  });
  await help.focus();
  await expect(help).toBeFocused();
  await expect(help).toHaveAttribute('href', '/help/contact');
  await expect(page.getByRole('button', { name: 'Resend code', exact: true })).toBeDisabled();
  await expect(page.getByText('Resend available after', { exact: false })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const codeField = page.getByRole('textbox', { name: 'Verification code', exact: true });
  await codeField.focus();
  await expect(codeField).toBeFocused();
  await expect(codeField).toBeInViewport({ ratio: 1 });
  const caption = await page
    .locator('label[for="verification-code"]')
    .evaluate((label: Readonly<HTMLElement>) => {
      const range = document.createRange();
      range.selectNodeContents(label);
      const bounds = label.getBoundingClientRect();
      return {
        left: bounds.left,
        right: bounds.right,
        text: Array.from(range.getClientRects()).map((rect: Readonly<DOMRect>) => ({
          left: rect.left,
          right: rect.right,
        })),
      };
    });
  for (const text of caption.text) {
    expect(text.left).toBeGreaterThanOrEqual(caption.left);
    expect(text.right).toBeLessThanOrEqual(caption.right);
    expect(text.right).toBeLessThanOrEqual(320);
  }
  expect(writes).toEqual([]);
  await checkpoint('verification-quarantine-320-text200.png');
});
