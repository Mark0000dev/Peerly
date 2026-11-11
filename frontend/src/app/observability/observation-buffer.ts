import { screens, uuid, traceId, qualityReasons } from './observation-contract';
import type {
  Action,
  ActionHandle,
  Batch,
  Delivery,
  Epoch,
  Observation,
  ObservationInput,
  Receipt,
  QualityReason,
  Screen,
} from './observation-contract';
import { sanitizeObservation, validatedRelease } from './observation-privacy';
import type { ReleaseAssets } from './observation-privacy';
interface ObservationClock {
  readonly monotonic: () => number;
  readonly wall: () => number;
  readonly schedule: (callback: () => void, delay: number) => () => void;
}
export interface BufferOptions {
  readonly actor: () => string | null;
  readonly screen: () => Screen;
  readonly uuid: () => string;
  readonly traceId: () => string;
  readonly delivery: Delivery;
  readonly clock: ObservationClock;
  readonly release: () => ReleaseAssets | null;
}
type DropReason = QualityReason | 'actor_changed';
type DropCounts = Readonly<Record<DropReason, number>>;
export interface ObservationBuffer {
  readonly observe: (input: ObservationInput) => boolean;
  readonly beginAction: (action: Action) => ActionHandle | null;
  readonly epoch: () => Epoch | null;
  readonly synchronize: () => void;
  readonly flush: () => void;
  readonly dispose: () => void;
  readonly drops: () => DropCounts;
}
interface Queued {
  readonly event: Observation;
  readonly admitted: number;
  readonly bytes: number;
}
interface Pending {
  readonly key: string;
  readonly body: Batch;
  readonly json: string;
  readonly events: readonly Queued[];
  readonly epoch: number;
  readonly attempts: number;
}
const maximumEvents = 100;
const maximumQueueBytes = 64 * 1024;
const maximumBatchBytes = 16 * 1024;
const maximumAge = 60000;
const batchSpacing = 6100;
function receipt(value: unknown, events: readonly Queued[]): value is Receipt {
  try {
    return validReceipt(value, events);
  } catch {
    return false;
  }
}
function validReceipt(value: unknown, events: readonly Queued[]): value is Receipt {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('schema_version' in value) ||
    value.schema_version !== 1 ||
    !('accepted' in value) ||
    !Array.isArray(value.accepted) ||
    !('duplicates' in value) ||
    !Array.isArray(value.duplicates) ||
    !('received_at' in value) ||
    typeof value.received_at !== 'string' ||
    !/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(value.received_at) ||
    !Number.isFinite(Date.parse(value.received_at))
  )
    return false;
  const accepted: readonly unknown[] = value.accepted;
  const duplicates: readonly unknown[] = value.duplicates;
  const ids: readonly unknown[] = [...accepted, ...duplicates];
  return (
    Object.keys(value).every((key) =>
      ['schema_version', 'accepted', 'duplicates', 'received_at'].includes(key),
    ) &&
    ids.length === events.length &&
    ids.every(uuid) &&
    new Set(ids).size === ids.length &&
    events.every((item) => ids.includes(item.event.event_id))
  );
}
export function createObservationBuffer(options: BufferOptions): ObservationBuffer {
  const encoder = new TextEncoder();
  let owner: string | null = null;
  let generation = 0;
  let startedAt = 0;
  let queue: readonly Queued[] = [];
  let pending: Pending | null = null;
  let qualitySlot: Queued | null = null;
  const emptyQuality = (): Readonly<Record<QualityReason, number>> => ({
    overflow: 0,
    invalid: 0,
    expired: 0,
    rejected: 0,
    exhausted: 0,
    unavailable: 0,
  });
  let qualityCounts = emptyQuality();
  let controller: AbortController | null = null;
  let cancelTimer: (() => void) | null = null;
  let cancelDeadline: (() => void) | null = null;
  let nextNewBatch = 0;
  let disposed = false;
  let suspended = false;
  let counts: DropCounts = {
    overflow: 0,
    invalid: 0,
    expired: 0,
    actor_changed: 0,
    rejected: 0,
    exhausted: 0,
    unavailable: 0,
  };
  const drop = (reason: DropReason, count: number, reportCount = count): void => {
    counts = { ...counts, [reason]: Math.min(Number.MAX_SAFE_INTEGER, counts[reason] + count) };
    if (reason !== 'actor_changed' && owner !== null && reportCount > 0)
      qualityCounts = {
        ...qualityCounts,
        [reason]: Math.min(Number.MAX_SAFE_INTEGER, qualityCounts[reason] + reportCount),
      };
  };
  const discard = (reason: DropReason, events: readonly Queued[]): void => {
    drop(
      reason,
      events.length,
      events.filter((item) => item.event.kind !== 'quality.observed').length,
    );
  };
  const clearTimer = (): void => {
    cancelTimer?.();
    cancelTimer = null;
  };
  const stop = (): void => {
    controller?.abort();
    controller = null;
    cancelDeadline?.();
    cancelDeadline = null;
    clearTimer();
  };
  const synchronize = (): void => {
    if (disposed) return;
    let candidate: string | null = null;
    try {
      candidate = options.actor();
    } catch {
      drop('unavailable', 1);
    }
    const actor = uuid(candidate) ? candidate : null;
    if (actor === owner) return;
    generation += 1;
    stop();
    drop(
      'actor_changed',
      queue.length + (pending?.events.length ?? 0) + (qualitySlot === null ? 0 : 1),
      0,
    );
    queue = [];
    pending = null;
    qualitySlot = null;
    qualityCounts = emptyQuality();
    owner = actor;
    startedAt = options.clock.monotonic();
    nextNewBatch = 0;
    suspended = false;
  };
  const epoch = (): Epoch | null => {
    synchronize();
    return disposed || owner === null ? null : { id: generation, startedAt };
  };
  const expire = (): void => {
    const now = options.clock.monotonic();
    const retained = queue.filter(
      (item) => now - item.admitted < maximumAge && now >= item.admitted,
    );
    discard(
      'expired',
      queue.filter((item) => !retained.includes(item)),
    );
    if (
      qualitySlot !== null &&
      (now - qualitySlot.admitted >= maximumAge || now < qualitySlot.admitted)
    ) {
      discard('expired', [qualitySlot]);
      qualitySlot = null;
    }
    queue = retained;
    if (
      pending?.events.some((item) => now - item.admitted >= maximumAge || now < item.admitted) ===
      true
    ) {
      discard('expired', pending.events);
      stop();
      pending = null;
    }
  };
  const schedule = (delay: number): void => {
    if (disposed || owner === null || cancelTimer !== null) return;
    cancelTimer = options.clock.schedule(() => {
      cancelTimer = null;
      flush();
    }, delay);
  };
  const envelope = (events: readonly Queued[], actor: string): Batch => ({
    schema_version: 1,
    expected_actor_id: actor,
    release_id: validatedRelease(options.release())?.releaseId ?? null,
    events: events.map((item) => item.event),
  });
  const assemble = (actor: string): Pending | null => {
    if (qualitySlot === null) {
      const reason = qualityReasons.find((value) => qualityCounts[value] > 0);
      if (reason !== undefined) {
        const id = options.uuid();
        const wall = options.clock.wall();
        const candidateScreen = options.screen();
        if (uuid(id) && Number.isFinite(wall)) {
          const count = Math.min(65535, qualityCounts[reason]);
          const event: Observation = {
            kind: 'quality.observed',
            reason,
            count,
            event_id: id,
            observed_at: new Date(wall).toISOString(),
            screen: screens.some((value) => value === candidateScreen)
              ? candidateScreen
              : 'unknown',
          };
          qualitySlot = {
            event,
            admitted: options.clock.monotonic(),
            bytes: encoder.encode(JSON.stringify(event)).byteLength,
          };
          qualityCounts = { ...qualityCounts, [reason]: qualityCounts[reason] - count };
        }
      }
    }
    let selected: readonly Queued[] = [];
    const candidates = qualitySlot === null ? queue : [qualitySlot, ...queue];
    for (const item of candidates.slice(0, 20)) {
      const candidate = [...selected, item];
      if (encoder.encode(JSON.stringify(envelope(candidate, actor))).byteLength > maximumBatchBytes)
        break;
      selected = candidate;
    }
    if (selected.length === 0) {
      discard('invalid', queue);
      if (qualitySlot !== null) {
        discard('invalid', [qualitySlot]);
        qualitySlot = null;
      }
      queue = [];
      return null;
    }
    const reserved = qualitySlot !== null && selected[0] === qualitySlot;
    queue = queue.slice(selected.length - (reserved ? 1 : 0));
    if (reserved) qualitySlot = null;
    const body = envelope(selected, actor);
    const key = options.uuid();
    if (!uuid(key)) {
      discard('invalid', selected);
      return null;
    }
    return {
      key,
      body,
      json: JSON.stringify(body),
      events: selected,
      epoch: generation,
      attempts: 0,
    };
  };
  const flush = (): void => {
    try {
      drain();
    } catch {
      discard('unavailable', [...queue, ...(pending?.events ?? [])]);
      stop();
      queue = [];
      pending = null;
    }
  };
  const drain = (): void => {
    synchronize();
    expire();
    if (disposed || suspended || owner === null || controller !== null) return;
    if (pending === null) {
      if (
        queue.length === 0 &&
        qualitySlot === null &&
        !qualityReasons.some((reason) => qualityCounts[reason] > 0)
      )
        return;
      const wait = nextNewBatch - options.clock.monotonic();
      if (wait > 0) {
        schedule(wait);
        return;
      }
      pending = assemble(owner);
      if (pending === null) return;
      nextNewBatch = options.clock.monotonic() + batchSpacing;
    }
    clearTimer();
    const batch = { ...pending, attempts: pending.attempts + 1 };
    pending = batch;
    const active = new AbortController();
    controller = active;
    const current = (): boolean =>
      !disposed &&
      !active.signal.aborted &&
      generation === batch.epoch &&
      pending === batch &&
      controller === active;
    cancelDeadline = options.clock.schedule(() => {
      if (!current()) return;
      active.abort();
      controller = null;
      cancelDeadline = null;
      retry(batch, undefined);
    }, 5000);
    // All telemetry errors settle here, never through ErrorHandler/UI promises.
    void Promise.resolve()
      .then(() => {
        synchronize();
        if (!current()) return null;
        return options.delivery.send({
          key: batch.key,
          body: batch.body,
          json: batch.json,
          signal: active.signal,
        });
      })
      .then((result) => {
        synchronize();
        if (!current()) return;
        cancelDeadline?.();
        cancelDeadline = null;
        controller = null;
        if (result?.kind === 'received' && receipt(result.receipt, batch.events)) {
          pending = null;
          schedule(Math.max(0, nextNewBatch - options.clock.monotonic()));
          return;
        }
        if (
          result?.kind === 'failed' &&
          result.status >= 400 &&
          result.status < 500 &&
          result.status !== 429
        ) {
          discard('rejected', batch.events);
          pending = null;
          schedule(Math.max(0, nextNewBatch - options.clock.monotonic()));
          return;
        }
        retry(batch, result?.kind === 'failed' ? result.retryAfterMs : undefined);
      })
      .catch(() => {
        synchronize();
        if (!current()) return;
        cancelDeadline?.();
        cancelDeadline = null;
        controller = null;
        retry(batch, undefined);
      });
  };
  const retry = (batch: Pending, retryAfter: number | undefined): void => {
    if (batch.attempts >= 3) {
      discard('exhausted', batch.events);
      pending = null;
      schedule(Math.max(0, nextNewBatch - options.clock.monotonic()));
      return;
    }
    const requested = retryAfter ?? 0;
    if (!Number.isFinite(requested) || requested < 0 || requested > 60000) {
      discard('unavailable', batch.events);
      pending = null;
      suspended = true;
      return;
    }
    nextNewBatch = Math.max(nextNewBatch, options.clock.monotonic() + requested);
    schedule(Math.max(1000 * 2 ** (batch.attempts - 1), requested));
  };
  const observe = (input: ObservationInput): boolean => {
    try {
      synchronize();
      expire();
      if (disposed || owner === null) return false;
      if (suspended) {
        drop('unavailable', 1, 0);
        return false;
      }
      const clean = sanitizeObservation(input, validatedRelease(options.release()));
      const id = options.uuid();
      const wall = options.clock.wall();
      if (
        clean === null ||
        !uuid(id) ||
        !Number.isFinite(wall) ||
        queue.some((item) => item.event.event_id === id) ||
        pending?.events.some((item) => item.event.event_id === id) === true ||
        qualitySlot?.event.event_id === id
      ) {
        drop('invalid', 1, input.kind === 'quality.observed' ? 0 : 1);
        return false;
      }
      const candidateScreen = options.screen();
      const screen = screens.some((item) => item === candidateScreen) ? candidateScreen : 'unknown';
      const event: Observation = {
        ...clean,
        event_id: id,
        observed_at: new Date(wall).toISOString(),
        screen,
      };
      const bytes = encoder.encode(JSON.stringify(event)).byteLength;
      if (bytes > maximumBatchBytes - 512) {
        drop('invalid', 1, input.kind === 'quality.observed' ? 0 : 1);
        return false;
      }
      const size =
        queue.reduce((total, item) => total + item.bytes, 0) +
        (pending?.events.reduce((total, item) => total + item.bytes, 0) ?? 0);
      if (
        queue.length +
          (pending?.events.filter((item) => item.event.kind !== 'quality.observed').length ?? 0) >=
          maximumEvents - 1 ||
        size + bytes > maximumQueueBytes - 1024
      ) {
        drop('overflow', 1, clean.kind === 'quality.observed' ? 0 : 1);
        return false;
      }
      queue = [...queue, { event, admitted: options.clock.monotonic(), bytes }];
      schedule(250);
      return true;
    } catch {
      drop('invalid', 1, 0);
      return false;
    }
  };
  return {
    observe,
    synchronize,
    flush,
    epoch,
    drops: () => ({ ...counts }),
    beginAction: (action: Action): ActionHandle | null => {
      if (epoch() === null) return null;
      const actionId = options.uuid();
      const trace = options.traceId();
      if (!uuid(actionId) || !traceId(trace)) return null;
      return observe({ kind: 'action.observed', action, outcome: 'invoked', action_id: actionId })
        ? { action, actionId, traceId: trace }
        : null;
    },
    dispose: () => {
      if (disposed) return;
      disposed = true;
      generation += 1;
      stop();
      queue = [];
      pending = null;
      owner = null;
      qualitySlot = null;
      qualityCounts = emptyQuality();
    },
  };
}
