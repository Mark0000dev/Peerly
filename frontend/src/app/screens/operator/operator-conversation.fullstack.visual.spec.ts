import type { Page, Response, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../testing/visual';
import {
  prepareOperatorFixture,
  changeOperatorFixtureGrant,
  readOperatorFixtureAudit,
  readOperatorStudentReadCounts,
} from '../../../../testing/operator-fixture';
import { isOperatorMessages } from './operator-conversation-contract';

type Scenario = Readonly<{
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}>;
function required<T>(value: T | null): T {
  if (value === null) throw new Error('Missing actual retained conversation source');
  return value;
}
function response(page: Readonly<Page>, id: string): Promise<Response> {
  return page.waitForResponse(
    (r) => new URL(r.url()).pathname === `/api/v1/operator/conversations/${id}/messages`,
  );
}
async function actual(value: Readonly<Response>) {
  expect(value.status()).toBe(200);
  expect(value.headers()['cache-control']).toBe('no-store');
  const body: unknown = await value.json();
  if (!isOperatorMessages(body)) throw new Error('Invalid actual operator message response');
  return body;
}
const region = (page: Readonly<Page>) =>
  page.getByRole('region', { name: 'Retained conversation', exact: true });

test('real M05 retained53 text source IDs pagination noACK and audited privileged reads', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'conversations', info.project.name);
  const refs = required(seed.conversation);
  const before = await readOperatorStudentReadCounts(page, seed.operatorId);
  const firstRead = response(page, refs.id);
  await page.goto(`/operator/conversations?conversation=${refs.id}`);
  const first = await actual(await firstRead);
  expect(first.relationship_id).toBe(refs.relationshipId);
  expect(first.request_id).toBe(refs.requestId);
  expect(first.low_id).toBe(refs.lowId);
  expect(first.high_id).toBe(refs.highId);
  expect(first.messages).toHaveLength(50);
  expect(first.messages.map((m) => m.sequence)).toEqual(
    Array.from({ length: 50 }, (_, i) => i + 4),
  );
  expect(first.next_cursor).not.toBeNull();
  await expect(region(page).getByRole('article')).toHaveCount(50);
  for (const m of first.messages) {
    await expect(
      region(page).getByRole('article', {
        name: `Message sequence ${String(m.sequence)}`,
        exact: true,
      }),
    ).toContainText(required(m.text));
  }
  await expect(region(page).locator('script')).toHaveCount(0);
  const olderRead = response(page, refs.id);
  await page.getByRole('button', { name: 'Older message page' }).click();
  const older = await actual(await olderRead);
  expect(older.messages.map((m) => m.sequence)).toEqual([1, 2, 3]);
  expect(new Set([...first.messages, ...older.messages].map((m) => m.message_id)).size).toBe(53);
  expect(older.anchor_sequence).toBe(first.anchor_sequence);
  expect(older.next_cursor).toBeNull();
  await expect(region(page).getByRole('article')).toHaveCount(3);
  await checkpoint('real-conversation-older3.png');
  expect(await readOperatorStudentReadCounts(page, seed.operatorId)).toEqual(before);
  const audit = await readOperatorFixtureAudit(page, seed.operatorId);
  expect(audit.audits).toBe(2);
  expect(audit.linkedEvents).toBe(audit.audits);
});

test('real M05 retained empty accepted container and missing conversation remain honest', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'conversations-empty', info.project.name);
  const refs = required(seed.conversation);
  const before = await readOperatorStudentReadCounts(page, seed.operatorId);
  const read = response(page, refs.id);
  await page.goto(`/operator/conversations?conversation=${refs.id}`);
  const empty = await actual(await read);
  expect(empty.messages).toEqual([]);
  expect(empty.anchor_sequence).toBe(0);
  expect(empty.request_id).toBe(refs.requestId);
  await expect(region(page)).toContainText('No retained messages');
  await checkpoint('real-conversation-empty.png');
  const missing = response(page, seed.targets.active);
  await page
    .getByRole('textbox', { name: 'Conversation ID', exact: true })
    .fill(seed.targets.active);
  await page.getByRole('button', { name: 'Open retained conversation', exact: true }).click();
  expect((await missing).status()).toBe(404);
  await expect(page.getByRole('alert')).toContainText('This retained conversation is unavailable');
  await checkpoint('real-conversation404.png');
  expect(await readOperatorStudentReadCounts(page, seed.operatorId)).toEqual(before);
  const audit = await readOperatorFixtureAudit(page, seed.operatorId);
  expect(audit.audits).toBe(2);
  expect(audit.linkedEvents).toBe(audit.audits);
});

test('real M05 revoked grant retires private messages and recheck restores; initial320 text200 keyboard', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'conversations-revocation', info.project.name);
  const refs = required(seed.conversation);
  await page.setViewportSize({ width: 320, height: 760 });
  await page.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      document.documentElement.style.setProperty('font-size', '200%');
    });
  });
  await page.goto(`/operator/conversations?conversation=${refs.id}`);
  await expect(region(page).getByRole('article')).toHaveCount(50);
  await changeOperatorFixtureGrant(page, seed.operatorId, false);
  const denied = response(page, refs.id);
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  expect((await denied).status()).toBe(403);
  await expect(
    page.getByRole('heading', { name: 'Operator access denied', exact: true }),
  ).toBeVisible();
  await expect(region(page)).toHaveCount(0);
  await checkpoint('real-conversation-revoked.png');
  await changeOperatorFixtureGrant(page, seed.operatorId, true);
  await page.getByRole('button', { name: 'Check operator access again' }).click();
  await expect(region(page).getByRole('article')).toHaveCount(50);
  await page.getByRole('button', { name: 'Older message page' }).click();
  await expect(region(page).getByRole('article')).toHaveCount(3);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await checkpoint('real-conversation320-restored.png');
  await page.getByRole('textbox', { name: 'Conversation ID', exact: true }).focus();
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('button', { name: 'Open retained conversation', exact: true }),
  ).toBeFocused();
  await checkpoint('real-conversation320-keyboard.png');
});

test('real M05 replacement operator cannot reuse former grant-bound signed cursor', async ({
  page,
  checkpoint,
}: Scenario, info: Readonly<TestInfo>) => {
  const seed = await prepareOperatorFixture(page, 'conversations-replacement', info.project.name);
  const refs = required(seed.conversation);
  await page.goto(`/operator/conversations?conversation=${refs.id}`);
  await expect(region(page).getByRole('article')).toHaveCount(50);
  await page.getByRole('button', { name: 'Older message page' }).click();
  await expect(region(page).getByRole('article')).toHaveCount(3);
  await expect(page).toHaveURL(/cursor=/);
  await checkpoint('real-conversation-replacement-before.png');
  await changeOperatorFixtureGrant(page, seed.operatorId, false);
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Operator access denied', exact: true }),
  ).toBeVisible();
  await seed.replaceActor();
  const read = response(page, refs.id);
  await page.getByRole('button', { name: 'Check operator access again' }).click();
  const fresh = await read;
  expect(new URL(fresh.url()).searchParams.get('cursor')).toBeNull();
  await actual(fresh);
  await expect(region(page).getByRole('article')).toHaveCount(50);
  await expect(page).not.toHaveURL(/cursor=/);
  await checkpoint('real-conversation-replacement-after.png');
  const audit = await readOperatorFixtureAudit(page, seed.replacementId);
  expect(audit.audits).toBeGreaterThanOrEqual(1);
  expect(audit.linkedEvents).toBe(audit.audits);
});
