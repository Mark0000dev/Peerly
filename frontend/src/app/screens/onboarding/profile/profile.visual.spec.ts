import type { Page, Route } from '@playwright/test';
import { test, expect } from '../../../../../testing/visual';
import { ownProfile, revision } from './profile.fixtures';
import { verifiedActor } from '../onboarding.fixtures';
import type { Api } from '../../../api.generated';

interface Context {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}
async function identity(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: verifiedActor });
  });
}
async function open(page: Readonly<Page>): Promise<void> {
  await page.goto('/onboarding');
  await page.getByRole('button', { name: 'Your profile', exact: true }).click();
}

function assertSave(route: Readonly<Route>): void {
  expect(route.request().headers()['x-csrf-token']).toBe(verifiedActor.csrf_token);
  expect(route.request().headers()['idempotency-key']).toMatch(/^[a-f0-9-]{36}$/);
  expect(route.request().postDataJSON()).toEqual({
    about: revision.about,
    programme: revision.programme,
    year_label: revision.year_label,
    languages: revision.languages,
    task: revision.task,
    display_name: 'Maya Tan',
    expected_version: 2,
  });
}

test('profile draft loading and explicit validated save preserve server revision', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let release: () => void = () => {
    throw new Error('Uninitialised response gate');
  };
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  let saved = false;
  await page.route('**/api/v1/me/profile', async (route) => {
    if (route.request().method() === 'PUT') {
      assertSave(route);
      saved = true;
      await route.fulfill({ json: { ...revision, version: 3, display_name: 'Maya Tan' } });
      return;
    }
    await pending;
    await route.fulfill({
      json: saved
        ? { profile: { ...revision, version: 3, display_name: 'Maya Tan' }, photo: null }
        : ownProfile,
    });
  });
  await open(page);
  await expect(page.getByText('Loading your profile…', { exact: true })).toBeVisible();
  await checkpoint('profile-loading.png');
  release();
  await expect(page.getByRole('textbox', { name: 'Display name' })).toHaveValue(
    revision.display_name,
  );
  await page.getByRole('textbox', { name: 'Display name' }).fill('Maya Tan');
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  await expect(page.getByText('Profile saved.', { exact: true })).toBeVisible();
  await checkpoint('profile-saved.png');
  await page.reload();
  await page.getByRole('button', { name: 'Your profile', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Display name' })).toHaveValue('Maya Tan');
  await checkpoint('profile-reloaded.png');
});

for (const { outcome, action } of [
  { outcome: 'uncertain', action: 'Retry same save' },
  { outcome: 'conflict', action: 'Reload saved profile' },
] as const) {
  test(`profile ${outcome} keeps draft and requires safe explicit recovery`, async ({
    page,
    checkpoint,
  }: Context) => {
    await identity(page);
    let writes = 0;
    let firstKey: string | undefined;
    let saved = false;
    await page.route('**/api/v1/me/profile', async (route: Route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          json: saved
            ? { profile: { ...revision, version: 3, display_name: 'Resolved name' }, photo: null }
            : ownProfile,
        });
        return;
      }
      writes += 1;
      const key = route.request().headers()['idempotency-key'];
      if (writes === 1) {
        firstKey = key;
        if (outcome === 'uncertain') await route.abort('failed');
        else
          await route.fulfill({
            status: 409,
            json: { code: 'profile_version_conflict', title: 'PRIVATE' },
          });
        return;
      }
      expect(key).toBe(firstKey);
      saved = true;
      await route.fulfill({ json: { ...revision, version: 3, display_name: 'Resolved name' } });
    });
    await open(page);
    await page.getByRole('textbox', { name: 'Display name' }).fill('My private draft');
    await page.getByRole('button', { name: 'Save profile', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText(
      outcome === 'uncertain' ? 'couldn’t confirm' : 'changed elsewhere',
    );
    await expect(page.getByRole('textbox', { name: 'Display name' })).toHaveValue(
      'My private draft',
    );
    await expect(page.getByRole('textbox', { name: 'Display name' })).not.toBeEditable();
    expect(writes).toBe(1);
    await checkpoint(`profile-${outcome}.png`);
    saved = true;
    await page.getByRole('button', { name: action }).click();
    await expect(page.getByRole('textbox', { name: 'Display name' })).toHaveValue('Resolved name');
    await expect(page.getByRole('textbox', { name: 'Display name' })).toBeEditable();
    await checkpoint(`profile-${outcome}-resolved.png`);
  });
}

for (const photo of [
  null,
  {
    upload_id: '00000000-0000-0000-0000-000000000003',
    version: 1,
    display_url: '/api/v1/media/00000000-0000-0000-0000-000000000003/display',
  },
] as const satisfies readonly (Api['schemas']['CurrentPhotoResponse'] | null)[]) {
  const action = photo === null ? 'Add photo' : 'Change photo';

  test(`invalid name makes no write and preserves keyboard focus at320px with ${photo === null ? 'no' : 'current'} photo`, async ({
    page,
    checkpoint,
  }: Context) => {
    await identity(page);
    let writes = 0;
    await page.route('**/api/v1/me/profile', async (route) => {
      if (route.request().method() === 'PUT') writes += 1;
      await route.fulfill({ json: { profile: null, photo } });
    });
    await page.setViewportSize({ width: 320, height: 740 });
    await open(page);
    const input = page.getByRole('textbox', { name: 'Display name' });
    await input.fill('M');
    await input.press('Enter');
    await expect(page.getByRole('alert')).toHaveText(
      'Enter a display name between 2 and 50 characters.',
    );
    await expect(input).toBeFocused();
    expect(writes).toBe(0);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await checkpoint(
      photo === null
        ? 'profile-name-invalid-keyboard.png'
        : 'profile-current-photo-invalid-keyboard.png',
    );
    await page.addStyleTag({ content: ':root { font-size: 200%; }' });
    await expect(input).toHaveValue('M');
    const photoButton = page.getByRole('button', { name: action, exact: true });
    await expect(photoButton).toBeVisible();
    expect(
      await photoButton.evaluate((button: Readonly<HTMLElement | SVGElement>, caption: string) => {
        const text = Array.from(button.childNodes).find(
          (node: Readonly<ChildNode>) => node.textContent?.trim() === caption,
        );
        if (text === undefined) return false;
        const range = document.createRange();
        range.selectNodeContents(text);
        const content = range.getBoundingClientRect();
        const bounds = button.getBoundingClientRect();
        return content.left >= bounds.left && content.right <= bounds.right;
      }, action),
    ).toBe(true);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await checkpoint(
      photo === null ? 'profile-name-enlarged.png' : 'profile-current-photo-enlarged.png',
    );
  });
}

test('profile read fails safely then retries explicitly', async ({ page, checkpoint }: Context) => {
  await identity(page);
  let requests = 0;
  await page.route('**/api/v1/me/profile', async (route) => {
    requests += 1;
    await route.fulfill(
      requests === 1
        ? { status: 503, json: { code: 'unavailable', title: 'PRIVATE' } }
        : { json: ownProfile },
    );
  });
  await open(page);
  await expect(page.getByRole('alert')).toHaveText('We couldn’t load your profile.');
  expect(requests).toBe(1);
  await checkpoint('profile-unavailable.png');
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Display name' })).toHaveValue(
    revision.display_name,
  );
  await checkpoint('profile-read-recovered.png');
});

test('expired save revalidates identity and removes private draft', async ({
  page,
  checkpoint,
}: Context) => {
  let expired = false;
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill(
      expired ? { status: 401, json: { code: 'unauthenticated' } } : { json: verifiedActor },
    );
  });
  await page.route('**/api/v1/me/profile', async (route) => {
    if (route.request().method() === 'PUT') {
      expired = true;
      await route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
    } else await route.fulfill({ json: ownProfile });
  });
  await open(page);
  await page.getByRole('textbox', { name: 'Display name' }).fill('Private draft');
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Continue with Google' })).toBeVisible();
  await expect(page.getByRole('textbox')).toHaveCount(0);
  await expect(page.getByText('Private draft', { exact: true })).toHaveCount(0);
  await checkpoint('profile-session-expired.png');
});
