import { noPhotoReview } from './profile/photo-review.fixtures';
import type { Page } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { verifiedActor } from './onboarding.fixtures';
import { ownProfile } from './profile/profile.fixtures';
import { ownGoal, goal } from './study/goal.fixtures';
import { ownHelp } from './study/help.fixtures';
import { complete } from './setup/setup.fixtures';

interface Context {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
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
  await checkpoint('own-profile-overview.png');
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
