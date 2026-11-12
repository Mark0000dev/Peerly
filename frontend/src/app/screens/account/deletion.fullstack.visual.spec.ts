import type { Page, Response, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import { prepareChatsFixture } from '../../../../testing/chats-fixture';
import { isConfirmedDeletion, isDeletionPreparation } from './deletion-contract';

interface Scenario {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}

async function loseResponse(
  page: Readonly<Page>,
  outcome: 'confirmed' | 'response-lost',
): Promise<void> {
  if (outcome !== 'response-lost') return;
  await page.route('**/api/v1/me/deletion', async (route) => {
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    await route.abort('failed');
  });
}

function authorityResponse(page: Readonly<Page>, status: number): Promise<Response> {
  return page.waitForResponse(
    (response: Readonly<Response>) =>
      new URL(response.url()).pathname === '/api/v1/me' && response.status() === status,
  );
}

for (const [outcome, cohort] of [
  ['confirmed', 'deletion-messages'],
  ['response-lost', 'deletion-goal-change'],
] as const) {
  test(`P05 real ${outcome} deletion recovers proof and preserves the accepted peer history`, async ({
    page,
    checkpoint,
  }: Scenario, info: Readonly<TestInfo>) => {
    const seed = await prepareChatsFixture(page, cohort, info.project.name);
    const before = seed.history.messages;
    await loseResponse(page, outcome);
    await page.goto('/account/delete');
    await expect(page.getByRole('heading', { name: 'Delete account', exact: true })).toBeVisible();
    // The real preparation guard requires the cohort's Google identity source,
    // not only an otherwise readable session and verified institutional binding.
    const preparing = page.waitForResponse(
      (response: Readonly<Response>) =>
        new URL(response.url()).pathname === '/api/v1/me/deletion-workflows' &&
        response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Delete account', exact: true }).click();
    const preparation = await preparing;
    expect(preparation.status()).toBe(200);
    const workflow: unknown = await preparation.json();
    expect(isDeletionPreparation(workflow)).toBe(true);
    await expect(
      page.getByRole('heading', { name: 'Delete your account?', exact: true }),
    ).toHaveCount(1);
    const revoked = authorityResponse(page, 401);
    await page.getByRole('button', { name: 'Delete account permanently', exact: true }).click();
    await expect(page).toHaveURL('/account/deletion-status');
    await expect(
      page.getByRole('heading', { name: 'Deletion confirmed', exact: true }),
    ).toBeVisible();
    const proof = await page.request.get('/api/v1/me/deletion-status');
    expect(proof.status()).toBe(200);
    expect(proof.headers()['cache-control']).toContain('no-store');
    const receipt: unknown = await proof.json();
    expect(isConfirmedDeletion(receipt)).toBe(true);
    expect((await page.request.get('/api/v1/me')).status()).toBe(401);
    expect(await (await revoked).finished()).toBeNull();
    await checkpoint(`real-deletion-${outcome}.png`);
    const reloadedAuthority = authorityResponse(page, 401);
    await page.reload();
    await expect(
      page.getByRole('heading', { name: 'Deletion confirmed', exact: true }),
    ).toBeVisible();
    expect(await (await reloadedAuthority).finished()).toBeNull();
    expect(page.url()).not.toContain('workflow');
    await checkpoint(`real-deletion-${outcome}-reload.png`);

    // A real second participant remains authenticated. The older proof must
    // not be treated as evidence that this different live account was deleted.
    await seed.usePeer();
    const peerAuthority = authorityResponse(page, 200);
    await page.reload();
    await expect(
      page.getByText('The account for this request is deleted.', { exact: false }),
    ).toBeVisible();
    const identity = await page.request.get('/api/v1/me');
    expect(identity.status()).toBe(200);
    const peer: unknown = await identity.json();
    expect(peer).toMatchObject({ account_id: seed.personId, account_status: 'active' });
    expect(await (await peerAuthority).finished()).toBeNull();
    const [detailsResponse, historyResponse] = await Promise.all([
      page.request.get(`/api/v1/conversations/${seed.conversationId}`),
      page.request.get(`/api/v1/conversations/${seed.conversationId}/messages`),
    ]);
    expect(detailsResponse.status()).toBe(200);
    expect(historyResponse.status()).toBe(200);
    const details: unknown = await detailsResponse.json();
    const history: unknown = await historyResponse.json();
    expect(details).toMatchObject({
      conversation_id: seed.conversationId,
      can_send: false,
      peer: { person_id: seed.viewerId, display_name: null, photo_version: null, state: 'deleted' },
    });
    expect(history).toHaveProperty('messages', before);
    await checkpoint(`real-deletion-${outcome}-different-live-account.png`);
    await page.goto(`/chats?conversation=${seed.conversationId}`);
    await expect(
      page.getByRole('heading', { name: 'Deleted account', exact: true }).first(),
    ).toBeVisible();
    await expect(
      page.getByRole('list', { name: 'Confirmed messages' }).getByRole('listitem'),
    ).toHaveCount(before.length);
    await expect(page.getByRole('button', { name: 'Send message', exact: true })).toBeDisabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      info.project.use.viewport?.width ?? 1440,
    );
    await checkpoint(`real-deletion-${outcome}-retained-peer-history.png`);
  });
}
