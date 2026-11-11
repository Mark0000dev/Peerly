import { Buffer } from 'node:buffer';
import type { Page } from '@playwright/test';
import { test, expect } from '../../../../../../testing/visual';
import { verifiedActor } from '../../onboarding.fixtures';
import { ownProfile } from '../profile.fixtures';
import type { Api } from '../../../../api.generated';

interface Context {
  readonly page: Page;
  readonly checkpoint: (
    name: string,
    options?: Readonly<{ readonly fullPage: boolean }>,
  ) => Promise<void>;
}
const upload: Api['schemas']['PhotoUploadResponse'] = {
  id: '00000000-0000-0000-0000-000000000003',
  version: 1,
  state: 'uploading',
  content_type: 'image/png',
  size_bytes: 120,
  expected_photo_version: 0,
  failure: null,
  display_url: null,
  poll_after_ms: null,
  updated_at: '2026-11-07T12:00:00Z',
  upload_expires_at: '2026-11-07T12:10:00Z',
  processing_expires_at: '2026-11-07T12:20:00Z',
};
const history = { photo: null, uploads: [{ upload, source_sha256: 'a'.repeat(64) }] };

test('photo completion refresh failure preserves the live editor and unsaved profile draft', async ({
  page,
  checkpoint,
}: Context) => {
  const photo = {
    upload_id: upload.id,
    version: 1,
    display_url: `/api/v1/media/${upload.id}/display`,
  } satisfies Api['schemas']['CurrentPhotoResponse'];
  const ready = { ...upload, state: 'ready', display_url: photo.display_url } as const;
  await page.route('**/api/v1/media/uploads', async (route) => {
    await route.fulfill({
      json: { photo, uploads: [{ upload: ready, source_sha256: 'a'.repeat(64) }] },
    });
  });
  await page.route(`**/api/v1/media/${upload.id}`, async (route) => {
    await route.fulfill({ json: ready });
  });
  await page.route(`**/api/v1/media/${upload.id}/display`, async (route) => {
    await route.fulfill({
      contentType: 'image/jpeg',
      headers: { 'cache-control': 'private, no-store', 'x-content-type-options': 'nosniff' },
      body: Buffer.from(
        await page.evaluate(async () => {
          const canvas = new OffscreenCanvas(16, 16);
          const context = canvas.getContext('2d');
          if (context === null) throw new Error('Expected native canvas');
          context.putImageData(
            new ImageData(
              Uint8ClampedArray.from({ length: 16 * 16 * 4 }, (_, index) =>
                index % 4 === 3 ? 255 : 180,
              ),
              16,
              16,
            ),
            0,
            0,
          );
          return Array.from(
            new Uint8Array(
              await (await canvas.convertToBlob({ type: 'image/jpeg' })).arrayBuffer(),
            ),
          );
        }),
      ),
    });
  });
  await open(page);
  const name = page.getByRole('textbox', { name: 'Display name', exact: true });
  await name.fill('Unsaved name');
  let reads = 0;
  await page.route('**/api/v1/me/profile', async (route) => {
    reads += 1;
    await route.fulfill(
      reads === 1
        ? { status: 503, json: { code: 'unavailable' } }
        : { json: { ...ownProfile, photo } },
    );
  });
  await page.getByRole('button', { name: 'Check upload 1', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText(
    'We couldn’t refresh your profile. Your draft is still here.',
  );
  await expect(name).toHaveValue('Unsaved name');
  await expect(page.getByText('Your photo is saved.', { exact: true })).toBeVisible();
  await expect
    .poll(() =>
      page
        .getByRole('img', { name: 'Your current profile photo', exact: true })
        .evaluate(
          (image: Readonly<HTMLElement | SVGElement>) =>
            image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0,
        ),
    )
    .toBe(true);
  await checkpoint('photo-ready-profile-refresh-failed.png');
  await page.getByRole('button', { name: 'Retry profile refresh', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(name).toHaveValue('Unsaved name');
  await expect(page.getByText('Your photo is saved.', { exact: true })).toBeVisible();
  expect(reads).toBe(2);
  await checkpoint('photo-ready-profile-refresh-recovered.png');
});

async function open(page: Readonly<Page>, alive: () => boolean = () => true): Promise<void> {
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill(
      alive() ? { json: verifiedActor } : { status: 401, json: { code: 'session_required' } },
    );
  });
  await page.route('**/api/v1/me/profile', async (route) => {
    await route.fulfill({ json: ownProfile });
  });
  await page.goto('/onboarding');
  await page.getByRole('button', { name: 'Your profile', exact: true }).click();
  await page.getByRole('button', { name: 'Add photo', exact: true }).click();
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
}

async function nativePhoto(
  page: Readonly<Page>,
): Promise<Pick<Api['schemas']['StartPhotoRequest'], 'size_bytes' | 'sha256' | 'content_type'>> {
  const source = await page.evaluate(async () => {
    const canvas = new OffscreenCanvas(64, 32);
    const context = canvas.getContext('2d');
    if (context === null) throw new Error('Expected native canvas');
    context.putImageData(
      new ImageData(
        Uint8ClampedArray.from({ length: 64 * 32 * 4 }, (_, index) =>
          index % 4 === 3 ? 255 : 180,
        ),
        64,
        32,
      ),
      0,
      0,
    );
    const bytes = await (await canvas.convertToBlob({ type: 'image/png' })).arrayBuffer();
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return {
      bytes: Array.from(new Uint8Array(bytes)),
      sha256: Array.from(new Uint8Array(digest), (value) =>
        value.toString(16).padStart(2, '0'),
      ).join(''),
    };
  });
  await page
    .locator('input[type="file"]')
    .first()
    .setInputFiles({ name: 'photo.png', mimeType: 'image/png', buffer: Buffer.from(source.bytes) });
  await expect(page.getByRole('dialog')).toBeVisible();
  return { size_bytes: source.bytes.length, sha256: source.sha256, content_type: 'image/png' };
}
async function empty(page: Readonly<Page>): Promise<void> {
  await page.route('**/api/v1/media/uploads', async (route) => {
    await route.fulfill({ json: { photo: null, uploads: [] } });
  });
  await open(page);
  await expect(page.getByRole('button', { name: 'Choose photo', exact: true })).toBeEnabled();
}

test('photo recovery reads recent intents without automatically transferring after reload', async ({
  page,
  checkpoint,
}: Context) => {
  let writes = 0;
  await page.route('**/api/v1/media/**', async (route) => {
    if (route.request().method() !== 'GET') writes += 1;
    await route.fulfill({ json: route.request().url().endsWith('/uploads') ? history : upload });
  });
  await open(page);
  await expect(page.getByRole('heading', { name: 'Recent uploads', exact: true })).toBeVisible();
  expect(writes).toBe(0);
  await checkpoint('photo-recent-uploads.png');
  await page.getByRole('button', { name: 'Check upload 1', exact: true }).click();
  await expect(page.getByText('Waiting for the file transfer.', { exact: true })).toBeVisible();
  await expect(page.getByText('To continue this upload', { exact: false })).toBeVisible();
  expect(writes).toBe(0);
  await checkpoint('photo-reselect-required.png');
  await page.reload();
  await page.getByRole('button', { name: 'Your profile', exact: true }).click();
  await page.getByRole('button', { name: 'Add photo', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recent uploads', exact: true })).toBeVisible();
  expect(writes).toBe(0);
  await checkpoint('photo-recovery-reloaded.png');
});

test('photo projection failure has an explicit truthful retry and empty state', async ({
  page,
  checkpoint,
}: Context) => {
  let reads = 0;
  await page.route('**/api/v1/media/uploads', async (route) => {
    reads += 1;
    await route.fulfill(
      reads === 1
        ? { status: 503, json: { code: 'unavailable' } }
        : { json: { photo: null, uploads: [] } },
    );
  });
  await open(page);
  await expect(page.getByRole('alert')).toContainText('We couldn’t load your recent uploads');
  await expect(page.getByRole('button', { name: 'Choose photo', exact: true })).toBeDisabled();
  await checkpoint('photo-recent-failed.png');
  await page.getByRole('button', { name: 'Refresh recent uploads', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Choose photo', exact: true })).toBeEnabled();
  await expect(page.getByRole('heading', { name: 'Recent uploads', exact: true })).toHaveCount(0);
  expect(reads).toBe(2);
  await checkpoint('photo-recent-empty.png');
});

test('photo crop is local and keyboard operable at320px and200percent text', async ({
  page,
  checkpoint,
}: Context) => {
  let writes = 0;
  await page.route('**/api/v1/media/**', async (route) => {
    if (route.request().method() !== 'GET') writes += 1;
    await route.fulfill({ json: { photo: null, uploads: [] } });
  });
  await page.setViewportSize({ width: 320, height: 740 });
  await open(page);
  await page.addStyleTag({ content: ':root { font-size: 200%; }' });
  await nativePhoto(page);
  const canvas = page.getByRole('group', {
    name: 'Crop area. Use arrow keys to move, plus and minus to zoom, zero to reset.',
    exact: true,
  });
  await expect(canvas).toBeVisible();
  await canvas.focus();
  await canvas.press('+');
  await canvas.press('ArrowRight');
  await canvas.press('0');
  await expect(canvas).toBeFocused();
  expect(writes).toBe(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const before = await canvas.boundingBox();
  // The fullscreen editor scrolls independently. Capture the actual visible viewport,
  // then its bottom controls; retain a separate whole-page closed-form checkpoint.
  await checkpoint('photo-crop-keyboard320-200.png', { fullPage: false });
  expect(await canvas.boundingBox()).toEqual(before);
  await page.getByRole('button', { name: 'Use photo', exact: true }).scrollIntoViewIfNeeded();
  await expect(page.getByRole('button', { name: 'Use photo', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await checkpoint('photo-crop-actions320-200.png', { fullPage: false });
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(canvas).toHaveCount(0);
  expect(writes).toBe(0);
  await checkpoint('photo-crop-cancelled320-200.png');
});

test('photo upload pause offers explicit resume after the same sign-in is confirmed', async ({
  page,
  checkpoint,
}: Context) => {
  await empty(page);
  const source = await nativePhoto(page);
  const current = { ...upload, size_bytes: source.size_bytes, content_type: source.content_type };
  let releaseStart: () => void = () => undefined;
  let releaseSession: () => void = () => undefined;
  const startGate = new Promise<void>((resolve) => {
    releaseStart = resolve;
  });
  const sessionGate = new Promise<void>((resolve) => {
    releaseSession = resolve;
  });
  let starts = 0;
  let accesses = 0;
  await page.route('**/api/v1/media/uploads', async (route) => {
    if (route.request().method() === 'POST') {
      starts += 1;
      await startGate;
      await route.fulfill({ status: 202, json: current });
    } else
      await route.fulfill({
        json: { photo: null, uploads: [{ upload: current, source_sha256: source.sha256 }] },
      });
  });
  await page.route(`**/api/v1/media/${upload.id}`, async (route) => {
    await route.fulfill({ json: current });
  });
  await page.route(`**/api/v1/media/uploads/${upload.id}/access`, async (route) => {
    accesses += 1;
    await route.fulfill({ status: 503, json: { code: 'media_storage_unavailable' } });
  });
  try {
    const created = page.waitForRequest(
      (request) => request.url().endsWith('/media/uploads') && request.method() === 'POST',
    );
    await page
      .getByRole('button', { name: 'Use the original without cropping', exact: true })
      .click();
    await created;
    await page.route('**/api/v1/me', async (route) => {
      await sessionGate;
      await route.fulfill({ json: verifiedActor });
    });
    await page.getByRole('button', { name: 'Check status', exact: true }).click();
    await expect(
      page.getByText(
        'Your sign-in is being checked. Your selected photo is still here; uploading is paused.',
      ),
    ).toBeVisible();
    releaseStart();
    await expect(
      page.getByText('Your photo upload paused before processing could be confirmed.', {
        exact: false,
      }),
    ).toBeVisible();
    releaseSession();
    const resume = page.getByRole('button', { name: 'Resume selected photo', exact: true });
    await expect(resume).toBeEnabled();
    await expect(page.getByText('Waiting for the file transfer.', { exact: true })).toHaveCount(0);
    expect(starts).toBe(1);
    expect(accesses).toBe(0);
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      .toBe(true);
    await checkpoint('photo-transfer-paused-resume.png');
  } finally {
    releaseStart();
    releaseSession();
  }
});

test('photo storage outage is not presented as an unsuitable photo', async ({
  page,
  checkpoint,
}: Context) => {
  const current = { ...upload, state: 'rejected', failure: 'storage_unavailable' } as const;
  let writes = 0;
  await page.route('**/api/v1/media/**', async (route) => {
    if (route.request().method() !== 'GET') writes += 1;
    await route.fulfill({
      json: route.request().url().endsWith('/uploads')
        ? { photo: null, uploads: [{ upload: current, source_sha256: 'a'.repeat(64) }] }
        : current,
    });
  });
  await open(page);
  await page.getByRole('button', { name: 'Check upload 1', exact: true }).click();
  const alert = page.getByRole('alert');
  await expect(alert).toContainText('Photo storage is temporarily unavailable.');
  await expect(alert).toContainText('try uploading the same photo again later');
  await expect(alert).not.toContainText('We couldn’t use this photo.');
  await expect(page.getByRole('button', { name: 'Choose new photo', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Cancel upload', exact: true })).toHaveCount(0);
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    .toBe(true);
  expect(writes).toBe(0);
  await checkpoint('photo-storage-unavailable.png');
});

for (const scenario of [
  { state: 'queued', text: 'Your photo is waiting for processing.', pending: true },
  { state: 'processing', text: 'Your photo is being processed.', pending: true },
  { state: 'rejected', text: 'We couldn’t use this photo.', pending: false },
  { state: 'expired', text: 'This upload expired.', pending: false },
  { state: 'cancelled', text: 'This upload was cancelled.', pending: false },
] as const) {
  const current = {
    ...upload,
    state: scenario.state,
    failure: scenario.state === 'rejected' ? 'invalid_image' : null,
  } as const;
  const cancelCount = scenario.pending ? 1 : 0;

  test(`photo recovery projects actual ${scenario.state} without invented progress`, async ({
    page,
    checkpoint,
  }: Context) => {
    let writes = 0;
    await page.route('**/api/v1/media/**', async (route) => {
      if (route.request().method() !== 'GET') writes += 1;
      await route.fulfill({
        json: route.request().url().endsWith('/uploads')
          ? { photo: null, uploads: [{ upload: current, source_sha256: 'a'.repeat(64) }] }
          : current,
      });
    });
    await open(page);
    await page.getByRole('button', { name: 'Check upload 1', exact: true }).click();
    await expect(page.getByText(scenario.text, { exact: false })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Cancel upload', exact: true })).toHaveCount(
      cancelCount,
    );
    expect(writes).toBe(0);
    await checkpoint(`photo-${scenario.state}.png`);
  });
}

test('photo projection loading waits for the server rather than offering a duplicate upload', async ({
  page,
  checkpoint,
}: Context) => {
  let release: () => void = () => {
    throw new Error('Missing response gate');
  };
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/media/uploads', async (route) => {
    await pending;
    await route.fulfill({ json: { photo: null, uploads: [] } });
  });
  await open(page);
  await expect(
    page.getByText('Checking your recent photo uploads…', { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Choose photo', exact: true })).toBeDisabled();
  await checkpoint('photo-recent-loading.png');
  release();
  await expect(page.getByRole('button', { name: 'Choose photo', exact: true })).toBeEnabled();
  await checkpoint('photo-loading-resolved.png');
});

test('photo authorization failure clears the private editor and unsaved name', async ({
  page,
  checkpoint,
}: Context) => {
  let expired = false;
  await page.route('**/api/v1/media/uploads', async (route) => {
    expired = true;
    await route.fulfill({ status: 401, json: { code: 'session_required' } });
  });
  await open(page, () => !expired);
  await expect(page.getByRole('link', { name: 'Continue with Google', exact: true })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Display name', exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Your photo', exact: true })).toHaveCount(0);
  await checkpoint('photo-session-expired.png');
});

test('uncertain photo creation uses one immutable intent and resolves the actual queued outcome', async ({
  page,
  checkpoint,
}: Context) => {
  await empty(page);
  const source = await nativePhoto(page);
  const current = { ...upload, size_bytes: source.size_bytes };
  let attempts = 0;
  let firstKey: string | undefined;
  let accesses = 0;
  let release: () => void = () => {
    throw new Error('Missing creation gate');
  };
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/media/uploads', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        json: {
          photo: null,
          uploads: [{ upload: { ...current, state: 'queued' }, source_sha256: source.sha256 }],
        },
      });
      return;
    }
    attempts += 1;
    expect(route.request().postDataJSON()).toEqual({ ...source, expected_photo_version: 0 });
    const key = route.request().headers()['idempotency-key'];
    if (attempts === 1) {
      firstKey = key;
      await pending;
      await route.fulfill({ status: 503, json: { code: 'unavailable' } });
      return;
    }
    expect(key).toBe(firstKey);
    await route.fulfill({ json: current });
  });
  await page.route(`**/api/v1/media/${upload.id}`, async (route) => {
    await route.fulfill({ json: { ...current, state: 'queued' } });
  });
  await page.route('**/api/v1/media/uploads/*/access', async (route) => {
    accesses += 1;
    await route.abort('failed');
  });
  await page
    .getByRole('button', { name: 'Use the original without cropping', exact: true })
    .click();
  await expect(page.getByText('Requesting a photo upload…', { exact: true })).toBeVisible();
  await checkpoint('photo-start-pending.png');
  release();
  await expect(page.getByRole('alert')).toContainText('We couldn’t confirm the photo request.');
  expect(attempts).toBe(1);
  await checkpoint('photo-start-unknown.png');
  await page.getByRole('button', { name: 'Retry photo request', exact: true }).click();
  await expect(
    page.getByText('Your photo is waiting for processing.', { exact: true }),
  ).toBeVisible();
  expect(attempts).toBe(2);
  expect(accesses).toBe(0);
  await checkpoint('photo-start-resolved-queued.png');
});

test('photo finalization uncertainty retries the same command without another storage transfer', async ({
  page,
  checkpoint,
}: Context) => {
  await empty(page);
  const source = await nativePhoto(page);
  const current = { ...upload, size_bytes: source.size_bytes };
  let finalized = false;
  let attempts = 0;
  let firstKey: string | undefined;
  let transfers = 0;
  let release: () => void = () => {
    throw new Error('Missing finalization gate');
  };
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/media/uploads', async (route) => {
    await route.fulfill({
      json:
        route.request().method() === 'POST'
          ? current
          : {
              photo: null,
              uploads: [
                {
                  upload: { ...current, state: finalized ? 'queued' : 'uploading' },
                  source_sha256: source.sha256,
                },
              ],
            },
    });
  });
  await page.route(`**/api/v1/media/${upload.id}`, async (route) => {
    await route.fulfill({ json: { ...current, state: finalized ? 'queued' : 'uploading' } });
  });
  await page.route('**/api/v1/media/uploads/*/access', async (route) => {
    await route.fulfill({
      json: { url: 'https://storage.invalid/fixture', fields: { policy: 'fixture-only' } },
    });
  });
  await page.route('https://storage.invalid/fixture', async (route) => {
    transfers += 1;
    expect(route.request().headers()['x-csrf-token']).toBeUndefined();
    await route.fulfill({
      status: 204,
      headers: { 'access-control-allow-origin': new URL(page.url()).origin },
    });
  });
  await page.route('**/api/v1/media/uploads/*/finalize', async (route) => {
    attempts += 1;
    const key = route.request().headers()['idempotency-key'];
    if (attempts === 1) {
      firstKey = key;
      await pending;
      await route.fulfill({ status: 503, json: { code: 'unavailable' } });
      return;
    }
    expect(key).toBe(firstKey);
    finalized = true;
    await route.fulfill({ json: { ...current, state: 'queued' } });
  });
  await page
    .getByRole('button', { name: 'Use the original without cropping', exact: true })
    .click();
  await expect(page.getByText('Starting photo processing…', { exact: true })).toBeVisible();
  await expect(page.getByText('Waiting for the file transfer.', { exact: true })).toHaveCount(0);
  await expect(page.getByText('To continue this upload, reselect', { exact: false })).toHaveCount(
    0,
  );
  await checkpoint('photo-finalize-pending.png');
  release();
  await expect(page.getByRole('alert')).toContainText('We couldn’t confirm processing started.');
  await expect(page.getByText('Waiting for the file transfer.', { exact: true })).toHaveCount(0);
  expect(attempts).toBe(1);
  await checkpoint('photo-finalize-unknown.png');
  await page.getByRole('button', { name: 'Retry finalization', exact: true }).click();
  await expect(
    page.getByText('Your photo is waiting for processing.', { exact: true }),
  ).toBeVisible();
  expect(attempts).toBe(2);
  expect(transfers).toBe(1);
  await checkpoint('photo-finalize-resolved.png');
});
