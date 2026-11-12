import { describe, it, expect } from 'vitest';
import { sanitizeObservation, validatedRelease, publicFrames } from './observation-privacy';
import type { ReleaseAssets } from './observation-privacy';
const release: ReleaseAssets = {
  releaseId: 'a'.repeat(40),
  origin: 'https://peerly.example.test',
  assets: [
    { basename: 'chunk-ABCDEFGH.js', assetId: 0 },
    { basename: 'main-12345678.js', assetId: 1 },
  ],
};
const id = '00000000-0000-4000-8000-000000000001';
describe('client observation closed privacy boundary', () => {
  it('reconstructs each allowed union and never serializes attached private properties', () => {
    const privateFields = {
      email: 'secret@mail.apu.edu.my',
      message: 'chat draft',
      otp: '123456',
      url: 'https://objects.test/private?signature=secret',
      stack: 'private stack',
      body: { prompt: 'private AI' },
    };
    expect(sanitizeObservation({ kind: 'screen.viewed', ...privateFields }, null)).toEqual({
      kind: 'screen.viewed',
    });
    expect(
      sanitizeObservation(
        {
          kind: 'action.observed',
          action: 'submit',
          outcome: 'invoked',
          action_id: id,
          ...privateFields,
        },
        null,
      ),
    ).toEqual({ kind: 'action.observed', action: 'submit', outcome: 'invoked', action_id: id });
    expect(
      sanitizeObservation(
        { kind: 'performance.observed', metric: 'cls', value: 0.25, ...privateFields },
        null,
      ),
    ).toEqual({ kind: 'performance.observed', metric: 'cls', value: 0.25 });
    expect(
      sanitizeObservation(
        {
          kind: 'error.observed',
          category: 'javascript',
          frames: [{ asset_id: 0, line: 3, column: 0, ...privateFields }],
          ...privateFields,
        },
        release,
      ),
    ).toEqual({
      kind: 'error.observed',
      category: 'javascript',
      frames: [{ asset_id: 0, line: 3, column: 0 }],
    });
    expect(
      sanitizeObservation(
        {
          kind: 'http.observed',
          method: 'POST',
          route: 'conversations',
          status_class: '5xx',
          duration_ms: 123,
          request_id: id,
          action_id: id,
          trace_id: 'a'.repeat(32),
          ...privateFields,
        },
        null,
      ),
    ).toEqual({
      kind: 'http.observed',
      method: 'POST',
      route: 'conversations',
      status_class: '5xx',
      duration_ms: 123,
      request_id: id,
      action_id: id,
      trace_id: 'a'.repeat(32),
    });
  });
  it('rejects nonfinite, out-of-bound and invented semantic fields without freeform fallbacks', () => {
    expect(
      sanitizeObservation({ kind: 'performance.observed', metric: 'cls', value: 101 }, null),
    ).toBeNull();
    expect(
      sanitizeObservation({ kind: 'performance.observed', metric: 'lcp', value: Infinity }, null),
    ).toBeNull();
    expect(
      sanitizeObservation({ kind: 'performance.observed', metric: 'lcp', value: -1 }, null),
    ).toBeNull();
    expect(
      sanitizeObservation(
        { kind: 'action.observed', action: 'email secret', outcome: 'success' },
        null,
      ),
    ).toBeNull();
    expect(
      sanitizeObservation(
        {
          kind: 'http.observed',
          method: 'POST',
          route: '/private/path',
          status_class: '2xx',
          duration_ms: 10,
        },
        null,
      ),
    ).toBeNull();
    expect(
      sanitizeObservation(
        {
          kind: 'http.observed',
          method: 'GET',
          route: 'profile',
          status_class: '2xx',
          duration_ms: 1.1,
        },
        null,
      ),
    ).toBeNull();
    expect(
      sanitizeObservation({ kind: 'error.observed', category: 'private exception text' }, null),
    ).toBeNull();
    expect(sanitizeObservation({ kind: 'unknown' }, null)).toBeNull();
    expect(sanitizeObservation(null, null)).toBeNull();
    expect(
      sanitizeObservation(
        {
          get kind() {
            throw new Error('private getter');
          },
        },
        null,
      ),
    ).toBeNull();
  });
  it('omits invalid correlations and frames when release is absent or assets are unknown', () => {
    expect(
      sanitizeObservation(
        { kind: 'action.observed', action: 'retry', outcome: 'invoked', action_id: 'email' },
        null,
      ),
    ).toEqual({ kind: 'action.observed', action: 'retry', outcome: 'invoked' });
    expect(
      sanitizeObservation(
        {
          kind: 'http.observed',
          method: 'GET',
          route: 'other',
          status_class: 'network',
          duration_ms: 0,
          request_id: 'private',
          trace_id: '0'.repeat(32),
        },
        null,
      ),
    ).toEqual({
      kind: 'http.observed',
      method: 'GET',
      route: 'other',
      status_class: 'network',
      duration_ms: 0,
    });
    expect(
      sanitizeObservation(
        {
          kind: 'error.observed',
          category: 'unknown',
          frames: [{ asset_id: 0, line: 1, column: 1 }],
        },
        null,
      ),
    ).toEqual({ kind: 'error.observed', category: 'unknown' });
    expect(
      sanitizeObservation(
        {
          kind: 'error.observed',
          category: 'unknown',
          frames: [{ asset_id: 9, line: 1, column: 1 }],
        },
        release,
      ),
    ).toEqual({ kind: 'error.observed', category: 'unknown' });
  });
  it('validates actual release map and permits only numeric coordinates of exact public same-origin assets', () => {
    expect(validatedRelease(release)).toEqual(release);
    expect(validatedRelease({ ...release, releaseId: 'unknown' })).toBeNull();
    expect(
      validatedRelease({ ...release, assets: [{ basename: 'private/report.js', assetId: 0 }] }),
    ).toBeNull();
    expect(
      validatedRelease({
        ...release,
        assets: [
          { basename: 'main-12345678.js', assetId: 1 },
          { basename: 'chunk-ABCDEFGH.js', assetId: 0 },
        ],
      }),
    ).toBeNull();
    expect(
      validatedRelease({ ...release, origin: 'https://peerly.example.test/private' }),
    ).toBeNull();
    const stack =
      'Error: private message\n at secretFunction (https://peerly.example.test/chunk-ABCDEFGH.js:12:0)\n at https://peerly.example.test/main-12345678.js:24:7\n at https://external.test/main-12345678.js:1:1\n at https://peerly.example.test/main-12345678.js?email=secret:1:1\n at https://peerly.example.test/private/main-12345678.js:1:1\n at https://peerly.example.test/main-12345678.js:0:1';
    expect(publicFrames(stack, release)).toEqual([
      { asset_id: 0, line: 12, column: 0 },
      { asset_id: 1, line: 24, column: 7 },
    ]);
    expect(publicFrames(stack, null)).toEqual([]);
    expect(publicFrames({ stack }, release)).toEqual([]);
    expect(
      publicFrames(
        Array.from({ length: 5 }, () => 'at https://peerly.example.test/main-12345678.js:1:1').join(
          '\n',
        ),
        release,
      ),
    ).toHaveLength(3);
  });
  it('accepts only the actual sixth closed quality union and never actor_changed or private extras', () => {
    expect(
      sanitizeObservation(
        { kind: 'quality.observed', reason: 'overflow', count: 65535, message: 'PRIVATE' },
        null,
      ),
    ).toEqual({ kind: 'quality.observed', reason: 'overflow', count: 65535 });
    expect(
      sanitizeObservation({ kind: 'quality.observed', reason: 'actor_changed', count: 1 }, null),
    ).toBeNull();
    expect(
      sanitizeObservation({ kind: 'quality.observed', reason: 'invalid', count: 0 }, null),
    ).toBeNull();
    expect(
      sanitizeObservation({ kind: 'quality.observed', reason: 'invalid', count: 1.5 }, null),
    ).toBeNull();
    expect(
      sanitizeObservation({ kind: 'quality.observed', reason: 'invalid', count: 65536 }, null),
    ).toBeNull();
  });
});
