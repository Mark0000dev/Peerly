import type { Page } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { verifiedActor } from './account.fixtures';

interface Context {
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}
// Three real loading/navigation scenarios hold their own HTTP response.
function heldResponse(): Readonly<{
  readonly promise: Promise<void>;
  readonly resolve: () => void;
}> {
  let release: (() => void) | null = null;
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return {
    promise,
    resolve: () => {
      if (release === null) throw new Error('Response gate was not initialized');
      release();
    },
  };
}

const preparation = {
  workflow_id: '11111111-1111-4111-8111-111111111111',
  expires_at: '2026-11-09T10:00:00Z',
} as const;
const receipt = {
  workflow_id: preparation.workflow_id,
  deleted_at: '2026-11-09T09:00:00Z',
  source_version: 1,
} as const;

async function identity(page: Readonly<Page>, active: () => boolean = () => true): Promise<void> {
  await page.route('**/api/v1/me', async (route) => {
    if (active()) await route.fulfill({ json: verifiedActor });
    else await route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
  });
}

test('P05 explain and deliberate confirmation can be cancelled without deleting', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let deletions = 0;
  await page.route('**/api/v1/me/deletion-workflows', async (route) => {
    expect(route.request().postDataJSON()).toEqual({});
    await route.fulfill({ json: preparation });
  });
  await page.route('**/api/v1/me/deletion', async (route) => {
    deletions += 1;
    await route.fulfill({ json: receipt });
  });
  await page.goto('/account/delete');
  await expect(
    page.getByText(
      'Deleting this account signs you out everywhere. This account cannot be restored.',
    ),
  ).toBeVisible();
  expect(deletions).toBe(0);
  await checkpoint('deletion-explain.png');
  await page.getByRole('button', { name: 'Delete account', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Delete account permanently', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Delete your account?', exact: true }),
  ).toHaveCount(1);
  await checkpoint('deletion-confirm.png', { fullPage: false });
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Delete account permanently', exact: true }),
  ).toHaveCount(0);
  expect(deletions).toBe(0);
  await checkpoint('deletion-cancelled.png');
});

test('P05 lost destructive response recovers actual committed state using cookie-proof endpoint', async ({
  page,
  checkpoint,
}: Context) => {
  let active = true;
  await identity(page, () => active);
  let deletes = 0;
  await page.route('**/api/v1/me/deletion-workflows', async (route) => {
    await route.fulfill({ json: preparation });
  });
  await page.route('**/api/v1/me/deletion', async (route) => {
    deletes += 1;
    expect(route.request().postDataJSON()).toEqual({ workflow_id: preparation.workflow_id });
    expect(route.request().headers()['idempotency-key']).toMatch(/^[a-f0-9-]{36}$/u);
    active = false;
    await route.abort('failed');
  });
  await page.route('**/api/v1/me/deletion-status', async (route) => {
    await route.fulfill({ json: { ...receipt, state: 'deleted' } });
  });
  await page.goto('/account/delete');
  await page.getByRole('button', { name: 'Delete account', exact: true }).click();
  await page.getByRole('button', { name: 'Delete account permanently', exact: true }).click();
  await expect(page).toHaveURL('/account/deletion-status');
  await expect(
    page.getByRole('heading', { name: 'Deletion confirmed', exact: true }),
  ).toBeVisible();
  expect(deletes).toBe(1);
  await checkpoint('deletion-recovered.png');
});

for (const state of ['pending', 'unavailable', 'transient'] as const) {
  test(`P05 recovery ${state} never invents deletion success or reversal`, async ({
    page,
    checkpoint,
  }: Context) => {
    await page.route('**/api/v1/me', async (route) => {
      await route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
    });
    let reads = 0;
    await page.route('**/api/v1/me/deletion-status', async (route) => {
      reads += 1;
      if (state === 'pending') await route.fulfill({ json: { ...preparation, state: 'pending' } });
      else
        await route.fulfill({
          status: state === 'unavailable' ? 404 : 503,
          json: {
            code: state === 'unavailable' ? 'deletion_status_unavailable' : 'unavailable',
            request_id: 'safe-reference',
          },
        });
    });
    await page.goto('/account/deletion-status');
    await expect(
      page.getByRole('heading', {
        name: state === 'pending' ? 'Deletion hasn’t been confirmed' : 'We can’t confirm deletion',
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Deletion confirmed', exact: true }),
    ).toHaveCount(0);
    await checkpoint(`deletion-status-${state}.png`);
    await page.getByRole('button', { name: 'Check again', exact: true }).click();
    await expect.poll(() => reads).toBe(2);
    await expect(page.getByRole('button', { name: 'Check again', exact: true })).toBeVisible();
    await checkpoint(`deletion-status-${state}-retried.png`);
  });
}

test('P05 320px and200% text keeps destructive confirmation readable and keyboard reachable', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await page.route('**/api/v1/me/deletion-workflows', async (route) => {
    await route.fulfill({ json: preparation });
  });
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto('/account/delete');
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  const action = page.getByRole('button', { name: 'Delete account', exact: true });
  await action.scrollIntoViewIfNeeded();
  await action.focus();
  await page.keyboard.press('Enter');
  const confirm = page.getByRole('button', { name: 'Delete account permanently', exact: true });
  await expect(confirm).toBeVisible();
  const heading = page.getByRole('heading', { name: 'Delete your account?', exact: true });
  await expect(heading).toHaveCount(1);
  await heading.scrollIntoViewIfNeeded();
  await expect(heading).toBeInViewport();
  const explanation = page.getByText(
    'This account cannot be restored. You’ll be signed out on every device. Joining again creates a new account and requires student email verification; your old profile and chats will not transfer.',
    { exact: true },
  );
  const textEdges = await explanation.evaluate((element: Readonly<HTMLElement>) => {
    const bounds = element.getBoundingClientRect();
    return { left: bounds.left, right: bounds.right };
  });
  expect(textEdges.left).toBeGreaterThanOrEqual(0);
  expect(textEdges.right).toBeLessThanOrEqual(320);
  // A fixed fullscreen dialog is a viewport surface: full-page capture includes
  // the inert underlying page beyond the visible overlay. Cover its actual top
  // and scrolled actions separately; retain the closed form's full-page shot.
  await checkpoint('deletion-confirm-reflow-200-top.png', { fullPage: false });
  await confirm.scrollIntoViewIfNeeded();
  const edges = await confirm.evaluate((element: Readonly<HTMLElement>) => {
    const bounds = element.getBoundingClientRect();
    return { left: bounds.left, right: bounds.right };
  });
  expect(edges.left).toBeGreaterThanOrEqual(0);
  expect(edges.right).toBeLessThanOrEqual(320);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  await checkpoint('deletion-confirm-reflow-200-actions.png', { fullPage: false });
  const cancel = page.getByRole('button', { name: 'Cancel', exact: true });
  await cancel.scrollIntoViewIfNeeded();
  await cancel.focus();
  await page.keyboard.press('Enter');
  await expect(confirm).toHaveCount(0);
  // Public dialog focus restoration completes after the overlay retires.
  // The keyboard user must return to the action that opened it.
  await expect(action).toBeFocused();
  await checkpoint('deletion-cancel-reflow-200.png');
});

test('P05 bootstrap loading and service failure never expose a destructive action before authority is known', async ({
  page,
  checkpoint,
}: Context) => {
  const gate = heldResponse();
  let reads = 0;
  let writes = 0;
  await page.route('**/api/v1/me', async (route) => {
    reads += 1;
    if (reads === 1) {
      await gate.promise;
      await route.fulfill({
        status: 503,
        json: {
          code: 'unavailable',
          request_id: 'safe-authority-reference',
          title: 'PRIVATE AUTHORITY DETAIL',
        },
      });
    } else await route.fulfill({ json: verifiedActor });
  });
  await page.route('**/api/v1/me/deletion-workflows', async (route) => {
    writes += 1;
    await route.fulfill({ json: preparation });
  });
  await page.goto('/account/delete');
  await expect(page.getByText('Checking your sign-in…', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Delete account', exact: true })).toHaveCount(0);
  await checkpoint('deletion-authority-loading.png');
  gate.resolve();
  await expect(page.getByText('We couldn’t check your sign-in.', { exact: true })).toBeVisible();
  await expect(
    page.getByText('Reference: safe-authority-reference', { exact: true }),
  ).toBeVisible();
  await expect(page.getByText('PRIVATE AUTHORITY DETAIL', { exact: true })).toHaveCount(0);
  await checkpoint('deletion-authority-error.png');
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Delete account', exact: true })).toBeVisible();
  expect(writes).toBe(0);
  await checkpoint('deletion-authority-retried.png');
});

test('P05 guest may recover an earlier request but cannot prepare a new deletion', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page, () => false);
  await page.goto('/account/delete');
  await expect(
    page.getByText(
      'Sign in to start a deletion request, or check an earlier request from this browser.',
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Sign in', exact: true })).toHaveAttribute(
    'href',
    '/onboarding',
  );
  await expect(
    page.getByRole('link', { name: 'Check deletion status', exact: true }),
  ).toHaveAttribute('href', '/account/deletion-status');
  await expect(page.getByRole('button', { name: 'Delete account', exact: true })).toHaveCount(0);
  await expect(
    page.getByRole('region', { name: 'Delete your Peerly account', exact: true }),
  ).toContainText('Without the app');
  await expect(
    page.getByRole('region', { name: 'What deletion changes', exact: true }),
  ).toContainText('Your messages stay readable');
  await expect(page.getByRole('navigation', { name: 'Main navigation', exact: true })).toHaveCount(
    1,
  );
  await checkpoint('deletion-guest.png');
});

test('P05 preparation failure and malformed success cannot invent a confirmation; only explicit retry proceeds', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let preparations = 0;
  let deletions = 0;
  await page.route('**/api/v1/me/deletion-workflows', async (route) => {
    preparations += 1;
    if (preparations === 1)
      await route.fulfill({
        status: 503,
        json: {
          code: 'unavailable',
          request_id: 'safe-preparation-reference',
          title: 'PRIVATE PREPARATION DETAIL',
        },
      });
    else if (preparations === 2)
      await route.fulfill({ json: { workflow_id: 'invalid', expires_at: preparation.expires_at } });
    else await route.fulfill({ json: preparation });
  });
  await page.route('**/api/v1/me/deletion', async (route) => {
    deletions += 1;
    await route.fulfill({ json: receipt });
  });
  await page.goto('/account/delete');
  await page.getByRole('button', { name: 'Delete account', exact: true }).click();
  await expect(
    page.getByText('Reference: safe-preparation-reference', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Delete account permanently', exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText('PRIVATE PREPARATION DETAIL', { exact: true })).toHaveCount(0);
  await checkpoint('deletion-preparation-error.png');
  await page.getByRole('button', { name: 'Delete account', exact: true }).click();
  await expect(
    page.getByText('We couldn’t prepare this request. You can try again.', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('Reference: safe-preparation-reference', { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Delete account permanently', exact: true }),
  ).toHaveCount(0);
  await checkpoint('deletion-preparation-invalid.png');
  await page.getByRole('button', { name: 'Delete account', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Delete account permanently', exact: true }),
  ).toBeVisible();
  await checkpoint('deletion-preparation-retried.png', { fullPage: false });
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  expect(preparations).toBe(3);
  expect(deletions).toBe(0);
});

test('P05 preparation connection loss retains the account and never sends deletion', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let writes = 0;
  await page.route('**/api/v1/me/deletion-workflows', async (route) => {
    await route.abort('failed');
  });
  await page.route('**/api/v1/me/deletion', async (route) => {
    writes += 1;
    await route.fulfill({ json: receipt });
  });
  await page.goto('/account/delete');
  await page.getByRole('button', { name: 'Delete account', exact: true }).click();
  await expect(
    page.getByText('We couldn’t prepare this request. You can try again.', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Delete account permanently', exact: true }),
  ).toHaveCount(0);
  expect(writes).toBe(0);
  await checkpoint('deletion-preparation-connection-lost.png');
});

test('P05 committed deletion clears ordinary authority and renders only the canonical proof result', async ({
  page,
  checkpoint,
}: Context) => {
  let active = true;
  let writes = 0;
  await identity(page, () => active);
  await page.route('**/api/v1/me/deletion-workflows', async (route) => {
    await route.fulfill({ json: preparation });
  });
  await page.route('**/api/v1/me/deletion', async (route) => {
    writes += 1;
    active = false;
    await route.fulfill({ json: receipt });
  });
  await page.route('**/api/v1/me/deletion-status', async (route) => {
    await route.fulfill({ json: { ...receipt, state: 'deleted' } });
  });
  await page.goto('/account/delete');
  await page.getByRole('button', { name: 'Delete account', exact: true }).click();
  await page.getByRole('button', { name: 'Delete account permanently', exact: true }).click();
  await expect(page).toHaveURL('/account/deletion-status');
  await expect(
    page.getByRole('heading', { name: 'Deletion confirmed', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('The account for this request is deleted.', { exact: false }),
  ).toBeVisible();
  expect(writes).toBe(1);
  await checkpoint('deletion-committed.png');
});

test('P05 mismatched destructive receipt stays uncertain until an explicit canonical status read confirms it', async ({
  page,
  checkpoint,
}: Context) => {
  let active = true;
  let writes = 0;
  let reads = 0;
  await identity(page, () => active);
  await page.route('**/api/v1/me/deletion-workflows', async (route) => {
    await route.fulfill({ json: preparation });
  });
  await page.route('**/api/v1/me/deletion', async (route) => {
    writes += 1;
    await route.fulfill({
      json: { ...receipt, workflow_id: '22222222-2222-4222-8222-222222222222' },
    });
  });
  await page.route('**/api/v1/me/deletion-status', async (route) => {
    reads += 1;
    if (reads === 1) await route.fulfill({ json: { ...preparation, state: 'pending' } });
    else {
      active = false;
      await route.fulfill({ json: { ...receipt, state: 'deleted' } });
    }
  });
  await page.goto('/account/delete');
  await page.getByRole('button', { name: 'Delete account', exact: true }).click();
  await page.getByRole('button', { name: 'Delete account permanently', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Deletion hasn’t been confirmed', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Deletion confirmed', exact: true })).toHaveCount(
    0,
  );
  await checkpoint('deletion-mismatched-receipt-pending.png');
  await page.getByRole('button', { name: 'Check again', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Deletion confirmed', exact: true }),
  ).toBeVisible();
  expect(writes).toBe(1);
  expect(reads).toBe(2);
  await checkpoint('deletion-mismatched-receipt-resolved.png');
});

test('P05 expired authority keeps proof recovery reachable without redirecting into a new login', async ({
  page,
  checkpoint,
}: Context) => {
  let active = true;
  await identity(page, () => active);
  await page.route('**/api/v1/me/deletion-workflows', async (route) => {
    await route.fulfill({ json: preparation });
  });
  await page.route('**/api/v1/me/deletion', async (route) => {
    active = false;
    await route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
  });
  await page.route('**/api/v1/me/deletion-status', async (route) => {
    await route.fulfill({ json: { ...preparation, state: 'pending' } });
  });
  await page.goto('/account/delete');
  await page.getByRole('button', { name: 'Delete account', exact: true }).click();
  await page.getByRole('button', { name: 'Delete account permanently', exact: true }).click();
  await expect(page).toHaveURL('/account/deletion-status');
  await expect(
    page.getByRole('heading', { name: 'Deletion hasn’t been confirmed', exact: true }),
  ).toBeVisible();
  await checkpoint('deletion-expired-authority-recovery.png');
  await page.getByRole('link', { name: 'Return to account deletion', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Sign in', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Delete account', exact: true })).toHaveCount(0);
  await checkpoint('deletion-expired-authority-sign-in.png');
});

test('P05 leaving during a destructive request does not cancel the server outcome or navigate from a retired view', async ({
  page,
  checkpoint,
}: Context) => {
  let active = true;
  await identity(page, () => active);
  const gate = heldResponse();
  await page.route('**/api/v1/me/deletion-workflows', async (route) => {
    await route.fulfill({ json: preparation });
  });
  await page.route('**/api/v1/me/deletion', async (route) => {
    await gate.promise;
    active = false;
    await route.fulfill({ json: receipt });
  });
  await page.goto('/account/delete');
  await page.getByRole('button', { name: 'Delete account', exact: true }).click();
  await page.getByRole('button', { name: 'Delete account permanently', exact: true }).click();
  await expect(page.getByText('Deleting account…', { exact: true })).toBeVisible();
  await checkpoint('deletion-in-flight.png');
  await page.getByRole('link', { name: 'Help', exact: true }).click();
  await expect(page).toHaveURL('/help');
  const committed = page.waitForResponse('**/api/v1/me/deletion');
  gate.resolve();
  expect((await committed).status()).toBe(200);
  await expect(page.getByRole('heading', { name: 'Help and contact', exact: true })).toBeVisible();
  await expect(page).toHaveURL('/help');
  await checkpoint('deletion-retired-view.png');
});

test('P05 proof loading stays independent of sign in and cannot display cached deletion success', async ({
  page,
  checkpoint,
}: Context) => {
  const gate = heldResponse();
  let reads = 0;
  await identity(page, () => false);
  await page.route('**/api/v1/me/deletion-status', async (route) => {
    reads += 1;
    await gate.promise;
    await route.fulfill({ json: { ...preparation, state: 'pending' } });
  });
  await page.goto('/account/deletion-status');
  await expect(page.getByText('Checking your deletion request…', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Deletion confirmed', exact: true })).toHaveCount(
    0,
  );
  await expect(page.getByRole('link', { name: 'Sign in', exact: true })).toHaveCount(0);
  await checkpoint('deletion-proof-loading.png');
  gate.resolve();
  await expect(
    page.getByRole('heading', { name: 'Deletion hasn’t been confirmed', exact: true }),
  ).toBeVisible();
  expect(reads).toBe(1);
  await checkpoint('deletion-proof-loaded-pending.png');
});
