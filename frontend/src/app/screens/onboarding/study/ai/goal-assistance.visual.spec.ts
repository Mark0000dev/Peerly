import type { Page, Route } from '@playwright/test';
import { createHash } from 'node:crypto';
import { test, expect } from '../../../../../../testing/visual';
import type { Api } from '../../../../api.generated';
import { verifiedActor } from '../../onboarding.fixtures';
import { goal as originalGoal } from '../goal.fixtures';
import type { GoalRequest } from './goal-assistance-contract';

interface Scenario {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}
const instant = '2026-11-09T07:00:00Z';
const catalogue = {
  items: [
    { id: '00000000-0000-4000-8000-000000000051', name: 'Databases', aliases: [] },
    { id: '00000000-0000-4000-8000-000000000052', name: 'Mathematics', aliases: [] },
  ],
  next_cursor: null,
} as const satisfies Api['schemas']['SubjectsResponse'];
const jobId = '00000000-0000-4000-8000-000000000060';
const suggestion =
  'I understand INNER JOIN, but need help with LEFT JOIN, NULLs and duplicate rows.';
function object(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function submitted(route: Readonly<Route>): GoalRequest {
  const body: unknown = route.request().postDataJSON();
  expect(route.request().headers()['x-csrf-token']).toBe(verifiedActor.csrf_token);
  expect(route.request().headers()['idempotency-key']).toMatch(/^[a-f0-9-]{36}$/);
  if (
    !object(body) ||
    !object(body['source']) ||
    body['source']['kind'] !== 'draft' ||
    typeof body['source']['id'] !== 'string' ||
    typeof body['source']['version'] !== 'number'
  )
    throw new Error('Missing actual draft source');
  const source: Api['schemas']['DraftSourceRequest'] = {
    kind: 'draft',
    id: body['source']['id'],
    version: body['source']['version'],
  };
  if (
    body['kind'] === 'clarify_goal' &&
    body['target'] === 'context' &&
    typeof body['text'] === 'string'
  ) {
    expect(Object.keys(body)).toHaveLength(4);
    expect(Object.keys(body)).toEqual(expect.arrayContaining(['kind', 'source', 'target', 'text']));
    return { kind: 'clarify_goal', source, target: 'context', text: body['text'] };
  }
  if (
    body['kind'] === 'suggest_subject' &&
    typeof body['label'] === 'string' &&
    Array.isArray(body['candidate_ids']) &&
    body['candidate_ids'].every((id: unknown) => typeof id === 'string')
  ) {
    expect(Object.keys(body)).toHaveLength(4);
    expect(Object.keys(body)).toEqual(
      expect.arrayContaining(['candidate_ids', 'kind', 'label', 'source']),
    );
    expect(body['candidate_ids']).toEqual(catalogue.items.map((item) => item.id));
    return {
      kind: 'suggest_subject',
      source,
      label: body['label'],
      candidate_ids: body['candidate_ids'],
    };
  }
  throw new Error('Unexpected goal AI request');
}
function response(
  body: GoalRequest,
  overrides: Partial<Api['schemas']['JobResponse']> = {},
): Api['schemas']['JobResponse'] {
  const content = body.kind === 'clarify_goal' ? body.text : '';
  const label = body.kind === 'suggest_subject' ? (body.label ?? '') : '';
  const candidates = body.kind === 'suggest_subject' ? [...body.candidate_ids].sort() : [];
  const hash = createHash('sha256')
    .update(
      JSON.stringify(['peerly-ai-draft-v1', body.kind, 'context', content, label, ...candidates]),
    )
    .digest('hex');
  return {
    id: jobId,
    kind: body.kind,
    source: { ...body.source, kind: 'draft', content_hash: hash },
    target: body.kind === 'clarify_goal' ? 'context' : null,
    created_at: instant,
    deadline: '2026-11-09T07:02:00Z',
    state: 'queued',
    result: null,
    failure: null,
    poll_after_ms: 100,
    ...overrides,
  };
}
async function boundary(
  page: Readonly<Page>,
): Promise<Readonly<{ readonly writes: () => readonly unknown[] }>> {
  let current: Api['schemas']['GoalResponse'] = {
    ...originalGoal,
    subject: { kind: 'canonical', id: catalogue.items[0].id, label: catalogue.items[0].name },
    topic: 'SQL JOINs',
    context: 'LEFT JOIN with NULLs gives duplicate rows.',
  };
  let writes: readonly unknown[] = [];
  await page.clock.setFixedTime(new Date(instant));
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({ json: verifiedActor }),
  );
  await page.route('**/api/v1/subjects?*', (route: Readonly<Route>) =>
    route.fulfill({ json: catalogue }),
  );
  await page.route('**/api/v1/me/goal', async (route: Readonly<Route>) => {
    if (route.request().method() === 'PUT') {
      const body: unknown = route.request().postDataJSON();
      if (
        !object(body) ||
        !object(body['subject']) ||
        body['subject']['kind'] !== 'canonical' ||
        typeof body['subject']['id'] !== 'string' ||
        !(body['context'] === null || typeof body['context'] === 'string') ||
        !(body['topic'] === null || typeof body['topic'] === 'string') ||
        typeof body['shared_learning'] !== 'boolean'
      )
        throw new Error('Malformed manual Goal save');
      expect(body['expected_goal_id']).toBe(current.id);
      expect(body['expected_version']).toBe(current.version);
      const id = body['subject']['id'];
      const area = catalogue.items.find((item) => item.id === id);
      if (area === undefined) throw new Error('Uncaptured area on Goal save');
      writes = [...writes, body];
      current = {
        ...current,
        version: current.version + 1,
        subject: { kind: 'canonical', id: area.id, label: area.name },
        context: body['context'],
        topic: body['topic'],
        shared_learning: body['shared_learning'],
      };
      await route.fulfill({ json: current });
    } else
      await route.fulfill({ json: { goal: current } satisfies Api['schemas']['OwnGoalResponse'] });
  });
  return { writes: () => writes };
}
async function open(page: Readonly<Page>): Promise<void> {
  await page.goto('/onboarding');
  await page.getByRole('button', { name: 'Your study goal', exact: true }).click();
  await expect(page.getByLabel('Context or module · optional', { exact: true })).toHaveValue(
    'LEFT JOIN with NULLs gives duplicate rows.',
  );
  await expect(
    page.getByRole('button', { name: 'Suggest clearer wording', exact: true }),
  ).toBeEnabled();
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
}
async function save(page: Readonly<Page>): Promise<void> {
  await page.getByRole('button', { name: 'Save goal', exact: true }).click();
  await expect(
    page.getByText('Goal saved. New requests will use this goal.', { exact: true }),
  ).toBeVisible();
}
async function ask(page: Readonly<Page>): Promise<void> {
  await page.getByRole('button', { name: 'Suggest clearer wording', exact: true }).click();
}

test('G01 actual-shaped hard-OFF 503 leaves the real Goal form manually saveable', async ({
  page,
  checkpoint,
}: Scenario) => {
  const goal = await boundary(page);
  let requests = 0;
  await page.route('**/api/v1/ai/jobs', (route: Readonly<Route>) => {
    submitted(route);
    requests += 1;
    return route.fulfill({ status: 503, json: { code: 'ai_unavailable' } });
  });
  await open(page);
  const context = page.getByLabel('Context or module · optional', { exact: true });
  await context.fill('');
  await expect(
    page.getByRole('button', { name: 'Suggest clearer wording', exact: true }),
  ).toBeDisabled();
  expect(requests).toBe(0);
  await checkpoint('g01-ai-empty-context-no-request.png');
  await context.fill('LEFT JOIN with NULLs gives duplicate rows.');
  await ask(page);
  await expect(
    page.getByText('AI assistance isn’t available right now. You can write and save as usual.', {
      exact: true,
    }),
  ).toBeVisible();
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-unavailable-manual-path.png');
  await page
    .getByLabel('Context or module · optional', { exact: true })
    .fill('Keep my own revised context.');
  await save(page);
  expect(goal.writes()).toHaveLength(1);
  expect(goal.writes()[0]).toMatchObject({ context: 'Keep my own revised context.' });
  await checkpoint('g01-ai-unavailable-manual-goal-saved.png');
});

test('G01 queued running and reviewed wording remain unsaved until separate explicit Goal save', async ({
  page,
  checkpoint,
}: Scenario) => {
  const goal = await boundary(page);
  let source: GoalRequest | null = null;
  let state: Api['schemas']['JobState'] = 'queued';
  await page.route('**/api/v1/ai/jobs', (route: Readonly<Route>) => {
    source = submitted(route);
    return route.fulfill({ status: 202, json: response(source) });
  });
  await page.route(`**/api/v1/ai/jobs/${jobId}`, (route: Readonly<Route>) => {
    if (source === null) throw new Error('Missing admitted source');
    return route.fulfill({
      json: response(source, {
        state,
        poll_after_ms: state === 'succeeded' ? null : 100,
        result: state === 'succeeded' ? { suggestion } : null,
      }),
    });
  });
  await open(page);
  await ask(page);
  await expect(
    page.getByText('AI assistance · waiting. You can keep editing or save.', { exact: true }),
  ).toBeVisible();
  await checkpoint('g01-ai-queued.png');
  state = 'running';
  await expect(
    page.getByText('AI assistance · preparing a suggestion. You can keep editing or save.', {
      exact: true,
    }),
  ).toBeVisible();
  await checkpoint('g01-ai-running.png');
  state = 'succeeded';
  await expect(page.getByRole('button', { name: 'Use suggestion', exact: true })).toBeVisible();
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-wording-review.png');
  await page.getByRole('button', { name: 'Use suggestion', exact: true }).click();
  await expect(page.getByLabel('Context or module · optional', { exact: true })).toHaveValue(
    suggestion,
  );
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-applied-not-saved.png');
  await save(page);
  expect(goal.writes()[0]).toMatchObject({ context: suggestion });
  await checkpoint('g01-ai-explicit-goal-saved.png');
});

test('G01 catalogue advice offers captured area IDs without inventing a topic or automatic save', async ({
  page,
  checkpoint,
}: Scenario) => {
  const goal = await boundary(page);
  let requests = 0;
  await page.route('**/api/v1/ai/jobs', (route: Readonly<Route>) => {
    const body = submitted(route);
    requests += 1;
    expect(body.kind).toBe('suggest_subject');
    return route.fulfill({
      status: 202,
      json: response(body, {
        state: 'succeeded',
        poll_after_ms: null,
        result: { ids: requests === 1 ? [catalogue.items[1].id] : [] },
      }),
    });
  });
  await open(page);
  await page.getByRole('button', { name: 'Suggest a knowledge area', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Use Mathematics', exact: true })).toBeVisible();
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-captured-area-review.png');
  await page.getByRole('button', { name: 'Use Mathematics', exact: true }).click();
  await expect(page.getByLabel('Knowledge area', { exact: true })).toHaveValue('Mathematics');
  await expect(page.getByLabel('Task or topic · optional', { exact: true })).toHaveValue(
    'SQL JOINs',
  );
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-area-applied-unsaved.png');
  await page.getByRole('button', { name: 'Suggest a knowledge area', exact: true }).click();
  await expect(
    page.getByText('No knowledge area was suggested from this list. Choose one yourself.', {
      exact: true,
    }),
  ).toBeVisible();
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-empty-catalogue-advice.png');
});

test('G01 parent edits withdraw an older successful suggestion instead of overwriting fresh words', async ({
  page,
  checkpoint,
}: Scenario) => {
  const goal = await boundary(page);
  await page.route('**/api/v1/ai/jobs', (route: Readonly<Route>) =>
    route.fulfill({
      status: 202,
      json: response(submitted(route), {
        state: 'succeeded',
        poll_after_ms: null,
        result: { suggestion },
      }),
    }),
  );
  await open(page);
  await ask(page);
  await expect(page.getByRole('button', { name: 'Use suggestion', exact: true })).toBeVisible();
  await page
    .getByLabel('Context or module · optional', { exact: true })
    .fill('My newer context must stay.');
  await expect(
    page.getByText(
      'You changed the goal after asking. This suggestion was for the earlier version.',
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Use suggestion', exact: true })).toHaveCount(0);
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-source-changed.png');
  await page.getByRole('button', { name: 'Dismiss earlier suggestion', exact: true }).click();
  await expect(page.getByLabel('Context or module · optional', { exact: true })).toHaveValue(
    'My newer context must stay.',
  );
});

test('G01 lost admission is reconciled only by explicit identical request and idempotency key', async ({
  page,
  checkpoint,
}: Scenario) => {
  const goal = await boundary(page);
  let requests: readonly Readonly<{
    readonly body: GoalRequest;
    readonly key: string | undefined;
  }>[] = [];
  await page.route('**/api/v1/ai/jobs', async (route: Readonly<Route>) => {
    const body = submitted(route);
    requests = [...requests, { body, key: route.request().headers()['idempotency-key'] }];
    if (requests.length === 1) {
      await route.abort('failed');
      return;
    }
    expect(requests[1]).toEqual(requests[0]);
    await route.fulfill({
      status: 202,
      json: response(body, { state: 'succeeded', poll_after_ms: null, result: { suggestion } }),
    });
  });
  await open(page);
  await ask(page);
  await expect(
    page.getByRole('button', { name: 'Retry the same AI request', exact: true }),
  ).toBeVisible();
  expect(requests).toHaveLength(1);
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-admission-unknown.png');
  await page.getByRole('button', { name: 'Retry the same AI request', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Use suggestion', exact: true })).toBeVisible();
  expect(requests).toHaveLength(2);
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-identical-explicit-retry.png');
});

test('G01 owned queued cancellation uses an empty command and preserves manual goal text', async ({
  page,
  checkpoint,
}: Scenario) => {
  const goal = await boundary(page);
  let source: GoalRequest | null = null;
  let releaseCancellation: () => void = () => {
    throw new Error('Missing cancellation gate');
  };
  const cancelGate = new Promise<void>((resolve) => {
    releaseCancellation = resolve;
  });
  await page.route('**/api/v1/ai/jobs', (route: Readonly<Route>) => {
    source = submitted(route);
    return route.fulfill({ status: 202, json: response(source) });
  });
  await page.route(`**/api/v1/ai/jobs/${jobId}`, (route: Readonly<Route>) => {
    if (source === null) throw new Error('Missing source');
    return route.fulfill({ json: response(source) });
  });
  await page.route(`**/api/v1/ai/jobs/${jobId}/cancel`, async (route: Readonly<Route>) => {
    if (source === null) throw new Error('Missing source');
    expect(route.request().postData()).toBeNull();
    expect(route.request().headers()['idempotency-key']).toBeUndefined();
    await cancelGate;
    return route.fulfill({ json: response(source, { state: 'cancelled', poll_after_ms: null }) });
  });
  try {
    await open(page);
    await ask(page);
    await expect(page.getByRole('button', { name: 'Cancel AI job', exact: true })).toBeVisible();
    await checkpoint('g01-ai-cancel-available.png');
    await page.getByRole('button', { name: 'Cancel AI job', exact: true }).click();
    await expect(
      page.getByText('Checking cancellation… Your goal is unchanged.', { exact: true }),
    ).toBeVisible();
    await checkpoint('g01-ai-cancellation-pending.png');
    releaseCancellation();
    await expect(
      page.getByText('AI suggestion cancelled. Your goal is unchanged.', { exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel('Context or module · optional', { exact: true })).toHaveValue(
      'LEFT JOIN with NULLs gives duplicate rows.',
    );
    expect(goal.writes()).toHaveLength(0);
    await checkpoint('g01-ai-cancelled.png');
  } finally {
    releaseCancellation();
    await page.unrouteAll({ behavior: 'wait' });
  }
});

test('G01 uncertain cancellation requires a canonical check and may reveal a result that already won', async ({
  page,
  checkpoint,
}: Scenario) => {
  const goal = await boundary(page);
  let source: GoalRequest | null = null;
  let cancellationAttempted = false;
  await page.route('**/api/v1/ai/jobs', (route: Readonly<Route>) => {
    source = submitted(route);
    return route.fulfill({ status: 202, json: response(source) });
  });
  await page.route(`**/api/v1/ai/jobs/${jobId}/cancel`, (route: Readonly<Route>) => {
    cancellationAttempted = true;
    return route.abort('failed');
  });
  await page.route(`**/api/v1/ai/jobs/${jobId}`, (route: Readonly<Route>) => {
    if (source === null) throw new Error('Missing actual source');
    return route.fulfill({
      json: response(source, {
        state: cancellationAttempted ? 'succeeded' : 'queued',
        poll_after_ms: cancellationAttempted ? null : 100,
        result: cancellationAttempted ? { suggestion } : null,
      }),
    });
  });
  await open(page);
  await ask(page);
  await page.getByRole('button', { name: 'Cancel AI job', exact: true }).click();
  await expect(
    page.getByText('Cancellation isn’t confirmed. Check the job or retry cancellation.', {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Use suggestion', exact: true })).toHaveCount(0);
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-cancellation-unknown.png');
  await page.getByRole('button', { name: 'Check AI job', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Use suggestion', exact: true })).toBeVisible();
  await expect(
    page.getByText('AI suggestion cancelled. Your goal is unchanged.', { exact: true }),
  ).toHaveCount(0);
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-result-won-before-cancel.png');
});

test('G01 actual failed expired and quota responses leave the editable manual route intact', async ({
  page,
  checkpoint,
}: Scenario) => {
  const goal = await boundary(page);
  let attempt = 0;
  await page.route('**/api/v1/ai/jobs', (route: Readonly<Route>) => {
    const body = submitted(route);
    attempt += 1;
    if (attempt === 3) return route.fulfill({ status: 429, json: { code: 'ai_quota_exceeded' } });
    return route.fulfill({
      status: 202,
      json: response(body, {
        state: attempt === 1 ? 'failed' : 'expired',
        failure: 'timeout',
        poll_after_ms: null,
      }),
    });
  });
  await open(page);
  await ask(page);
  await expect(
    page.getByText('We couldn’t get a suggestion. You can ask again or keep writing yourself.', {
      exact: true,
    }),
  ).toBeVisible();
  await checkpoint('g01-ai-failed-manual-path.png');
  await page.getByRole('button', { name: 'Keep mine', exact: true }).click();
  await ask(page);
  await expect(
    page.getByText('This AI job expired. You can ask again or keep writing yourself.', {
      exact: true,
    }),
  ).toBeVisible();
  await checkpoint('g01-ai-expired-manual-path.png');
  await page.getByRole('button', { name: 'Keep mine', exact: true }).click();
  await ask(page);
  await expect(
    page.getByText('AI assistance is busy. You can write and save as usual, or try again later.', {
      exact: true,
    }),
  ).toBeVisible();
  expect(attempt).toBe(3);
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-quota-manual-path.png');
});

test('G01 changed returned source hash is rejected and only explicit job read retry recovers', async ({
  page,
  checkpoint,
}: Scenario) => {
  const goal = await boundary(page);
  let source: GoalRequest | null = null;
  let wrongHash = true;
  await page.route('**/api/v1/ai/jobs', (route: Readonly<Route>) => {
    source = submitted(route);
    return route.fulfill({ status: 202, json: response(source) });
  });
  await page.route(`**/api/v1/ai/jobs/${jobId}`, (route: Readonly<Route>) => {
    if (source === null) throw new Error('Missing admitted source');
    const current = response(source, {
      state: 'succeeded',
      result: { suggestion },
      poll_after_ms: null,
    });
    return route.fulfill({
      json: wrongHash
        ? { ...current, source: { ...current.source, kind: 'draft', content_hash: '0'.repeat(64) } }
        : current,
    });
  });
  await open(page);
  await ask(page);
  await expect(page.getByRole('button', { name: 'Check AI job again', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Use suggestion', exact: true })).toHaveCount(0);
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-wrong-hash-rejected.png');
  wrongHash = false;
  await page.getByRole('button', { name: 'Check AI job again', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Use suggestion', exact: true })).toBeVisible();
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-explicit-canonical-read-recovered.png');
});

test('G01 leaving the real Goal form retires a late admission without restoring an old suggestion', async ({
  page,
  checkpoint,
}: Scenario) => {
  const goal = await boundary(page);
  let release: () => void = () => {
    throw new Error('Missing admission gate');
  };
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/ai/jobs', async (route: Readonly<Route>) => {
    const body = submitted(route);
    await pending;
    await route.fulfill({
      status: 202,
      json: response(body, { state: 'succeeded', result: { suggestion }, poll_after_ms: null }),
    });
  });
  try {
    await open(page);
    await ask(page);
    await expect(
      page.getByText('Requesting AI assistance… Your text is unchanged.', { exact: true }),
    ).toBeVisible();
    await checkpoint('g01-ai-admission-pending.png');
    await page.getByRole('button', { name: 'Back to setup', exact: true }).click();
    await expect(page.getByRole('region', { name: 'AI assistance', exact: true })).toHaveCount(0);
    const completed = page.waitForResponse(
      (reply) => reply.url().endsWith('/api/v1/ai/jobs') && reply.status() === 202,
    );
    release();
    await completed;
    await page.getByRole('button', { name: 'Your study goal', exact: true }).click();
    await expect(
      page.getByRole('button', { name: 'Suggest clearer wording', exact: true }),
    ).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Use suggestion', exact: true })).toHaveCount(0);
    expect(goal.writes()).toHaveLength(0);
    await checkpoint('g01-ai-late-admission-retired.png');
  } finally {
    release();
    await page.unrouteAll({ behavior: 'wait' });
  }
});

test('G01 assistance reflows at 320px with 200 percent text and supports keyboard Apply without saving', async ({
  page,
  checkpoint,
}: Scenario) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const goal = await boundary(page);
  await page.route('**/api/v1/ai/jobs', (route: Readonly<Route>) =>
    route.fulfill({
      status: 202,
      json: response(submitted(route), {
        state: 'succeeded',
        result: { suggestion },
        poll_after_ms: null,
      }),
    }),
  );
  await open(page);
  await page.addStyleTag({ content: 'html { font-size: 200%; }' });
  await ask(page);
  const apply = page.getByRole('button', { name: 'Use suggestion', exact: true });
  await expect(apply).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await apply.focus();
  await expect(apply).toBeFocused();
  await checkpoint('g01-ai-reflow320-text200-keyboard.png');
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Context or module · optional', { exact: true })).toHaveValue(
    suggestion,
  );
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-keyboard-applied-unsaved.png');
});

test('G01 denied AI command revalidates the actual parent session and removes private advice', async ({
  page,
  checkpoint,
}: Scenario) => {
  const goal = await boundary(page);
  await page.route('**/api/v1/ai/jobs', (route: Readonly<Route>) => {
    submitted(route);
    return route.fulfill({ status: 403, json: { code: 'account_unavailable' } });
  });
  await open(page);
  await page.unroute('**/api/v1/me');
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({ status: 401, json: { code: 'unauthenticated' } }),
  );
  await ask(page);
  await expect(page.getByRole('link', { name: 'Continue with Google', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'AI assistance', exact: true })).toHaveCount(0);
  expect(goal.writes()).toHaveLength(0);
  await checkpoint('g01-ai-expired-parent-session.png');
});
