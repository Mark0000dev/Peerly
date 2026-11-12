import assert from 'node:assert/strict';
import { Buffer } from 'node:buffer';
import { URL } from 'node:url';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { captureWebkitPreviewFrame } from '../testing/webkit-preview-frame.mts';

const jpeg = readFileSync(new URL('../testing/fixtures/chat-study-image.jpg', import.meta.url));
const options = { engine: 'webkit', state: 'open', timeoutMs: 20 };
function fixture(change = (frame) => frame, cleanup = async () => {}) {
  const events = [];
  return {
    events,
    page: {
      viewportSize: () => ({ width: 640, height: 480 }),
      screencast: {
        start: async ({ onFrame, size, quality }) => {
          events.push('start');
          assert.deepEqual(size, { width: 640, height: 480 });
          assert.equal(quality, 100);
          const frame = change(
            {
              data: jpeg,
              timestamp: Date.now(),
              viewportWidth: 640,
              viewportHeight: 480,
            },
            events.filter((entry) => entry === 'start').length,
          );
          if (frame !== null) await onFrame(frame);
          return { [Symbol.dispose]() {} };
        },
        stop: async () => {
          events.push('stop');
          await cleanup();
        },
      },
    },
  };
}

test('three independently started fresh full-size JPEG frames must match exact bytes', async () => {
  const { page, events } = fixture();
  assert.deepEqual(await captureWebkitPreviewFrame(page, options), jpeg);
  assert.deepEqual(events, ['start', 'stop', 'start', 'stop', 'start', 'stop']);
});
for (const [name, change, message] of [
  ['stale', (frame) => ({ ...frame, timestamp: 0 }), /Stale/],
  ['wrong viewport', (frame) => ({ ...frame, viewportWidth: 320 }), /dimensions/],
  [
    'scaled JPEG',
    (frame) => {
      const data = Buffer.from(frame.data);
      // Actual JPEG SOF dimensions must agree too, not only callback metadata.
      const marker = data.indexOf(Buffer.from([0xff, 0xc0]));
      assert.ok(marker >= 0);
      data.writeUInt16BE(320, marker + 7);
      return { ...frame, data };
    },
    /dimensions/,
  ],
  ['not JPEG', (frame) => ({ ...frame, data: Buffer.from('not image') }), /not JPEG/],
  [
    'different fresh bytes',
    (frame, cycle) => ({
      ...frame,
      data: cycle === 1 ? frame.data : Buffer.concat([frame.data, Buffer.from([0])]),
    }),
    /byte-stable/,
  ],
]) {
  test(`${name} fails closed and stops the public capture`, async () => {
    const { page, events } = fixture(change);
    await assert.rejects(captureWebkitPreviewFrame(page, options), message);
    assert.equal(events.at(-1), 'stop');
  });
}
test('no frame times out without hiding cleanup', async () => {
  const { page, events } = fixture(() => null);
  await assert.rejects(captureWebkitPreviewFrame(page, options), /No fresh/);
  assert.deepEqual(events, ['start', 'stop']);
});
test('cleanup failure fails a successful capture', async () => {
  const { page } = fixture(undefined, async () => {
    throw new Error('stop failed');
  });
  await assert.rejects(captureWebkitPreviewFrame(page, options), /stop failed/);
});
test('capture and cleanup errors are both retained', async () => {
  const { page } = fixture(
    (frame) => ({ ...frame, timestamp: 0 }),
    async () => {
      throw new Error('stop failed');
    },
  );
  await assert.rejects(
    captureWebkitPreviewFrame(page, options),
    (error) =>
      error instanceof AggregateError &&
      /Stale/.test(error.errors[0].message) &&
      /stop failed/.test(error.errors[1].message),
  );
});
test('unsupported public API fails without a private fallback', async () => {
  await assert.rejects(
    captureWebkitPreviewFrame(
      { viewportSize: () => ({ width: 640, height: 480 }), screencast: {} },
      options,
    ),
    /unavailable/,
  );
});

for (const afterFrame of [false, true]) {
  test(`public start rejection fails even when frame already arrived=${afterFrame}`, async () => {
    const { page, events } = fixture();
    const original = page.screencast.start;
    page.screencast.start = async (settings) => {
      if (afterFrame) await original(settings);
      throw new Error('public start failed');
    };
    await assert.rejects(captureWebkitPreviewFrame(page, options), /public start failed/);
    assert.equal(events.at(-1), 'stop');
  });
}

test('unstable failing frame is preserved before strict rejection', async () => {
  const recorded = [];
  const { page } = fixture((frame, cycle) => ({
    ...frame,
    data: cycle === 1 ? frame.data : Buffer.concat([frame.data, Buffer.from([0])]),
  }));
  await assert.rejects(
    captureWebkitPreviewFrame(page, {
      ...options,
      recordFrame: async (frame, cycle) => {
        recorded.push({ data: frame.data, cycle });
      },
    }),
    /byte-stable/,
  );
  assert.deepEqual(
    recorded.map((frame) => frame.cycle),
    [0, 1],
  );
  assert.notDeepEqual(recorded[0].data, recorded[1].data);
});
