import { describe, expect, it } from 'vitest';
import {
  acceptsPhotoJob,
  isPhotoAdvice,
  photoAdvice,
  samePhotoSource,
  validPhotoSource,
} from './photo-assistance-contract';
import { photoJob, photoSource } from './assistance-test-data';

describe('O02 actual resource and observation contract', () => {
  it('binds tips to the actual current photo UUID and current photo version', () => {
    expect(validPhotoSource(photoSource)).toBe(true);
    expect(validPhotoSource({ ...photoSource, id: 'not-an-upload-id' })).toBe(false);
    for (const version of [0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1])
      expect(validPhotoSource({ ...photoSource, version })).toBe(false);
    expect(samePhotoSource(photoSource, { ...photoSource })).toBe(true);
    expect(samePhotoSource(photoSource, { ...photoSource, version: 8 })).toBe(false);
    expect(samePhotoSource(photoSource, { ...photoSource, id: 'another-resource' })).toBe(false);
  });
  it('accepts only the three actual observation enums without inferred scores or provider text', () => {
    for (const observation of ['yes', 'no', 'uncertain'] as const) {
      expect(
        isPhotoAdvice({
          blurred: observation,
          face_visible: observation,
          multiple_people: observation,
        }),
      ).toBe(true);
      expect(photoAdvice.blurred[observation].length).toBeGreaterThan(0);
      expect(photoAdvice.face_visible[observation].length).toBeGreaterThan(0);
      expect(photoAdvice.multiple_people[observation].length).toBeGreaterThan(0);
    }
    for (const value of [
      null,
      {},
      { blurred: 'yes', face_visible: 'yes' },
      { blurred: 'unknown', face_visible: 'yes', multiple_people: 'no' },
      { blurred: true, face_visible: 'yes', multiple_people: 'no' },
      { blurred: 'yes', face_visible: 'yes', multiple_people: 'no', approved: true },
    ])
      expect(isPhotoAdvice(value)).toBe(false);
  });
  it('accepts actual pending and terminal states, with no fabricated photo verdict', () => {
    expect(acceptsPhotoJob(photoJob(), photoSource)).toBe(true);
    expect(acceptsPhotoJob(photoJob({ state: 'running' }), photoSource)).toBe(true);
    for (const state of ['failed', 'expired', 'cancelled'] as const)
      expect(acceptsPhotoJob(photoJob({ state, poll_after_ms: null }), photoSource)).toBe(true);
    expect(
      acceptsPhotoJob(
        photoJob({ state: 'failed', failure: 'invalid_output', poll_after_ms: null }),
        photoSource,
      ),
    ).toBe(true);
    expect(
      acceptsPhotoJob(
        photoJob({
          state: 'succeeded',
          result: { blurred: 'yes', face_visible: 'no', multiple_people: 'uncertain' },
          poll_after_ms: null,
        }),
        photoSource,
      ),
    ).toBe(true);
  });
  it('rejects different jobs, resources, versions, task kinds and malformed lifecycle fields', () => {
    const initial = photoJob();
    const invalid: readonly unknown[] = [
      null,
      1,
      [],
      {},
      { ...initial, id: 'wrong' },
      { ...initial, kind: 'clarify_goal' },
      { ...initial, target: 'context' },
      { ...initial, source: null },
      { ...initial, source: { ...photoSource, kind: 'draft' } },
      { ...initial, source: { ...photoSource, id: initial.id } },
      { ...initial, source: { ...photoSource, version: 2 } },
      { ...initial, created_at: 'wrong' },
      { ...initial, deadline: 'wrong' },
      { ...initial, deadline: initial.created_at },
      { ...initial, poll_after_ms: null },
      { ...initial, poll_after_ms: 0 },
      { ...initial, poll_after_ms: 1.5 },
      { ...initial, result: { blurred: 'yes', face_visible: 'yes', multiple_people: 'no' } },
      { ...initial, failure: 'timeout' },
      {
        ...initial,
        state: 'succeeded',
        poll_after_ms: null,
        result: { suggestion: 'Wrong goal result' },
      },
      { ...initial, state: 'failed', poll_after_ms: null, failure: 'vendor_details' },
      { ...initial, state: 'cancelled', poll_after_ms: null, failure: 'transient' },
      { ...initial, state: 'unknown', poll_after_ms: null },
      {
        ...initial,
        state: 'succeeded',
        poll_after_ms: 10,
        result: { blurred: 'yes', face_visible: 'yes', multiple_people: 'no' },
      },
    ];
    for (const value of invalid) expect(acceptsPhotoJob(value, photoSource)).toBe(false);
    expect(acceptsPhotoJob(initial, photoSource, initial.id)).toBe(true);
    expect(acceptsPhotoJob(initial, photoSource, photoSource.id)).toBe(false);
  });
});
