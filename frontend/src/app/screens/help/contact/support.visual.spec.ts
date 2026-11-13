import type { Locator, Page, Route, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../../testing/visual';
import { supportActorFixture, supportReceiptFixture } from './support-test-data';

interface Scenario {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}

async function replayReceipt(
  route: Readonly<Route>,
  body: unknown,
  key: string | undefined,
): Promise<void> {
  expect(route.request().postDataJSON()).toEqual(body);
  expect(route.request().headers()['idempotency-key']).toBe(key);
  await route.fulfill({ status: 201, json: supportReceiptFixture });
}

async function session(page: Readonly<Page>, actor = false): Promise<void> {
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({
      status: actor ? 200 : 401,
      json: actor ? supportActorFixture : { code: 'unauthenticated' },
    });
  });
}
async function context(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/support-context', async (route) => {
    expect(route.request().postDataJSON()).toEqual({});
    await route.fulfill({
      json: { csrf_token: 'public-proof-csrf', expires_at: '2099-11-09T08:00:00Z' },
    });
  });
}
async function fill(page: Readonly<Page>): Promise<void> {
  await page.getByRole('textbox', { name: 'Where we can reply' }).fill('student@example.org');
  await page
    .getByRole('textbox', { name: 'What’s happening?', exact: true })
    .fill('I cannot access the university inbox.');
}

test('A04/W04 validation, sending and actual receipt without email delivery promise', async ({
  page,
  checkpoint,
}: Readonly<Scenario>) => {
  await session(page);
  await context(page);
  await page.route('**/api/v1/support-cases', async (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().headers()['x-csrf-token']).toBe('public-proof-csrf');
    await route.fulfill({ status: 201, json: supportReceiptFixture });
  });
  await page.goto('/help/contact');
  await expect(page.getByRole('button', { name: 'Send to the team' })).toBeEnabled();
  await checkpoint('support-empty.png');
  await page.getByRole('button', { name: 'Send to the team' }).click();
  await expect(page.getByRole('alert')).toContainText('valid reply address');
  await checkpoint('support-validation.png');
  await fill(page);
  await page.getByRole('button', { name: 'Send to the team' }).click();
  await expect(page.getByRole('heading', { name: 'Request received' })).toBeVisible();
  await expect(page.getByText(supportReceiptFixture.case_id, { exact: false })).toBeVisible();
  await checkpoint('support-received.png');
});

test('A04 unknown admission explicit identical replay preserves captured body and key', async ({
  page,
  checkpoint,
}: Readonly<Scenario>) => {
  await session(page);
  await context(page);
  let requests = 0;
  let original: unknown = null;
  let key: string | undefined;
  await page.route('**/api/v1/support-cases', async (route) => {
    requests += 1;
    if (requests === 1) {
      original = route.request().postDataJSON();
      key = route.request().headers()['idempotency-key'];
      await route.abort('failed');
    } else {
      await replayReceipt(route, original, key);
    }
  });
  await page.goto('/help/contact');
  await fill(page);
  await page.getByRole('button', { name: 'Send to the team' }).click();
  await expect(page.getByRole('alert')).toContainText('whether your request was received');
  await expect(page.getByRole('textbox', { name: 'Where we can reply' })).toBeDisabled();
  await checkpoint('support-outcome-unknown.png');
  await page.getByRole('button', { name: 'Retry identical request' }).click();
  await expect(page.getByRole('heading', { name: 'Request received' })).toBeVisible();
  expect(requests).toBe(2);
  await checkpoint('support-replay-receipt.png');
});

test('A04 account support uses actual session CSRF without activation requirement', async ({
  page,
  checkpoint,
}: Readonly<Scenario>) => {
  await session(page, true);
  await context(page);
  await page.route('**/api/v1/me/support-cases', async (route) => {
    expect(route.request().headers()['x-csrf-token']).toBe(supportActorFixture.csrf_token);
    await route.fulfill({ status: 201, json: supportReceiptFixture });
  });
  await page.goto('/help/contact');
  await fill(page);
  await page.getByRole('button', { name: 'Send to the team' }).click();
  await expect(page.getByRole('heading', { name: 'Request received' })).toBeVisible();
  await checkpoint('support-actor-receipt.png');
});

for (const status of [422, 429, 503])
  test(`A04 failure ${String(status)} retains input and actual recovery path`, async ({
    page,
    checkpoint,
  }: Readonly<Scenario>) => {
    await session(page);
    await context(page);
    await page.route('**/api/v1/support-cases', async (route) => {
      await route.fulfill({
        status,
        json: {
          code:
            status === 429
              ? 'support_quota_exceeded'
              : status === 503
                ? 'storage_unavailable'
                : 'invalid_request',
          request_id: 'support-reference',
        },
      });
    });
    await page.goto('/help/contact');
    await fill(page);
    await page.getByRole('button', { name: 'Send to the team' }).click();
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'What’s happening?', exact: true })).toHaveValue(
      'I cannot access the university inbox.',
    );
    await checkpoint(`support-failure-${String(status)}.png`);
  });

test('A04 follow-up discovery survives reload without ID, empty is not proof of rejected admission', async ({
  page,
  checkpoint,
}: Readonly<Scenario>) => {
  await session(page);
  let reads = 0;
  await page.route('**/api/v1/support-cases', async (route) => {
    expect(route.request().method()).toBe('GET');
    reads += 1;
    await route.fulfill({
      json: {
        cases: reads === 1 ? [{ ...supportReceiptFixture, status: 'in_review', version: 2 }] : [],
      },
    });
  });
  await page.goto('/help/contact/status');
  await expect(page.getByRole('heading', { name: 'In review' })).toBeVisible();
  await checkpoint('support-recent-in-review.png');
  await page.reload();
  await expect(page.getByRole('status')).toContainText('No recent requests');
  await expect(page.getByRole('status')).toContainText('does not confirm');
  await checkpoint('support-recent-empty.png');
});

test('A04 expired proof recovery reports unavailable without issuing a replacement proof', async ({
  page,
  checkpoint,
}: Readonly<Scenario>) => {
  await session(page);
  await page.route('**/api/v1/support-cases', async (route) => {
    await route.fulfill({ status: 404, json: { code: 'support_unavailable' } });
  });
  let preparations = 0;
  page.on('request', (request) => {
    if (request.url().endsWith('/support-context')) preparations += 1;
  });
  await page.goto('/help/contact/status');
  await expect(page.getByRole('alert')).toContainText('original proof');
  expect(preparations).toBe(0);
  await checkpoint('support-proof-unavailable.png');
});

test('A04 narrow keyboard form at 200 percent keeps independent manual support available', async ({
  page,
  checkpoint,
}: Readonly<Scenario>, testInfo: Readonly<TestInfo>) => {
  await session(page);
  await page.setViewportSize({ width: 320, height: 800 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/help/contact');
  await page.evaluate(() => {
    document.documentElement.style.setProperty('font-size', '200%');
  });
  await page.getByRole('textbox', { name: 'Where we can reply' }).focus();
  await page.keyboard.type('student@example.org');
  await expect(page.getByRole('textbox', { name: 'Where we can reply' })).toBeFocused();
  const submit = page.getByRole('button', { name: 'Send to the team', exact: true });
  await expect(submit).toHaveText('Send to the team');
  await expect(submit).toHaveAccessibleName('Send to the team');
  await assertFullTextFits(submit);
  for (const field of [
    { id: 'support-reply', label: 'Where we can reply' },
    { id: 'support-message', label: 'What’s happening?' },
    { id: 'support-details', label: 'Details · optional' },
  ]) {
    const label = page.locator(`label[for="${field.id}"]`);
    await expect(label).toHaveText(field.label);
    await expect(page.locator(`#${field.id}`)).toHaveAccessibleName(field.label);
    await assertFullTextFits(label);
  }
  const layout = await page.evaluate(() => ({
    viewport: { width: window.innerWidth, height: window.innerHeight },
    root: {
      width: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    },
    elements: Array.from(
      document.querySelectorAll(
        'app-support-contact, main, form, fieldset, legend, label, tui-textfield, input, textarea, button',
      ),
    ).map((element: Readonly<Element>) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        tag: element.tagName,
        id: element.id,
        x: rect.x,
        width: rect.width,
        right: rect.right,
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
        display: style.display,
        gridTemplateColumns: style.gridTemplateColumns,
        minInlineSize: style.minInlineSize,
        inlineSize: style.inlineSize,
        boxSizing: style.boxSizing,
        fontSize: style.fontSize,
        overflowWrap: style.overflowWrap,
      };
    }),
  }));
  await testInfo.attach('support-narrow-layout-NO-CONTENT.json', {
    body: JSON.stringify(layout, null, 2),
    contentType: 'application/json',
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await checkpoint('support-narrow-keyboard-200.png');
});

test('A04 unsent and unconfirmed leave guards preserve the form without claiming cancellation', async ({
  page,
  checkpoint,
}: Readonly<Scenario>) => {
  await session(page);
  await context(page);
  let pending: Readonly<Route> | undefined;
  await page.route('**/api/v1/support-cases', (route) => {
    pending = route;
  });
  await page.goto('/help/contact');
  await fill(page);
  await page.getByRole('link', { name: 'Back to help', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Discard unsaved changes?' })).toBeVisible();
  await checkpoint('support-unsent-leave-confirmation.png');
  await page.getByRole('button', { name: 'Keep editing', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Where we can reply' })).toHaveValue(
    'student@example.org',
  );
  await page.getByRole('button', { name: 'Send to the team' }).click();
  await expect(page.getByRole('status')).toContainText('Sending your request');
  await checkpoint('support-sending.png');
  await page.getByRole('link', { name: 'Back to help', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Leave before the save is confirmed?' }),
  ).toBeVisible();
  await checkpoint('support-unconfirmed-leave.png');
  await page.getByRole('button', { name: 'Keep editing', exact: true }).click();
  await fulfillPending(pending);
  await expect(page.getByRole('heading', { name: 'Request received' })).toBeVisible();
});

async function fulfillPending(route: Readonly<Route> | undefined): Promise<void> {
  if (route === undefined) throw new Error('Missing held support request');
  await route.fulfill({ status: 201, json: supportReceiptFixture });
}

async function assertFullTextFits(locator: Readonly<Locator>): Promise<void> {
  const fit = await locator.evaluate((element: Readonly<HTMLElement>) => {
    const box = element.getBoundingClientRect();
    const range = document.createRange();
    range.selectNodeContents(element);
    return {
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
      allTextRectsInside: Array.from(range.getClientRects()).every(
        (rect: Readonly<DOMRect>) =>
          rect.left >= box.left &&
          rect.right <= box.right &&
          rect.top >= box.top &&
          rect.bottom <= box.bottom,
      ),
    };
  });
  expect(fit.scrollWidth).toBeLessThanOrEqual(fit.clientWidth);
  expect(fit.scrollHeight).toBeLessThanOrEqual(fit.clientHeight);
  expect(fit.allTextRectsInside).toBe(true);
}
