import type { Page, Route } from '@playwright/test';
import type { Api } from '../../../api.generated';
import { test, expect } from '../../../../../testing/visual';
import { verifiedActor } from '../onboarding.fixtures';
import { catalogue, goal, ownGoal } from './goal.fixtures';

interface Context {
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}
// Adaptive overlays are asserted in the real viewport, then the closed form in full.
// Keep geometry unchanged by capture and fail overflow rather than cropping application content.
async function popup(
  page: Readonly<Page>,
  checkpoint: Context['checkpoint'],
  name: string,
): Promise<void> {
  const list = page.getByRole('listbox');
  const before = await list.boundingBox();
  const viewport = page.viewportSize();
  if (before === null || viewport === null) throw new Error('Missing visible catalogue viewport');
  expect(before.x).toBeGreaterThanOrEqual(0);
  expect(before.y).toBeGreaterThanOrEqual(0);
  expect(before.x + before.width).toBeLessThanOrEqual(viewport.width);
  expect(before.y + before.height).toBeLessThanOrEqual(viewport.height);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await checkpoint(name, { fullPage: false });
  expect(await list.boundingBox()).toEqual(before);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
}
async function identity(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: verifiedActor });
  });
}
async function open(page: Readonly<Page>): Promise<void> {
  await page.goto('/onboarding');
  await page.getByRole('button', { name: 'Your study goal', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Your study goal');
  // Load local fonts before interacting with adaptive overlays. The screenshot
  // helper waits for fonts after interaction, which does not stabilise its starting metrics.
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
}
async function subjects(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/subjects?*', async (route) => {
    await route.fulfill({ json: catalogue });
  });
}
function canonicalSave(route: Readonly<Route>): void {
  expect(route.request().headers()['x-csrf-token']).toBe(verifiedActor.csrf_token);
  expect(route.request().headers()['idempotency-key']).toMatch(/^[a-f0-9-]{36}$/);
  expect(route.request().postDataJSON()).toEqual({
    subject: { kind: 'canonical', id: catalogue.items[1].id },
    topic: 'JOINs',
    context: 'Practice with examples',
    shared_learning: true,
    expected_goal_id: goal.id,
    expected_version: 2,
  });
}

test('goal loading resolves to the actual saved draft', async ({ page, checkpoint }: Context) => {
  await identity(page);
  await subjects(page);
  let release: () => void = () => {
    throw new Error('Uninitialised goal response');
  };
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/me/goal', async (route) => {
    await pending;
    await route.fulfill({ json: ownGoal });
  });
  await open(page);
  await expect(page.getByText('Loading your goal…', { exact: true })).toBeVisible();
  await checkpoint('goal-loading.png');
  release();
  await expect(page.getByLabel('Knowledge area', { exact: true })).toHaveValue('Calculus');
  await expect(page.getByLabel('Task or topic · optional', { exact: true })).toHaveValue('Limits');
  await checkpoint('goal-loaded.png');
});

test('canonical catalogue choice saves exact fields and resumes the new goal revision', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await subjects(page);
  let current: Api['schemas']['GoalResponse'] = goal;
  await page.route('**/api/v1/me/goal', async (route) => {
    if (route.request().method() === 'PUT') {
      canonicalSave(route);
      current = {
        ...goal,
        version: 3,
        subject: { kind: 'canonical', id: catalogue.items[1].id, label: 'SQL' },
        topic: 'JOINs',
        context: 'Practice with examples',
        shared_learning: true,
      };
      await route.fulfill({ json: current });
      return;
    }
    await route.fulfill({ json: { goal: current } });
  });
  await open(page);
  await page.getByLabel('Knowledge area', { exact: true }).fill('Databases');
  await expect(page.getByRole('option', { name: /SQL/ })).toBeVisible();
  await checkpoint('goal-catalogue-aliases.png');
  await page.getByRole('option', { name: /SQL/ }).click();
  await expect(page.getByLabel('Knowledge area', { exact: true })).toHaveValue('SQL');
  await page.getByLabel('Task or topic · optional', { exact: true }).fill('JOINs');
  await page
    .getByLabel('Context or module · optional', { exact: true })
    .fill('Practice with examples');
  await page.getByRole('checkbox', { name: 'Open to studying together', exact: true }).check();
  await page.getByRole('button', { name: 'Save goal', exact: true }).click();
  await expect(
    page.getByText('Goal saved. New requests will use this goal.', { exact: true }),
  ).toBeVisible();
  await checkpoint('goal-canonical-saved.png');
  await page.reload();
  await page.getByRole('button', { name: 'Your study goal', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Your study goal');
  await expect(page.getByLabel('Knowledge area', { exact: true })).toHaveValue('SQL');
  await expect(
    page.getByRole('checkbox', { name: 'Open to studying together', exact: true }),
  ).toBeChecked();
  await checkpoint('goal-canonical-reloaded.png');
});

test('a custom subject requires an explicit real option rather than typed text', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await page.route('**/api/v1/subjects?*', async (route) => {
    await route.fulfill({ json: { items: [], next_cursor: null } });
  });
  let current: Api['schemas']['GoalResponse'] | null = null;
  await page.route('**/api/v1/me/goal', async (route) => {
    if (route.request().method() === 'PUT') {
      current = {
        ...goal,
        version: 1,
        subject: { kind: 'custom', label: 'Distributed systems' },
        topic: null,
        context: null,
      };
      await route.fulfill({ json: current });
      return;
    }
    await route.fulfill({ json: { goal: current } });
  });
  await open(page);
  await page.getByLabel('Knowledge area', { exact: true }).fill('Distributed systems');
  await expect(page.getByText('No areas found.', { exact: true })).toBeVisible();
  await checkpoint('goal-custom-search.png');
  await page.getByRole('option', { name: 'Use this as another area', exact: true }).click();
  await expect(
    page.getByText('Another area isn’t linked to a listed area.', {
      exact: false,
    }),
  ).toBeVisible();
  await checkpoint('goal-custom-selected.png');
  const saving = page.waitForRequest(
    (request) => request.url().endsWith('/api/v1/me/goal') && request.method() === 'PUT',
  );
  await page.getByRole('button', { name: 'Save goal', exact: true }).click();
  const request = await saving;
  expect(request.postDataJSON()).toEqual({
    subject: { kind: 'custom', label: 'Distributed systems' },
    topic: null,
    context: null,
    shared_learning: false,
    expected_goal_id: null,
    expected_version: 0,
  });

  await expect(
    page.getByText('Goal saved. New requests will use this goal.', { exact: true }),
  ).toBeVisible();
  await checkpoint('goal-custom-saved.png');
});

for (const { outcome, action } of [
  { outcome: 'uncertain', action: 'Retry same save' },
  { outcome: 'conflict', action: 'Reload saved goal' },
] as const) {
  test(`goal ${outcome} preserves the draft and requires explicit safe recovery`, async ({
    page,
    checkpoint,
  }: Context) => {
    await identity(page);
    await subjects(page);
    let writes = 0;
    let key: string | undefined;
    let resolved = false;
    await page.route('**/api/v1/me/goal', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          json: { goal: resolved ? { ...goal, version: 3, topic: 'Resolved topic' } : goal },
        });
        return;
      }
      writes += 1;
      const nextKey = route.request().headers()['idempotency-key'];
      if (writes === 1) {
        key = nextKey;
        if (outcome === 'uncertain') await route.abort('failed');
        else
          await route.fulfill({
            status: 409,
            json: { code: 'goal_version_conflict', title: 'PRIVATE' },
          });
        return;
      }
      expect(nextKey).toBe(key);
      resolved = true;
      await route.fulfill({ json: { ...goal, version: 3, topic: 'Resolved topic' } });
    });
    await open(page);
    await page.getByLabel('Task or topic · optional', { exact: true }).fill('Private draft');
    await page.getByRole('button', { name: 'Save goal', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText(
      outcome === 'uncertain' ? 'couldn’t confirm' : 'changed elsewhere',
    );
    await expect(page.getByLabel('Task or topic · optional', { exact: true })).toHaveValue(
      'Private draft',
    );
    await expect(page.getByLabel('Task or topic · optional', { exact: true })).not.toBeEditable();
    expect(writes).toBe(1);
    await checkpoint(`goal-${outcome}.png`);
    resolved = true;
    await page.getByRole('button', { name: action, exact: true }).click();
    await expect(page.getByLabel('Task or topic · optional', { exact: true })).toHaveValue(
      'Resolved topic',
    );
    await checkpoint(`goal-${outcome}-resolved.png`);
  });
}

test('missing subject and long drafts stay local at320px with keyboard and enlarged text', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await subjects(page);
  let writes = 0;
  await page.route('**/api/v1/me/goal', async (route) => {
    if (route.request().method() === 'PUT') writes += 1;
    await route.fulfill({ json: { goal: null } });
  });
  await page.setViewportSize({ width: 320, height: 740 });
  await open(page);
  await page.getByLabel('Task or topic · optional', { exact: true }).fill('x'.repeat(81));
  await page.getByLabel('Context or module · optional', { exact: true }).fill('x'.repeat(241));
  await page.getByRole('button', { name: 'Save goal', exact: true }).click();
  await expect(
    page.getByText('Choose an area from the list or use it as another area.', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('Keep the topic within 80 characters.', { exact: true }),
  ).toBeVisible();
  expect(writes).toBe(0);
  await page.getByLabel('Context or module · optional', { exact: true }).focus();
  await expect(page.getByLabel('Context or module · optional', { exact: true })).toBeFocused();
  await checkpoint('goal-invalid-keyboard.png');
  await page.addStyleTag({ content: ':root { font-size: 200%; }' });
  const labels = await page
    .locator('label[for^="goal-"]')
    .evaluateAll((elements: readonly Element[]) =>
      elements.map((element: Readonly<Element>) => {
        const text = document.createRange();
        text.selectNodeContents(element);
        return {
          text: element.textContent.trim(),
          fits: text.getBoundingClientRect().width <= element.getBoundingClientRect().width,
        };
      }),
    );
  expect(labels).toEqual([
    { text: 'Area', fits: true },
    { text: 'Task', fits: true },
    { text: 'Context', fits: true },
  ]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await checkpoint('goal-enlarged.png');
});

test('catalogue failure is safe and only retries after an explicit action', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  let requests = 0;
  let fail: () => void = () => {
    throw new Error('Uninitialised catalogue failure');
  };
  const first = new Promise<void>((resolve) => {
    fail = resolve;
  });
  await page.route('**/api/v1/me/goal', async (route) => {
    await route.fulfill({ json: ownGoal });
  });
  await page.route('**/api/v1/subjects?*', async (route) => {
    requests += 1;
    if (requests === 1) await first;
    await route.fulfill(
      requests === 1
        ? { status: 503, json: { code: 'unavailable', title: 'PRIVATE' } }
        : { json: catalogue },
    );
  });
  await open(page);
  await page.getByLabel('Knowledge area', { exact: true }).click();
  await expect(page.getByText('Searching areas…', { exact: true })).toBeVisible();
  await popup(page, checkpoint, 'goal-catalogue-before-failure.png');
  fail();
  await expect(page.getByText('We couldn’t load areas.', { exact: true })).toBeVisible();
  expect(requests).toBe(1);
  await expect(page.getByText('Nothing found', { exact: true })).toHaveCount(0);
  await popup(page, checkpoint, 'goal-catalogue-unavailable.png');
  await page.getByRole('button', { name: 'Retry areas', exact: true }).click();
  await expect(page.getByRole('option', { name: /SQL/ })).toBeVisible();
  await popup(page, checkpoint, 'goal-catalogue-recovered.png');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('option', { name: /SQL/ })).toBeHidden();
  await checkpoint('goal-catalogue-recovered-closed.png');
});

test('catalogue pagination keeps the chosen subject while loading the next server page', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await page.route('**/api/v1/me/goal', async (route) => {
    await route.fulfill({ json: ownGoal });
  });
  let loadFirst: () => void = () => {
    throw new Error('Uninitialised first page');
  };
  const firstPage = new Promise<void>((resolve) => {
    loadFirst = resolve;
  });
  let release: () => void = () => {
    throw new Error('Uninitialised next page');
  };
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/subjects?*', async (route) => {
    const cursor = new URL(route.request().url()).searchParams.get('cursor');
    if (cursor !== null) {
      await pending;
      await route.fulfill({ json: { items: [catalogue.items[1]], next_cursor: null } });
      return;
    }
    await firstPage;
    await route.fulfill({ json: { items: [catalogue.items[0]], next_cursor: 'opaque cursor' } });
  });
  await open(page);
  await page.getByLabel('Knowledge area', { exact: true }).click();
  await expect(page.getByText('Searching areas…', { exact: true })).toBeVisible();
  await popup(page, checkpoint, 'goal-catalogue-before-first-page.png');
  loadFirst();
  await expect(page.getByRole('button', { name: 'Next areas', exact: true })).toBeVisible();
  await popup(page, checkpoint, 'goal-catalogue-first-page.png');
  const next = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname === '/api/v1/subjects' &&
      new URL(request.url()).searchParams.has('cursor'),
  );
  await page.getByRole('button', { name: 'Next areas', exact: true }).click();
  expect(new URL((await next).url()).searchParams.get('cursor')).toBe('opaque cursor');
  await expect(page.getByText('Searching areas…', { exact: true })).toBeVisible();
  await expect(page.getByText('Nothing found', { exact: true })).toHaveCount(0);
  await popup(page, checkpoint, 'goal-catalogue-next-loading.png');
  release();
  await expect(page.getByRole('option', { name: /SQL/ })).toBeVisible();
  await expect(page.getByLabel('Knowledge area', { exact: true })).toHaveValue('Calculus');
  await popup(page, checkpoint, 'goal-catalogue-next-page.png');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('option', { name: /SQL/ })).toBeHidden();
  await checkpoint('goal-catalogue-next-page-closed.png');
});

test('goal read failure recovers through a real retry without leaking server text', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await subjects(page);
  let requests = 0;
  await page.route('**/api/v1/me/goal', async (route) => {
    requests += 1;
    await route.fulfill(
      requests === 1
        ? { status: 503, json: { code: 'unavailable', title: 'PRIVATE' } }
        : { json: ownGoal },
    );
  });
  await open(page);
  await expect(page.getByRole('alert')).toHaveText('We couldn’t load your goal.');
  expect(requests).toBe(1);
  await checkpoint('goal-unavailable.png');
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByLabel('Knowledge area', { exact: true })).toHaveValue('Calculus');
  await checkpoint('goal-read-recovered.png');
});

test('retired subject recovery does not pretend a version changed', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await subjects(page);
  await page.route('**/api/v1/me/goal', async (route) => {
    await route.fulfill(
      route.request().method() === 'PUT'
        ? { status: 409, json: { code: 'subject_unavailable' } }
        : { json: ownGoal },
    );
  });
  await open(page);
  await page.getByRole('button', { name: 'Save goal', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText(
    'This area is no longer available. Reload the saved goal and choose another area.',
  );
  await expect(page.getByText('Your goal changed elsewhere', { exact: false })).toHaveCount(0);
  await checkpoint('goal-subject-unavailable.png');
});

test('expired goal save revalidates identity and removes the private draft', async ({
  page,
  checkpoint,
}: Context) => {
  let expired = false;
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill(
      expired ? { status: 401, json: { code: 'unauthenticated' } } : { json: verifiedActor },
    );
  });
  await subjects(page);
  await page.route('**/api/v1/me/goal', async (route) => {
    if (route.request().method() === 'PUT') {
      expired = true;
      await route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
    } else await route.fulfill({ json: ownGoal });
  });
  await open(page);
  await page.getByLabel('Task or topic · optional', { exact: true }).fill('Private draft');
  await page.getByRole('button', { name: 'Save goal', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Continue with Google' })).toBeVisible();
  await expect(page.getByLabel('Task or topic · optional', { exact: true })).toHaveCount(0);
  await checkpoint('goal-session-expired.png');
});

test('actual shell delivers explicit goal action correlations without private draft text', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await subjects(page);
  let delivered: readonly string[] = [];
  await page.route('**/api/v1/telemetry/events', async (route) => {
    const batch: unknown = route.request().postDataJSON();
    expect(route.request().headers()['x-csrf-token']).toBe(verifiedActor.csrf_token);
    expect(route.request().headers()['idempotency-key']).toMatch(/^[a-f0-9-]{36}$/);
    if (
      typeof batch !== 'object' ||
      batch === null ||
      !('expected_actor_id' in batch) ||
      batch.expected_actor_id !== verifiedActor.account_id ||
      !('events' in batch) ||
      !Array.isArray(batch.events)
    )
      throw new Error('Invalid actual shell observation envelope');
    const events: readonly unknown[] = batch.events;
    const ids = events.map((event) => {
      if (
        typeof event !== 'object' ||
        event === null ||
        !('event_id' in event) ||
        typeof event.event_id !== 'string'
      )
        throw new Error('Missing observation identity');
      return event.event_id;
    });
    // Accumulate only validated event-kind/action identifiers, not private inputs.
    for (const event of events) {
      if (
        typeof event === 'object' &&
        event !== null &&
        'kind' in event &&
        event.kind === 'action.observed' &&
        'action' in event &&
        event.action === 'submit' &&
        'outcome' in event &&
        event.outcome === 'invoked' &&
        'action_id' in event &&
        typeof event.action_id === 'string'
      ) {
        delivered = [...delivered, event.action_id];
      }
    }
    expect(JSON.stringify(batch)).not.toContain('PRIVATE unsent task context');
    expect(JSON.stringify(batch)).not.toContain('fixture-csrf');
    await route.fulfill({
      json: {
        accepted: ids,
        duplicates: [],
        received_at: '2026-11-07T12:00:00Z',
        schema_version: 1,
      } satisfies Api['schemas']['ObservationBatchResponse'],
    });
  });
  let current: Api['schemas']['GoalResponse'] = goal;
  let sentAction: string | undefined;
  let sentTrace: string | undefined;
  await page.route('**/api/v1/me/goal', async (route) => {
    if (route.request().method() === 'PUT') {
      sentAction = route.request().headers()['x-action-id'];
      sentTrace = route.request().headers()['traceparent'];
      current = { ...goal, topic: 'PRIVATE unsent task context', version: goal.version + 1 };
      await route.fulfill({ json: current });
    } else await route.fulfill({ json: { goal: current } });
  });
  await open(page);
  await expect(page.getByLabel('Knowledge area', { exact: true })).toHaveValue('Calculus');
  await page
    .getByLabel('Task or topic · optional', { exact: true })
    .fill('PRIVATE unsent task context');
  await page.getByRole('button', { name: 'Save goal', exact: true }).click();
  await expect(
    page.getByText('Goal saved. New requests will use this goal.', { exact: true }),
  ).toBeVisible();
  expect(sentAction).toMatch(/^[a-f0-9-]{36}$/);
  expect(sentTrace).toMatch(/^00-[a-f0-9]{32}-[a-f0-9]{16}-01$/);
  await expect
    .poll(() => sentAction !== undefined && delivered.includes(sentAction), { timeout: 15_000 })
    .toBe(true);
  await checkpoint('goal-observation-correlated-save.png');
});

test('reviewing saved setup keeps an unsaved goal until explicit discard', async ({
  page,
  checkpoint,
}: Context) => {
  await identity(page);
  await subjects(page);
  await page.route('**/api/v1/me/goal', async (route) => {
    expect(route.request().method()).toBe('GET');
    await route.fulfill({ json: ownGoal });
  });
  await open(page);
  const topic = page.getByLabel('Task or topic · optional', { exact: true });
  await topic.fill('Unsent draft topic');
  await page.getByRole('button', { name: 'Review saved setup', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Discard unsaved changes?' })).toBeVisible();
  await checkpoint('goal-review-setup-dirty-confirmation.png');
  await page.getByRole('button', { name: 'Keep editing', exact: true }).click();
  await expect(topic).toHaveValue('Unsent draft topic');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Your study goal');
  await checkpoint('goal-review-setup-keeps-draft.png');
});
