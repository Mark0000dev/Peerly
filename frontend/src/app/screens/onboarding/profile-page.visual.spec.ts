import {
  assertNaturalWordWrapping,
  assertFullTextFits,
  assertTextPaintNotClipped,
} from '../../../../testing/readable-text';
import { noPhotoReview } from './profile/photo-review.fixtures';
import type { Page } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { verifiedActor } from './onboarding.fixtures';
import { ownProfile, profileReference } from './profile/profile.fixtures';
import type { Api } from '../../api.generated';
import { ownGoal, goal } from './study/goal.fixtures';
import { ownHelp } from './study/help.fixtures';
import { complete, receipt } from './setup/setup.fixtures';

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

async function overview(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: verifiedActor });
  });
  await page.route('**/api/v1/me/profile', async (route) => {
    await route.fulfill({ json: ownProfile });
  });
  await page.route('**/api/v1/me/goal', async (route) => {
    await route.fulfill({ json: ownGoal });
  });
  await page.route('**/api/v1/me/help-subjects', async (route) => {
    await route.fulfill({ json: ownHelp });
  });
  await page.route('**/api/v1/me/onboarding', async (route) => {
    await route.fulfill({ json: complete });
  });
}

test('P01 overview is actual profile/goal/help data and real settings navigation', async ({
  page,
  checkpoint,
}: Context) => {
  await overview(page);
  await page.goto('/profile');
  await expect(page.getByRole('heading', { name: ownProfile.profile.display_name })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Your study goal' })).toContainText(goal.topic);
  await expect(page.getByRole('region', { name: 'You can help with' })).toContainText(
    ownHelp.selection.subjects[0].label,
  );
  await expect(page.getByRole('link', { name: 'Notifications', exact: true })).toHaveAttribute(
    'href',
    '/profile/notifications',
  );
  await expect(page.getByRole('link', { name: 'Blocked people', exact: true })).toHaveAttribute(
    'href',
    '/profile/blocks',
  );
  const navigationViewport = await page
    .getByRole('navigation', { name: 'Student navigation', exact: true })
    .evaluate((element: Readonly<HTMLElement>) => {
      const box = element.getBoundingClientRect();
      return {
        top: box.top,
        bottom: box.bottom,
        width: box.width,
        height: box.height,
        viewportHeight: innerHeight,
        viewportWidth: innerWidth,
        scrollY,
        position: getComputedStyle(element).position,
      };
    });
  await test.info().attach('student-navigation-viewport.json', {
    body: JSON.stringify(navigationViewport),
    contentType: 'application/json',
  });
  expect(navigationViewport.top).toBeGreaterThanOrEqual(0);
  expect(navigationViewport.bottom).toBeLessThanOrEqual(navigationViewport.viewportHeight);
  await expect(page.getByRole('link', { name: 'Profile', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await expect(page.getByText('Visible in Discover', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Profile visibility', exact: true })).toHaveAttribute(
    'href',
    '/profile/visibility',
  );
  await checkpoint('own-profile-overview-viewport.png', { fullPage: false });
  await checkpoint('own-profile-overview.png');
});

test('P01 compact original overview retains actual completion and capability-owned feedback', async ({
  page,
  checkpoint,
}: Context) => {
  await overview(page);
  await page.route('**/api/v1/me', async (route) =>
    route.fulfill({
      json: {
        ...verifiedActor,
        registration: receipt,
        capabilities: { ...verifiedActor.capabilities, can_use_student_features: true },
      } satisfies Api['schemas']['IdentityResponse'],
    }),
  );
  await page.route('**/api/v1/me/goal', async (route) =>
    route.fulfill({
      json: {
        goal: { ...ownGoal.goal, shared_learning: true },
      } satisfies Api['schemas']['OwnGoalResponse'],
    }),
  );
  await page.route('**/api/v1/me/help-subjects', async (route) =>
    route.fulfill({
      json: {
        selection: {
          ...ownHelp.selection,
          subjects: [
            ...ownHelp.selection.subjects,
            {
              subject_id: '00000000-0000-0000-0000-000000000011',
              label: 'Statistics',
              topic_note: null,
            },
          ],
        },
      } satisfies Api['schemas']['OwnHelpResponse'],
    }),
  );
  await page.route('**/api/v1/me/feedback-summary', async (route) =>
    route.fulfill({
      json: {
        state: 'building',
        responses: 0,
        publicly_visible: true,
      } satisfies Api['schemas']['BuildingFeedbackSummaryResponse'],
    }),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/profile');
  await expect(page.getByRole('heading', { name: ownProfile.profile.display_name })).toBeVisible();
  const goalRegion = page.getByRole('region', { name: 'Your study goal', exact: true });
  await expect(goalRegion.locator('[tuiSubtitle]')).toContainText('Your active goal');
  await expect(goalRegion.locator('[tuiSubtitle]')).toContainText('Open to studying together');
  await expect(
    goalRegion.getByRole('button', { name: 'Mark goal done', exact: true }),
  ).toBeEnabled();
  const helpRegion = page.getByRole('region', { name: 'You can help with', exact: true });
  await expect(helpRegion.locator('h2')).toContainText('Calculus');
  await expect(helpRegion.locator('h2')).toContainText('Limits');
  await expect(helpRegion.locator('h2')).toContainText('Statistics');
  await expect(helpRegion.locator(':scope > p')).toHaveCount(0);
  await expect(page.locator('.verified')).toHaveAttribute('data-appearance', 'sp-subject');
  await checkpoint('own-profile-compact-active-original.png', { fullPage: false });
  const feedback = page.getByRole('region', { name: 'Your peer feedback', exact: true });
  await feedback.scrollIntoViewIfNeeded();
  await expect(feedback).toContainText('0 partners');
  await expect(page.getByRole('link', { name: 'Delete account', exact: true })).toHaveAttribute(
    'href',
    '/account/delete',
  );
  await checkpoint('own-profile-compact-feedback-original.png', { fullPage: false });
});

test('P01 320px text200 keeps profile identity and editor heading readable', async ({
  page,
  checkpoint,
}: Context) => {
  await overview(page);
  await page.route('**/api/v1/profile-reference-data', (route) =>
    route.fulfill({ json: profileReference }),
  );
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto('/profile');
  const name = page.getByRole('heading', { name: ownProfile.profile.display_name });
  await expect(name).toBeVisible();
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  await assertNaturalWordWrapping(page.getByRole('heading', { name: 'Profile', exact: true }));
  await assertNaturalWordWrapping(name);
  await assertNaturalWordWrapping(page.getByText('APU email confirmed', { exact: true }));
  await assertFullTextFits(page.getByRole('link', { name: 'Edit profile', exact: true }));
  for (const label of ['Mark goal done']) {
    const action = page.getByRole('button', { name: label, exact: true });
    await assertNaturalWordWrapping(action);
    await assertFullTextFits(action);
  }
  await assertNaturalWordWrapping(
    page.getByRole('region', { name: 'You can help with', exact: true }).locator('h2'),
  );
  await assertTextPaintNotClipped(page.getByText(goal.context, { exact: true }));

  const settings = page.getByRole('navigation', { name: 'Profile and settings', exact: true });
  const notificationPaint = await settings
    .getByRole('link', { name: 'Notifications', exact: true })
    .evaluate((element: Readonly<HTMLElement>) => {
      const range = document.createRange();
      range.selectNodeContents(element);
      const style = getComputedStyle(element);
      const bounds = element.getBoundingClientRect();
      return {
        clientHeight: element.clientHeight,
        scrollHeight: element.scrollHeight,
        box: { left: bounds.left, right: bounds.right, top: bounds.top, bottom: bounds.bottom },
        ranges: Array.from(range.getClientRects()).map((rect: Readonly<DOMRect>) => ({
          left: rect.left,
          right: rect.right,
          top: rect.top,
          bottom: rect.bottom,
        })),
        overflowX: style.overflowX,
        overflowY: style.overflowY,
        fontSize: style.fontSize,
        lineHeight: style.lineHeight,
      };
    });
  await test.info().attach('native-notification-row-paint.json', {
    body: JSON.stringify(notificationPaint),
    contentType: 'application/json',
  });
  for (const label of [
    'Notifications',
    'Profile visibility',
    'Blocked people',
    'Help and support',
    'Terms of Use',
    'Privacy Policy',
    'Delete account',
  ]) {
    const link = settings.getByRole('link', { name: label, exact: true });
    await assertNaturalWordWrapping(link);
    await assertTextPaintNotClipped(link);
  }

  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const navigation = page.getByRole('navigation', { name: 'Student navigation', exact: true });
  const initialNavigation = await navigation.evaluate((element: Readonly<HTMLElement>) => {
    const box = element.getBoundingClientRect();
    return { top: box.top, bottom: box.bottom, viewportHeight: innerHeight };
  });
  expect(initialNavigation.top).toBeGreaterThanOrEqual(0);
  expect(initialNavigation.bottom).toBeLessThanOrEqual(initialNavigation.viewportHeight);
  await settings.getByRole('link', { name: 'Notifications', exact: true }).focus();
  for (const target of [
    { role: 'link', name: 'Profile visibility' },
    { role: 'link', name: 'Blocked people' },
    { role: 'link', name: 'Help and support' },
    { role: 'link', name: 'Terms of Use' },
    { role: 'link', name: 'Privacy Policy' },
    { role: 'button', name: 'Sign out' },
    { role: 'link', name: 'Delete account' },
  ] as const) {
    await page.keyboard.press('Tab');
    const control = settings.getByRole(target.role, { name: target.name, exact: true });
    await expect(control).toBeFocused();
    const bottom = await control.evaluate(
      (element: Readonly<HTMLElement>) => element.getBoundingClientRect().bottom,
    );
    const navigationTop = await navigation.evaluate(
      (element: Readonly<HTMLElement>) => element.getBoundingClientRect().top,
    );
    expect(bottom).toBeLessThanOrEqual(navigationTop);
  }
  const deleteLink = settings.getByRole('link', { name: 'Delete account', exact: true });
  await deleteLink.focus();
  await expect(deleteLink).toBeFocused();
  const focusedLink = await deleteLink.evaluate((element: Readonly<HTMLElement>) => {
    const box = element.getBoundingClientRect();
    return { top: box.top, bottom: box.bottom };
  });
  const scrolledNavigationTop = await navigation.evaluate(
    (element: Readonly<HTMLElement>) => element.getBoundingClientRect().top,
  );
  expect(focusedLink.top).toBeGreaterThanOrEqual(0);
  expect(focusedLink.bottom).toBeLessThanOrEqual(scrolledNavigationTop);
  await checkpoint('own-profile-settings-narrow-text200.png', { fullPage: false });
  await page.getByRole('heading', { name: 'Profile', exact: true }).scrollIntoViewIfNeeded();
  await checkpoint('own-profile-narrow-text200-viewport.png', { fullPage: false });
  await checkpoint('own-profile-narrow-text200.png');
  await page.getByRole('link', { name: 'Edit profile', exact: true }).click();
  const title = page.getByRole('heading', { name: 'Edit profile', exact: true });
  await expect(title).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Display name', exact: true })).toHaveValue(
    ownProfile.profile.display_name,
  );
  await assertNaturalWordWrapping(title);
  await assertFullTextFits(page.getByText('English', { exact: true }));
  await assertNaturalWordWrapping(page.getByText('English', { exact: true }));
  const back = page.getByRole('link', { name: 'Back to profile', exact: true });
  await back.focus();
  await expect(back).toBeFocused();
  await expect(back).toHaveAttribute('href', '/profile');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await checkpoint('own-profile-editor-narrow-text200.png');
  const save = page.getByRole('button', { name: 'Save profile', exact: true });
  await save.focus();
  await expect(save).toBeFocused();
  await expect(save).toBeInViewport({ ratio: 1 });
  await expect(page.getByText('English', { exact: true })).toBeInViewport({ ratio: 1 });
  await checkpoint('own-profile-editor-languages-narrow.png', { fullPage: false });
});

test('P01 visibility summary distinguishes hidden, freshness pause and unavailable without changing exposure', async ({
  page,
  checkpoint,
}: Context) => {
  await overview(page);
  let status: Api['schemas']['OnboardingStatusResponse'] = complete;
  let writes = 0;
  page.on('request', (request) => {
    if (request.method() === 'PUT' && new URL(request.url()).pathname === '/api/v1/me/visibility')
      writes += 1;
  });
  await page.route('**/api/v1/me/onboarding', (route) => route.fulfill({ json: status }));
  for (const state of [
    {
      kind: 'hidden',
      label: 'Hidden in Discover',
      action: 'Profile visibility',
      hiddenAt: '2026-11-07T12:00:00Z',
    },
    {
      kind: 'paused',
      label: 'Paused in Discover',
      action: 'Show my profile again',
      hiddenAt: null,
    },
    {
      kind: 'unavailable',
      label: 'Not appearing in Discover',
      action: 'Profile visibility',
      hiddenAt: null,
    },
  ] as const) {
    status = {
      ...complete,
      visibility: {
        ...complete.visibility,
        hidden: state.kind === 'hidden',
        hidden_at: state.hiddenAt,
      },
      discovery_exposure: {
        ...complete.discovery_exposure,
        paused: state.kind === 'paused',
        can_confirm: state.kind === 'paused',
      },
      capabilities: {
        ...complete.capabilities,
        can_discover: state.kind === 'paused',
        can_make_new_contacts: state.kind === 'paused',
        can_hide_profile: state.kind === 'paused',
        can_restore_profile: state.kind === 'hidden',
      },
    };
    await page.goto('/profile');
    await expect(page.getByText(state.label, { exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: state.action, exact: true })).toHaveAttribute(
      'href',
      '/profile/visibility',
    );
    await expect(
      page.getByRole('button', { name: 'Show my profile again', exact: true }),
    ).toHaveCount(0);
    expect(writes).toBe(0);
    await checkpoint(`own-profile-discovery-${state.kind}.png`);
  }
});

test('P01 helper-only and goal-only context retain real editor entrypoints', async ({
  page,
  checkpoint,
}: Context) => {
  await overview(page);
  const emptyGoal = { goal: null } as const satisfies Api['schemas']['OwnGoalResponse'];
  await page.route('**/api/v1/me/goal', (route) => route.fulfill({ json: emptyGoal }));
  await page.goto('/profile');
  await expect(page.getByText('No active study goal yet.', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Set a study goal', exact: true })).toHaveAttribute(
    'href',
    '/profile/goal',
  );
  await expect(page.getByRole('link', { name: 'Edit help areas', exact: true })).toHaveAttribute(
    'href',
    '/profile/help',
  );
  await checkpoint('own-profile-helper-only.png');
  const emptyHelp = {
    selection: { ...ownHelp.selection, subjects: [] },
  } as const satisfies Api['schemas']['OwnHelpResponse'];
  await page.route('**/api/v1/me/goal', (route) => route.fulfill({ json: ownGoal }));
  await page.route('**/api/v1/me/help-subjects', (route) => route.fulfill({ json: emptyHelp }));
  await page.reload();
  await expect(page.getByText('No help areas selected yet.', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Choose help areas', exact: true })).toHaveAttribute(
    'href',
    '/profile/help',
  );
  await expect(page.getByRole('link', { name: 'Edit profile', exact: true })).toHaveAttribute(
    'href',
    '/profile/edit',
  );
  await checkpoint('own-profile-goal-only.png');
});

test('P01 failed reads do not fabricate an empty profile or goal', async ({
  page,
  checkpoint,
}: Context) => {
  await overview(page);
  await page.route('**/api/v1/me/profile', async (route) => {
    await route.fulfill({ status: 503, json: { code: 'temporarily_unavailable' } });
  });
  await page.goto('/profile');
  await expect(page.getByRole('alert')).toContainText(
    'Some profile information could not be loaded',
  );
  await expect(page.getByRole('button', { name: 'Retry profile information' })).toBeEnabled();
  await checkpoint('own-profile-read-failed.png');
});

test('P01 goal completion requires confirmation and uncertain recovery preserves the command identity', async ({
  page,
  checkpoint,
}: Context) => {
  await overview(page);
  let received: readonly Readonly<{ readonly key: string | undefined; readonly body: unknown }>[] =
    [];
  let committed = false;
  await page.route('**/api/v1/me/goal', async (route) => {
    await route.fulfill({ json: committed ? { goal: null } : ownGoal });
  });
  await page.route('**/api/v1/me/goal/complete', async (route) => {
    received = [
      ...received,
      { key: route.request().headers()['idempotency-key'], body: route.request().postDataJSON() },
    ];
    expect(route.request().headers()['x-csrf-token']).toBe(verifiedActor.csrf_token);
    if (received.length === 1) {
      await route.abort('failed');
      return;
    }
    committed = true;
    await route.fulfill({ json: { ...goal, version: 3, completed_at: '2026-11-09T08:00:00Z' } });
  });
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Mark goal done', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  expect(received).toHaveLength(0);
  await checkpoint('own-goal-complete-confirmation.png');
  await page.getByRole('button', { name: 'Mark done', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry same completion' })).toBeVisible();
  await checkpoint('own-goal-completion-unknown.png');
  await page.getByRole('button', { name: 'Retry same completion' }).click();
  await expect(page.getByText('No active study goal yet.', { exact: true })).toBeVisible();
  expect(received).toHaveLength(2);
  expect(received[1]).toEqual(received[0]);
  expect(received[0]?.body).toEqual({ goal_id: goal.id, expected_version: goal.version });
  await checkpoint('own-goal-completed.png');
});

const blockedPerson = {
  block: {
    person_id: '00000000-0000-4000-8000-000000000055',
    blocked: true,
    version: 2,
    changed_at: '2026-11-07T12:00:00Z',
  },
  display_name: 'Maya Tan',
  deleted: false,
} as const;

test('P04 owner block list and uncertain explicit unblock preserve CAS and idempotency', async ({
  page,
  checkpoint,
}: Context) => {
  await overview(page);
  let keys: readonly string[] = [];
  let blocked = true;
  await page.route('**/api/v1/me/blocks', async (route) => {
    await route.fulfill({ json: { people: blocked ? [blockedPerson] : [], next_cursor: null } });
  });
  await page.route(`**/api/v1/me/blocks/${blockedPerson.block.person_id}`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({ blocked: false, expected_version: 2 });
    expect(route.request().headers()['x-csrf-token']).toBe(verifiedActor.csrf_token);
    const key = route.request().headers()['idempotency-key'];
    expect(typeof key).toBe('string');
    if (key !== undefined) keys = [...keys, key];
    if (keys.length === 1) {
      await route.abort('failed');
      return;
    }
    blocked = false;
    await route.fulfill({ json: { ...blockedPerson.block, blocked: false, version: 3 } });
  });
  await page.goto('/profile/blocks');
  await expect(page.getByText(blockedPerson.display_name, { exact: false })).toBeVisible();
  await checkpoint('blocked-people-list.png');
  await page.getByRole('button', { name: 'Unblock', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry same unblock' })).toBeVisible();
  await checkpoint('unblock-unknown.png');
  await page.getByRole('button', { name: 'Retry same unblock' }).click();
  await expect(page.getByText('No blocked people on this page.')).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  await checkpoint('blocked-people-empty.png');
});

test('P04 deleted names, pagination and malformed response never invent people', async ({
  page,
  checkpoint,
}: Context) => {
  await overview(page);
  await page.route('**/api/v1/me/blocks**', async (route) => {
    const cursor = new URL(route.request().url()).searchParams.get('cursor');
    await route.fulfill({
      json:
        cursor === null
          ? {
              people: [{ ...blockedPerson, deleted: true, display_name: null }],
              next_cursor: 'next-page',
            }
          : { people: [{ block: {} }], next_cursor: null },
    });
  });
  await page.goto('/profile/blocks');
  await expect(page.getByText('Deleted account', { exact: false })).toBeVisible();
  await checkpoint('blocked-deleted-person.png');
  await page.getByRole('button', { name: 'Next page' }).click();
  await expect(page.getByRole('alert')).toContainText('Blocked people could not be loaded');
  await checkpoint('blocked-list-invalid-response.png');
});

const avatarProbePath = '/api/v1/media/11111111-1111-4111-8111-111111111111/display';
const avatarProfile = {
  ...ownProfile,
  photo: {
    upload_id: '11111111-1111-4111-8111-111111111111',
    version: 1,
    display_url: avatarProbePath,
  },
} as const satisfies Api['schemas']['OwnProfileResponse'];

async function avatarProbeJpeg(page: Readonly<Page>) {
  const probe = await page.evaluate(async () => {
    const canvas = new OffscreenCanvas(240, 320);
    const context = canvas.getContext('2d');
    if (context === null) throw new Error('Missing native JPEG fixture renderer');
    const pixels = Uint8ClampedArray.from({ length: 240 * 320 * 4 }, (_, index) => {
      const y = Math.floor(index / 4 / 240);
      const color = y < 80 ? [220, 20, 60, 255] : y < 240 ? [30, 160, 90, 255] : [40, 90, 220, 255];
      return color[index % 4] ?? 0;
    });
    context.putImageData(new ImageData(pixels, 240, 320), 0, 0);
    const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 1 });
    if (blob.type !== 'image/jpeg') throw new Error('Expected actual JPEG probe');
    const bitmap = await createImageBitmap(blob);
    // Native cover for the actual3:4 portrait case: centered square viewport,
    // without distorting or rewriting the supplied image bytes.
    context.drawImage(bitmap, 0, (320 - 240) / 2, 240, 240, 0, 0, 240, 240);
    bitmap.close();
    return {
      bytes: Array.from(new Uint8Array(await blob.arrayBuffer())),
      expected: [48, 120, 192].map((y) => Array.from(context.getImageData(120, y, 1, 1).data)),
    };
  });
  return { bytes: Buffer.from(probe.bytes), expected: probe.expected };
}

async function assertAvatarPaint(
  page: Readonly<Page>,
  expected: readonly (readonly number[])[],
): Promise<void> {
  const image = page.getByRole('img', { name: 'Your current profile photo', exact: true });
  await expect
    .poll(() =>
      image.evaluate(
        (element: Readonly<HTMLImageElement>) =>
          element.complete && element.naturalWidth === 240 && element.naturalHeight === 320,
      ),
    )
    .toBe(true);
  await image.scrollIntoViewIfNeeded();
  const box = await image.boundingBox();
  if (box === null) throw new Error('Missing actual avatar bounds');
  const frame = await page.screenshot({ fullPage: false, animations: 'disabled' });
  // Decode the WHOLE actual viewport; inspect three interior color bands, not
  // image source bytes. A blank/covered circle cannot pass by merely loading src.
  const paint = await page.evaluate(
    async ({
      encoded,
      bounds,
    }: Readonly<{
      readonly encoded: string;
      readonly bounds: Readonly<{
        readonly x: number;
        readonly y: number;
        readonly width: number;
        readonly height: number;
      }>;
    }>) => {
      const bytes = Uint8Array.from(atob(encoded), (letter) => letter.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
      const context = canvas.getContext('2d');
      if (context === null) throw new Error('Missing native viewport pixel decoder');
      context.drawImage(bitmap, 0, 0);
      bitmap.close();
      return [0.2, 0.5, 0.8].map((fraction) =>
        Array.from(
          context.getImageData(
            Math.floor(bounds.x + bounds.width / 2),
            Math.floor(bounds.y + bounds.height * fraction),
            1,
            1,
          ).data,
        ),
      );
    },
    { encoded: frame.toString('base64'), bounds: box },
  );
  expect(paint).toEqual(expected);
}

for (const mode of ['overview', 'editor'] as const) {
  test(`P01 portrait photo preserves native cover proportions in ${mode}`, async ({
    page,
    checkpoint,
  }: Context) => {
    await overview(page);
    await page.route('**/api/v1/me/profile', (route) => route.fulfill({ json: avatarProfile }));
    await page.route('**/api/v1/profile-reference-data', (route) =>
      route.fulfill({ json: profileReference }),
    );
    const probe = await avatarProbeJpeg(page);
    await page.route(`**${avatarProbePath}`, (route) =>
      route.fulfill({
        contentType: 'image/jpeg',
        body: probe.bytes,
      }),
    );
    await page.goto(mode === 'overview' ? '/profile' : '/profile/edit');
    await expect(
      page.getByRole('img', { name: 'Your current profile photo', exact: true }),
    ).toBeVisible();
    await assertAvatarPaint(page, probe.expected);
    await checkpoint(`own-profile-avatar-${mode}-portrait-cover.png`);
  });
}
