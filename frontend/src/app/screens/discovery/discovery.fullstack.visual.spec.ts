import type { Page, Route, APIResponse, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { prepareDiscoveryFixture } from '../../../../testing/discovery-fixture';

type Context = Readonly<{
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}>;
function isDeckResponse(url: string): boolean {
  return new URL(url).pathname === '/api/v1/discovery';
}
async function candidate(page: Readonly<Page>, personId: string): Promise<void> {
  await page.goto(`/discover?mode=find_help&person=${encodeURIComponent(personId)}`);
  await expect(page.getByRole('heading', { name: 'Aiko Tan', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Pass', exact: true })).toBeEnabled();
}

async function decodedPhoto(page: Readonly<Page>): Promise<void> {
  const image = page.getByRole('img', { name: 'Photo of Aiko Tan', exact: true });
  await expect(image).toHaveJSProperty('complete', true);
  await expect
    .poll(() =>
      image.evaluate((element: Readonly<Element>) =>
        element instanceof HTMLImageElement ? element.naturalWidth : 0,
      ),
    )
    .toBeGreaterThan(0);
}

async function committedReceipt(response: Readonly<APIResponse>): Promise<unknown> {
  expect(response.status()).toBe(200);
  return await response.json();
}
function equalReceipt(actual: unknown, receipt: unknown): void {
  expect(actual).toEqual(receipt);
}

test('actual activated students have genuine relevance and authorized JPEGs in all three modes', async ({
  page,
  checkpoint,
}: Context, info: Readonly<TestInfo>) => {
  const seed = await prepareDiscoveryFixture(page, `modes/${info.project.name}`);
  for (const mode of ['find_help', 'offer_help', 'study_together'] as const) {
    const response = page.waitForResponse(
      (value) =>
        isDeckResponse(value.url()) && new URL(value.url()).searchParams.get('mode') === mode,
    );
    const photo = page.waitForResponse((value) =>
      new URL(value.url()).pathname.startsWith(`/api/v1/people/${seed.personId}/photo/`),
    );
    await page.goto(`/discover?mode=${mode}&person=${encodeURIComponent(seed.personId)}`);
    const actual = await response;
    expect(actual.status()).toBe(200);
    const projection: unknown = await actual.json();
    expect(projection).toMatchObject({
      context: { mode },
      people: expect.arrayContaining([
        expect.objectContaining({
          id: seed.personId,
          display_name: 'Aiko Tan',
          relevance: expect.objectContaining({
            subject_id: seed.subjectId,
            subject_label: seed.subjectLabel,
          }),
        }),
      ]),
    });
    const bytes = await photo;
    expect(bytes.status()).toBe(200);
    expect(bytes.headers()['content-type']).toContain('image/jpeg');
    expect(bytes.headers()['cache-control']).toContain('no-store');
    expect(bytes.headers()['x-content-type-options']).toBe('nosniff');
    expect((await bytes.body()).length).toBeGreaterThan(0);
    await expect(page.getByRole('img', { name: 'Photo of Aiko Tan', exact: true })).toBeVisible();
    await decodedPhoto(page);
    await checkpoint(`real-${mode}.png`);
  }
});

test('actual private pass survives reload into passed view and reconsideration restores eligibility', async ({
  page,
  checkpoint,
}: Context, info: Readonly<TestInfo>) => {
  const seed = await prepareDiscoveryFixture(page, `pass/${info.project.name}`);
  await candidate(page, seed.personId);
  const committed = page.waitForResponse(
    (value) => new URL(value.url()).pathname === `/api/v1/discovery/passes/${seed.personId}`,
  );
  await page.getByRole('button', { name: 'Pass', exact: true }).click();
  expect((await committed).status()).toBe(200);
  await expect(page.getByRole('button', { name: 'Undo pass', exact: true })).toBeVisible();
  await checkpoint('real-private-pass.png');
  await page.goto('/discover?mode=find_help&view=passed');
  await expect(page.getByRole('list', { name: 'Passed people', exact: true })).toContainText(
    'Aiko Tan',
  );
  await page.reload();
  await expect(page.getByRole('list', { name: 'Passed people', exact: true })).toContainText(
    'Aiko Tan',
  );
  await checkpoint('real-passed-after-reload.png');
  await page.getByRole('button', { name: 'Review again', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'No available passed profiles', exact: true }),
  ).toBeVisible();
  await checkpoint('real-reconsidered.png');
  await page.getByRole('button', { name: 'Back to Discover', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Aiko Tan', exact: true })).toBeVisible();
  await checkpoint('real-reconsidered-deck.png');
});

function sameReplay(route: Readonly<Route>, payload: string | null, key: string | undefined): void {
  expect(route.request().postData()).toBe(payload);
  expect(route.request().headers()['idempotency-key']).toBe(key);
}

test('real server Undo and a durably stored pass replay preserve exact immutable intent', async ({
  page,
  checkpoint,
}: Context, info: Readonly<TestInfo>) => {
  const seed = await prepareDiscoveryFixture(page, `undo/${info.project.name}`);
  await candidate(page, seed.personId);
  await page.getByRole('button', { name: 'Pass', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Undo pass', exact: true })).toBeEnabled();
  await checkpoint('real-undo-capability.png');
  await page.getByRole('button', { name: 'Undo pass', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Aiko Tan', exact: true })).toBeVisible();
  await checkpoint('real-undo-restored.png');
  let writes = 0;
  let payload: string | null = null;
  let key: string | undefined;
  let receipt: unknown;
  await page.route(
    `**/api/v1/discovery/passes/${seed.personId}`,
    async (route: Readonly<Route>) => {
      writes += 1;
      if (writes === 1) {
        payload = route.request().postData();
        key = route.request().headers()['idempotency-key'];
        const committed = await route.fetch();
        receipt = await committedReceipt(committed);
        await route.abort();
      } else {
        sameReplay(route, payload, key);
        const replay = await route.fetch();
        equalReceipt(await committedReceipt(replay), receipt);
        await route.fulfill({ response: replay });
      }
    },
  );
  await page.getByRole('button', { name: 'Pass', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Decision not yet confirmed');
  await checkpoint('real-pass-reply-lost.png');
  await page.getByRole('button', { name: 'Retry same decision', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Undo pass', exact: true })).toBeEnabled();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await checkpoint('real-pass-replayed.png');
});
