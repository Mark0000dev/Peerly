import type { Page, Response, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import {
  prepareOperatorFixture,
  changeOperatorFixtureGrant,
  readOperatorFixtureAudit,
} from '../../../../testing/operator-fixture';
import { isGoals, isGoalHistory, isHelpHistory } from './operator-academic-contract';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}>;
function required<T>(value: T | undefined): T {
  if (value === undefined) throw new Error('Missing retained academic fixture record');
  return value;
}
function response(page: Readonly<Page>, path: string): Promise<Response> {
  return page.waitForResponse((value) => new URL(value.url()).pathname === path);
}
async function actual<T>(
  value: Readonly<Response>,
  guard: (body: unknown) => body is T,
): Promise<T> {
  expect(value.status()).toBe(200);
  expect(value.headers()['cache-control']).toContain('no-store');
  const body: unknown = await value.json();
  if (!guard(body)) throw new Error('Malformed actual academic response');
  return body;
}
async function goals(page: Readonly<Page>, account: string, extra = '') {
  const loaded = response(page, `/api/v1/operator/accounts/${account}/goals`);
  await page.goto(`/operator/accounts?account=${account}&tab=goals${extra}`);
  const body = await actual(await loaded, isGoals);
  expect(body.account_id).toBe(account);
  await expect(page.getByRole('region', { name: 'Goal records', exact: true })).toBeVisible();
  return body;
}
async function activeRoot(page: Readonly<Page>, account: string) {
  const body = await goals(page, account, '&goal_state=active');
  expect(body.goals).toHaveLength(1);
  const root = body.goals.find((value) => value.completed_at === null);
  if (root === undefined) throw new Error('Missing retained active goal');
  await expect(
    page.getByRole('button', { name: `Inspect goal ${root.id}`, exact: true }),
  ).toBeVisible();
  return root;
}

test('real M04 academic pages retained roots and exact goal/help revisions without implicit fanout', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'academic', info.project.name);
  const account = seed.targets.active;
  const base = `/api/v1/operator/accounts/${account}`;
  let successes = 0;
  let histories = 0;
  page.on('response', (value) => {
    const path = new URL(value.url()).pathname;
    if (path.startsWith('/api/v1/operator/') && value.status() === 200) successes += 1;
    if (path.endsWith('/history')) histories += 1;
  });
  const identity = response(page, '/api/v1/me');
  const first = await goals(page, account);
  expect((await identity).status()).toBe(200);
  const viewer: unknown = await (await identity).json();
  expect(viewer).toMatchObject({
    account_id: seed.operatorId,
    capabilities: { can_use_student_features: false },
  });
  expect(first.goals).toHaveLength(50);
  expect(first.next_cursor).not.toBeNull();
  await expect(page.getByRole('button', { name: /^Inspect goal / })).toHaveCount(50);
  expect(histories).toBe(0);
  const olderRoots = response(page, `${base}/goals`);
  await page.getByRole('button', { name: 'Next goals', exact: true }).click();
  const second = await actual(await olderRoots, isGoals);
  expect(second.goals).toHaveLength(3);
  expect(second.next_cursor).toBeNull();
  expect(new Set([...first.goals, ...second.goals].map((value) => value.id)).size).toBe(53);
  await expect(page.getByRole('button', { name: /^Inspect goal / })).toHaveCount(3);
  await checkpoint('real-academic-goals-older.png');
  const filtered = response(page, `${base}/goals`);
  const form = page.getByRole('form', { name: 'Goal filters', exact: true });
  await form
    .getByRole('combobox', { name: 'State', exact: true })
    .selectOption({ label: 'active' });
  await form.getByRole('button', { name: 'Apply filters', exact: true }).click();
  const active = await actual(await filtered, isGoals);
  expect(active.goals).toHaveLength(1);
  const root = required(active.goals.find((value) => value.completed_at === null));
  expect(root.current_version).toBe(53);
  await expect(page).not.toHaveURL(/goals_cursor=/);
  await expect(
    page.getByRole('button', { name: `Inspect goal ${root.id}`, exact: true }),
  ).toBeVisible();
  await checkpoint('real-academic-goal-active.png');
  const historyPath = `${base}/goals/${root.id}/history`;
  const history = response(page, historyPath);
  await page.getByRole('button', { name: `Inspect goal ${root.id}`, exact: true }).click();
  const head = await actual(await history, isGoalHistory);
  expect(head.goal.id).toBe(root.id);
  expect(head.revisions.map((value) => value.version)).toEqual(
    Array.from({ length: 50 }, (_, index) => 53 - index),
  );
  expect(head.anchor_version).toBe(53);
  await expect(
    page
      .getByRole('region', { name: 'Goal history', exact: true })
      .getByRole('heading', { level: 3 }),
  ).toHaveCount(50);
  const olderHistory = response(page, historyPath);
  await page.getByRole('button', { name: 'Older goal revisions', exact: true }).click();
  const tail = await actual(await olderHistory, isGoalHistory);
  expect(tail.revisions.map((value) => value.version)).toEqual([3, 2, 1]);
  expect(tail.next_cursor).toBeNull();
  const historyPanel = page.getByRole('region', { name: 'Goal history', exact: true });
  await expect(historyPanel.getByRole('heading', { level: 3 })).toHaveText([
    'Revision 3',
    'Revision 2',
    'Revision 1',
  ]);
  await expect(historyPanel).toContainText('Saved literal <b>revision 1</b>');
  await expect(historyPanel.locator('b')).toHaveCount(0);
  await checkpoint('real-academic-goal-history-older.png');
  const help = response(page, `${base}/help-history`);
  await page.getByRole('tab', { name: 'Help', exact: true }).click();
  const helpHead = await actual(await help, isHelpHistory);
  expect(helpHead.account_id).toBe(account);
  expect(helpHead.revisions).toHaveLength(50);
  expect(helpHead.anchor_version).toBe(53);
  const clear = required(helpHead.revisions.find((value) => value.version === 53));
  const saved = required(helpHead.revisions.find((value) => value.version === 52));
  expect(clear.selections).toEqual([]);
  expect(saved.selections.map((value) => [value.slot, value.subject_label])).toEqual([
    [0, 'Stored SQL before catalogue rename'],
    [1, 'Stored Calculus'],
  ]);
  const helpPanel = page.getByRole('region', { name: 'Help history', exact: true });
  await expect(helpPanel.getByRole('heading', { level: 3 })).toHaveCount(50);
  const clearRow = helpPanel
    .getByRole('listitem')
    .filter({ has: page.getByRole('heading', { name: 'Revision 53', exact: true }) });
  await expect(clearRow).toContainText('Stored clear');
  await checkpoint('real-academic-help-clear.png');
  const olderHelp = response(page, `${base}/help-history`);
  await page.getByRole('button', { name: 'Older help revisions', exact: true }).click();
  const helpTail = await actual(await olderHelp, isHelpHistory);
  expect(helpTail.revisions.map((value) => value.version)).toEqual([3, 2, 1]);
  expect(helpTail.next_cursor).toBeNull();
  await expect(helpPanel.getByRole('heading', { level: 3 })).toHaveText([
    'Revision 3',
    'Revision 2',
    'Revision 1',
  ]);
  const savedRow = helpPanel
    .getByRole('listitem')
    .filter({ has: page.getByRole('heading', { name: 'Revision 3', exact: true }) });
  await expect(savedRow).toContainText('Stored SQL before catalogue rename');
  await expect(savedRow).toContainText('Stored Calculus');
  const rendered = await savedRow.locator('dd').allTextContents();
  expect(rendered.indexOf('Stored SQL before catalogue rename')).toBeLessThan(
    rendered.indexOf('Stored Calculus'),
  );
  await checkpoint('real-academic-help-older.png');
  for (const [state, id] of [
    ['hidden', seed.targets.hidden],
    ['banned', seed.targets.banned],
    ['deleted', seed.targets.deleted],
  ] as const) {
    const retained = await activeRoot(page, id);
    expect(retained.account_id).toBe(id);
    await checkpoint(`real-academic-retained-${state}.png`);
  }
  const audit = await readOperatorFixtureAudit(page, seed.operatorId);
  expect(audit.audits).toBe(successes);
  expect(audit.audits).toBeGreaterThanOrEqual(10);
  expect(audit.linkedEvents).toBe(audit.audits);
});

test('real M04 academic empty history sources and missing goal stay distinct from access denial', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'academic-empty', info.project.name);
  const account = seed.targets.nullable;
  const base = `/api/v1/operator/accounts/${account}`;
  const roots = await goals(page, account);
  expect(roots.goals).toEqual([]);
  expect(roots.next_cursor).toBeNull();
  await expect(page.getByText('No stored goals match these filters.')).toBeVisible();
  await checkpoint('real-academic-goals-empty.png');
  const help = response(page, `${base}/help-history`);
  await page.getByRole('tab', { name: 'Help', exact: true }).click();
  const body = await actual(await help, isHelpHistory);
  expect(body.revisions).toEqual([]);
  expect(body.anchor_version).toBe(0);
  await expect(page.getByText('No stored help revisions.')).toBeVisible();
  await expect(page.getByText(/Stored clear/)).toHaveCount(0);
  await checkpoint('real-academic-help-empty.png');
  const missing = response(page, `${base}/goals/00000000-0000-4000-8000-000000000099/history`);
  await page.goto(
    `/operator/accounts?account=${account}&tab=goals&goal=00000000-0000-4000-8000-000000000099`,
  );
  expect((await missing).status()).toBe(404);
  await expect(
    page.getByRole('region', { name: 'Goal history', exact: true }).getByRole('alert'),
  ).toContainText('academic record is unavailable');
  await expect(page.getByRole('region', { name: 'Goal records', exact: true })).toContainText(
    'No stored goals',
  );
  await checkpoint('real-academic-goal-unavailable.png');
  const audit = await readOperatorFixtureAudit(page, seed.operatorId);
  expect(audit.audits).toBeGreaterThanOrEqual(3);
  expect(audit.linkedEvents).toBe(audit.audits);
});

test('real M04 academic child grant revocation retires prior roots and explicit restore reads actual history', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'academic-revocation', info.project.name);
  const account = seed.targets.active;
  const root = await activeRoot(page, account);
  const before = await readOperatorFixtureAudit(page, seed.operatorId);
  await changeOperatorFixtureGrant(page, seed.operatorId, false);
  const path = `/api/v1/operator/accounts/${account}/goals/${root.id}/history`;
  const denied = response(page, path);
  await page.getByRole('button', { name: `Inspect goal ${root.id}`, exact: true }).click();
  expect((await denied).status()).toBe(403);
  await expect(page.getByRole('alert')).toContainText('Operator access denied');
  await expect(page.getByRole('region', { name: 'Goal records', exact: true })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Goal history', exact: true })).toHaveCount(0);
  await checkpoint('real-academic-revoked.png');
  expect((await readOperatorFixtureAudit(page, seed.operatorId)).audits).toBe(before.audits);
  await changeOperatorFixtureGrant(page, seed.operatorId, true);
  const restored = response(page, path);
  await page.getByRole('button', { name: 'Check access again', exact: true }).click();
  const head = await actual(await restored, isGoalHistory);
  expect(head.goal.id).toBe(root.id);
  const older = response(page, path);
  await page.getByRole('button', { name: 'Older goal revisions', exact: true }).click();
  const tail = await actual(await older, isGoalHistory);
  expect(tail.revisions.map((value) => value.version)).toEqual([3, 2, 1]);
  await expect(page.getByRole('region', { name: 'Goal history', exact: true })).toContainText(
    'Saved literal <b>revision 1</b>',
  );
  await checkpoint('real-academic-restored-history.png');
  const after = await readOperatorFixtureAudit(page, seed.operatorId);
  expect(after.audits).toBeGreaterThan(before.audits);
  expect(after.linkedEvents).toBe(after.audits);
});

test('real M04 academic replacement actor resets real history cursor and owns subsequent audited reads', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'academic-replacement', info.project.name);
  const account = seed.targets.active;
  const root = await activeRoot(page, account);
  const path = `/api/v1/operator/accounts/${account}/goals/${root.id}/history`;
  const first = response(page, path);
  await page.getByRole('button', { name: `Inspect goal ${root.id}`, exact: true }).click();
  await actual(await first, isGoalHistory);
  const older = response(page, path);
  await page.getByRole('button', { name: 'Older goal revisions', exact: true }).click();
  await actual(await older, isGoalHistory);
  await expect(page).toHaveURL(/goal_cursor=/);
  await changeOperatorFixtureGrant(page, seed.operatorId, false);
  const denied = response(page, `/api/v1/operator/accounts/${account}/goals`);
  await page.getByRole('button', { name: 'Refresh goals', exact: true }).click();
  expect((await denied).status()).toBe(403);
  await expect(page.getByRole('alert')).toContainText('Operator access denied');
  await expect(page).toHaveURL(/goal_cursor=/);
  const old = await readOperatorFixtureAudit(page, seed.operatorId);
  await seed.replaceActor();
  const identity = response(page, '/api/v1/me');
  const replaced = response(page, path);
  await page.getByRole('button', { name: 'Check access again', exact: true }).click();
  const viewer: unknown = await (await identity).json();
  expect(viewer).toMatchObject({ account_id: seed.replacementId });
  const value = await replaced;
  expect(new URL(value.url()).searchParams.get('cursor')).toBeNull();
  await actual(value, isGoalHistory);
  await expect(page).not.toHaveURL(/goal_cursor=/);
  const last = response(page, path);
  await page.getByRole('button', { name: 'Older goal revisions', exact: true }).click();
  await actual(await last, isGoalHistory);
  await expect(page.getByRole('region', { name: 'Goal history', exact: true })).toContainText(
    'Saved literal <b>revision 1</b>',
  );
  await checkpoint('real-academic-replacement-history.png');
  const current = await readOperatorFixtureAudit(page, seed.replacementId);
  expect(current.audits).toBeGreaterThanOrEqual(3);
  expect(current.linkedEvents).toBe(current.audits);
  expect((await readOperatorFixtureAudit(page, seed.operatorId)).audits).toBe(old.audits);
});
