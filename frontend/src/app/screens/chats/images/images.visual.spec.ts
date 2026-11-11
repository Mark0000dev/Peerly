import type { Page, Request, Route, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../../testing/visual';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import type { Api } from '../../../api.generated';
import {
  conversation,
  history,
  identity,
  message,
  page as conversations,
  shares,
} from '../chats.fixtures';
import { isImageSource } from './image-contract';
import { isHistory } from '../chats-contract';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?:
      | Readonly<{ readonly fullPage: boolean }>
      | Readonly<{ readonly webkitPreview: 'open' | 'zoom' }>,
  ) => Promise<void>;
}>;

const base = `/api/v1/conversations/${conversation.conversation_id}`;
const imageId = '00000000-0000-4000-8000-000000000040';
const image = readFileSync('testing/fixtures/chat-study-image.jpg');
const replacementImage = readFileSync('testing/fixtures/chat-study-image.png');
const ready: Api['schemas']['ImagePreparationResponse'] = {
  client_message_id: message.client_message_id,
  conversation_id: conversation.conversation_id,
  image_id: imageId,
  created_at: '2026-11-08T06:00:00Z',
  updated_at: '2026-11-08T06:01:00Z',
  processing_expires_at: '2026-11-08T07:00:00Z',
  upload_expires_at: '2026-11-08T06:10:00Z',
  state: 'ready',
  source_state: 'ready',
  source_version: 3,
  failure: null,
  message_outcome: null,
  expected_source: {
    content_type: 'image/jpeg',
    size: image.length,
    sha256: createHash('sha256').update(image).digest('hex'),
  },
  display: { width: 640, height: 480, size: image.length },
};
async function setup(
  page: Readonly<Page>,
  preparations: readonly Api['schemas']['ImagePreparationResponse'][] = [],
  imageMessage: Api['schemas']['MessageResponse'] | null = null,
): Promise<() => readonly Request[]> {
  let writes: readonly Request[] = [];
  page.on('request', (request: Readonly<Request>) => {
    if (
      request.method() !== 'GET' &&
      (request.url().includes('/image-preparations') || request.url().endsWith('/messages'))
    )
      writes = [...writes, request];
  });
  await page.clock.setFixedTime(new Date('2026-11-08T06:20:00Z'));
  await page.route('**/api/v1/me', (route: Readonly<Route>) => route.fulfill({ json: identity }));
  await page.route(/\/api\/v1\/conversations(?:\?.*)?$/, (route: Readonly<Route>) =>
    route.fulfill({ json: conversations }),
  );
  await page.route(`**${base}`, (route: Readonly<Route>) => route.fulfill({ json: conversation }));
  await page.route(`**${base}/messages?*`, (route: Readonly<Route>) =>
    route.fulfill({
      json: { ...history, messages: imageMessage === null ? history.messages : [imageMessage] },
    }),
  );
  await page.route(`**${base}/messages`, (route: Readonly<Route>) =>
    route.fulfill({
      json: { ...history, messages: imageMessage === null ? history.messages : [imageMessage] },
    }),
  );
  await page.route(`**${base}/goal-shares*`, (route: Readonly<Route>) =>
    route.fulfill({ json: shares }),
  );
  await page.route(`**${base}/study-prompt-visits`, (route: Readonly<Route>) =>
    route.fulfill({ json: { outcome: 'no_offer' } }),
  );
  await page.route(`**${base}/image-preparations`, (route: Readonly<Route>) =>
    route.fulfill({ json: { preparations } }),
  );
  await page.route(`**${base}/image-preparations/*/display`, (route: Readonly<Route>) =>
    route.fulfill({ body: image, contentType: 'image/jpeg' }),
  );
  await page.route(`**${base}/messages/${message.message_id}/image`, (route: Readonly<Route>) =>
    route.fulfill({
      body: image,
      contentType: 'image/jpeg',
      headers: { 'Cache-Control': 'no-store' },
    }),
  );
  return () => writes;
}
async function open(page: Readonly<Page>): Promise<void> {
  await page.goto(`/chats?conversation=${conversation.conversation_id}`);
  await expect(page.getByRole('region', { name: 'Message image', exact: true })).toBeVisible();
}
async function previewZoomValue(page: Readonly<Page>): Promise<string> {
  const value = await page
    .getByRole('slider', { name: 'Zoom out / Zoom in', exact: true })
    .getAttribute('aria-valuetext');
  if (value === null) throw new Error('Missing public Preview zoom value');
  return value;
}
function expectIdenticalStartRetry(requests: readonly Request[]): void {
  const [first, retry] = requests;
  if (first === undefined || retry === undefined) throw new Error('Missing retry evidence');
  expect(retry.postDataJSON()).toEqual(first.postDataJSON());
  expect(retry.headers()['idempotency-key']).toBe(first.headers()['idempotency-key']);
}
async function previewReady(
  page: Readonly<Page>,
  info: Readonly<TestInfo>,
  state: 'open' | 'zoom',
): Promise<void> {
  const evidence = await page.evaluate(async () => {
    await document.fonts.ready;
    const images = Array.from(document.images).filter(
      (image: Readonly<HTMLImageElement>) => image.alt === 'Image shared in this conversation',
    );
    await Promise.all(images.map((image: Readonly<HTMLImageElement>) => image.decode()));
    const animations = document
      .getAnimations()
      .filter(
        (animation: Readonly<Animation>) =>
          animation.playState === 'running' &&
          Number.isFinite(animation.effect?.getComputedTiming().endTime),
      );
    const before = animations.map((animation: Readonly<Animation>) => ({
      playState: animation.playState,
      endTime: animation.effect?.getComputedTiming().endTime,
    }));
    await Promise.all(animations.map((animation: Readonly<Animation>) => animation.finished));
    return {
      fonts: document.fonts.status,
      images: images.map((image: Readonly<HTMLImageElement>) => ({
        width: image.naturalWidth,
        height: image.naturalHeight,
      })),
      finiteAnimationsBefore: before,
      finiteAnimationsAfter: animations.map(
        (animation: Readonly<Animation>) => animation.playState,
      ),
    };
  });
  await info.attach(`preview-public-ready-${state}`, {
    body: JSON.stringify(evidence),
    contentType: 'application/json',
  });
}
async function previewActionsInViewport(page: Readonly<Page>): Promise<void> {
  const viewport = page.viewportSize();
  if (viewport === null) throw new Error('Missing Preview viewport');
  const controls = [
    page.getByRole('button', { name: 'Close image', exact: true }),
    page.getByRole('button', { name: 'Zoom in', exact: true }),
    page.getByRole('button', { name: 'Zoom out', exact: true }),
    page.getByRole('slider', { name: 'Zoom out / Zoom in', exact: true }),
  ];
  for (const control of controls) {
    const bounds = await control.boundingBox();
    if (bounds === null) throw new Error('Missing public Preview control bounds');
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.y).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(viewport.height);
  }
}
async function previewRaw(
  page: Readonly<Page>,
  info: Readonly<TestInfo>,
  name: string,
): Promise<void> {
  const path = info.outputPath(`${name}-full-raw.png`);
  await page.screenshot({ path, fullPage: true, animations: 'disabled' });
  await info.attach(`${name}-full-raw-uncompared`, { path, contentType: 'image/png' });
}
async function previewBackdropEvidence(
  page: Readonly<Page>,
  info: Readonly<TestInfo>,
  phase: string,
): Promise<void> {
  const evidence = await page.evaluate(() => {
    const modal = document.querySelector('tui-modal');
    if (modal === null) throw new Error('Missing native Preview modal');
    const backdrop = getComputedStyle(modal, '::before');
    const bounds = modal.getBoundingClientRect();
    return JSON.stringify(
      {
        viewport: { width: innerWidth, height: innerHeight },
        modal: { left: bounds.left, top: bounds.top, width: bounds.width, height: bounds.height },
        backdrop: {
          content: backdrop.content,
          display: backdrop.display,
          filter: backdrop.getPropertyValue('backdrop-filter'),
          webkitFilter: backdrop.getPropertyValue('-webkit-backdrop-filter'),
          width: backdrop.width,
          height: backdrop.height,
          animationName: backdrop.animationName,
        },
        supportsFilter: CSS.supports('backdrop-filter', 'brightness(.25)'),
        supportsSelector: CSS.supports(
          'selector(:nth-last-child(1 of tui-modal:not(.tui-leave):not(:has(.tui-backdrop-hidden))))',
        ),
      },
      null,
      2,
    );
  });
  await info.attach(`native-preview-backdrop-layout-${phase}`, {
    body: evidence,
    contentType: 'application/json',
  });
}
async function reportLayout(
  page: Readonly<Page>,
  info: Readonly<TestInfo>,
  phase: string,
): Promise<boolean> {
  const evidence = await page.evaluate(() => {
    const root = document.documentElement;
    const nodes = Array.from(
      document.querySelectorAll(
        'app-chat-image-report, app-chat-image-report section, app-chat-image-report form, app-chat-image-report fieldset, app-chat-image-report legend, app-chat-image-report tui-textfield, app-chat-image-report textarea, app-chat-image-report p[role="alert"]',
      ),
      (element: Readonly<Element>) => {
        const box = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return {
          tag: element.tagName,
          left: box.left,
          right: box.right,
          width: box.width,
          client: element.clientWidth,
          scroll: element.scrollWidth,
          display: style.display,
          columns: style.gridTemplateColumns,
          minInline: style.minInlineSize,
          maxInline: style.maxInlineSize,
          inline: style.inlineSize,
          boxSizing: style.boxSizing,
          paddingStart: style.paddingInlineStart,
          paddingEnd: style.paddingInlineEnd,
          whiteSpace: style.whiteSpace,
          wrap: style.overflowWrap,
        };
      },
    );
    return {
      fits: root.scrollWidth <= root.clientWidth,
      raw: JSON.stringify({ viewport: root.clientWidth, scroll: root.scrollWidth, nodes }, null, 2),
    } as const;
  });
  await info.attach(`report-validation-layout-${phase}`, {
    body: evidence.raw,
    contentType: 'application/json',
  });
  return evidence.fits;
}

// Deterministic HTTP boundary coverage, not the real worker/PG acceptance.
async function pipeline(page: Readonly<Page>, caption: string | null, failFirstAccess = false) {
  await setup(page);
  let start: Api['schemas']['StartImageBody'] | null = null;
  let finalized = false;
  let accessCount = 0;
  let transferCount = 0;
  let stored: Api['schemas']['ConfirmedOperationResponse'] | null = null;
  let startRequests: readonly Request[] = [];
  const destination = 'https://images.example.test/c03-upload';
  function preparation(): Api['schemas']['ImagePreparationResponse'] {
    const body = start;
    if (body === null) throw new Error('Preparation read before Start');
    return {
      ...ready,
      client_message_id: body.client_message_id,
      source_state: finalized ? 'ready' : 'uploading',
      state: finalized ? 'ready' : 'uploading',
      display: finalized ? ready.display : null,
      expected_source: { size: body.size, sha256: body.sha256, content_type: body.content_type },
    };
  }
  await page.route(`**${base}/image-preparations`, (route: Readonly<Route>) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { preparations: [] } });
    const body: unknown = route.request().postDataJSON();
    if (
      !isImageSource(body) ||
      !('client_message_id' in body) ||
      typeof body.client_message_id !== 'string'
    )
      throw new Error('Invalid actual Start body');
    expect(body.sha256).toBe(createHash('sha256').update(image).digest('hex'));
    expect(body.size).toBe(image.length);
    expect(body.content_type).toBe('image/jpeg');
    start = {
      size: body.size,
      sha256: body.sha256,
      content_type: body.content_type,
      client_message_id: body.client_message_id,
    };
    startRequests = [...startRequests, route.request()];
    return route.fulfill({
      status: 202,
      json: {
        client_message_id: body.client_message_id,
        conversation_id: conversation.conversation_id,
        image_id: imageId,
        receipt_version: 1,
        receipt_state: 'uploading',
      },
    });
  });
  await page.route(`**${base}/image-preparations/${imageId}`, (route: Readonly<Route>) =>
    route.fulfill({ json: preparation() }),
  );
  await page.route(
    `**${base}/image-preparations/${imageId}/upload-access`,
    (route: Readonly<Route>) => {
      expect(route.request().method()).toBe('POST');
      expect(route.request().postData()).toBeNull();
      accessCount += 1;
      return failFirstAccess && accessCount === 1
        ? route.fulfill({ status: 503, json: { code: 'storage_unavailable' } })
        : route.fulfill({
            json: { url: destination, fields: { key: 'fixture-image', policy: 'fixture-policy' } },
          });
    },
  );
  await page.route(destination, (route: Readonly<Route>) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().headers()['cookie']).toBeUndefined();
    expect(route.request().headers()['referer']).toBeUndefined();
    transferCount += 1;
    return route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': '*' } });
  });
  await page.route(`**${base}/image-preparations/${imageId}/finalize`, (route: Readonly<Route>) => {
    expect(transferCount).toBe(1);
    expect(route.request().postData()).toBeNull();
    finalized = true;
    return route.fulfill({
      status: 202,
      json: {
        client_message_id: preparation().client_message_id,
        conversation_id: conversation.conversation_id,
        image_id: imageId,
        receipt_version: 2,
        receipt_state: 'queued',
      },
    });
  });
  await page.route(`**${base}/message-operations/*`, (route: Readonly<Route>) =>
    route.fulfill({
      json: stored ?? {
        conversation_id: conversation.conversation_id,
        client_message_id: preparation().client_message_id,
        outcome: 'unobserved',
      },
    }),
  );
  await page.route(new RegExp(`${base}/messages(?:\\?.*)?$`, 'u'), (route: Readonly<Route>) => {
    const confirmed = stored;
    if (route.request().method() === 'GET') {
      const current: Api['schemas']['MessageHistoryResponse'] = {
        ...history,
        anchor_sequence: confirmed === null ? history.anchor_sequence : confirmed.message.sequence,
        messages: confirmed === null ? history.messages : [...history.messages, confirmed.message],
      };
      expect(isHistory(current)).toBe(true);
      return route.fulfill({ json: current });
    }
    const body: unknown = route.request().postDataJSON();
    expect(finalized).toBe(true);
    expect(body).toEqual({
      client_message_id: preparation().client_message_id,
      image_id: imageId,
      text: caption,
    });
    stored = {
      conversation_id: conversation.conversation_id,
      client_message_id: preparation().client_message_id,
      operation_id: '00000000-0000-4000-8000-000000000051',
      outcome: 'confirmed',
      message: {
        ...message,
        author_id: identity.account_id,
        client_message_id: preparation().client_message_id,
        message_id: '00000000-0000-4000-8000-000000000052',
        sequence: 2,
        image_id: imageId,
        text: caption,
        sent_at: '2026-11-08T06:20:00Z',
      },
    };
    return route.fulfill({ json: stored });
  });
  await page.route(
    `**${base}/messages/00000000-0000-4000-8000-000000000052/image`,
    (route: Readonly<Route>) => route.fulfill({ contentType: 'image/jpeg', body: image }),
  );
  await page.route(`**${base}`, (route: Readonly<Route>) =>
    route.fulfill({ json: { ...conversation, last_confirmed_sequence: stored === null ? 1 : 2 } }),
  );
  await page.route(/\/api\/v1\/conversations(?:\?.*)?$/, (route: Readonly<Route>) => {
    const confirmed = stored;
    return route.fulfill({
      json:
        confirmed === null
          ? conversations
          : {
              ...conversations,
              conversations: conversations.conversations.map((entry) => ({
                ...entry,
                last_message: confirmed.message,
                activity_at: confirmed.message.sent_at,
              })),
            },
    });
  });
  return { starts: () => startRequests, stored: () => stored, transfers: () => transferCount };
}

test('C03 choose, replace and remove stay local and preserve the parent caption', async ({
  page,
  checkpoint,
}: Scenario) => {
  const writes = await setup(page);
  await open(page);
  const caption = page.getByRole('textbox', { name: 'Message', exact: true });
  await caption.fill('Keep my caption');
  await page
    .getByLabel('Attach an image', { exact: true })
    .setInputFiles({ name: 'sample.jpg', mimeType: 'image/jpeg', buffer: image });
  await expect(page.getByAltText('Selected image attachment')).toBeVisible();
  expect(writes()).toHaveLength(0);
  await checkpoint('image-local-selected.png');
  const originalSource = await page
    .getByAltText('Selected image attachment')
    .evaluate((element: Readonly<HTMLImageElement>) => element.src);
  await page
    .getByLabel('Attach an image', { exact: true })
    .setInputFiles({ name: 'replacement.png', mimeType: 'image/png', buffer: replacementImage });
  await expect(page.getByAltText('Selected image attachment')).not.toHaveAttribute(
    'src',
    originalSource,
  );
  await expect(page.getByAltText('Selected image attachment')).toHaveJSProperty(
    'naturalWidth',
    640,
  );
  expect(writes()).toHaveLength(0);
  await checkpoint('image-local-replaced.png');
  await page.getByRole('button', { name: 'Remove image', exact: true }).click();
  await expect(page.getByAltText('Selected image attachment')).toHaveCount(0);
  await expect(caption).toHaveValue('Keep my caption');
  expect(writes()).toHaveLength(0);
  await checkpoint('image-local-removed-caption-retained.png');
});

test('C03 invalid type and exact size limit do not create an upload', async ({
  page,
  checkpoint,
}: Scenario) => {
  const writes = await setup(page);
  await open(page);
  const caption = page.getByRole('textbox', { name: 'Message', exact: true });
  await caption.fill('Do not silently send this caption without the selected image.');
  await page
    .getByLabel('Attach an image', { exact: true })
    .setInputFiles({ name: 'sample.gif', mimeType: 'image/gif', buffer: Buffer.from('not jpeg') });
  await expect(page.getByRole('alert')).toHaveText('Choose a JPEG or PNG image.');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(caption).toHaveValue(
    'Do not silently send this caption without the selected image.',
  );
  expect(writes()).toHaveLength(0);
  await checkpoint('image-local-type-invalid.png');
  await page
    .getByLabel('Attach an image', { exact: true })
    .setInputFiles({ name: 'large.jpg', mimeType: 'image/jpeg', buffer: Buffer.alloc(10_000_001) });
  await expect(page.getByRole('alert')).toHaveText('Choose an image up to 10 MB.');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(caption).toHaveValue(
    'Do not silently send this caption without the selected image.',
  );
  expect(writes()).toHaveLength(0);
  await checkpoint('image-local-too-large.png');
  await page.getByRole('button', { name: 'Remove image', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(caption).toHaveValue(
    'Do not silently send this caption without the selected image.',
  );
  expect(writes()).toHaveLength(0);
  await checkpoint('image-invalid-removed-caption-retained.png');
});

test('C03 owner READY recovery remains unsent without explicit Send after reload', async ({
  page,
  checkpoint,
}: Scenario) => {
  const other = {
    ...ready,
    image_id: '00000000-0000-4000-8000-000000000043',
    client_message_id: '00000000-0000-4000-8000-000000000044',
    created_at: '2026-11-08T06:10:00Z',
  };
  const writes = await setup(page, [ready, other]);
  await open(page);
  await page.getByText('Your recent image preparations', { exact: true }).click();
  const firstRead = page.waitForRequest(`**${base}/image-preparations/${ready.image_id}/display`);
  await page
    .getByRole('listitem')
    .filter({ has: page.locator('time[datetime="2026-11-08T06:00:00Z"]') })
    .getByRole('button', { name: 'Select preparation', exact: true })
    .click();
  await firstRead;
  const preview = page.getByAltText('Preview of your selected prepared image');
  await expect(preview).toHaveJSProperty('naturalWidth', 640);
  const originalPreview = await preview.evaluate(
    (element: Readonly<HTMLImageElement>) => element.src,
  );
  const nextRead = page.waitForRequest(`**${base}/image-preparations/${other.image_id}/display`);
  await page
    .getByRole('listitem')
    .filter({ has: page.locator('time[datetime="2026-11-08T06:10:00Z"]') })
    .getByRole('button', { name: 'Select preparation', exact: true })
    .click();
  await nextRead;
  await expect(preview).not.toHaveAttribute('src', originalPreview);
  await expect(preview).toHaveJSProperty('naturalWidth', 640);
  await expect(
    page.getByText('The image is prepared. Press Send to publish it with your current caption.', {
      exact: true,
    }),
  ).toBeVisible();
  expect(writes()).toHaveLength(0);
  await checkpoint('image-ready-explicit-send-required.png');
  await page.reload();
  await expect(page.getByLabel('Attach an image', { exact: true })).toBeVisible();
  expect(writes()).toHaveLength(0);
  await checkpoint('image-reload-no-automatic-send.png');
});

const previewTest = test.extend({
  trace: {
    mode: 'retain-on-failure',
    screenshots: false,
    snapshots: true,
    sources: true,
  },
});

previewTest(
  'C03 confirmed peer image uses participant grant and exposes genuine Preview',
  async ({ page, checkpoint }: Scenario, info: Readonly<TestInfo>) => {
    await setup(page, [], { ...message, image_id: imageId });
    await open(page);
    const shared = page.getByAltText('Image shared in this conversation');
    await expect(shared).toBeVisible();
    await page.getByRole('button', { name: 'View image', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Close image', exact: true })).toBeVisible();
    await previewReady(page, info, 'open');
    await previewActionsInViewport(page);
    await previewBackdropEvidence(page, info, 'before-screenshot');
    try {
      await checkpoint('image-public-preview-open.png', { webkitPreview: 'open' });
    } finally {
      await previewBackdropEvidence(page, info, 'after-screenshot');
    }
    await previewRaw(page, info, 'image-public-preview-open');
    const slider = page.getByRole('slider', { name: 'Zoom out / Zoom in', exact: true });
    const initialZoom = await previewZoomValue(page);
    await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
    await expect(slider).not.toHaveAttribute('aria-valuetext', initialZoom);
    await previewReady(page, info, 'zoom');
    await previewActionsInViewport(page);
    await checkpoint('image-public-preview-zoomed.png', { webkitPreview: 'zoom' });
    await previewRaw(page, info, 'image-public-preview-zoomed');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: 'Close image', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'View image', exact: true })).toBeFocused();
    await expect(page.getByRole('button', { name: 'Report image', exact: true })).toBeVisible();
    await checkpoint('image-preview-closed-focus-returned.png');
  },
);

test('C03 report is bound to the peer confirmed image and requires an explanation for Other', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  await setup(page, [], { ...message, image_id: imageId });
  const contextId = '00000000-0000-4000-8000-000000000041';
  let submitted: Api['schemas']['MessageImageReportRequest'] | null = null;
  await page.route(
    `**${base}/messages/${message.message_id}/report-contexts`,
    (route: Readonly<Route>) => {
      expect(route.request().method()).toBe('POST');
      expect(route.request().postData()).toBeNull();
      return route.fulfill({
        status: 201,
        json: {
          id: contextId,
          conversation_id: conversation.conversation_id,
          image_id: imageId,
          message_id: message.message_id,
          kind: 'message_image',
          issued_at: '2026-11-08T06:20:00Z',
        },
      });
    },
  );
  await page.route('**/api/v1/reports', (route: Readonly<Route>) => {
    const body: unknown = route.request().postDataJSON();
    expect(body).toEqual({
      kind: 'message_image',
      context_id: contextId,
      category: 'other',
      comment: 'This image reveals another student’s private details.',
    });
    expect(route.request().headers()['idempotency-key']).toBeTruthy();
    submitted = {
      kind: 'message_image',
      context_id: contextId,
      category: 'other',
      comment: 'This image reveals another student’s private details.',
    };
    return route.fulfill({
      status: 201,
      json: {
        id: '00000000-0000-4000-8000-000000000042',
        kind: 'message_image',
        context_id: contextId,
        submitted_at: '2026-11-08T06:20:00Z',
      },
    });
  });
  await open(page);
  await page.getByRole('button', { name: 'Report image', exact: true }).click();
  const initialFits = await reportLayout(page, info, 'before-other');
  await page.getByRole('radio', { name: 'Other', exact: true }).check();
  await page.getByRole('button', { name: 'Submit report', exact: true }).click();
  expect(submitted).toBeNull();
  const before = await reportLayout(page, info, 'before-screenshot');
  await checkpoint('image-report-other-explanation-required.png');
  const after = await reportLayout(page, info, 'after-screenshot');
  expect(initialFits).toBe(true);
  expect(before).toBe(true);
  expect(after).toBe(true);
  await page
    .getByRole('textbox', { name: 'Private explanation (required for Other)', exact: true })
    .fill('This image reveals another student’s private details.');
  await page.getByRole('button', { name: 'Submit report', exact: true }).click();
  await expect(
    page.getByRole('status').filter({ hasText: 'Report submitted. Thank you.' }),
  ).toBeVisible();
  expect(submitted).not.toBeNull();
  await checkpoint('image-report-actual-context-submitted.png');
});

test('C03 own confirmed image has no report action and attachment controls reflow at 320px and 200% text', async ({
  page,
  checkpoint,
}: Scenario) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await setup(page, [], { ...message, author_id: identity.account_id, image_id: imageId });
  await open(page);
  await page.addStyleTag({ content: 'html { font-size: 200%; }' });
  await expect(page.getByRole('button', { name: 'Report image', exact: true })).toHaveCount(0);
  await page
    .getByLabel('Attach an image', { exact: true })
    .setInputFiles({ name: 'sample.jpg', mimeType: 'image/jpeg', buffer: image });
  await expect(page.getByAltText('Selected image attachment')).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await checkpoint('image-own-no-report-reflow320-text200.png');
});

test('C03 actual browser Back retires the viewer with its conversation route', async ({
  page,
  checkpoint,
}: Scenario) => {
  await setup(page, [], { ...message, image_id: imageId });
  await page.goto('/chats');
  await page.getByRole('link', { name: 'Maya Lim', exact: true }).click();
  await expect(page.getByAltText('Image shared in this conversation')).toBeVisible();
  await page.getByRole('button', { name: 'View image', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Close image', exact: true })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/chats$/u);
  await expect(page.getByRole('button', { name: 'Close image', exact: true })).toHaveCount(0);
  await expect(page.getByAltText('Image shared in this conversation')).toHaveCount(0);
  await checkpoint('image-browser-back-route-retired.png');
});

test('C03 explicit captioned Send uses the genuine mounted image protocol before confirming storage', async ({
  page,
  checkpoint,
}: Scenario) => {
  const flow = await pipeline(page, 'Sketch for our JOIN example');
  await open(page);
  const caption = page.getByRole('textbox', { name: 'Message', exact: true });
  await caption.fill('Sketch for our JOIN example');
  await page
    .getByLabel('Attach an image', { exact: true })
    .setInputFiles({ name: 'sample.jpg', mimeType: 'image/jpeg', buffer: image });
  expect(flow.starts()).toHaveLength(0);
  await checkpoint('image-pipeline-selected-unsent.png');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(caption).toHaveValue('');
  await expect(page.getByText('Sketch for our JOIN example', { exact: true })).toBeVisible();
  await expect(page.getByAltText('Image shared in this conversation')).toBeVisible();
  expect(flow.starts()).toHaveLength(1);
  expect(flow.transfers()).toBe(1);
  expect(flow.stored()).not.toBeNull();
  await checkpoint('image-pipeline-message-confirmed.png');
  await page.getByRole('link', { name: 'Back to chats', exact: true }).click();
  await expect(page.getByText('You: Sketch for our JOIN example', { exact: true })).toBeVisible();
  await checkpoint('image-pipeline-list-confirmed.png');
});

test('C03 access failure preserves immutable Send identity and original caption through explicit retry', async ({
  page,
  checkpoint,
}: Scenario) => {
  const flow = await pipeline(page, 'Original caption', true);
  await open(page);
  const caption = page.getByRole('textbox', { name: 'Message', exact: true });
  await caption.fill('Original caption');
  await page
    .getByLabel('Attach an image', { exact: true })
    .setInputFiles({ name: 'sample.jpg', mimeType: 'image/jpeg', buffer: image });
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry image send', exact: true })).toBeVisible();
  await expect(caption).toHaveValue('Original caption');
  await expect(caption).toHaveAttribute('readonly');
  expect(flow.transfers()).toBe(0);
  expect(flow.stored()).toBeNull();
  await checkpoint('image-pipeline-access-failed-uncertain.png');
  await page.getByRole('button', { name: 'Retry image send', exact: true }).click();
  await expect(caption).toHaveValue('');
  expect(flow.starts()).toHaveLength(2);
  expect(flow.transfers()).toBe(1);
  expectIdenticalStartRetry(flow.starts());
  expect(flow.stored()).not.toBeNull();
  await expect(page.getByText('Original caption', { exact: true })).toBeVisible();
  const rendition = page.getByAltText('Image shared in this conversation');
  await expect(rendition).toBeVisible();
  await expect(rendition).toHaveJSProperty('naturalWidth', 640);
  await expect(page.getByRole('button', { name: 'Retry messages', exact: true })).toHaveCount(0);
  await checkpoint('image-pipeline-explicit-retry-confirmed.png');
});
