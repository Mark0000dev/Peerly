import type { Page, Route } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { account, accounts, detail, operatorIdentity } from './operator.fixtures';
import {
  academicGoal,
  academicGoals,
  academicRevision,
  academicHistory,
  academicHelp,
  academicSelection,
} from './operator-academic.fixtures';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}>;
const target = `/api/v1/operator/accounts/${account.account_id}`;
const roots = `${target}/goals`;
const history = `${roots}/${academicGoal.id}/history`;
const help = `${target}/help-history`;
async function setup(page: Readonly<Page>): Promise<void> {
  await page.clock.setFixedTime(new Date('2026-11-08T06:20:00Z'));
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({ json: operatorIdentity }),
  );
  await page.route('**/api/v1/operator/accounts?*', (route: Readonly<Route>) =>
    route.fulfill({ json: accounts }),
  );
  await page.route(`**${target}`, (route: Readonly<Route>) => route.fulfill({ json: detail }));
  await page.route(`**${roots}?*`, (route: Readonly<Route>) =>
    route.fulfill({ json: academicGoals }),
  );
  await page.route(`**${history}?*`, (route: Readonly<Route>) =>
    route.fulfill({ json: academicHistory }),
  );
  await page.route(`**${help}?*`, (route: Readonly<Route>) =>
    route.fulfill({ json: academicHelp }),
  );
}
async function open(page: Readonly<Page>, tab: 'goals' | 'help', extra = ''): Promise<void> {
  await page.goto(`/operator/accounts?account=${account.account_id}&tab=${tab}${extra}`);
  await expect(
    page.getByRole('heading', { name: 'Operator · accounts', exact: true }),
  ).toBeVisible();
}
function release(value: (() => void) | undefined): void {
  if (value === undefined) throw new Error('Missing boundary release');
  value();
}

test('M04 academic roots are metadata only and goal history is explicit safe stored text', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${roots}?*`, (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...academicGoals,
        goals: [
          academicGoal,
          {
            ...academicGoal,
            id: '00000000-0000-4000-8000-000000000023',
            completed_at: academicRevision.saved_at,
          },
        ],
      },
    }),
  );
  let histories = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.endsWith('/history')) histories += 1;
  });
  await open(page, 'goals');
  await expect(page.getByRole('region', { name: 'Goal records', exact: true })).toContainText(
    'Completed at',
  );
  await expect(page.getByText(academicRevision.subject_label, { exact: true })).toHaveCount(0);
  expect(histories).toBe(0);
  await checkpoint('academic-goal-roots.png');
  await page.getByRole('button', { name: `Inspect goal ${academicGoal.id}`, exact: true }).click();
  const panel = page.getByRole('region', { name: 'Goal history', exact: true });
  await expect(panel).toContainText(academicRevision.subject_label);
  await expect(panel).toContainText('ARCHIVE:key/unchanged');
  await expect(panel.locator('b')).toHaveCount(0);
  expect(histories).toBe(1);
  await expect(page).toHaveURL(new RegExp(`goal=${academicGoal.id}`));
  await checkpoint('academic-goal-history-literal.png');
});

test('M04 academic empty roots history and help are distinct stored absence', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${roots}?*`, (route: Readonly<Route>) =>
    route.fulfill({
      json: { ...academicGoals, goals: [], anchor_created_at: null, anchor_goal_id: null },
    }),
  );
  await page.route(`**${history}?*`, (route: Readonly<Route>) =>
    route.fulfill({ json: { ...academicHistory, revisions: [] } }),
  );
  await page.route(`**${help}?*`, (route: Readonly<Route>) =>
    route.fulfill({ json: { ...academicHelp, anchor_version: 0, revisions: [] } }),
  );
  await open(page, 'goals');
  await expect(page.getByText('No stored goals match these filters.')).toBeVisible();
  await checkpoint('academic-goals-empty.png');
  await open(page, 'goals', `&goal=${academicGoal.id}`);
  await expect(page.getByText('No stored goal revisions on this page.')).toBeVisible();
  await checkpoint('academic-history-empty.png');
  await page.getByRole('tab', { name: 'Help', exact: true }).click();
  await expect(page.getByText('No stored help revisions.')).toBeVisible();
  await expect(page.getByText(/Stored clear/)).toHaveCount(0);
  await checkpoint('academic-help-empty.png');
});

test('M04 academic help keeps stored clear slot ordering and historical literal facts', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${help}?*`, (route: Readonly<Route>) =>
    route.fulfill({
      json: {
        ...academicHelp,
        revisions: [
          ...academicHelp.revisions.filter((revision) => revision.version === 2),
          {
            account_id: account.account_id,
            version: 1,
            saved_at: academicRevision.saved_at,
            selections: [
              academicSelection,
              {
                ...academicSelection,
                slot: 1,
                subject_id: academicGoal.id,
                subject_label: 'Second archived label',
                topic_note: null,
                topic_match_key: null,
              },
            ],
          },
        ],
      },
    }),
  );
  await open(page, 'help');
  const panel = page.getByRole('region', { name: 'Help history', exact: true });
  await expect(panel).toContainText('Stored clear');
  await expect(panel).toContainText('Historical SQL <literal>');
  await expect(panel).toContainText('old:KEY');
  await expect(panel.locator('h3')).toHaveText(['Revision 2', 'Revision 1']);
  await expect(panel.locator('b')).toHaveCount(0);
  await checkpoint('academic-help-clear-history.png');
});

test('M04 academic root filters are explicit and reset opaque page and selected goal', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${roots}?*`, (route: Readonly<Route>) => {
    const params = new URL(route.request().url()).searchParams;
    return route.fulfill({
      json: {
        ...academicGoals,
        goals: [
          {
            ...academicGoal,
            id: params.has('cursor') ? '00000000-0000-4000-8000-000000000023' : academicGoal.id,
            created_at: params.has('cursor') ? '2024-12-15T00:00:00Z' : academicGoal.created_at,
            completed_at: params.get('state') === 'completed' ? academicRevision.saved_at : null,
          },
        ],
        next_cursor: params.has('cursor') ? null : 'opaque +/=',
      },
    });
  });
  await open(page, 'goals');
  await expect(page.getByRole('button', { name: 'Next goals', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Next goals', exact: true }).click();
  await expect(page).toHaveURL(/goals_cursor=/);
  await expect(page.getByRole('button', { name: 'First goals page', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Goal records', exact: true })).toContainText(
    '00000000-0000-4000-8000-000000000023',
  );
  await checkpoint('academic-goals-next.png');
  const form = page.getByRole('form', { name: 'Goal filters', exact: true });
  await form
    .getByRole('combobox', { name: 'State', exact: true })
    .selectOption({ label: 'completed' });
  await form
    .getByRole('textbox', { name: 'Created from', exact: true })
    .fill('2025-01-01T00:00:00Z');
  await form
    .getByRole('textbox', { name: 'Created before', exact: true })
    .fill('2026-01-01T00:00:00Z');
  await form.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await expect(page).toHaveURL(/goal_state=completed/);
  await expect(page).not.toHaveURL(/goals_cursor=/);
  await expect(page.getByRole('region', { name: 'Goal records', exact: true })).toContainText(
    'Completed at',
  );
  await checkpoint('academic-goals-filtered.png');
});

test('M04 academic invalid URL and form filters block accidental broad inspection', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let reads = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === roots) reads += 1;
  });
  await open(page, 'goals', '&goal=invalid');
  await expect(page.getByRole('alert')).toContainText('must be a UUID');
  expect(reads).toBe(0);
  await checkpoint('academic-invalid-url.png');
  await page.getByRole('button', { name: 'Reset academic filters', exact: true }).click();
  await expect(
    page.getByRole('button', { name: `Inspect goal ${academicGoal.id}`, exact: true }),
  ).toBeVisible();
  const before = reads;
  const form = page.getByRole('form', { name: 'Goal filters', exact: true });
  await form.getByRole('textbox', { name: 'Created from', exact: true }).fill('not-aware');
  await form.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await expect(form.getByRole('alert')).toContainText('timezone');
  expect(reads).toBe(before);
  await checkpoint('academic-invalid-form.png');
});

test('M04 academic roots503 retry and goal404 remain local and honest', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let failed = true;
  await page.route(`**${roots}?*`, (route: Readonly<Route>) =>
    failed
      ? route.fulfill({ status: 503, json: { code: 'unavailable' } })
      : route.fulfill({ json: academicGoals }),
  );
  await page.route(`**${history}?*`, (route: Readonly<Route>) =>
    route.fulfill({ status: 404, json: { code: 'operator_resource_unavailable' } }),
  );
  await open(page, 'goals');
  await expect(page.getByRole('alert')).toContainText('records could not be loaded');
  await checkpoint('academic-goals-service-error.png');
  failed = false;
  await page.getByRole('button', { name: 'Retry goals', exact: true }).click();
  await expect(
    page.getByRole('button', { name: `Inspect goal ${academicGoal.id}`, exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: `Inspect goal ${academicGoal.id}`, exact: true }).click();
  await expect(
    page.getByRole('region', { name: 'Goal history', exact: true }).getByRole('alert'),
  ).toContainText('academic record is unavailable');
  await expect(page.getByRole('region', { name: 'Goal records', exact: true })).toContainText(
    academicGoal.id,
  );
  await checkpoint('academic-history-unavailable.png');
});

test('M04 academic history cursor422 resets without inferring end or losing selected root', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${history}?*`, (route: Readonly<Route>) =>
    new URL(route.request().url()).searchParams.has('cursor')
      ? route.fulfill({ status: 422, json: { code: 'validation_failed' } })
      : route.fulfill({ json: { ...academicHistory, next_cursor: 'older-goal/+' } }),
  );
  await open(page, 'goals', `&goal=${academicGoal.id}`);
  await expect(
    page.getByRole('button', { name: 'Older goal revisions', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Older goal revisions', exact: true }).click();
  await expect(
    page.getByRole('region', { name: 'Goal history', exact: true }).getByRole('alert'),
  ).toContainText('cursor could not be used');
  await checkpoint('academic-history-cursor-invalid.png');
  await page.getByRole('button', { name: 'First goal history page', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Goal history', exact: true })).toContainText(
    academicRevision.subject_label,
  );
  await expect(page).toHaveURL(new RegExp(`goal=${academicGoal.id}`));
  await expect(page).not.toHaveURL(/goal_cursor=/);
  await checkpoint('academic-history-cursor-reset.png');
});

test('M04 academic help503 retry then opaque history page distinguishes saved clear', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let failed = true;
  await page.route(`**${help}?*`, (route: Readonly<Route>) =>
    failed
      ? route.fulfill({ status: 503, json: { code: 'unavailable' } })
      : route.fulfill({
          json: {
            ...academicHelp,
            revisions: academicHelp.revisions.filter(
              (revision) =>
                revision.version ===
                (new URL(route.request().url()).searchParams.has('cursor') ? 1 : 2),
            ),
            next_cursor: new URL(route.request().url()).searchParams.has('cursor')
              ? null
              : 'older-help/+',
          },
        }),
  );
  await open(page, 'help');
  await expect(page.getByRole('alert')).toContainText('records could not be loaded');
  await checkpoint('academic-help-service-error.png');
  failed = false;
  await page.getByRole('button', { name: 'Retry help history', exact: true }).click();
  await expect(page.getByText(/Stored clear/)).toBeVisible();
  await page.getByRole('button', { name: 'Older help revisions', exact: true }).click();
  await expect(page).toHaveURL(/help_cursor=/);
  await expect(
    page.getByRole('button', { name: 'First help history page', exact: true }),
  ).toBeVisible();
  await expect(page.getByText('Historical SQL <literal>', { exact: true })).toBeVisible();
  await expect(page.getByText(/Stored clear/)).toHaveCount(0);
  await checkpoint('academic-help-older.png');
});

test('M04 academic child403 retires cached parents and pending root without late reveal', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let finish: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    finish = resolve;
  });
  let entered: (() => void) | undefined;
  const started = new Promise<void>((resolve) => {
    entered = resolve;
  });
  let finished: (() => void) | undefined;
  const completed = new Promise<void>((resolve) => {
    finished = resolve;
  });
  await page.route(`**${roots}?*`, async (route: Readonly<Route>) => {
    release(entered);
    await held;
    await route.fulfill({ json: academicGoals });
    release(finished);
  });
  await page.route(`**${history}?*`, async (route: Readonly<Route>) => {
    await started;
    await route.fulfill({ status: 403, json: { code: 'operator_access_denied' } });
  });
  await open(page, 'goals', `&lifecycle=all&goal=${academicGoal.id}`);
  await expect(page.getByRole('alert')).toContainText('Operator access denied');
  release(finish);
  await completed;
  await expect(page.getByRole('region', { name: 'Account results', exact: true })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Goal history', exact: true })).toHaveCount(0);
  await expect(page.getByText('Maya Lee', { exact: true })).toHaveCount(0);
  await checkpoint('academic-child-denied.png');
});

test('M04 academic child401 retires records and uses canonical Google session recheck', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.route(`**${help}?*`, (route: Readonly<Route>) =>
    route.fulfill({ status: 401, json: { code: 'unauthenticated' } }),
  );
  let identities = 0;
  await page.route('**/api/v1/me', (route: Readonly<Route>) => {
    identities += 1;
    return identities === 1
      ? route.fulfill({ json: operatorIdentity })
      : route.fulfill({ status: 401, json: { code: 'unauthenticated' } });
  });
  await open(page, 'help');
  await expect(
    page.getByRole('heading', { name: 'Sign in with your operator Google account', exact: true }),
  ).toBeVisible();
  expect(identities).toBe(2);
  await expect(page.getByRole('region', { name: 'Help history', exact: true })).toHaveCount(0);
  await checkpoint('academic-child-expired.png');
});

test('M04 academic actor replacement clears old cursor and cannot reuse denied history', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let replacement = false;
  let deny = false;
  await page.route('**/api/v1/me', (route: Readonly<Route>) =>
    route.fulfill({
      json: replacement
        ? { ...operatorIdentity, account_id: '00000000-0000-4000-8000-000000000099' }
        : operatorIdentity,
    }),
  );
  await page.route(`**${help}?*`, (route: Readonly<Route>) =>
    deny && !replacement
      ? route.fulfill({ status: 403, json: { code: 'operator_access_denied' } })
      : route.fulfill({
          json: {
            ...academicHelp,
            revisions: academicHelp.revisions.filter((revision) => revision.version === 2),
            next_cursor: 'deny-actor-page',
          },
        }),
  );
  await open(page, 'help', '&help_cursor=old-actor-page');
  await expect(page.getByText(/Stored clear/)).toBeVisible();
  deny = true;
  await page.getByRole('button', { name: 'Older help revisions', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Operator access denied');
  replacement = true;
  const loaded = page.waitForResponse((response) => new URL(response.url()).pathname === help);
  await page.getByRole('button', { name: 'Check access again', exact: true }).click();
  expect(new URL((await loaded).url()).searchParams.get('cursor')).toBeNull();
  await expect(page.getByText(/Stored clear/)).toBeVisible();
  await expect(page).not.toHaveURL(/help_cursor=/);
  await checkpoint('academic-actor-replacement.png');
});

test('MX academic320 text200 keyboard keeps public controls labels and stored facts visible', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.setViewportSize({ width: 320, height: 800 });
  await open(page, 'goals');
  const form = page.getByRole('form', { name: 'Goal filters', exact: true });
  await form.getByRole('textbox', { name: 'Created from', exact: true }).focus();
  await page.keyboard.type('2025-01-01T00:00:00Z');
  await expect(form.getByRole('textbox', { name: 'Created from', exact: true })).toBeFocused();
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  await form.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await expect(
    page.getByRole('button', { name: `Inspect goal ${academicGoal.id}`, exact: true }),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 320)).toBe(true);
  expect(
    await form
      .locator('label')
      .evaluateAll((elements: readonly Readonly<HTMLElement>[]) =>
        elements.every(
          (element: Readonly<HTMLElement>) => element.scrollWidth <= element.clientWidth,
        ),
      ),
  ).toBe(true);
  const geometry = async (name: string) =>
    page.getByRole('tab', { name, exact: true }).evaluate((button: Readonly<HTMLElement>) => {
      const tabs = button.closest('tui-tabs');
      if (!(tabs instanceof HTMLElement)) throw new Error('Missing public tablist');
      const range = document.createRange();
      range.selectNodeContents(button);
      const label = range.getBoundingClientRect();
      const container = tabs.getBoundingClientRect();
      return {
        labelVisible:
          label.left >= Math.max(0, container.left) &&
          label.right <= Math.min(320, container.right),
        focused: document.activeElement === button,
        selected: button.getAttribute('aria-selected') === 'true',
        scrollLeft: tabs.scrollLeft,
        scrollWidth: tabs.scrollWidth,
        clientWidth: tabs.clientWidth,
      };
    });
  await test.info().attach('tabs-before-keyboard', {
    body: JSON.stringify(await geometry('Goals')),
    contentType: 'application/json',
  });
  expect((await geometry('Goals')).labelVisible).toBe(true);
  await page.getByRole('tab', { name: 'Goals', exact: true }).focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('tab', { name: 'Help', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('region', { name: 'Help history', exact: true })).toContainText(
    'Historical SQL <literal>',
  );
  const helpGeometry = await geometry('Help');
  expect(helpGeometry.labelVisible).toBe(true);
  expect(helpGeometry.selected).toBe(true);
  expect(helpGeometry.focused).toBe(true);
  await test.info().attach('tabs-help-after-keyboard', {
    body: JSON.stringify(helpGeometry),
    contentType: 'application/json',
  });
  await checkpoint('academic-320-help-text200.png');
  await page.keyboard.press('ArrowUp');
  await expect(page.getByRole('tab', { name: 'Goals', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('region', { name: 'Goal records', exact: true })).toContainText(
    academicGoal.id,
  );
  const goalsGeometry = await geometry('Goals');
  expect(goalsGeometry.labelVisible).toBe(true);
  expect(goalsGeometry.selected).toBe(true);
  expect(goalsGeometry.focused).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= 320)).toBe(true);
  await test.info().attach('tabs-goals-after-keyboard', {
    body: JSON.stringify(goalsGeometry),
    contentType: 'application/json',
  });
  await checkpoint('academic-320-text200.png');
});

test('M04 academic loading panels complete into actual records after each explicit selection', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  let rootsReady: (() => void) | undefined;
  let historyReady: (() => void) | undefined;
  let helpReady: (() => void) | undefined;
  const rootsHeld = new Promise<void>((resolve) => {
    rootsReady = resolve;
  });
  const historyHeld = new Promise<void>((resolve) => {
    historyReady = resolve;
  });
  const helpHeld = new Promise<void>((resolve) => {
    helpReady = resolve;
  });
  await page.route(`**${roots}?*`, async (route: Readonly<Route>) => {
    await rootsHeld;
    await route.fulfill({ json: academicGoals });
  });
  await page.route(`**${history}?*`, async (route: Readonly<Route>) => {
    await historyHeld;
    await route.fulfill({ json: academicHistory });
  });
  await page.route(`**${help}?*`, async (route: Readonly<Route>) => {
    await helpHeld;
    await route.fulfill({ json: academicHelp });
  });
  await open(page, 'goals');
  await expect(page.getByRole('status')).toHaveText('Loading goals…');
  await checkpoint('academic-goals-loading.png');
  release(rootsReady);
  await page.getByRole('button', { name: `Inspect goal ${academicGoal.id}`, exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Loading goal history…');
  await checkpoint('academic-history-loading.png');
  release(historyReady);
  await expect(page.getByRole('region', { name: 'Goal history', exact: true })).toContainText(
    academicRevision.subject_label,
  );
  await page.getByRole('tab', { name: 'Help', exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Loading help history…');
  await checkpoint('academic-help-loading.png');
  release(helpReady);
  await expect(page.getByRole('region', { name: 'Help history', exact: true })).toContainText(
    'Historical SQL <literal>',
  );
  await checkpoint('academic-help-loaded.png');
});

test('MX academic initial active caption stays readable on direct scaled records links', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page);
  await page.setViewportSize({ width: 320, height: 800 });
  await page.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      document.documentElement.style.setProperty('font-size', '200%');
    });
  });
  for (const [tab, caption, query] of [
    ['goals', 'Goals', 'goals'],
    ['help', 'Help', 'help'],
    ['overview', 'Overview', 'overview'],
    ['goal-history', 'Goals', `goals&goal=${academicGoal.id}`],
  ] as const) {
    await page.goto(`/operator/accounts?account=${account.account_id}&tab=${query}`);
    const active = page.getByRole('tab', { name: caption, exact: true });
    await expect(active).toHaveAttribute('aria-selected', 'true');
    await expect
      .poll(() =>
        active.evaluate((button: Readonly<HTMLElement>) => {
          const container = button.closest('tui-tabs');
          if (!(container instanceof HTMLElement)) throw new Error('Missing public tabs');
          const range = document.createRange();
          range.selectNodeContents(button);
          const label = range.getBoundingClientRect();
          const bounds = container.getBoundingClientRect();
          return (
            label.width > 0 &&
            label.left >= Math.max(0, bounds.left) &&
            label.right <= Math.min(320, bounds.right)
          );
        }),
      )
      .toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= 320)).toBe(true);
    await expect(page.getByRole('status')).toHaveCount(0);
    await expect
      .poll(() =>
        page.getByRole('button').evaluateAll((buttons: readonly Readonly<HTMLElement>[]) =>
          buttons.flatMap((button) => {
            const bounds = button.getBoundingClientRect();
            if (bounds.width === 0 || bounds.height === 0) return [];
            const texts = document.createTreeWalker(button, NodeFilter.SHOW_TEXT);
            let text = texts.nextNode();
            while (text !== null) {
              if ((text.textContent ?? '').trim().length > 0) {
                const range = document.createRange();
                range.selectNodeContents(text);
                const clipped = Array.from(range.getClientRects()).some(
                  (rect: Readonly<DOMRect>) =>
                    rect.left < Math.max(0, bounds.left) ||
                    rect.right > Math.min(320, bounds.right),
                );
                if (clipped)
                  return [
                    { label: button.textContent.trim(), font: getComputedStyle(button).fontSize },
                  ];
              }
              text = texts.nextNode();
            }
            return [];
          }),
        ),
      )
      .toEqual([]);
    await expect
      .poll(() =>
        page
          .locator('app-operator-overview')
          .locator('dt, dd, h3')
          .evaluateAll((facts: readonly Readonly<HTMLElement>[]) =>
            facts.flatMap((fact) => {
              const container = fact.closest('section');
              if (!(container instanceof HTMLElement)) throw new Error('Missing record section');
              const bounds = container.getBoundingClientRect();
              const range = document.createRange();
              range.selectNodeContents(fact);
              const clipped = Array.from(range.getClientRects()).some(
                (rect: Readonly<DOMRect>) =>
                  rect.left < Math.max(0, bounds.left) || rect.right > Math.min(320, bounds.right),
              );
              return clipped
                ? [{ text: fact.textContent, font: getComputedStyle(fact).fontSize }]
                : [];
            }),
          ),
      )
      .toEqual([]);
    await checkpoint(`academic-initial-${tab}-text200.png`);
  }
});
