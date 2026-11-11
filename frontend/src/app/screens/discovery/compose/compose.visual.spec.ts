import type { Locator, Page, Route, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../../testing/visual';
import { jpegBase64 } from '../../../../../testing/image-fixture';
import type { Api } from '../../../api.generated';
import { actor, recipientId, preview, receipt, connected } from './compose.fixtures';

type Mode = Api['schemas']['DiscoveryMode'];
type PreviewResult = Api['paths']['/api/v1/requests/preview']['post']['responses']['200'];
type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}>;

async function account(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/me', async (route: Readonly<Route>) =>
    route.fulfill({ json: actor }),
  );
  await page.route('**/api/v1/people/*/photo/*', async (route: Readonly<Route>) =>
    route.fulfill({ contentType: 'image/jpeg', body: Buffer.from(jpegBase64, 'base64') }),
  );
  await page.route('**/api/v1/discovery?*', async (route: Readonly<Route>) => {
    const mode = new URL(route.request().url()).searchParams.get('mode');
    const actual = mode === 'offer_help' || mode === 'study_together' ? mode : 'find_help';
    const context: Api['schemas']['DiscoveryContextBody'] =
      actual === 'offer_help'
        ? { mode: actual, help_version: 1 }
        : { mode: actual, goal_id: '60000000-0000-4000-8000-000000000001', goal_version: 1 };
    const deck: Api['schemas']['DiscoveryPageResponse'] = {
      context,
      next_cursor: null,
      empty_reason: null,
      undo_pass: null,
      people: [
        {
          id: recipientId,
          display_name: 'Aiko Tanaka',
          about: 'I like drawing tables before writing a query.',
          version: 1,
          photo: { version: 1, display_url: `/api/v1/people/${recipientId}/photo/1` },
          own_pass: { person_id: recipientId, passed: false, version: 0, changed_at: null },
          relevance: {
            reason:
              actual === 'find_help'
                ? 'can_help'
                : actual === 'offer_help'
                  ? 'you_can_help'
                  : 'shared_goal',
            same_topic: true,
            subject_id: '20000000-0000-4000-8000-000000000001',
            subject_label: 'SQL',
            topic: 'JOINs',
            reciprocal_subject_id: null,
            reciprocal_subject_label: null,
          },
        },
      ],
    };
    await route.fulfill({ json: deck });
  });
}

async function open(page: Readonly<Page>, mode: Mode = 'find_help'): Promise<void> {
  await page.goto(`/discover?mode=${mode}&person=${recipientId}`);
  await page.getByRole('button', { name: 'Review request', exact: true }).click();
  await expect(page.getByRole('dialog', { name: /^Review request/ })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Request composer', exact: true })).toBeVisible();
}

async function fixedPreview(page: Readonly<Page>, value: PreviewResult): Promise<void> {
  await page.route('**/api/v1/requests/preview', async (route: Readonly<Route>) =>
    route.fulfill({ json: value }),
  );
}

async function linkedError(
  page: Readonly<Page>,
  field: Readonly<Locator>,
  message: string,
): Promise<void> {
  const error = page.getByRole('alert');
  await expect(error).toContainText(message);
  const id = await error.getAttribute('id');
  if (id === null || id.length === 0)
    throw new Error('Actual error must expose its accessible target');
  await expect(field).toHaveAttribute('aria-describedby', id);
  await error.scrollIntoViewIfNeeded();
  await expect(error).toBeInViewport({ ratio: 1 });
  await expect(page.getByRole('button', { name: 'Send request', exact: true })).toBeInViewport({
    ratio: 1,
  });
  await expect(
    page.getByRole('button', { name: 'Close without sending', exact: true }),
  ).toBeInViewport({ ratio: 1 });
}

async function reflowGeometry(page: Readonly<Page>) {
  return await page.evaluate(() => ({
    fits: document.documentElement.scrollWidth <= innerWidth,
    viewport: innerWidth,
    client: document.documentElement.clientWidth,
    root: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    fontSize: getComputedStyle(document.documentElement).fontSize,
    boxes: Array.from(
      document.querySelectorAll(
        'main, main header, main .actions, main button, h1, tui-dialog, section[aria-label="Request composer"], tui-textfield, iframe',
      ),
    )
      .map((element: Readonly<Element>) => {
        const rect = element.getBoundingClientRect();
        return {
          tag: element.tagName,
          id: element.id,
          classes: element.getAttribute('class'),
          display: getComputedStyle(element).display,
          overflowX: getComputedStyle(element).overflowX,
          minimum: getComputedStyle(element).minInlineSize,
          whiteSpace: getComputedStyle(element).whiteSpace,
          left: rect.left,
          right: rect.right,
          width: rect.width,
          client: element.clientWidth,
          scroll: element.scrollWidth,
        } as const;
      })
      .slice(0, 32),
  }));
}

async function focusGeometry(page: Readonly<Page>) {
  return await page.evaluate(() => {
    const active = document.activeElement;
    const activation: unknown = Reflect.get(navigator, 'userActivation');
    const counts: unknown = Reflect.get(window, '__peerlyComposeValidationCounts');
    const pointerEvents: unknown = Reflect.get(window, '__peerlyComposePointerEvents');
    const form = document.querySelector('form');
    const field = document.getElementById('request-text');
    const send = document.querySelector('button[aria-label="Send request"]');
    const layout = Array.from(
      document.querySelectorAll(
        '.composer-layout, .composer-layout > section, .composer-layout > footer, tui-dialog, tui-modal',
      ),
    ).map((element: Readonly<Element>) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      const parent = element.parentElement;
      const parentStyle = parent === null ? null : getComputedStyle(parent);
      return {
        tag: element.tagName,
        class: element.className,
        height: style.height,
        minHeight: style.minHeight,
        maxHeight: style.maxHeight,
        flex: style.flex,
        display: style.display,
        gridRows: style.gridTemplateRows,
        top: rect.top,
        bottom: rect.bottom,
        clientHeight: element.clientHeight,
        scrollHeight: element.scrollHeight,
        parent:
          parent === null
            ? null
            : {
                tag: parent.tagName,
                height: parentStyle?.height,
                minHeight: parentStyle?.minHeight,
                display: parentStyle?.display,
                gridRows: parentStyle?.gridTemplateRows,
              },
      };
    });
    return {
      layout,
      focusedTag: active?.tagName,
      focusedId: active?.id,
      documentFocused: document.hasFocus(),
      platform: navigator.platform,
      maxTouchPoints: navigator.maxTouchPoints,
      visibility: document.visibilityState,
      form:
        form instanceof HTMLFormElement
          ? {
              noValidate: form.noValidate,
              attribute: form.hasAttribute('novalidate'),
              submitted: form.classList.contains('ng-submitted'),
              pending: form.classList.contains('ng-pending'),
            }
          : null,
      field:
        field instanceof HTMLTextAreaElement
          ? {
              willValidate: field.willValidate,
              nativeValid: field.validity.valid,
              disabled: field.disabled,
              readOnly: field.readOnly,
              connected: field.isConnected,
            }
          : null,
      sendDisabled: send instanceof HTMLButtonElement ? send.disabled : null,
      pointerEvents,
      events:
        typeof counts === 'object' &&
        counts !== null &&
        'submit' in counts &&
        typeof counts.submit === 'number' &&
        'invalid' in counts &&
        typeof counts.invalid === 'number'
          ? { submit: counts.submit, invalid: counts.invalid }
          : null,
      userActive:
        typeof activation === 'object' &&
        activation !== null &&
        'isActive' in activation &&
        typeof activation.isActive === 'boolean'
          ? activation.isActive
          : null,
      inputs: Array.from(document.querySelectorAll('input')).map(
        (element: Readonly<HTMLInputElement>) =>
          ({
            id: element.id,
            type: element.type,
            connected: element.isConnected,
            focused: document.activeElement === element,
            readOnly: element.readOnly,
            position: getComputedStyle(element).position,
            zIndex: getComputedStyle(element).zIndex,
          }) as const,
      ),
    };
  });
}

function replayMatches(route: Readonly<Route>, body: string | null, key: string | undefined): void {
  expect(route.request().postData()).toBe(body);
  expect(route.request().headers()['idempotency-key']).toBe(key);
  expect(key).toBeTruthy();
}

function changedPreview(): Api['schemas']['PreviewResponse'] {
  const initial = preview();
  const goal = initial.context.sender_goal;
  if (goal === null) throw new Error('Find-help fixture requires sender goal');
  return {
    ...initial,
    preview_id: '30000000-0000-4000-8000-000000000002',
    suggested_text: 'Could we review SQL aggregation?',
    context: {
      ...initial.context,
      sender_goal: {
        ...goal,
        version: 2,
        topic: 'Aggregation',
        context: 'GROUP BY and HAVING practice.',
      },
    },
  };
}

async function sentReads(page: Readonly<Page>, text: string, note: string | null): Promise<void> {
  const summary: Api['schemas']['RequestSummaryResponse'] = {
    request_id: receipt.request_id,
    version: receipt.version,
    peer: {
      person_id: recipientId,
      display_name: 'Aiko Tanaka',
      state: 'public',
      photo_version: 1,
    },
    mode: 'find_help',
    subject_id: '20000000-0000-4000-8000-000000000001',
    subject_label: 'SQL',
    topic: 'JOINs',
    text,
    note,
    state: 'pending',
    unread: false,
    sent_at: receipt.changed_at,
    expires_at: '2026-11-15T00:00:00Z',
    observed_at: receipt.changed_at,
    undo_until: null,
    cooldown_until: null,
    conversation_id: null,
    capabilities: {
      accept: false,
      decline: false,
      undo_decline: false,
      withdraw: true,
      view_profile: true,
      open_conversation: false,
    },
  };
  const list: Api['schemas']['RequestPageResponse'] = {
    requests: [summary],
    observed_at: receipt.changed_at,
    next_cursor: null,
    unread_received: 0,
    outgoing_pending: 1,
    outgoing_pending_limit: 5,
    successful_today: 1,
    daily_send_limit: 10,
  };
  const detail: Api['schemas']['RequestDetailResponse'] = {
    request: summary,
    disclosure_id: '70000000-0000-4000-8000-000000000001',
    disclosed_at: receipt.changed_at,
    disclosed_version: receipt.version,
    text,
    note,
    context: preview().context,
  };
  await page.route('**/api/v1/requests?*', async (route: Readonly<Route>) =>
    route.fulfill({ json: list }),
  );
  await page.route(`**/api/v1/requests/${receipt.request_id}`, async (route: Readonly<Route>) =>
    route.fulfill({ json: detail }),
  );
}

function releaseRequest(release: (() => void) | undefined): void {
  if (release === undefined) throw new Error('Request was not held');
  release();
}

function assertSend(route: Readonly<Route>, text: string, note: string | null): void {
  expect(route.request().postDataJSON()).toEqual({
    person_id: recipientId,
    preview_id: preview().preview_id,
    text,
    note,
  });
  expect(route.request().headers()['x-csrf-token']).toBe(actor.csrf_token);
  expect(route.request().headers()['idempotency-key']).toBeTruthy();
}

test('D03 preview pending locks closing, then Escape closes without sending', async ({
  page,
  checkpoint,
}: Scenario) => {
  await account(page);
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/requests/preview', async (route: Readonly<Route>) => {
    await held;
    await route.fulfill({ json: preview() });
  });
  await open(page);
  await expect(
    page.getByText('Checking the current pair and academic context…', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Close without sending', exact: true }),
  ).toBeDisabled();
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Request composer', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('region', { name: 'Request composer', exact: true })).toBeVisible();
  await checkpoint('preview-pending.png', { fullPage: false });
  releaseRequest(release);
  await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveValue(
    preview().suggested_text,
  );
  await page.keyboard.press('Escape');
  await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveCount(0);
  await expect(page).not.toHaveURL(/compose=request/);
  await expect(page.getByRole('button', { name: 'Review request', exact: true })).toBeFocused();
  await checkpoint('escape-returned-to-discovery.png');
});

for (const [outcome, value] of [
  ['existing_outgoing', { ...receipt, outcome: 'existing_outgoing' }],
  ['incoming', { ...receipt, outcome: 'incoming' }],
  ['connected', connected],
] as const)
  test(`R03 send ${outcome} keeps draft and provides canonical recovery`, async ({
    page,
    checkpoint,
  }: Scenario) => {
    await account(page);
    await fixedPreview(page, preview());
    let writes = 0;
    await page.route('**/api/v1/requests', async (route: Readonly<Route>) => {
      writes += 1;
      await route.fulfill({ json: value });
    });
    await open(page);
    await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveValue(
      preview().suggested_text,
    );
    await page
      .getByRole('textbox', { name: 'Request text', exact: true })
      .fill('Draft retained on pair recovery.');
    await page.getByRole('button', { name: 'Send request', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Existing pair', exact: true })).toBeVisible();
    await expect(page).toHaveURL(/\/discover\?/);
    await expect(page.getByRole('button', { name: 'Send request', exact: true })).toHaveCount(0);
    expect(writes).toBe(1);
    await checkpoint(`send-${outcome}-recovery.png`, { fullPage: false });
  });

for (const [status, code] of [
  [409, 'source_changed'],
  [429, 'rate_limited'],
  [404, 'unavailable'],
  [422, 'validation_error'],
] as const)
  test(`D03 confirmed ${String(status)} preserves draft for explicit current-context review`, async ({
    page,
    checkpoint,
  }: Scenario) => {
    await account(page);
    await fixedPreview(page, preview());
    await page.route('**/api/v1/requests', async (route: Readonly<Route>) =>
      route.fulfill({ status, json: { code } }),
    );
    await open(page);
    const text = page.getByRole('textbox', { name: 'Request text', exact: true });
    await expect(text).toHaveValue(preview().suggested_text);
    await text.fill('Keep my text after a confirmed server rejection.');
    await page.getByRole('button', { name: 'Send request', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Request recovery', exact: true })).toBeVisible();
    await expect(text).toHaveValue('Keep my text after a confirmed server rejection.');
    await expect(page.getByRole('button', { name: 'Retry same request', exact: true })).toHaveCount(
      0,
    );
    await page
      .getByRole('region', { name: 'Request recovery', exact: true })
      .scrollIntoViewIfNeeded();
    await checkpoint(`confirmed-${String(status)}-retained.png`, { fullPage: false });
    await page.getByRole('button', { name: 'Review current context', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Request recovery', exact: true })).toHaveCount(
      0,
    );
    await expect(text).toHaveValue('Keep my text after a confirmed server rejection.');
    await page
      .getByRole('region', { name: 'Saved academic context', exact: true })
      .scrollIntoViewIfNeeded();
    await checkpoint(`confirmed-${String(status)}-reviewed.png`, { fullPage: false });
  });

test('D03 actual 401 expires feature and clears draft before subsequent eligible login', async ({
  page,
  checkpoint,
}: Scenario) => {
  await account(page);
  await fixedPreview(page, preview());
  let expired = false;
  await page.route('**/api/v1/me', async (route: Readonly<Route>) => {
    await route.fulfill(
      expired ? { status: 401, json: { code: 'session_required' } } : { json: actor },
    );
  });
  await page.route('**/api/v1/requests', async (route: Readonly<Route>) => {
    expired = true;
    await route.fulfill({ status: 401, json: { code: 'session_required' } });
  });
  await open(page);
  const text = page.getByRole('textbox', { name: 'Request text', exact: true });
  await expect(text).toHaveValue(preview().suggested_text);
  await text.fill('Private text must not survive the session.');
  await page.getByRole('button', { name: 'Send request', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Sign in with your verified APU account', exact: true }),
  ).toBeVisible();
  await expect(text).toHaveCount(0);
  await checkpoint('expired-cleared.png');
  expired = false;
  await open(page);
  await expect(text).toHaveValue(preview().suggested_text);
  await checkpoint('fresh-session-no-old-draft.png', { fullPage: false });
});

test('D03 320px reflow, 200 percent text, reduced motion and keyboard-height form', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  await account(page);
  await fixedPreview(page, preview());
  await page.setViewportSize({ width: 320, height: 740 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await open(page);
  const text = page.getByRole('textbox', { name: 'Request text', exact: true });
  await expect(text).toHaveValue(preview().suggested_text);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await checkpoint('320px-dialog.png', { fullPage: false });
  await info.attach('100percent-geometry', {
    body: JSON.stringify(await reflowGeometry(page)),
    contentType: 'application/json',
  });
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  await expect(text).toBeVisible();
  await info.attach('200percent-initial-geometry', {
    body: JSON.stringify(await reflowGeometry(page)),
    contentType: 'application/json',
  });
  await expect.poll(() => reflowGeometry(page)).toMatchObject({ fits: true });
  await info.attach('200percent-settled-geometry', {
    body: JSON.stringify(await reflowGeometry(page)),
    contentType: 'application/json',
  });
  await checkpoint('320px-200percent.png', { fullPage: false });
  await page.locator('tui-textfield').filter({ has: text }).scrollIntoViewIfNeeded();
  await expect(page.locator('tui-textfield').filter({ has: text })).toBeInViewport({ ratio: 1 });
  await expect(text).toHaveValue(preview().suggested_text);
  await text.fill('My request remains editable at 200 percent.');
  await expect(text).toBeFocused();
  await text.press('End');
  await page.keyboard.type(' 🙂');
  await expect(text).toHaveValue('My request remains editable at 200 percent. 🙂');
  await checkpoint('320px-200percent-text.png', { fullPage: false });
  await page.getByRole('button', { name: 'Personal note · optional', exact: true }).click();
  const note = page.getByRole('textbox', { name: 'Personal note', exact: true });
  await note.fill('Optional note remains usable at 200 percent.');
  await expect(note).toBeFocused();
  await page.locator('tui-textfield').filter({ has: note }).scrollIntoViewIfNeeded();
  await expect(page.locator('tui-textfield').filter({ has: note })).toBeInViewport({ ratio: 1 });
  await checkpoint('320px-200percent-note.png', { fullPage: false });
  const send = page.getByRole('button', { name: 'Send request', exact: true });
  await send.scrollIntoViewIfNeeded();
  await expect(send).toBeInViewport({ ratio: 1 });
  await expect(send).toBeEnabled();
  expect(
    await page
      .getByRole('region', { name: 'Request composer', exact: true })
      .evaluate(
        (element: Readonly<HTMLElement | SVGElement>) => element.scrollWidth <= element.clientWidth,
      ),
  ).toBe(true);
  await checkpoint('320px-200percent-actions.png', { fullPage: false });
  await page.getByRole('button', { name: 'Close without sending', exact: true }).click();
  await expect(text).toHaveCount(0);
  const review = page.getByRole('button', { name: 'Review request', exact: true });
  await review.scrollIntoViewIfNeeded();
  await expect(review).toBeInViewport({ ratio: 1 });
  expect(
    await review.evaluate(
      (element: Readonly<Element>) => element.scrollWidth <= element.clientWidth,
    ),
  ).toBe(true);
  expect(
    await page
      .getByRole('button', { name: 'Pass', exact: true })
      .evaluate((element: Readonly<Element>) => element.scrollWidth <= element.clientWidth),
  ).toBe(true);
  await expect.poll(() => reflowGeometry(page)).toMatchObject({ fits: true });
  await info.attach('200percent-closed-geometry', {
    body: JSON.stringify(await reflowGeometry(page)),
    contentType: 'application/json',
  });
  await checkpoint('320px-200percent-discovery-actions.png');
  await review.click();
  await expect(text).toHaveValue('My request remains editable at 200 percent. 🙂');
  await page.locator('tui-textfield').filter({ has: text }).scrollIntoViewIfNeeded();
  await expect(page.locator('tui-textfield').filter({ has: text })).toBeInViewport({ ratio: 1 });
  await checkpoint('320px-200percent-reopened-draft.png', { fullPage: false });
  await page.evaluate(() => {
    document.documentElement.style.removeProperty('font-size');
  });
  await page.setViewportSize({ width: 320, height: 420 });
  await text.focus();
  await expect(text).toBeFocused();
  await text.fill('A draft with an open keyboard.');
  await page.locator('tui-textfield').filter({ has: text }).scrollIntoViewIfNeeded();
  await expect(page.locator('tui-textfield').filter({ has: text })).toBeInViewport({ ratio: 1 });
  await expect(text).toBeFocused();
  await expect(page.getByRole('button', { name: 'Close', exact: true })).toBeInViewport({
    ratio: 1,
  });
  await expect(send).toBeInViewport({ ratio: 1 });
  await expect(
    page.getByRole('button', { name: 'Close without sending', exact: true }),
  ).toBeInViewport({ ratio: 1 });
  await info.attach('keyboard-height-layout', {
    body: JSON.stringify(await focusGeometry(page)),
    contentType: 'application/json',
  });
  await checkpoint('keyboard-height.png', { fullPage: false });
  await page.getByRole('button', { name: 'Close without sending', exact: true }).click();
  await expect(text).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Review request', exact: true })).toBeVisible();
  await checkpoint('keyboard-close-return.png');
});

test('D03 explicit edited send locks pending dialog and advances to canonical Requests', async ({
  page,
  checkpoint,
}: Scenario) => {
  await account(page);
  await fixedPreview(page, preview());
  const text = '  Could we compare SQL examples?\nI tried LEFT JOIN.  ';
  const note = ' My lab attempt is ready. ';
  await sentReads(page, text, note);
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let writes = 0;
  await page.route('**/api/v1/requests', async (route: Readonly<Route>) => {
    writes += 1;
    assertSend(route, text, note);
    await held;
    await route.fulfill({ json: receipt });
  });
  await open(page);
  await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveValue(
    preview().suggested_text,
  );
  await page.getByRole('textbox', { name: 'Request text', exact: true }).fill(text);
  await page.getByRole('button', { name: 'Personal note · optional', exact: true }).click();
  await page.getByRole('textbox', { name: 'Personal note', exact: true }).fill(note);
  await page.getByRole('button', { name: 'Send request', exact: true }).click();
  await expect(page.getByText('Sending your request…', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Close without sending', exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveAttribute(
    'readonly',
  );
  await page.keyboard.press('Escape');
  await expect(page.getByRole('region', { name: 'Request composer', exact: true })).toBeVisible();
  await page.getByText('Sending your request…', { exact: true }).scrollIntoViewIfNeeded();
  await checkpoint('send-pending-locked.png', { fullPage: false });
  releaseRequest(release);
  await expect(page).toHaveURL(
    (url: Readonly<URL>) =>
      url.pathname === '/requests' &&
      url.searchParams.get('box') === 'sent' &&
      url.searchParams.get('request') === receipt.request_id,
  );
  await expect(page.getByRole('heading', { name: 'Requests', exact: true })).toBeVisible();
  await expect(page.getByText(text, { exact: true })).toBeVisible();
  expect(writes).toBe(1);
  await checkpoint('sent-canonical-request.png');
});

test('D03 unknown send keeps exact body and key through close, reopen and manual replay', async ({
  page,
  checkpoint,
}: Scenario) => {
  await account(page);
  await fixedPreview(page, preview());
  const text = 'Please review my original immutable SQL request.';
  await sentReads(page, text, null);
  let body: string | null = null;
  let key: string | undefined;
  let writes = 0;
  await page.route('**/api/v1/requests', async (route: Readonly<Route>) => {
    writes += 1;
    if (writes === 1) {
      assertSend(route, text, null);
      body = route.request().postData();
      key = route.request().headers()['idempotency-key'];
      await route.abort();
    } else {
      replayMatches(route, body, key);
      await route.fulfill({ json: receipt });
    }
  });
  await open(page);
  await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveValue(
    preview().suggested_text,
  );
  await page.getByRole('textbox', { name: 'Request text', exact: true }).fill(text);
  await page.getByRole('button', { name: 'Send request', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry same request', exact: true })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveAttribute(
    'readonly',
  );
  await page
    .getByRole('region', { name: 'Request recovery', exact: true })
    .scrollIntoViewIfNeeded();
  await checkpoint('send-unknown-retained.png', { fullPage: false });
  await page.getByRole('button', { name: 'Close without sending', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Review request', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveValue(text);
  await page
    .getByRole('region', { name: 'Request recovery', exact: true })
    .scrollIntoViewIfNeeded();
  await checkpoint('send-unknown-reopened.png', { fullPage: false });
  await page.getByRole('button', { name: 'Retry same request', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Requests', exact: true })).toBeVisible();
  expect(writes).toBe(2);
  await checkpoint('send-replayed-canonical.png');
});

for (const mode of ['find_help', 'offer_help', 'study_together'] as const)
  test(`D03 ${mode} genuine suggestion, readonly sources and retained edited draft`, async ({
    page,
    checkpoint,
  }: Scenario) => {
    await account(page);
    await fixedPreview(page, preview(mode));
    let sends = 0;
    await page.route('**/api/v1/requests', async (route: Readonly<Route>) => {
      sends += 1;
      await route.fulfill({ json: receipt });
    });
    await open(page, mode);
    await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveValue(
      preview(mode).suggested_text,
    );
    await expect(
      page.getByRole('region', { name: 'Saved academic context', exact: true }),
    ).toContainText('JOINs');
    await expect(page.getByText('5 pending slots remaining', { exact: true })).toBeVisible();
    await checkpoint(`${mode}-server-preview.png`, { fullPage: false });
    await page
      .getByRole('textbox', { name: 'Request text', exact: true })
      .fill('Could we compare our SQL examples?');
    await page.getByRole('button', { name: 'Personal note · optional', exact: true }).click();
    await page
      .getByRole('textbox', { name: 'Personal note', exact: true })
      .fill('I tried the lab example.');
    await checkpoint(`${mode}-edited-note.png`, { fullPage: false });
    await page.getByRole('button', { name: 'Close without sending', exact: true }).click();
    await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveCount(0);
    await expect(page).not.toHaveURL(/compose=request/);
    expect(sends).toBe(0);
    await page.getByRole('button', { name: 'Review request', exact: true }).click();
    await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveValue(
      'Could we compare our SQL examples?',
    );
    await expect(page.getByRole('textbox', { name: 'Personal note', exact: true })).toHaveValue(
      'I tried the lab example.',
    );
    await page
      .getByRole('textbox', { name: 'Personal note', exact: true })
      .scrollIntoViewIfNeeded();
    await expect(
      page
        .locator('tui-textfield')
        .filter({ has: page.getByRole('textbox', { name: 'Request text', exact: true }) }),
    ).toBeInViewport({ ratio: 1 });
    await expect(
      page
        .locator('tui-textfield')
        .filter({ has: page.getByRole('textbox', { name: 'Personal note', exact: true }) }),
    ).toBeInViewport({ ratio: 1 });
    await checkpoint(`${mode}-reopened-draft.png`, { fullPage: false });
    await page
      .getByRole('button', { name: 'Reset request text to server suggestion', exact: true })
      .click();
    await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveValue(
      preview(mode).suggested_text,
    );
    expect(sends).toBe(0);
    await checkpoint(`${mode}-explicit-reset.png`, { fullPage: false });
  });

test('D03 required and Unicode codepoint limits preserve invalid raw input', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  await page.addInitScript({
    content: `(() => {
    const counts = { submit: 0, invalid: 0 };
    Object.defineProperty(window, '__peerlyComposeValidationCounts', { value: counts });
    document.addEventListener('submit', () => { counts.submit += 1; }, true);
    document.addEventListener('invalid', () => { counts.invalid += 1; }, true);
    const events = [];
    Object.defineProperty(window, '__peerlyComposePointerEvents', { value: events });
    const capture = (event, phase) => {
      const send = document.querySelector('button[aria-label="Send request"]');
      if (!(send instanceof HTMLButtonElement)) return;
      const target = event.target;
      const rect = send.getBoundingClientRect();
      events.push({
        event: event.type, phase,
        targetTag: target instanceof Element ? target.tagName : null,
        targetId: target instanceof Element ? target.id : null,
        targetLabel: target instanceof Element ? target.getAttribute('aria-label') : null,
        sendTarget: target === send || (target instanceof Node && send.contains(target)),
        x: event instanceof MouseEvent ? event.clientX : null,
        y: event instanceof MouseEvent ? event.clientY : null,
        sendRect: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom },
        sendType: send.type, formAssociated: send.form !== null,
        activeTag: document.activeElement?.tagName,
        activeId: document.activeElement?.id,
      });
    };
    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click', 'focusout']) {
      document.addEventListener(type, event => {
        capture(event, 'capture');
        if (type === 'focusout') requestAnimationFrame(() => capture(event, 'next-frame'));
      }, { capture: true, passive: true });
    }
  })();`,
  });
  await account(page);
  await fixedPreview(page, preview());
  await open(page);
  const text = page.getByRole('textbox', { name: 'Request text', exact: true });
  await expect(text).toHaveValue(preview().suggested_text);
  await text.fill('');
  const send = page.getByRole('button', { name: 'Send request', exact: true });
  await send.scrollIntoViewIfNeeded();
  const before = await send.boundingBox();
  expect(before).not.toBeNull();
  await info.attach('validation-before-submit-focus', {
    body: JSON.stringify(await focusGeometry(page)),
    contentType: 'application/json',
  });
  await send.click();
  await expect(page.getByRole('alert')).toContainText('Write a request before sending.');
  await info.attach('validation-after-submit-focus', {
    body: JSON.stringify(await focusGeometry(page)),
    contentType: 'application/json',
  });
  expect(await send.boundingBox()).toEqual(before);
  try {
    await expect(text).toBeFocused();
  } finally {
    await info.attach('validation-final-focus', {
      body: JSON.stringify(await focusGeometry(page)),
      contentType: 'application/json',
    });
  }
  await linkedError(page, text, 'Write a request before sending.');
  await checkpoint('required-text.png', { fullPage: false });
  await text.press('Tab');
  await expect(
    page.getByRole('button', { name: 'Reset request text to server suggestion', exact: true }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('button', { name: 'Personal note · optional', exact: true }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('button', { name: 'Recheck availability', exact: true }),
  ).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Send request', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(text).toBeFocused();
  await linkedError(page, text, 'Write a request before sending.');
  await checkpoint('required-text-keyboard.png', { fullPage: false });
  await text.fill('🙂'.repeat(240));
  await expect(
    page.getByText('Request text: 240 / 240 characters.', { exact: true }),
  ).toBeVisible();
  await checkpoint('240-codepoints.png', { fullPage: false });
  await text.fill('🙂'.repeat(241));
  await page.getByRole('button', { name: 'Send request', exact: true }).click();
  await expect(text).toHaveValue('🙂'.repeat(241));
  await linkedError(page, text, '240');
  await checkpoint('241-preserved.png', { fullPage: false });
  await text.fill('A valid request.');
  await page.getByRole('button', { name: 'Personal note · optional', exact: true }).click();
  const note = page.getByRole('textbox', { name: 'Personal note', exact: true });
  await note.fill('🙂'.repeat(241));
  await page.getByRole('button', { name: 'Send request', exact: true }).click();
  await expect(note).toHaveValue('🙂'.repeat(241));
  await expect(note).toBeFocused();
  await info.attach('note-limit-layout', {
    body: JSON.stringify(await focusGeometry(page)),
    contentType: 'application/json',
  });
  await linkedError(page, note, '240');
  await checkpoint('note-241-preserved.png', { fullPage: false });
  await note.fill('A note with\u0001an unsupported control.');
  await page.getByRole('button', { name: 'Send request', exact: true }).click();
  await expect(note).toBeFocused();
  await info.attach('note-control-layout', {
    body: JSON.stringify(await focusGeometry(page)),
    contentType: 'application/json',
  });
  await linkedError(page, note, 'Remove unsupported control characters');
  await checkpoint('note-control-validation.png', { fullPage: false });
});

for (const [outcome, value, direction] of [
  ['existing_outgoing', { ...receipt, outcome: 'existing_outgoing' }, 'sent'],
  ['incoming', { ...receipt, outcome: 'incoming' }, 'received'],
  ['connected', connected, null],
] as const)
  test(`R03 preview ${outcome} recovery never sends or autoaccepts`, async ({
    page,
    checkpoint,
  }: Scenario) => {
    await account(page);
    await fixedPreview(page, value);
    let sends = 0;
    await page.route('**/api/v1/requests', async (route: Readonly<Route>) => {
      sends += 1;
      await route.fulfill({ json: receipt });
    });
    await open(page);
    await expect(page.getByRole('region', { name: 'Existing pair', exact: true })).toBeVisible();
    const href = await page
      .getByRole('link', { name: 'Review existing request', exact: true })
      .getAttribute('href');
    expect(new URL(href ?? '', 'http://localhost').searchParams.get('request')).toBe(
      receipt.request_id,
    );
    expect(new URL(href ?? '', 'http://localhost').searchParams.get('box')).toBe(direction);
    await expect(page.getByRole('button', { name: 'Send request', exact: true })).toHaveCount(0);
    await expect(
      page
        .getByRole('region', { name: 'Existing pair', exact: true })
        .getByRole('link', { name: /chat/i }),
    ).toHaveCount(0);
    await expect(
      page
        .getByRole('navigation', { name: 'Student navigation' })
        .getByRole('link', { name: 'Chats', exact: true }),
    ).toHaveAttribute('href', '/chats');
    expect(sends).toBe(0);
    await checkpoint(`${outcome}-recovery.png`, { fullPage: false });
  });

for (const [reason, copy] of [
  ['outgoing_pending_limit', 'Your outgoing pending limit has been reached.'],
  ['daily_send_limit', 'Your daily send limit has been reached.'],
  ['cooldown', 'A new request in this pair is not available until the server’s date.'],
  ['source_changed', 'The saved academic source changed. Review the current context.'],
  ['unavailable', 'This person or academic context is no longer available.'],
] as const)
  test(`D03 actual ${reason} capability denies send without guessing from counts`, async ({
    page,
    checkpoint,
  }: Scenario) => {
    await account(page);
    await fixedPreview(page, {
      ...preview(),
      can_send: false,
      block_reason: reason,
      cooldown_until: reason === 'cooldown' ? '2026-11-09T12:00:00Z' : null,
    });
    await open(page);
    await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveValue(
      preview().suggested_text,
    );
    await expect(page.getByText('5 pending slots remaining', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Send request', exact: true })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Review Requests', exact: true })).toHaveAttribute(
      'href',
      '/requests',
    );
    await expect(page.getByRole('status')).toHaveText(copy);
    const recovery = page.getByRole('link', { name: 'Review Requests', exact: true });
    await recovery.scrollIntoViewIfNeeded();
    await expect(recovery).toBeInViewport({ ratio: 1 });
    await expect(page.getByRole('status')).toBeInViewport({ ratio: 1 });
    const detail = page.getByText(
      reason === 'cooldown' ? 'Available after Nov 9, 2026, 8:00:00 PM Kuala Lumpur time.' : copy,
      { exact: true },
    );
    await expect(detail).toBeInViewport({ ratio: 1 });
    await checkpoint(`${reason}-denied.png`, { fullPage: false });
  });

test('D03 unknown preview replays original intent and only then initializes form', async ({
  page,
  checkpoint,
}: Scenario) => {
  await account(page);
  let original: string | null = null;
  let key: string | undefined;
  let checks = 0;
  await page.route('**/api/v1/requests/preview', async (route: Readonly<Route>) => {
    checks += 1;
    if (checks === 1) {
      original = route.request().postData();
      key = route.request().headers()['idempotency-key'];
      await route.abort();
    } else {
      replayMatches(route, original, key);
      await route.fulfill({ json: preview() });
    }
  });
  await open(page);
  await expect(
    page.getByRole('button', { name: 'Retry same preview check', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveCount(0);
  await checkpoint('unknown-preview.png', { fullPage: false });
  await page.getByRole('button', { name: 'Retry same preview check', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Request text', exact: true })).toHaveValue(
    preview().suggested_text,
  );
  expect(checks).toBe(2);
  await checkpoint('preview-replayed.png', { fullPage: false });
});

test('D03 changed actual context requires explicit review before keeping edited text', async ({
  page,
  checkpoint,
}: Scenario) => {
  await account(page);
  let checks = 0;
  const initial = preview();
  const revised = changedPreview();
  await page.route('**/api/v1/requests/preview', async (route: Readonly<Route>) => {
    checks += 1;
    await route.fulfill({ json: checks === 1 ? initial : revised });
  });
  await open(page);
  const text = page.getByRole('textbox', { name: 'Request text', exact: true });
  await expect(text).toHaveValue(initial.suggested_text);
  await text.fill('Keep this carefully edited draft.');
  await page.getByRole('button', { name: 'Recheck availability', exact: true }).click();
  await expect(
    page.getByRole('region', { name: 'Changed academic context', exact: true }),
  ).toContainText('GROUP BY and HAVING practice.');
  await expect(text).toHaveValue('Keep this carefully edited draft.');
  await expect(text).toHaveAttribute('readonly');
  await expect(page.getByRole('button', { name: 'Send request', exact: true })).toBeDisabled();
  await page
    .getByRole('region', { name: 'Saved academic context', exact: true })
    .scrollIntoViewIfNeeded();
  await checkpoint('changed-source-original.png', { fullPage: false });
  await page
    .getByRole('region', { name: 'Changed academic context', exact: true })
    .scrollIntoViewIfNeeded();
  await checkpoint('changed-source-review.png', { fullPage: false });
  await page
    .getByRole('button', { name: 'Use reviewed context and keep my text', exact: true })
    .click();
  await expect(
    page.getByRole('region', { name: 'Changed academic context', exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('region', { name: 'Saved academic context', exact: true }),
  ).toContainText('GROUP BY and HAVING practice.');
  await expect(text).toHaveValue('Keep this carefully edited draft.');
  await expect(text).not.toHaveAttribute('readonly');
  await checkpoint('reviewed-source-edits-kept.png', { fullPage: false });
});

test('D03 mode change retains one draft until explicit original selection reconciliation', async ({
  page,
  checkpoint,
}: Scenario) => {
  await account(page);
  await fixedPreview(page, preview());
  await open(page);
  const text = page.getByRole('textbox', { name: 'Request text', exact: true });
  await expect(text).toHaveValue(preview().suggested_text);
  await text.fill('My original find-help draft.');
  await page.getByRole('button', { name: 'Close without sending', exact: true }).click();
  await expect(text).toHaveCount(0);
  await page.getByRole('button', { name: 'Offer help', exact: true }).click();
  await page.getByRole('button', { name: 'Review request', exact: true }).click();
  await expect(
    page.getByRole('region', { name: 'Draft reconciliation', exact: true }),
  ).toBeVisible();
  await checkpoint('mode-draft-reconciliation.png', { fullPage: false });
  await page.getByRole('button', { name: 'Keep original draft', exact: true }).click();
  await expect(page).toHaveURL(/mode=find_help/);
  await expect(text).toHaveValue('My original find-help draft.');
  await checkpoint('original-mode-restored.png', { fullPage: false });
});

function requestedMode(route: Readonly<Route>): Mode {
  const value: unknown = route.request().postDataJSON();
  if (typeof value !== 'object' || value === null || !('mode' in value))
    throw new Error('Missing actual preview mode');
  const mode = value.mode;
  if (mode !== 'find_help' && mode !== 'offer_help' && mode !== 'study_together')
    throw new Error('Invalid actual preview mode');
  return mode;
}

test('D03 deliberate discard reviews new mode without attaching old text', async ({
  page,
  checkpoint,
}: Scenario) => {
  await account(page);
  await page.route('**/api/v1/requests/preview', async (route: Readonly<Route>) =>
    route.fulfill({ json: preview(requestedMode(route)) }),
  );
  await open(page);
  const text = page.getByRole('textbox', { name: 'Request text', exact: true });
  await expect(text).toHaveValue(preview().suggested_text);
  await text.fill('This draft must not silently become an offer.');
  await page.getByRole('button', { name: 'Close without sending', exact: true }).click();
  await expect(text).toHaveCount(0);
  await page.getByRole('button', { name: 'Offer help', exact: true }).click();
  await page.getByRole('button', { name: 'Review request', exact: true }).click();
  await expect(
    page.getByRole('region', { name: 'Draft reconciliation', exact: true }),
  ).toBeVisible();
  await checkpoint('discard-mode-decision.png', { fullPage: false });
  await page
    .getByRole('button', { name: 'Discard draft and review this selection', exact: true })
    .click();
  await expect(
    page.getByRole('region', { name: 'Saved academic context', exact: true }),
  ).toContainText('Sender’s help area: SQL');
  await expect(text).toHaveValue(preview('offer_help').suggested_text);
  await expect(page).toHaveURL(/mode=offer_help/);
  await checkpoint('discarded-old-draft-new-mode.png', { fullPage: false });
});

test('D03 deliberate source reset shows actual new suggestion after review', async ({
  page,
  checkpoint,
}: Scenario) => {
  await account(page);
  let checks = 0;
  const revised = changedPreview();
  await page.route('**/api/v1/requests/preview', async (route: Readonly<Route>) => {
    checks += 1;
    await route.fulfill({ json: checks === 1 ? preview() : revised });
  });
  await open(page);
  const text = page.getByRole('textbox', { name: 'Request text', exact: true });
  await expect(text).toHaveValue(preview().suggested_text);
  await text.fill('My old source draft.');
  await page.getByRole('button', { name: 'Recheck availability', exact: true }).click();
  await expect(
    page.getByRole('region', { name: 'Changed academic context', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('region', { name: 'Changed academic context', exact: true })
    .scrollIntoViewIfNeeded();
  await checkpoint('discard-source-review.png', { fullPage: false });
  await page
    .getByRole('button', { name: 'Discard draft and use new suggestion', exact: true })
    .click();
  await expect(text).toHaveValue(revised.suggested_text);
  await expect(
    page.getByRole('region', { name: 'Saved academic context', exact: true }),
  ).toContainText('GROUP BY and HAVING practice.');
  await checkpoint('discarded-source-new-suggestion.png', { fullPage: false });
});
