import { describe, expect, it } from 'vitest';
import {
  cursorProblem,
  isReview,
  isReviewAction,
  isReviewHistory,
  reasonProblem,
} from './review-contract';
import { anchoredHistory, earlierHistory, emptyHistory, revision } from './review.fixtures';

describe('actual59 human review protocol validation', () => {
  it('accepts empty history and an independently newer current head on both anchored pages', () => {
    expect(isReviewHistory(emptyHistory)).toBe(true);
    expect(isReviewHistory(anchoredHistory)).toBe(true);
    expect(isReviewHistory(earlierHistory)).toBe(true);
  });
  it('allows only the two genuine actions and preserves original multiline Unicode reason', () => {
    expect(isReviewAction('dismiss')).toBe(true);
    expect(isReviewAction('escalate')).toBe(true);
    for (const action of ['ban', 'resolve', '', null]) expect(isReviewAction(action)).toBe(false);
    expect(reasonProblem('  Reason 🦉\n\tsecond line  ')).toBeNull();
    expect(reasonProblem('🦉'.repeat(1000))).toBeNull();
    for (const reason of ['', ' \n\t', '🦉'.repeat(1001), 'bad\u0000text', '\ud800'])
      expect(reasonProblem(reason)).not.toBeNull();
  });
  it('rejects malformed lineage, private-origin formats and unsupported stored actions', () => {
    expect(isReview(revision(1))).toBe(true);
    expect(isReview(revision(2147483647))).toBe(true);
    for (const delta of [
      { previous_version: 0 },
      { version: 0 },
      { version: 1.5 },
      { version: 2147483648 },
      { operator_access_version: 0 },
      { report_id: 'bad' },
      { trace_id: 'private text' },
      { span_id: '' },
      { http_request_id: 'bad' },
      { action_id: 'bad' },
      { actor_session_id: null },
      { reviewed_at: 'yesterday' },
      { reason: ' ' },
      { action: 'ban' },
    ])
      expect(isReview({ ...revision(1), ...delta })).toBe(false);
  });
  it('rejects mixed reports, unsorted/duplicate/oversize rows and inconsistent anchors', () => {
    for (const delta of [
      { current: null },
      { anchor_version: 53 },
      { anchor_version: -1 },
      { kind: 'invented' },
      { context_id: null },
      { revisions: [revision(1), revision(2)] },
      { revisions: [revision(2), revision(2)] },
      { revisions: Array.from({ length: 51 }, (_, index) => revision(51 - index)) },
      { revisions: [{ ...revision(1), report_id: 'c1111111-1111-4111-8111-111111111111' }] },
      { revisions: [revision(52)] },
      { next_cursor: '' },
      { revisions: [], next_cursor: 'bad-empty-page' },
    ])
      expect(isReviewHistory({ ...anchoredHistory, ...delta })).toBe(false);
    expect(
      isReviewHistory({
        ...emptyHistory,
        current: revision(1),
        anchor_version: 1,
        revisions: [{ ...revision(1), id: revision(2).id }],
      }),
    ).toBe(false);
    expect(isReviewHistory(null)).toBe(false);
  });
  it('bounds opaque cursors without interpreting or manufacturing them', () => {
    expect(cursorProblem(null)).toBeNull();
    expect(cursorProblem('a'.repeat(1024))).toBeNull();
    expect(cursorProblem('')).not.toBeNull();
    expect(cursorProblem('a'.repeat(1025))).not.toBeNull();
  });
});
