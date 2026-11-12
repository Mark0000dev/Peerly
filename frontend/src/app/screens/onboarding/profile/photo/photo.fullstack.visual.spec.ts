import { Buffer } from 'node:buffer';
import type { Page, Route, TestInfo } from '@playwright/test';
import { verifyFixtureStudent } from '../../../../../../testing/verified-student';
import { test, expect } from '../../../../../../testing/visual';

async function nativeFile(
  page: Readonly<Page>,
): Promise<{ readonly name: string; readonly mimeType: string; readonly buffer: Buffer }> {
  const bytes = await page.evaluate(async () => {
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
    return Array.from(
      new Uint8Array(await (await canvas.convertToBlob({ type: 'image/png' })).arrayBuffer()),
    );
  });
  return { name: 'fixture.png', mimeType: 'image/png', buffer: Buffer.from(bytes) };
}

async function loseCreationResponse(route: Readonly<Route>): Promise<void> {
  if (route.request().method() !== 'POST') {
    await route.continue();
    return;
  }
  const response = await route.fetch();
  expect(response.status()).toBe(202);
  // The actual server transaction commits; only its browser response is lost.
  await route.abort('failed');
}

test('real photo upload processes native crop bytes and restores the private READY projection after reload', async ({
  page,
  checkpoint,
}: {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}, info: Readonly<TestInfo>) => {
  await verifyFixtureStudent(page, info.project.name, 'photo');
  await page.getByRole('button', { name: 'Your profile', exact: true }).click();
  await page.getByRole('button', { name: 'Add photo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Choose photo', exact: true })).toBeEnabled();
  await checkpoint('real-photo-empty.png');
  await page
    .locator('input[type="file"]')
    .first()
    .setInputFiles(await nativeFile(page));
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Use photo', exact: true }).click();
  await expect(
    page.getByText('Your photo is waiting for processing.', { exact: true }),
  ).toBeVisible();
  await checkpoint('real-photo-queued.png');
  const processed = await page.request.post('http://127.0.0.1:8768/__fixture/photo/process');
  expect(processed.status()).toBe(200);
  const outcome: unknown = await processed.json();
  expect(outcome).toEqual({ outcome: 'ready' });
  await page.getByRole('button', { name: 'Check photo status', exact: true }).click();
  await expect(page.getByText('Your photo is saved.', { exact: true })).toBeVisible();
  const photo = page.getByRole('img', { name: 'Your current profile photo', exact: true });
  await expect(photo).toBeVisible();
  await expect(photo).toHaveJSProperty('naturalWidth', 32);
  await checkpoint('real-photo-ready.png');
  await page.reload();
  await page.getByRole('button', { name: 'Your profile', exact: true }).click();
  await page.getByRole('button', { name: 'Change photo', exact: true }).click();
  await expect(photo).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Recent uploads', exact: true })).toBeVisible();
  await expect(page.locator('input[type="file"]').first()).toHaveValue('');
  await checkpoint('real-photo-ready-reloaded.png');
});

test('real committed photo creation survives a lost202 and reload before explicit same-file reselection', async ({
  page,
  checkpoint,
}: {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}, info: Readonly<TestInfo>) => {
  await verifyFixtureStudent(page, info.project.name, 'photo-resume');
  await page.getByRole('button', { name: 'Your profile', exact: true }).click();
  await page.getByRole('button', { name: 'Add photo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Choose photo', exact: true })).toBeEnabled();
  const file = await nativeFile(page);
  let creations = 0;
  let transfers = 0;
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/v1/media/uploads'))
      creations += 1;
    if (request.method() === 'POST' && request.url().startsWith('https://127.0.0.1:8769/uploads/'))
      transfers += 1;
  });
  await page.route('**/api/v1/media/uploads', loseCreationResponse);
  await page.locator('input[type="file"]').first().setInputFiles(file);
  await page
    .getByRole('button', { name: 'Use the original without cropping', exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText('We couldn’t confirm the photo request.');
  expect(creations).toBe(1);
  expect(transfers).toBe(0);
  await checkpoint('real-photo-lost202.png');
  await page.unroute('**/api/v1/media/uploads', loseCreationResponse);
  await page.reload();
  await page.getByRole('button', { name: 'Your profile', exact: true }).click();
  await page.getByRole('button', { name: 'Add photo', exact: true }).click();
  await page.getByRole('button', { name: 'Check upload 1', exact: true }).click();
  await expect(page.getByText('Waiting for the file transfer.', { exact: true })).toBeVisible();
  await expect(page.locator('input[type="file"]').first()).toHaveValue('');
  expect(creations).toBe(1);
  expect(transfers).toBe(0);
  await checkpoint('real-photo-lost202-reselect.png');
  await page.locator('input[type="file"]').first().setInputFiles(file);
  await page
    .getByRole('button', { name: 'Use the original without cropping', exact: true })
    .click();
  await expect(
    page.getByText('Your photo is waiting for processing.', { exact: true }),
  ).toBeVisible();
  expect(creations).toBe(1);
  expect(transfers).toBe(1);
  await checkpoint('real-photo-resumed-queued.png');
  const step = await page.request.post('http://127.0.0.1:8768/__fixture/photo/process');
  expect(step.status()).toBe(200);
  await page.getByRole('button', { name: 'Check photo status', exact: true }).click();
  await expect(page.getByText('Your photo is saved.', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('img', { name: 'Your current profile photo', exact: true }),
  ).toHaveJSProperty('naturalWidth', 64);
  await checkpoint('real-photo-resumed-ready.png');
});
