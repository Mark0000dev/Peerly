import assert from 'node:assert/strict';
import { test } from 'node:test';
import { closeOwnedPage } from '../testing/owned-page.mts';

for (const primaryFailed of [false, true]) {
  test(`owned page closes before context disposal after primaryFailed=${primaryFailed}`, async () => {
    const events = [];
    const page = {
      isClosed: () => false,
      close: async () => {
        await Promise.resolve();
        events.push('page');
      },
    };
    assert.equal(await closeOwnedPage(page, primaryFailed), null);
    events.push('context');
    assert.deepEqual(events, ['page', 'context']);
  });
}

test('an already closed owned page needs no second browser operation', async () => {
  assert.equal(
    await closeOwnedPage(
      { isClosed: () => true, close: () => assert.fail('must not close twice') },
      false,
    ),
    null,
  );
});

test('cleanup failure cannot replace the primary assertion but fails a passing test', async () => {
  const failure = new Error('Controlled cleanup failure');
  const page = {
    isClosed: () => false,
    close: async () => {
      throw failure;
    },
  };
  assert.deepEqual(await closeOwnedPage(page, true), { error: failure });
  await assert.rejects(closeOwnedPage(page, false), (error) => error === failure);
});
