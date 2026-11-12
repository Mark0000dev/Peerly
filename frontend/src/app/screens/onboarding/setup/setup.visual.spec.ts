import {
  assertNaturalWordWrapping,
  assertFullTextFits,
} from '../../../../../testing/readable-text';
import { noPhotoReview } from '../profile/photo-review.fixtures';
import type { Page } from '@playwright/test';
import { test, expect } from '../../../../../testing/visual';
import { verifiedActor } from '../onboarding.fixtures';
import { ownProfile } from '../profile/profile.fixtures';
import { complete, context, ready, receipt, visibility } from './setup.fixtures';
import type { Api } from '../../../api.generated';

interface Context {
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}

// This controlled ordinary-profile fixture declares no recorded human decision.
// Dedicated photo-review scenarios and all real-backend suites remain unmocked here.
test.beforeEach(async ({ page }: Context) => {
  await page.route('**/api/v1/me/photo-review', (route) => route.fulfill({ json: noPhotoReview }));
});

async function identity(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: verifiedActor });
  });
  await page.route('**/api/v1/me/profile', async (route) => {
    await route.fulfill({ json: ownProfile });
  });
}
async function open(page: Readonly<Page>): Promise<void> {
  await page.goto('/onboarding');
  await page.getByRole('button', { name: 'Your study setup', exact: true }).click();
}

async function performVisibilityAction(page: Readonly<Page>, action: string): Promise<void> {
  await page.getByRole('button', { name: action, exact: true }).click();
  if (action === 'Hide my profile') {
    const dialog = page.getByRole('dialog', { name: 'Hide your profile?', exact: true });
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Hide profile', exact: true }).click();
  }
}

test('setup opens explicitly and renders only actual missing requirements', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let reads = 0;
  await page.route('**/api/v1/me/onboarding', async (route) => {
    reads += 1;
    await route.fulfill({
      json: {
        ...ready,
        setup_requirements: ['photo', 'study_goal'],
        capabilities: { ...ready.capabilities, can_complete_registration: false },
      },
    });
  });
  await page.goto('/onboarding');
  await expect(page.getByRole('button', { name: 'Your study setup', exact: true })).toBeVisible();
  expect(reads).toBe(0);
  await page.getByRole('button', { name: 'Your study setup', exact: true }).click();
  await expect(
    page.getByText('Add a photo and wait for it to be ready.', { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Your study goal', exact: true })).toBeVisible();
  expect(reads).toBe(1);
  await checkpoint('setup-missing-requirements.png');
});

test('issued registration notice remains inline with versioned links and no extra consent controls', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let writes = 0;
  await page.route('**/api/v1/me/onboarding', async (route) => {
    await route.fulfill({ json: ready });
  });
  await page.route('**/api/v1/me/registration-context', async (route) => {
    await route.fulfill({ json: context });
  });
  await page.route('**/api/v1/me/registration', async (route) => {
    writes += 1;
    expect(route.request().postDataJSON()).toEqual({ context_id: context.id });
    await route.fulfill({ status: 503, json: { code: 'unavailable' } });
  });
  await open(page);
  await expect(page.getByText(context.notice_text, { exact: false })).toBeVisible();
  await expect(
    page
      .getByRole('region', { name: 'Your study setup', exact: true })
      .getByRole('link', { name: 'Terms of Use', exact: true }),
  ).toHaveAttribute('href', '/terms?version=1');
  await expect(
    page
      .getByRole('region', { name: 'Your study setup', exact: true })
      .getByRole('link', { name: 'Privacy Policy', exact: true }),
  ).toHaveAttribute('href', '/privacy?version=1');
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(writes).toBe(0);
  await checkpoint('setup-inline-notice.png');
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(
    page.getByText(
      'We couldn’t confirm completion. Retry the same action or check your saved setup.',
      { exact: true },
    ),
  ).toBeVisible();
  expect(writes).toBe(1);
  await checkpoint('setup-completion-unknown.png');
});

for (const scenario of [
  {
    name: 'visible',
    status: complete,
    action: 'Hide my profile',
    hidden: true,
    outcome: 'Your profile is hidden from Discover.',
  },
  {
    name: 'hidden',
    status: {
      ...complete,
      visibility: { ...visibility, hidden: true, hidden_at: visibility.changed_at },
      capabilities: { ...complete.capabilities, can_restore_profile: true },
    },
    action: 'Show my profile',
    hidden: false,
    outcome: 'Your profile can appear in Discover.',
  },
  {
    name: 'paused',
    status: {
      ...complete,
      discovery_exposure: { paused: true, can_confirm: true, requirements: [] },
    },
    action: 'Show my profile again',
    hidden: false,
    outcome: 'Your profile can appear in Discover.',
  },
] as const) {
  test(`actual setup ${scenario.name} requires explicit visibility command`, async ({
    page,
    checkpoint,
  }: Context) => {
    await identity(page);
    let status: Api['schemas']['OnboardingStatusResponse'] = scenario.status;
    let writes = 0;
    await page.route('**/api/v1/me/onboarding', async (route) => {
      await route.fulfill({ json: status });
    });
    await page.route('**/api/v1/me/visibility', async (route) => {
      writes += 1;
      expect(route.request().headers()['x-csrf-token']).toBe(verifiedActor.csrf_token);
      expect(route.request().postDataJSON()).toEqual({
        hidden: scenario.hidden,
        expected_version: 1,
      });
      const next = { ...visibility, hidden: scenario.hidden, version: 2 };
      status = {
        ...complete,
        visibility: next,
        capabilities: { ...complete.capabilities, can_restore_profile: next.hidden },
      };
      await route.fulfill({ json: next });
    });
    await open(page);
    await expect(page.getByText('Your setup is saved.', { exact: true })).toBeVisible();
    expect(writes).toBe(0);
    await expect(page.getByRole('button', { name: scenario.action, exact: true })).toBeVisible();
    await checkpoint(`setup-${scenario.name}.png`);
    await performVisibilityAction(page, scenario.action);
    await expect(page.getByText(scenario.outcome, { exact: true })).toBeVisible();
    expect(writes).toBe(1);
    await checkpoint(`setup-${scenario.name}-changed.png`);
  });
}

test('hidden profile retains actual existing-chat capability', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await page.route('**/api/v1/me/onboarding', async (route) => {
    await route.fulfill({
      json: {
        ...complete,
        visibility: { ...visibility, hidden: true },
        capabilities: { ...complete.capabilities, can_restore_profile: true },
      },
    });
  });
  await open(page);
  await expect(page.getByText('Existing chats continue to work.', { exact: true })).toBeVisible();
  await checkpoint('setup-hidden-existing-chats.png');
});

test('freshness requirements prevent invented confirmation capability', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await page.route('**/api/v1/me/onboarding', async (route) => {
    await route.fulfill({
      json: {
        ...complete,
        discovery_exposure: {
          paused: true,
          can_confirm: false,
          requirements: ['photo', 'study_context'],
        },
      },
    });
  });
  await open(page);
  await expect(
    page.getByText('Review your photo and study setup before showing your profile again.', {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Show my profile again', exact: true }),
  ).toHaveCount(0);
  await checkpoint('setup-restore-required.png');
});

test('study setup supports 320px reflow, enlarged text and native keyboard radio choices', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await page.route('**/api/v1/me/onboarding', async (route) => {
    await route.fulfill({ json: complete });
  });
  await page.setViewportSize({ width: 320, height: 800 });
  await open(page);
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  await expect(page.getByRole('heading', { name: 'Your study setup', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await checkpoint('setup-narrow-enlarged-text.png');
  await page.getByRole('radio', { name: 'Find help', exact: true }).focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('radio', { name: 'Offer help', exact: true })).toBeChecked();
  await expect(page.getByRole('button', { name: 'Save task', exact: true })).toBeEnabled();
  await checkpoint('setup-keyboard-task-draft.png');
});

test('setup loading and failed read require explicit canonical retry', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let release: () => void = () => {
    throw new Error('Missing controlled read gate');
  };
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/me/onboarding', async (route) => {
    await route.fulfill({ json: complete });
  });
  await page.route(
    '**/api/v1/me/onboarding',
    async (route) => {
      await gate;
      await route.fulfill({ status: 503, json: { code: 'unavailable' } });
    },
    { times: 1 },
  );
  await open(page);
  await expect(page.getByText('Checking your saved setup…', { exact: true })).toBeVisible();
  await checkpoint('setup-read-loading.png');
  release();
  await expect(page.getByRole('button', { name: 'Retry setup check', exact: true })).toBeVisible();
  await checkpoint('setup-read-failed.png');
  await page.getByRole('button', { name: 'Retry setup check', exact: true }).click();
  await expect(page.getByText('Your setup is saved.', { exact: true })).toBeVisible();
  await checkpoint('setup-read-recovered.png');
});

test('failed context issuance retries the exact metadata intent without auto registering', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await page.route('**/api/v1/me/onboarding', async (route) => {
    await route.fulfill({ json: ready });
  });
  let key: string | undefined;
  await page.route('**/api/v1/me/registration-context', async (route) => {
    expect(route.request().headers()['idempotency-key']).toBe(key);
    await route.fulfill({ json: context });
  });
  await page.route(
    '**/api/v1/me/registration-context',
    async (route) => {
      key = route.request().headers()['idempotency-key'];
      await route.abort('failed');
    },
    { times: 1 },
  );
  await open(page);
  await expect(
    page.getByRole('button', { name: 'Retry registration details', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeDisabled();
  await checkpoint('setup-context-unknown.png');
  await page.getByRole('button', { name: 'Retry registration details', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeEnabled();
  await checkpoint('setup-context-recovered.png');
});

test('expired context refresh is explicit and does not replay completion automatically', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await page.route('**/api/v1/me/onboarding', async (route) => {
    await route.fulfill({ json: ready });
  });
  await page.route('**/api/v1/me/registration-context', async (route) => {
    await route.fulfill({ json: context });
  });
  let writes = 0;
  await page.route('**/api/v1/me/registration', async (route) => {
    writes += 1;
    await route.fulfill({ status: 409, json: { code: 'registration_context_unavailable' } });
  });
  await open(page);
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Refresh registration details', exact: true }),
  ).toBeVisible();
  await checkpoint('setup-context-expired.png');
  await page.route('**/api/v1/me/registration-context', async (route) => {
    await route.fulfill({ json: { ...context, id: 'renewed-context' } });
  });
  await page.getByRole('button', { name: 'Refresh registration details', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeEnabled();
  expect(writes).toBe(1);
  await checkpoint('setup-context-renewed.png');
});

test('uncertain hide retries the same hidden body rather than turning into a restore', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let status: Api['schemas']['OnboardingStatusResponse'] = complete;
  let key: string | undefined;
  await page.route('**/api/v1/me/onboarding', async (route) => {
    await route.fulfill({ json: status });
  });
  await page.route('**/api/v1/me/visibility', async (route) => {
    expect(route.request().headers()['idempotency-key']).toBe(key);
    expect(route.request().postDataJSON()).toEqual({ hidden: true, expected_version: 1 });
    const next = { ...visibility, hidden: true, hidden_at: visibility.changed_at, version: 2 };
    status = {
      ...complete,
      visibility: next,
      capabilities: { ...complete.capabilities, can_restore_profile: true },
    };
    await route.fulfill({ json: next });
  });
  await page.route(
    '**/api/v1/me/visibility',
    async (route) => {
      key = route.request().headers()['idempotency-key'];
      await route.abort('failed');
    },
    { times: 1 },
  );
  await open(page);
  await performVisibilityAction(page, 'Hide my profile');
  await expect(page.getByRole('button', { name: 'Retry same change', exact: true })).toBeVisible();
  await checkpoint('setup-visibility-unknown.png');
  await page.getByRole('button', { name: 'Retry same change', exact: true }).click();
  await expect(
    page.getByText('Your profile is hidden from Discover.', { exact: true }),
  ).toBeVisible();
  await checkpoint('setup-visibility-replayed.png');
});

test('registration denial returns to actual sign-in without a context remount loop', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await page.route('**/api/v1/me/onboarding', async (route) => {
    await route.fulfill({ json: ready });
  });
  await page.route('**/api/v1/me/registration-context', async (route) => {
    await route.fulfill({ json: context });
  });
  let writes = 0;
  await page.route('**/api/v1/me/registration', async (route) => {
    writes += 1;
    await page.route('**/api/v1/me', async (read) => {
      await read.fulfill({ status: 401, json: { code: 'unauthenticated' } });
    });
    await route.fulfill({ status: 403, json: { code: 'request_context_invalid' } });
  });
  await open(page);
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Continue with Google', exact: true })).toBeVisible();
  expect(writes).toBe(1);
  await expect(page.getByRole('region', { name: 'Your study setup', exact: true })).toHaveCount(0);
  await checkpoint('setup-denied-session-recovery.png');
});

test('unknown first-task save retries the original body and key without erasing profile fields', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let saved: Api['schemas']['ProfileRevisionResponse'] = ownProfile.profile;
  let writes = 0;
  let firstBody: string | null = null;
  let key: string | undefined;
  await page.route('**/api/v1/me/onboarding', async (route) => {
    await route.fulfill({
      json: {
        ...ready,
        setup_requirements: ['photo'],
        capabilities: { ...ready.capabilities, can_complete_registration: false },
      },
    });
  });
  await page.route('**/api/v1/me/profile', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: { ...ownProfile, profile: saved } });
      return;
    }
    writes += 1;
    const body: unknown = route.request().postDataJSON();
    expect(body).toEqual({
      expected_version: 2,
      display_name: 'Maya Lee',
      about: 'Learning together',
      programme: 'Computing',
      year_label: 'Year 1',
      languages: ['en'],
      task: 'offer_help',
    });
    const requestKey = route.request().headers()['idempotency-key'];
    expect(requestKey).toMatch(/^[a-f0-9-]{36}$/);
    if (writes === 1) {
      firstBody = route.request().postData();
      key = requestKey;
      saved = { ...saved, task: 'offer_help', version: 3 };
      await route.abort('failed');
      return;
    }
    expect(route.request().postData()).toBe(firstBody);
    expect(route.request().headers()['idempotency-key']).toBe(key);
    await route.fulfill({ json: saved });
  });
  await open(page);
  await page.getByRole('radio', { name: 'Offer help', exact: true }).check();
  await page.getByRole('button', { name: 'Save task', exact: true }).click();
  await expect(
    page.getByText('We couldn’t confirm that save. Your choice is still here.', { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('radio', { name: 'Offer help', exact: true })).toBeChecked();
  expect(writes).toBe(1);
  await checkpoint('task-save-unknown-preserved.png');
  await page.getByRole('button', { name: 'Retry same task save', exact: true }).click();
  await expect(
    page.getByText('We couldn’t confirm that save. Your choice is still here.', { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole('radio', { name: 'Offer help', exact: true })).toBeChecked();
  await expect(page.getByRole('button', { name: 'Save task', exact: true })).toBeDisabled();
  expect(writes).toBe(2);
  await checkpoint('task-save-replayed-canonical.png');
});

test('first-task CAS conflict keeps the draft until explicit canonical reload', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let saved: Api['schemas']['ProfileRevisionResponse'] = ownProfile.profile;
  let writes = 0;
  await page.route('**/api/v1/me/onboarding', async (route) => {
    await route.fulfill({
      json: {
        ...ready,
        setup_requirements: ['photo'],
        capabilities: { ...ready.capabilities, can_complete_registration: false },
      },
    });
  });
  await page.route('**/api/v1/me/profile', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: { ...ownProfile, profile: saved } });
      return;
    }
    writes += 1;
    saved = { ...saved, version: 3, programme: 'Engineering' };
    await route.fulfill({
      status: 409,
      json: {
        code: 'profile_version_conflict',
        status: 409,
        title: 'Profile changed',
        type: 'about:blank',
        request_id: '00000000-0000-4000-8000-000000000001',
        trace_id: null,
        errors: [],
        recovery: {},
      } satisfies Api['schemas']['ProblemResponse'],
    });
  });
  await open(page);
  await page.getByRole('radio', { name: 'Offer help', exact: true }).check();
  await page.getByRole('button', { name: 'Save task', exact: true }).click();
  await expect(
    page.getByText(
      'We couldn’t save your first task. Reload the saved choice before editing again.',
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page.getByRole('radio', { name: 'Offer help', exact: true })).toBeChecked();
  await checkpoint('task-cas-conflict-draft.png');
  await page.getByRole('button', { name: 'Reload saved first task', exact: true }).click();
  await expect(page.getByRole('radio', { name: 'Find help', exact: true })).toBeChecked();
  await expect(page.getByRole('button', { name: 'Save task', exact: true })).toBeDisabled();
  expect(writes).toBe(1);
  await checkpoint('task-cas-explicit-reload.png');
});

test('changed readiness rejects completion without consuming the issued context or activating locally', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let status: Api['schemas']['OnboardingStatusResponse'] = ready;
  let contexts = 0;
  let completions = 0;
  await page.route('**/api/v1/me/onboarding', async (route) => {
    await route.fulfill({ json: status });
  });
  await page.route('**/api/v1/me/registration-context', async (route) => {
    contexts += 1;
    await route.fulfill({ json: context });
  });
  await page.route('**/api/v1/me/registration', async (route) => {
    completions += 1;
    const body: unknown = route.request().postDataJSON();
    expect(body).toEqual({ context_id: context.id });
    status = {
      ...ready,
      setup_requirements: ['photo'],
      capabilities: { ...ready.capabilities, can_complete_registration: false },
    };
    await route.fulfill({
      status: 409,
      json: {
        code: 'onboarding_incomplete',
        status: 409,
        title: 'Saved setup is incomplete',
        type: 'about:blank',
        request_id: '00000000-0000-4000-8000-000000000002',
        trace_id: null,
        errors: [{ path: ['onboarding', 'photo'], code: 'required' }],
        recovery: {},
      } satisfies Api['schemas']['ProblemResponse'],
    });
  });
  await open(page);
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(
    page.getByText('Add a photo and wait for it to be ready.', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('We couldn’t finish setup. Review your saved requirements and try again.', {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeDisabled();
  await expect(page).toHaveURL(/\/onboarding$/);
  expect(contexts).toBe(1);
  expect(completions).toBe(1);
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  await checkpoint('completion-readiness-changed.png');
});

test('registered incomplete setup uses its existing receipt without another registration notice', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: { ...verifiedActor, registration: receipt } });
  });
  await page.route('**/api/v1/me/onboarding', async (route) => {
    await route.fulfill({
      json: {
        ...ready,
        registered: true,
        capabilities: {
          ...ready.capabilities,
          can_complete_registration: false,
          can_complete_setup: true,
        },
      },
    });
  });
  let contexts = 0;
  let completions = 0;
  await page.route('**/api/v1/me/registration-context', async (route) => {
    contexts += 1;
    await route.fulfill({ json: context });
  });
  await page.route('**/api/v1/me/registration', async (route) => {
    completions += 1;
    await route.fulfill({ json: receipt });
  });
  await open(page);
  const region = page.getByRole('region', { name: 'Your study setup', exact: true });
  await expect(region.getByRole('button', { name: 'Finish setup', exact: true })).toBeEnabled();
  await expect(region.getByText(context.notice_text, { exact: false })).toHaveCount(0);
  await expect(region.getByRole('link', { name: 'Terms of Use', exact: true })).toHaveCount(0);
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  expect(contexts).toBe(0);
  expect(completions).toBe(0);
  await checkpoint('registered-existing-receipt-review.png');
});

const photoRestricted = {
  ...complete,
  capabilities: { ...complete.capabilities, can_discover: false, can_make_new_contacts: false },
} as const satisfies Api['schemas']['OnboardingStatusResponse'];
const reviewVisibilityCases = [
  {
    name: 'not-hidden',
    status: photoRestricted,
    message: 'Your profile can’t appear in Discover right now.',
  },
  {
    name: 'hidden',
    status: {
      ...photoRestricted,
      visibility: { ...visibility, hidden: true, hidden_at: '2026-11-07T12:00:00Z' },
      restore_requirements: ['photo_review'],
      capabilities: {
        ...photoRestricted.capabilities,
        can_hide_profile: false,
        can_restore_profile: false,
      },
    },
    message: 'A replacement photo reviewed by the team',
  },
] as const;
for (const scenario of reviewVisibilityCases) {
  test(`actual photo-review visibility restriction: ${scenario.name}`, async ({
    page,
    checkpoint,
  }: Context) => {
    await page.route('**/api/v1/me', (route) =>
      route.fulfill({
        json: {
          ...verifiedActor,
          registration: receipt,
          capabilities: { ...verifiedActor.capabilities, can_use_student_features: true },
        },
      }),
    );
    await page.route('**/api/v1/me/onboarding', (route) =>
      route.fulfill({ json: scenario.status }),
    );
    await page.route('**/api/v1/events', (route) =>
      route.fulfill({ contentType: 'text/event-stream', body: ': heartbeat\n\n' }),
    );
    await page.goto('/profile/visibility');
    const panel = page.getByRole('region', { name: 'Your profile in Discover', exact: true });
    await expect(panel.getByText(scenario.message, { exact: true })).toBeVisible();
    await expect(
      panel.getByText('Your profile can appear in Discover.', { exact: true }),
    ).toHaveCount(0);
    await expect(panel.getByRole('button', { name: 'Show my profile', exact: true })).toHaveCount(
      0,
    );
    await expect(
      panel.getByRole('link', { name: 'Review profile and study setup', exact: true }),
    ).toHaveAttribute('href', '/profile');
    await checkpoint(`visibility-${scenario.name}-human-review.png`);
  });
}

test('P03 consequences and native confirmation remain deliberate at320 text200', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let writes = 0;
  await page.route('**/api/v1/me/onboarding', (route) => route.fulfill({ json: complete }));
  await page.route('**/api/v1/me/visibility', (route) => {
    writes += 1;
    return route.fulfill({ json: { ...visibility, hidden: true, version: 2 } });
  });
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto('/profile/visibility');
  await expect(
    page.getByRole('heading', { name: 'Profile visibility', exact: true }),
  ).toBeVisible();
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  const effects = page.getByRole('list', { name: 'While your profile is hidden', exact: true });
  await expect(effects.getByRole('listitem')).toHaveCount(4);
  await expect(effects).toContainText('Pending requests close and won’t reopen');
  await expect(effects).toContainText('Your existing chats keep working');
  expect(writes).toBe(0);
  await assertNaturalWordWrapping(effects);
  await assertFullTextFits(page.getByRole('button', { name: 'Hide my profile', exact: true }));
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await checkpoint('profile-visibility-effects-narrow.png');
  const hide = page.getByRole('button', { name: 'Hide my profile', exact: true });
  await hide.focus();
  await expect(hide).toBeFocused();
  await expect(hide).toBeInViewport({ ratio: 1 });
  await checkpoint('profile-visibility-action-narrow.png', { fullPage: false });
  await hide.click();
  const dialog = page.getByRole('dialog', { name: 'Hide your profile?', exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('Pending requests will close and won’t reopen.');
  expect(writes).toBe(0);
  const title = dialog.getByRole('heading', { name: 'Hide your profile?', exact: true });
  const cancel = dialog.getByRole('button', { name: 'Cancel', exact: true });
  const confirm = dialog.getByRole('button', { name: 'Hide profile', exact: true });
  await expect(title).toBeFocused();
  await assertNaturalWordWrapping(title);
  await expect(title).toBeInViewport({ ratio: 1 });
  const titleTop = await title.evaluate(
    (element: Readonly<HTMLElement>) => element.getBoundingClientRect().top,
  );
  const closeBottom = await dialog
    .getByRole('button', { name: 'Close', exact: true })
    .evaluate((element: Readonly<HTMLElement>) => element.getBoundingClientRect().bottom);
  expect(titleTop).toBeGreaterThanOrEqual(closeBottom);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await checkpoint('profile-hide-confirmation-narrow.png', { fullPage: false });
  await expect(title).toBeInViewport({ ratio: 1 });
  await page.keyboard.press('Tab');
  await expect(cancel).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(confirm).toBeFocused();
  await expect(cancel).toBeInViewport({ ratio: 1 });
  await expect(confirm).toBeInViewport({ ratio: 1 });
  await assertFullTextFits(cancel);
  await assertFullTextFits(confirm);
  await checkpoint('profile-hide-actions-narrow.png', { fullPage: false });
  await expect(cancel).toBeInViewport({ ratio: 1 });
  await expect(confirm).toBeInViewport({ ratio: 1 });
  await test.info().attach('profile-hide-confirmation-full-document-raw.png', {
    body: await page.screenshot({ fullPage: true, animations: 'disabled' }),
    contentType: 'image/png',
  });
  await cancel.click();
  await expect(dialog).toBeHidden();
  expect(writes).toBe(0);
  await expect(
    page.getByText('Your profile can appear in Discover.', { exact: true }),
  ).toBeVisible();
  await checkpoint('profile-hide-cancelled-narrow.png');
});
