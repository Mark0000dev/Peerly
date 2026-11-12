import type { Page, Route } from '@playwright/test';
import type { Api } from '../../../api.generated';
import { test, expect } from '../../../../../testing/visual';
import { verifiedActor } from '../onboarding.fixtures';
import { helpSelection } from './help.fixtures';
import { catalogue } from './goal.fixtures';

interface Context {
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}
async function identity(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: verifiedActor });
  });
}
async function open(page: Readonly<Page>): Promise<void> {
  await page.goto('/onboarding');
  await page.getByRole('button', { name: 'Your help areas', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Your help areas');
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
}
async function subjects(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/subjects?*', async (route) => {
    await route.fulfill({ json: catalogue });
  });
}
async function modal(
  page: Readonly<Page>,
  checkpoint: Context['checkpoint'],
  name: string,
): Promise<void> {
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  const before = await dialog.boundingBox();
  const viewport = page.viewportSize();
  if (before === null || viewport === null) throw new Error('Missing visible picker viewport');
  expect(before.x).toBeGreaterThanOrEqual(0);
  expect(before.y).toBeGreaterThanOrEqual(0);
  expect(before.x + before.width).toBeLessThanOrEqual(viewport.width);
  expect(before.y + before.height).toBeLessThanOrEqual(viewport.height);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await checkpoint(name, { fullPage: false });
  expect(await dialog.boundingBox()).toEqual(before);
}
function saveHeaders(route: Readonly<Route>): void {
  expect(route.request().headers()['x-csrf-token']).toBe(verifiedActor.csrf_token);
  expect(route.request().headers()['idempotency-key']).toMatch(/^[a-f0-9-]{36}$/);
}

function canonicalSave(route: Readonly<Route>): void {
  saveHeaders(route);
  expect(route.request().postDataJSON()).toEqual({
    expected_version: 0,
    subjects: [{ subject_id: catalogue.items[1].id, topic_note: 'JOINs' }],
  });
}
function emptySave(route: Readonly<Route>): void {
  expect(route.request().postDataJSON()).toEqual({ expected_version: 2, subjects: [] });
}
function retrySame(route: Readonly<Route>, original: string | null, key: string | undefined): void {
  expect(route.request().postData()).toBe(original);
  expect(route.request().headers()['idempotency-key']).toBe(key);
}

for (const status of [200, 401])
  test(`old helper save ${String(status)} cannot alter a replacement actor draft`, async ({
    page,
    checkpoint,
  }: Context) => {
    let replacement = false;
    let release: () => void = () => {
      throw new Error('Uninitialised old helper save');
    };
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route('**/api/v1/me', async (route) => {
      await route.fulfill({
        json: replacement
          ? { ...verifiedActor, account_id: '00000000-0000-0000-0000-000000000099' }
          : verifiedActor,
      });
    });
    await page.route('**/api/v1/me/help-subjects', async (route) => {
      if (route.request().method() === 'PUT') {
        await pending;
        await route.fulfill({
          status,
          json: status === 200 ? helpSelection : { code: 'unauthenticated' },
        });
      } else
        await route.fulfill({
          json: {
            selection: replacement
              ? {
                  ...helpSelection,
                  subjects: [
                    { subject_id: catalogue.items[1].id, label: 'SQL', topic_note: 'Replacement' },
                  ],
                }
              : helpSelection,
          },
        });
    });
    await open(page);
    await page
      .getByLabel('Note for Calculus · optional', { exact: true })
      .fill('Old private draft');
    await page.getByRole('button', { name: 'Save help areas', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Saving…', exact: true })).toBeVisible();
    replacement = true;
    await page.getByRole('button', { name: 'Check status', exact: true }).click();
    await page.getByRole('button', { name: 'Your help areas', exact: true }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Your help areas');
    const note = page.getByLabel('Note for SQL · optional', { exact: true });
    await expect(note).toHaveValue('Replacement');
    await note.fill('Replacement private draft');
    const previous = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/v1/me/help-subjects') &&
        response.request().method() === 'PUT',
    );
    release();
    await previous;
    await expect(note).toHaveValue('Replacement private draft');
    await expect(page.getByLabel('Note for Calculus · optional', { exact: true })).toHaveCount(0);
    await checkpoint(`help-actor-replaced-${String(status)}.png`);
  });

test('help loading resolves to the saved canonical notes', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let release: () => void = () => {
    throw new Error('Uninitialised help read');
  };
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/me/help-subjects', async (route) => {
    await pending;
    await route.fulfill({ json: { selection: helpSelection } });
  });
  await open(page);
  await expect(page.getByText('Loading your help areas…', { exact: true })).toBeVisible();
  await checkpoint('help-loading.png');
  release();
  await expect(page.getByLabel('Note for Calculus · optional', { exact: true })).toHaveValue(
    'Limits',
  );
  await checkpoint('help-loaded.png');
});

test('existing choices are disabled and a fifth canonical subject reaches the honest limit', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await subjects(page);
  await page.route('**/api/v1/me/help-subjects', async (route) => {
    await route.fulfill({
      json: {
        selection: {
          ...helpSelection,
          subjects: [
            ...helpSelection.subjects,
            {
              subject_id: '00000000-0000-0000-0000-000000000040',
              label: 'Python',
              topic_note: 'pandas basics',
            },
            {
              subject_id: '00000000-0000-0000-0000-000000000041',
              label: 'Statistics',
              topic_note: 'hypothesis testing',
            },
            {
              subject_id: '00000000-0000-0000-0000-000000000042',
              label: 'Data structures',
              topic_note: null,
            },
          ],
        },
      },
    });
  });
  await open(page);
  await page.getByRole('button', { name: 'Add an area', exact: true }).click();
  await expect(page.getByRole('button', { name: /Calculus.*Already added/ })).toBeDisabled();
  await modal(page, checkpoint, 'help-picker-existing.png');
  await page.getByRole('button', { name: 'SQL Databases', exact: true }).click();
  await expect(
    page.getByText('You can help with up to 5 areas. Remove one to add another.', {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add an area', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await checkpoint('help-five-subjects.png');
});

test('catalogue pagination preserves the helper draft and closes with keyboard Escape', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await page.route('**/api/v1/me/help-subjects', async (route) => {
    await route.fulfill({ json: { selection: helpSelection } });
  });
  await page.route('**/api/v1/subjects?*', async (route) => {
    const cursor = new URL(route.request().url()).searchParams.get('cursor');
    await route.fulfill({
      json:
        cursor === null
          ? { items: [catalogue.items[0]], next_cursor: 'opaque' }
          : { items: [catalogue.items[1]], next_cursor: null },
    });
  });
  await open(page);
  await page.getByLabel('Note for Calculus · optional', { exact: true }).fill('Unsaved note');
  await page.getByRole('button', { name: 'Add an area', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Next areas', exact: true })).toBeVisible();
  await modal(page, checkpoint, 'help-picker-first-page.png');
  await page.getByRole('button', { name: 'Next areas', exact: true }).click();
  await expect(page.getByRole('button', { name: 'SQL Databases', exact: true })).toBeVisible();
  await modal(page, checkpoint, 'help-picker-next-page.png');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(page.getByLabel('Note for Calculus · optional', { exact: true })).toHaveValue(
    'Unsaved note',
  );
  await checkpoint('help-picker-escape.png');
});

test('a denied helper save revalidates identity and removes the private draft', async ({
  page,
  checkpoint,
}: Context) => {
  let expired = false;
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill(
      expired ? { status: 401, json: { code: 'unauthenticated' } } : { json: verifiedActor },
    );
  });
  await page.route('**/api/v1/me/help-subjects', async (route) => {
    if (route.request().method() === 'PUT') {
      expired = true;
      await route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
    } else await route.fulfill({ json: { selection: helpSelection } });
  });
  await open(page);
  await page
    .getByLabel('Note for Calculus · optional', { exact: true })
    .fill('Private helper draft');
  await page.getByRole('button', { name: 'Save help areas', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Continue with Google', exact: true })).toBeVisible();
  await expect(page.getByText('Private helper draft', { exact: true })).toHaveCount(0);
  await checkpoint('help-session-expired.png');
});

test('empty helper selection uses an explicit canonical picker and saves exact ordered request fields', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await subjects(page);
  let current: Api['schemas']['HelpResponse'] | null = null;
  let release: () => void = () => {
    throw new Error('Uninitialised help save');
  };
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/me/help-subjects', async (route) => {
    if (route.request().method() === 'PUT') {
      canonicalSave(route);
      await pending;
      current = {
        ...helpSelection,
        version: 1,
        subjects: [{ subject_id: catalogue.items[1].id, label: 'SQL', topic_note: 'JOINs' }],
      };
      await route.fulfill({ json: current });
    } else await route.fulfill({ json: { selection: current } });
  });
  await open(page);
  await expect(
    page.getByText('0 of 5 areas. Changes apply after you save.', { exact: true }),
  ).toBeVisible();
  await checkpoint('help-empty.png');
  await page.getByRole('button', { name: 'Add an area', exact: true }).click();
  await page.getByLabel('Search areas', { exact: true }).fill('Databases');
  await expect(page.getByRole('button', { name: 'SQL Databases', exact: true })).toBeVisible();
  await modal(page, checkpoint, 'help-picker-alias.png');
  await page.getByRole('button', { name: 'SQL Databases', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  await page.getByLabel('Note for SQL · optional', { exact: true }).fill('JOINs');
  await checkpoint('help-unsaved.png');
  await page.getByRole('button', { name: 'Save help areas', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Saving…', exact: true })).toBeDisabled();
  await checkpoint('help-saving.png');
  release();
  await expect(page.getByText('Help areas saved.', { exact: true })).toBeVisible();
  await checkpoint('help-saved.png');
  await page.reload();
  await page.getByRole('button', { name: 'Your help areas', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Your help areas');
  await expect(page.getByLabel('Note for SQL · optional', { exact: true })).toHaveValue('JOINs');
  await checkpoint('help-reloaded.png');
});

test('removing the final helper subject is an explicit saved empty revision', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let current: Api['schemas']['HelpResponse'] = helpSelection;
  await page.route('**/api/v1/me/help-subjects', async (route) => {
    if (route.request().method() === 'PUT') {
      emptySave(route);
      current = { ...helpSelection, version: 3, subjects: [] };
      await route.fulfill({ json: current });
    } else await route.fulfill({ json: { selection: current } });
  });
  await open(page);
  await page.getByRole('button', { name: 'Remove Calculus', exact: true }).click();
  await checkpoint('help-remove-draft.png');
  await page.getByRole('button', { name: 'Save help areas', exact: true }).click();
  await expect(page.getByText('Help areas saved.', { exact: true })).toBeVisible();
  await checkpoint('help-empty-saved.png');
});

test('helper note validation stays local at320px with keyboard and200percent text', async ({
  page,
  checkpoint,
}: Context) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await identity(page);
  await page.route('**/api/v1/me/help-subjects', async (route) => {
    expect(route.request().method()).toBe('GET');
    await route.fulfill({ json: { selection: helpSelection } });
  });
  await open(page);
  const note = page.getByLabel('Note for Calculus · optional', { exact: true });
  await note.fill('x'.repeat(81));
  await page.getByRole('button', { name: 'Save help areas', exact: true }).click();
  await expect(
    page.getByText('Keep each topic note within 80 characters.', { exact: true }),
  ).toBeVisible();
  await note.focus();
  await expect(note).toBeFocused();
  await checkpoint('help-invalid-keyboard.png');
  await page.addStyleTag({ content: ':root { font-size: 200%; }' });
  const label = await page
    .locator('label[for="help-note-0"]')
    .evaluate((element: Readonly<Element>) => {
      const text = document.createRange();
      text.selectNodeContents(element);
      return {
        text: element.textContent.trim(),
        fits: text.getBoundingClientRect().width <= element.getBoundingClientRect().width,
      };
    });
  expect(label).toEqual({ text: 'Note', fits: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  const caption = await page
    .getByRole('button', { name: 'Save help areas', exact: true })
    .evaluate((button: Readonly<HTMLElement | SVGElement>) => {
      const text = document.createRange();
      text.selectNodeContents(button);
      const styles = getComputedStyle(button);
      return {
        text: text.getBoundingClientRect().width,
        available:
          button.clientWidth -
          Number.parseFloat(styles.paddingLeft) -
          Number.parseFloat(styles.paddingRight),
      };
    });
  expect(caption.text).toBeLessThanOrEqual(caption.available);
  await checkpoint('help-enlarged.png');
});

test('catalogue picker loading failure retry and empty search remain explicit', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await page.route('**/api/v1/me/help-subjects', async (route) => {
    await route.fulfill({ json: { selection: null } });
  });
  let requests = 0;
  let release: () => void = () => {
    throw new Error('Uninitialised picker');
  };
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/subjects?*', async (route) => {
    requests += 1;
    if (requests === 1) {
      await pending;
      await route.fulfill({ status: 503, json: { code: 'unavailable', title: 'PRIVATE' } });
    } else await route.fulfill({ json: { items: [], next_cursor: null } });
  });
  await open(page);
  await page.getByRole('button', { name: 'Add an area', exact: true }).click();
  await expect(page.getByText('Searching areas…', { exact: true })).toBeVisible();
  await modal(page, checkpoint, 'help-picker-loading.png');
  release();
  await expect(page.getByText('We couldn’t load areas.', { exact: true })).toBeVisible();
  expect(requests).toBe(1);
  await modal(page, checkpoint, 'help-picker-unavailable.png');
  await page.getByRole('button', { name: 'Retry areas', exact: true }).click();
  await expect(
    page.getByText('No areas found. Try another name or alias.', { exact: true }),
  ).toBeVisible();
  await modal(page, checkpoint, 'help-picker-empty.png');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  await checkpoint('help-picker-cancelled.png');
});

test('helper read failures require an explicit retry', async ({ page, checkpoint }: Context) => {
  await identity(page);
  let requests = 0;
  await page.route('**/api/v1/me/help-subjects', async (route) => {
    requests += 1;
    await route.fulfill(
      requests === 1
        ? { status: 503, json: { code: 'unavailable' } }
        : { json: { selection: helpSelection } },
    );
  });
  await open(page);
  await expect(page.getByText('We couldn’t load your help areas.', { exact: true })).toBeVisible();
  await checkpoint('help-read-unavailable.png');
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByLabel('Note for Calculus · optional', { exact: true })).toHaveValue(
    'Limits',
  );
  await checkpoint('help-read-recovered.png');
});

for (const { code, status, copy, action } of [
  {
    code: 'unavailable',
    status: 503,
    copy: 'We couldn’t confirm your save.',
    action: 'Retry same save',
  },
  {
    code: 'help_version_conflict',
    status: 409,
    copy: 'Your help areas changed elsewhere.',
    action: 'Reload saved areas',
  },
  {
    code: 'subject_unavailable',
    status: 409,
    copy: 'An area is no longer available.',
    action: 'Reload saved areas',
  },
] as const)
  test(`helper ${code} preserves the draft and requires explicit recovery`, async ({
    page,
    checkpoint,
  }: Context) => {
    await identity(page);
    let writes = 0;
    let original: string | null = null;
    let key: string | undefined;
    await page.route('**/api/v1/me/help-subjects', async (route) => {
      if (route.request().method() === 'PUT') {
        writes += 1;
        if (writes === 1) {
          original = route.request().postData();
          key = route.request().headers()['idempotency-key'];
          await route.fulfill({ status, json: { code, title: 'PRIVATE' } });
        } else {
          retrySame(route, original, key);
          await route.fulfill({ json: { ...helpSelection, version: 3 } });
        }
      } else await route.fulfill({ json: { selection: helpSelection } });
    });
    await open(page);
    await page.getByLabel('Note for Calculus · optional', { exact: true }).fill('My private draft');
    await page.getByRole('button', { name: 'Save help areas', exact: true }).click();
    await expect(page.getByText(copy, { exact: false })).toBeVisible();
    await expect(page.getByLabel('Note for Calculus · optional', { exact: true })).toHaveValue(
      'My private draft',
    );
    expect(writes).toBe(1);
    await checkpoint(`help-${code}.png`);
    await page.getByRole('button', { name: action, exact: true }).click();
    await expect(page.getByLabel('Note for Calculus · optional', { exact: true })).toHaveValue(
      'Limits',
    );
    await checkpoint(`help-${code}-resolved.png`);
  });
