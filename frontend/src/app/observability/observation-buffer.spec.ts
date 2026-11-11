import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createObservationBuffer } from './observation-buffer';
import type { BufferOptions } from './observation-buffer';
import type { DeliveryIntent, DeliveryResult } from './observation-contract';
const actorA = '00000000-0000-4000-8000-000000000001';
const actorB = '00000000-0000-4000-8000-000000000002';
function harness(overrides: Readonly<Partial<Omit<BufferOptions, 'delivery'>>> = {}) {
  let actor: string | null = actorA;
  let sequence = 100;
  let calls: readonly DeliveryIntent[] = [];
  let deliver: (intent: DeliveryIntent) => Promise<DeliveryResult> = (intent) =>
    Promise.resolve({
      kind: 'received',
      receipt: {
        schema_version: 1,
        accepted: intent.body.events.map((event) => event.event_id),
        duplicates: [],
        received_at: '2026-11-10T10:00:00Z',
      },
    });
  const buffer = createObservationBuffer({
    actor: () => actor,
    screen: () => 'chats',
    uuid: () => `00000000-0000-4000-8000-${String(sequence++).padStart(12, '0')}`,
    traceId: () => 'a'.repeat(32),
    release: () => null,
    clock: {
      monotonic: () => Date.now(),
      wall: () => Date.now(),
      schedule: (callback, delay) => {
        const timer = setTimeout(callback, delay);
        return () => {
          clearTimeout(timer);
        };
      },
    },
    ...overrides,
    delivery: {
      send: async (intent) => {
        calls = [...calls, intent];
        return await deliver(intent);
      },
    },
  });
  return {
    buffer,
    calls: () => calls,
    actor: (value: string | null) => {
      actor = value;
      buffer.synchronize();
    },
    delivery: (value: typeof deliver) => {
      deliver = value;
    },
  };
}
describe('authenticated ephemeral observation delivery', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-10T10:00:00Z'));
  });
  afterEach(() => {
    vi.useRealTimers();
  });
  it('retains no guest event, emits a closed identified batch and never stores input extras', async () => {
    const h = harness();
    h.actor(null);
    expect(h.buffer.observe({ kind: 'screen.viewed' })).toBe(false);
    h.actor(actorA);
    expect(h.buffer.observe({ kind: 'screen.viewed' })).toBe(true);
    await vi.advanceTimersByTimeAsync(250);
    expect(h.calls()).toHaveLength(1);
    expect(h.calls()[0]?.body.expected_actor_id).toBe(actorA);
    expect(h.calls()[0]?.body.release_id).toBeNull();
    expect(h.calls()[0]?.body.events[0]).toMatchObject({
      kind: 'screen.viewed',
      screen: 'chats',
      observed_at: '2026-11-10T10:00:00.000Z',
    });
    expect(h.calls()[0]?.json).toBe(JSON.stringify(h.calls()[0]?.body));
    h.buffer.dispose();
  });
  it('uses one in-flight <=20-event raw16KiB batch and bounded overflow counters', async () => {
    const h = harness();
    h.delivery(() => new Promise(() => undefined));
    for (let index = 0; index < 120; index += 1) {
      h.buffer.observe({ kind: 'screen.viewed' });
    }
    expect(h.buffer.drops().overflow).toBe(21);
    await vi.advanceTimersByTimeAsync(250);
    expect(h.calls()).toHaveLength(1);
    expect(h.calls()[0]?.body.events).toHaveLength(20);
    expect(new TextEncoder().encode(h.calls()[0]?.json).byteLength).toBeLessThanOrEqual(16384);
    h.buffer.flush();
    expect(h.calls()).toHaveLength(1);
    h.buffer.dispose();
    expect(h.calls()[0]?.signal.aborted).toBe(true);
  });
  it('ambiguous outcome replays exact key/JSON and validates exact disjoint receipt membership', async () => {
    const h = harness();
    let attempt = 0;
    h.delivery((intent) => {
      attempt += 1;
      return Promise.resolve(
        attempt === 1
          ? { kind: 'failed', status: 503 }
          : {
              kind: 'received',
              receipt: {
                schema_version: 1,
                accepted: [],
                duplicates: intent.body.events.map((event) => event.event_id),
                received_at: '2026-11-10T10:00:00Z',
              },
            },
      );
    });
    h.buffer.observe({ kind: 'screen.viewed' });
    await vi.advanceTimersByTimeAsync(1250);
    expect(h.calls()).toHaveLength(2);
    expect(h.calls()[1]?.key).toBe(h.calls()[0]?.key);
    expect(h.calls()[1]?.json).toBe(h.calls()[0]?.json);
    expect(h.buffer.drops().exhausted).toBe(0);
    h.buffer.dispose();
  });
  it('foreign or duplicate receipt IDs are not acceptance and finite retry exhaustion drops the batch', async () => {
    const h = harness();
    h.delivery(() =>
      Promise.resolve({
        kind: 'received',
        receipt: {
          schema_version: 1,
          accepted: [actorB],
          duplicates: [actorB],
          received_at: '2026-11-10T10:00:00Z',
        },
      }),
    );
    h.buffer.observe({ kind: 'screen.viewed' });
    await vi.advanceTimersByTimeAsync(4000);
    expect(h.calls()).toHaveLength(3);
    expect(h.buffer.drops().exhausted).toBe(1);
    h.buffer.dispose();
  });
  it('actor change aborts/discards old epoch and an old late receipt cannot affect the new actor', async () => {
    const h = harness();
    let settle: ((result: DeliveryResult) => void) | undefined;
    h.delivery(
      () =>
        new Promise((resolve) => {
          settle = resolve;
        }),
    );
    h.buffer.observe({ kind: 'screen.viewed' });
    await vi.advanceTimersByTimeAsync(250);
    const old = h.calls()[0];
    h.actor(actorB);
    expect(old?.signal.aborted).toBe(true);
    expect(h.buffer.drops().actor_changed).toBe(1);
    h.delivery((intent) =>
      Promise.resolve({
        kind: 'received',
        receipt: {
          schema_version: 1,
          accepted: intent.body.events.map((event) => event.event_id),
          duplicates: [],
          received_at: '2026-11-10T10:00:00Z',
        },
      }),
    );
    h.buffer.observe({ kind: 'screen.viewed' });
    settle?.({
      kind: 'received',
      receipt: {
        schema_version: 1,
        accepted: old?.body.events.map((event) => event.event_id),
        duplicates: [],
        received_at: '2026-11-10T10:00:00Z',
      },
    });
    await vi.advanceTimersByTimeAsync(250);
    expect(h.calls()).toHaveLength(2);
    expect(h.calls()[1]?.body.expected_actor_id).toBe(actorB);
    expect(
      h.calls()[1]?.body.events.some((event) => event.event_id === old?.body.events[0]?.event_id),
    ).toBe(false);
    h.buffer.dispose();
  });
  it('hung transport has an abort deadline and expired queued events cannot later be attributed', async () => {
    const h = harness();
    h.delivery(() => new Promise(() => undefined));
    h.buffer.observe({ kind: 'screen.viewed' });
    await vi.advanceTimersByTimeAsync(5250);
    expect(h.calls()[0]?.signal.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(45000);
    // Three original attempts and at most three attempts of its ONE quality report.
    expect(h.calls()).toHaveLength(6);
    expect(
      h.calls().filter((call) => call.body.events.some((event) => event.kind === 'screen.viewed')),
    ).toHaveLength(3);
    expect(
      h
        .calls()
        .filter((call) => call.body.events.every((event) => event.kind === 'quality.observed')),
    ).toHaveLength(3);
    await vi.advanceTimersByTimeAsync(60000);
    expect(h.calls()).toHaveLength(6);
    h.buffer.observe({ kind: 'screen.viewed' });
    vi.setSystemTime(Date.now() + 120000);
    h.buffer.flush();
    expect(h.buffer.drops().expired).toBe(1);
    h.buffer.dispose();
  });
  it('actor mismatch and other definitive4xx do not retry while429 honors bounded delay', async () => {
    const h = harness();
    h.delivery(() => Promise.resolve({ kind: 'failed', status: 409 }));
    h.buffer.observe({ kind: 'screen.viewed' });
    await vi.advanceTimersByTimeAsync(250);
    expect(h.buffer.drops().rejected).toBe(1);
    h.delivery(() => Promise.resolve({ kind: 'failed', status: 429, retryAfterMs: 10000 }));
    h.buffer.observe({ kind: 'screen.viewed' });
    await vi.advanceTimersByTimeAsync(6100);
    expect(h.calls()).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(9999);
    expect(h.calls()).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(h.calls()).toHaveLength(3);
    h.buffer.dispose();
  });
  it('explicit action handles use stable logical IDs rather than queue event IDs and dispose prevents capture', () => {
    const h = harness();
    const handle = h.buffer.beginAction('submit');
    expect(handle).toMatchObject({ action: 'submit', traceId: 'a'.repeat(32) });
    expect(handle?.actionId).not.toBeNull();
    h.buffer.dispose();
    expect(h.buffer.beginAction('retry')).toBeNull();
    expect(h.buffer.observe({ kind: 'screen.viewed' })).toBe(false);
  });
  it('reserves a bounded quality slot and freezes count/event ID through ambiguous retry while new losses get a new event', async () => {
    const h = harness();
    let attempt = 0;
    h.delivery((intent) => {
      attempt += 1;
      return Promise.resolve(
        attempt === 1
          ? { kind: 'failed', status: 503 }
          : {
              kind: 'received',
              receipt: {
                schema_version: 1,
                accepted: intent.body.events.map((event) => event.event_id),
                duplicates: [],
                received_at: '2026-11-10T10:00:00Z',
              },
            },
      );
    });
    for (let index = 0; index < 120; index += 1) h.buffer.observe({ kind: 'screen.viewed' });
    await vi.advanceTimersByTimeAsync(250);
    const first = h.calls()[0];
    expect(first?.body.events[0]).toMatchObject({
      kind: 'quality.observed',
      reason: 'overflow',
      count: 21,
    });
    h.buffer.observe({ kind: 'screen.viewed' });
    h.buffer.observe({ kind: 'screen.viewed' });
    await vi.advanceTimersByTimeAsync(1000);
    expect(h.calls()[1]?.json).toBe(first?.json);
    expect(h.calls()[1]?.key).toBe(first?.key);
    await vi.advanceTimersByTimeAsync(5100);
    expect(h.calls()[2]?.body.events[0]).toMatchObject({
      kind: 'quality.observed',
      reason: 'overflow',
      count: 2,
    });
    expect(h.calls()[2]?.body.events[0]?.event_id).not.toBe(first?.body.events[0]?.event_id);
    h.buffer.dispose();
  });
  it('never rebinds old-actor loss metadata and a quality-only rejected report cannot recursively enqueue another report', async () => {
    const h = harness();
    for (let index = 0; index < 120; index += 1) h.buffer.observe({ kind: 'screen.viewed' });
    h.actor(actorB);
    h.buffer.observe({ kind: 'screen.viewed' });
    await vi.advanceTimersByTimeAsync(250);
    expect(h.calls()[0]?.body.events).toHaveLength(1);
    expect(h.calls()[0]?.body.events[0]?.kind).toBe('screen.viewed');
    h.delivery(() => Promise.resolve({ kind: 'failed', status: 422 }));
    h.buffer.observe({ kind: 'quality.observed', reason: 'invalid', count: 1 });
    await vi.advanceTimersByTimeAsync(20000);
    const calls = h.calls().length;
    await vi.advanceTimersByTimeAsync(60000);
    expect(h.calls()).toHaveLength(calls);
    expect(
      h
        .calls()
        .flatMap((call) => call.body.events)
        .some((event) => event.kind === 'quality.observed' && event.reason === 'overflow'),
    ).toBe(false);
    h.buffer.dispose();
  });
  it('an excessive Retry-After suspends this epoch instead of retrying earlier than server policy', async () => {
    const h = harness();
    h.delivery(() => Promise.resolve({ kind: 'failed', status: 429, retryAfterMs: 120000 }));
    h.buffer.observe({ kind: 'screen.viewed' });
    await vi.advanceTimersByTimeAsync(120000);
    expect(h.calls()).toHaveLength(1);
    expect(h.buffer.observe({ kind: 'screen.viewed' })).toBe(false);
    h.buffer.dispose();
  });
  it.each([
    null,
    'not a receipt',
    {},
    { schema_version: 2 },
    { schema_version: 1, accepted: null },
    { schema_version: 1, accepted: [], duplicates: null },
    { schema_version: 1, accepted: [], duplicates: [], received_at: 0 },
    { schema_version: 1, accepted: [], duplicates: [], received_at: '2026-11-10T10:00:00' },
    { schema_version: 1, accepted: [], duplicates: [], received_at: '2026-99-99T10:00:00Z' },
  ])(
    'retries the original batch without acknowledging malformed receipt %#',
    async (receipt: unknown) => {
      const h = harness();
      h.delivery(() => Promise.resolve({ kind: 'received', receipt }));
      h.buffer.observe({ kind: 'screen.viewed' });
      await vi.advanceTimersByTimeAsync(1250);
      expect(h.calls()).toHaveLength(2);
      expect(h.calls()[1]?.json).toBe(h.calls()[0]?.json);
      expect(h.calls()[1]?.key).toBe(h.calls()[0]?.key);
      h.buffer.dispose();
    },
  );
  it('isolates a throwing receipt accessor and preserves ambiguous retry identity', async () => {
    const h = harness();
    const receipt: unknown = Object.defineProperty({}, 'schema_version', {
      get: () => {
        throw new Error('private decoder failure');
      },
    });
    h.delivery(() => Promise.resolve({ kind: 'received', receipt }));
    h.buffer.observe({ kind: 'screen.viewed' });
    await vi.advanceTimersByTimeAsync(1250);
    expect(h.calls()).toHaveLength(2);
    expect(h.calls()[1]?.json).toBe(h.calls()[0]?.json);
    h.buffer.dispose();
  });
  it('rejects duplicate IDs both in queued and in-flight events', async () => {
    const uuid = vi.fn(() => actorA);
    const h = harness({ uuid });
    h.delivery(() => new Promise(() => undefined));
    expect(h.buffer.observe({ kind: 'screen.viewed' })).toBe(true);
    expect(h.buffer.observe({ kind: 'screen.viewed' })).toBe(false);
    uuid.mockReturnValue(actorB);
    await vi.advanceTimersByTimeAsync(250);
    uuid.mockReturnValue(actorA);
    expect(h.buffer.observe({ kind: 'screen.viewed' })).toBe(false);
    expect(h.buffer.drops().invalid).toBe(2);
    expect(h.calls()).toHaveLength(1);
    h.buffer.dispose();
  });
  it.each([120000, -1000])(
    'expires and aborts an in-flight batch after clock discontinuity %i',
    async (offset) => {
      const h = harness();
      h.delivery(() => new Promise(() => undefined));
      h.buffer.observe({ kind: 'screen.viewed' });
      await vi.advanceTimersByTimeAsync(250);
      const original = h.calls()[0];
      vi.setSystemTime(Date.now() + offset);
      h.buffer.flush();
      expect(original?.signal.aborted).toBe(true);
      expect(h.buffer.drops().expired).toBe(1);
      h.buffer.dispose();
    },
  );
  it('expires queued work on backwards clock movement and disposal is idempotent', () => {
    const h = harness();
    h.buffer.observe({ kind: 'screen.viewed' });
    vi.setSystemTime(Date.now() - 1);
    h.buffer.flush();
    expect(h.buffer.drops().expired).toBe(1);
    h.buffer.dispose();
    h.buffer.dispose();
    expect(h.buffer.epoch()).toBeNull();
  });
  it('never retries a rejected retired transport under the replacement actor', async () => {
    const h = harness();
    let rejectOld: ((reason: Readonly<Error>) => void) | undefined;
    h.delivery(
      () =>
        new Promise((_resolve, reject) => {
          rejectOld = reject;
        }),
    );
    h.buffer.observe({ kind: 'screen.viewed' });
    await vi.advanceTimersByTimeAsync(250);
    h.actor(actorB);
    rejectOld?.(new Error('retired private diagnostic'));
    await vi.advanceTimersByTimeAsync(10000);
    expect(h.calls()).toHaveLength(1);
    expect(h.buffer.drops().exhausted).toBe(0);
    expect(h.buffer.drops().actor_changed).toBe(1);
    h.buffer.dispose();
  });
  it('retires a batch before its delivery microtask on synchronous owner change', async () => {
    const h = harness();
    h.buffer.observe({ kind: 'screen.viewed' });
    h.buffer.flush();
    h.actor(actorB);
    await vi.advanceTimersByTimeAsync(0);
    expect(h.calls()).toHaveLength(0);
    expect(h.buffer.drops().actor_changed).toBe(1);
    h.buffer.dispose();
  });
  it('aborts old delivery when the canonical actor reader fails', async () => {
    const actor = vi.fn((): string | null => actorA);
    const h = harness({ actor });
    h.delivery(() => new Promise(() => undefined));
    h.buffer.observe({ kind: 'screen.viewed' });
    await vi.advanceTimersByTimeAsync(250);
    actor.mockImplementation(() => {
      throw new Error('private session read');
    });
    h.buffer.synchronize();
    expect(h.calls()[0]?.signal.aborted).toBe(true);
    expect(h.buffer.epoch()).toBeNull();
    expect(h.buffer.drops().unavailable).toBeGreaterThan(0);
    expect(h.buffer.observe({ kind: 'screen.viewed' })).toBe(false);
    h.buffer.dispose();
  });
  it('rejects invalid action and trace correlations without creating handles', () => {
    const uuid = vi.fn(() => actorA);
    const h = harness({ uuid, traceId: () => '0'.repeat(32) });
    expect(h.buffer.beginAction('submit')).toBeNull();
    uuid.mockReturnValue('invalid');
    expect(h.buffer.beginAction('retry')).toBeNull();
    expect(h.calls()).toHaveLength(0);
    h.buffer.dispose();
  });
  it('returns no action handle when the ordinary queue budget is exhausted', () => {
    const h = harness();
    for (let index = 0; index < 99; index += 1)
      expect(h.buffer.observe({ kind: 'screen.viewed' })).toBe(true);
    expect(h.buffer.beginAction('submit')).toBeNull();
    expect(h.buffer.drops().overflow).toBe(1);
    h.buffer.dispose();
  });
  it('discards queued work safely when release lookup fails during assembly', async () => {
    const release = vi.fn(() => null);
    const h = harness({ release });
    h.buffer.observe({ kind: 'screen.viewed' });
    release.mockImplementation(() => {
      throw new Error('private release read');
    });
    h.buffer.flush();
    await vi.advanceTimersByTimeAsync(0);
    expect(h.calls()).toHaveLength(0);
    expect(h.buffer.drops().unavailable).toBe(1);
    h.buffer.dispose();
  });
  it('isolates screen producer failure without recursive quality reports', async () => {
    const h = harness({
      screen: () => {
        throw new Error('private route read');
      },
    });
    expect(h.buffer.observe({ kind: 'screen.viewed' })).toBe(false);
    expect(h.buffer.drops().invalid).toBe(1);
    await vi.advanceTimersByTimeAsync(10000);
    expect(h.calls()).toHaveLength(0);
    h.buffer.dispose();
  });
  it('rejects nonfinite wall time and cannot dispatch an invalid quality-only envelope', async () => {
    const h = harness({
      clock: {
        monotonic: () => Date.now(),
        wall: () => Number.NaN,
        schedule: (callback, delay) => {
          const timer = setTimeout(callback, delay);
          return () => {
            clearTimeout(timer);
          };
        },
      },
    });
    expect(h.buffer.observe({ kind: 'screen.viewed' })).toBe(false);
    h.buffer.flush();
    await vi.advanceTimersByTimeAsync(0);
    expect(h.calls()).toHaveLength(0);
    expect(h.buffer.drops().invalid).toBe(1);
    h.buffer.dispose();
  });
  it('never sends a selected batch with an invalid idempotency key', async () => {
    const uuid = vi.fn(() => 'invalid').mockReturnValueOnce(actorA);
    const h = harness({ uuid });
    expect(h.buffer.observe({ kind: 'screen.viewed' })).toBe(true);
    h.buffer.flush();
    await vi.advanceTimersByTimeAsync(0);
    expect(h.calls()).toHaveLength(0);
    expect(h.buffer.drops().invalid).toBe(1);
    h.buffer.dispose();
  });
  it('ignores a timeout callback already queued before disposal', async () => {
    let callbacks: readonly Readonly<{ readonly callback: () => void; readonly delay: number }>[] =
      [];
    const h = harness({
      clock: {
        monotonic: () => Date.now(),
        wall: () => Date.now(),
        schedule: (callback, delay) => {
          callbacks = [...callbacks, { callback, delay }];
          return () => undefined;
        },
      },
    });
    h.delivery(() => new Promise(() => undefined));
    h.buffer.observe({ kind: 'screen.viewed' });
    callbacks.find((item) => item.delay === 250)?.callback();
    await vi.advanceTimersByTimeAsync(0);
    expect(h.calls()).toHaveLength(1);
    const timeout = callbacks.find((item) => item.delay === 5000);
    expect(timeout).toBeDefined();
    h.buffer.dispose();
    timeout?.callback();
    await vi.advanceTimersByTimeAsync(10000);
    expect(h.calls()).toHaveLength(1);
    expect(h.calls()[0]?.signal.aborted).toBe(true);
    expect(h.buffer.drops().exhausted).toBe(0);
  });
});
