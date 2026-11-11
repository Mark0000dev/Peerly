import { describe, expect, it } from 'vitest';
import {
  acceptsJob,
  boundedText,
  canClarify,
  canSuggest,
  isUuid,
  sameDraft,
  validDraft,
} from './goal-assistance-contract';
import type { GoalAssistanceDraft } from './goal-assistance-contract';
import { clarify, draft, job, suggest } from './assistance-test-data';

describe('G01 actual draft and job boundary', () => {
  it('validates the actual draft identity, source revision and codepoint input bounds', () => {
    expect(validDraft(draft)).toBe(true);
    expect(validDraft({ ...draft, source: { ...draft.source, id: 'wrong' } })).toBe(false);
    for (const version of [0, -1, 1.2, Number.MAX_SAFE_INTEGER + 1])
      expect(validDraft({ ...draft, source: { ...draft.source, version } })).toBe(false);
    expect(canClarify(draft)).toBe(true);
    expect(canClarify({ ...draft, context: '🙂'.repeat(240) })).toBe(true);
    expect(canClarify({ ...draft, context: '🙂'.repeat(241) })).toBe(false);
    expect(canClarify({ ...draft, context: ' \t\n ' })).toBe(false);
    expect(boundedText('a\nb\tc', 10, true)).toBe(true);
    for (const value of ['a\nb', 'a\tb', 'a\u0000b', 'a\u007fb', 'a\u0080b', 'a\ud800b'])
      expect(boundedText(value, 20)).toBe(false);
    expect(isUuid(null)).toBe(false);
  });
  it('captures only distinct actual catalogue IDs and bounded typed labels', () => {
    expect(canSuggest(draft)).toBe(true);
    expect(canSuggest({ ...draft, candidates: [] })).toBe(false);
    expect(canSuggest({ ...draft, candidates: [...draft.candidates, ...draft.candidates] })).toBe(
      false,
    );
    expect(canSuggest({ ...draft, areaLabel: 'x'.repeat(81) })).toBe(false);
    expect(canSuggest({ ...draft, areaLabel: ' ' })).toBe(false);
    expect(canSuggest({ ...draft, candidates: [{ id: 'bad', name: 'Computing' }] })).toBe(false);
    expect(canSuggest({ ...draft, candidates: [{ id: draft.source.id, name: ' ' }] })).toBe(false);
    const candidates = Array.from({ length: 20 }, (_: unknown, index: number) => ({
      id: `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`,
      name: 'Area',
    }));
    expect(canSuggest({ ...draft, candidates })).toBe(true);
    expect(
      canSuggest({
        ...draft,
        candidates: [...candidates, { id: '00000000-0000-4000-8000-000000000099', name: 'Other' }],
      }),
    ).toBe(false);
  });
  it('invalidates advice on every relevant parent edit, candidate or source revision', () => {
    expect(sameDraft(draft, { ...draft })).toBe(true);
    const edits: readonly GoalAssistanceDraft[] = [
      { ...draft, context: 'New words' },
      { ...draft, topic: 'New topic' },
      { ...draft, areaLabel: 'New area' },
      { ...draft, source: { ...draft.source, version: 4 } },
      { ...draft, source: { ...draft.source, id: draft.candidates[0]?.id ?? '' } },
      { ...draft, candidates: [] },
      {
        ...draft,
        candidates: draft.candidates.map(
          (
            candidate: Readonly<Pick<GoalAssistanceDraft['candidates'][number], 'id' | 'name'>>,
          ) => ({ ...candidate, name: 'Renamed' }),
        ),
      },
      { ...draft, candidates: [...draft.candidates].reverse() },
    ];
    for (const edit of edits) expect(sameDraft(draft, edit)).toBe(false);
  });
  it('accepts all actual states without inventing successful result or terminal failure', () => {
    expect(acceptsJob(job(), clarify)).toBe(true);
    expect(acceptsJob(job({ state: 'running' }), clarify)).toBe(true);
    for (const state of ['cancelled', 'expired', 'failed'] as const)
      expect(acceptsJob(job({ state, poll_after_ms: null }), clarify)).toBe(true);
    expect(
      acceptsJob(job({ state: 'failed', failure: 'invalid_output', poll_after_ms: null }), clarify),
    ).toBe(true);
    expect(
      acceptsJob(job({ state: 'expired', failure: 'timeout', poll_after_ms: null }), clarify),
    ).toBe(true);
    expect(
      acceptsJob(
        job({
          state: 'succeeded',
          result: { suggestion: 'A clearer context.' },
          poll_after_ms: null,
        }),
        clarify,
      ),
    ).toBe(true);
    expect(
      acceptsJob(
        job({
          target: 'topic',
          state: 'succeeded',
          result: { suggestion: 'JOINs' },
          poll_after_ms: null,
        }),
        { ...clarify, target: 'topic' },
      ),
    ).toBe(true);
    expect(
      acceptsJob(job(), { kind: 'clarify_goal', source: draft.source, text: draft.context }),
    ).toBe(true);
  });
  it('rejects malformed, cross-kind, cross-source and cross-hash responses', () => {
    const initial = job();
    const invalid: readonly unknown[] = [
      undefined,
      null,
      [],
      3,
      {},
      { ...initial, id: 'not-uuid' },
      { ...initial, kind: 'assess_photo' },
      { ...initial, source: null },
      { ...initial, source: { ...draft.source, kind: 'resource' } },
      { ...initial, source: { ...draft.source, version: 4, content_hash: '1'.repeat(64) } },
      { ...initial, source: { ...draft.source, id: initial.id, content_hash: '1'.repeat(64) } },
      { ...initial, source: { ...draft.source, content_hash: 'bad' } },
      { ...initial, target: 'topic' },
      { ...initial, created_at: 'wrong' },
      { ...initial, deadline: 'wrong' },
      { ...initial, deadline: initial.created_at },
      { ...initial, poll_after_ms: null },
      { ...initial, poll_after_ms: 0 },
      { ...initial, poll_after_ms: 1.2 },
      { ...initial, result: { suggestion: 'Premature' } },
      { ...initial, failure: 'transient' },
      { ...initial, state: 'unknown', poll_after_ms: null },
      { ...initial, state: 'failed', failure: 'private_provider_error', poll_after_ms: null },
      { ...initial, state: 'cancelled', failure: 'timeout', poll_after_ms: null },
    ];
    for (const value of invalid) expect(acceptsJob(value, clarify)).toBe(false);
    expect(acceptsJob(initial, clarify, { id: initial.id, hash: '1'.repeat(64) })).toBe(true);
    expect(acceptsJob(initial, clarify, { id: draft.source.id, hash: '1'.repeat(64) })).toBe(false);
    expect(acceptsJob(initial, clarify, { id: initial.id, hash: '2'.repeat(64) })).toBe(false);
  });
  it('checks task-specific result bounds and never accepts an uncaptured area', () => {
    const result = job({ state: 'succeeded', poll_after_ms: null });
    for (const suggestion of ['', 'x'.repeat(241), 'a\u0000b'])
      expect(acceptsJob({ ...result, result: { suggestion } }, clarify)).toBe(false);
    for (const value of [null, { ids: [] }, { suggestion: 'Okay', extra: true }])
      expect(acceptsJob({ ...result, result: value }, clarify)).toBe(false);
    expect(
      acceptsJob(
        { ...result, result: { suggestion: 'x'.repeat(81) }, target: 'topic' },
        { ...clarify, target: 'topic' },
      ),
    ).toBe(false);
    const area = { ...result, kind: 'suggest_subject', target: null };
    expect(acceptsJob({ ...area, result: { ids: [] } }, suggest)).toBe(true);
    expect(acceptsJob({ ...area, result: { ids: suggest.candidate_ids } }, suggest)).toBe(true);
    for (const value of [
      { ids: [draft.source.id] },
      { ids: ['bad'] },
      { ids: [null] },
      { ids: [...suggest.candidate_ids, ...suggest.candidate_ids] },
      { ids: [suggest.candidate_ids[0], suggest.candidate_ids[0]] },
      { ids: [], suggestion: 'Not this result kind' },
      { suggestion: 'Wrong result kind' },
    ])
      expect(acceptsJob({ ...area, result: value }, suggest)).toBe(false);
    expect(
      acceptsJob({ ...result, state: 'failed', result: { suggestion: 'Wrong' } }, clarify),
    ).toBe(false);
    expect(
      acceptsJob({ ...result, poll_after_ms: 100, result: { suggestion: 'Wrong' } }, clarify),
    ).toBe(false);
    expect(
      acceptsJob({ ...result, failure: 'timeout', result: { suggestion: 'Wrong' } }, clarify),
    ).toBe(false);
  });
});
