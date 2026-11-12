import { describe, expect, it } from 'vitest';
import {
  isDescriptor,
  isOutcome,
  isOwnFeedback,
  isOwnOutcome,
  isPrompt,
  isReceipt,
  studyKey,
} from './study-contract';
import { offered, outcome, ownFeedback, receipt } from './study.fixtures';

describe('F01/F02 actual response boundaries', () => {
  it('accepts actual independent versions and all documented answers/publication states', () => {
    expect(isOwnFeedback(ownFeedback, outcome.conversation_id)).toBe(true);
    expect(isOwnOutcome({ outcome: null }, outcome.conversation_id)).toBe(true);
    for (const answer of ['yes', 'not_yet', 'did_not_work_out'])
      expect(isOutcome({ ...outcome, answer })).toBe(true);
    for (const again of ['yes', 'maybe', 'no']) expect(isReceipt({ ...receipt, again })).toBe(true);
    for (const publication of ['eligible', 'private_only', 'removed', null])
      expect(
        isOwnFeedback(
          { ...ownFeedback, current_publication: publication, submission_publication: publication },
          outcome.conversation_id,
        ),
      ).toBe(true);
    expect(
      isOwnFeedback({ ...ownFeedback, current: null, outcome: null }, outcome.conversation_id),
    ).toBe(true);
    expect(isReceipt({ ...receipt, team_note: null, descriptors: [] })).toBe(true);
    for (const descriptor of ['easy_to_communicate', 'prepared', 'supportive'])
      expect(isDescriptor(descriptor)).toBe(true);
  });
  it('rejects malformed records, peer conversation records and unknown enum values', () => {
    for (const value of [
      null,
      [],
      1,
      {},
      { ...outcome, version: 0 },
      { ...outcome, version: 1.5 },
      { ...outcome, changed_at: 'bad' },
      { ...outcome, answer: 'unknown' },
      { ...outcome, id: null },
      { ...outcome, conversation_id: null },
    ])
      expect(isOutcome(value)).toBe(false);
    expect(isOwnOutcome({ outcome }, 'another-conversation')).toBe(false);
    expect(isOwnOutcome(null, outcome.conversation_id)).toBe(false);
    expect(isOwnFeedback(ownFeedback, 'another-conversation')).toBe(false);
    for (const value of [
      null,
      { ...receipt, version: -1 },
      { ...receipt, id: null },
      { ...receipt, conversation_id: 1 },
      { ...receipt, changed_at: false },
      { ...receipt, again: 'later' },
      { ...receipt, descriptors: null },
      { ...receipt, descriptors: ['supportive', 'supportive'] },
      { ...receipt, descriptors: ['unlisted'] },
      { ...receipt, descriptors: ['prepared', 'supportive', 'easy_to_communicate', 'prepared'] },
      { ...receipt, team_note: 1 },
      { ...receipt, team_note: 'x'.repeat(1001) },
      { ...receipt, worked_outcome_id: null },
      { ...receipt, worked_outcome_version: 0 },
      { ...receipt, captured_public_eligibility: null },
    ])
      expect(isReceipt(value)).toBe(false);
    for (const value of [
      null,
      {},
      { ...ownFeedback, current: {} },
      { ...ownFeedback, current: { ...receipt, conversation_id: 'other' } },
      { ...ownFeedback, can_submit: 'yes' },
      { ...ownFeedback, current_publication: 'public' },
      { ...ownFeedback, submission_publication: 'public' },
    ])
      expect(isOwnFeedback(value, outcome.conversation_id)).toBe(false);
  });
  it('requires the actual prompt discriminator/owner and separates actor/conversation keys', () => {
    expect(isPrompt(offered, outcome.conversation_id)).toBe(true);
    expect(isPrompt({ outcome: 'no_offer' }, outcome.conversation_id)).toBe(true);
    for (const value of [
      null,
      {},
      { ...offered, outcome: 'yes' },
      { ...offered, conversation_id: 'other' },
      { ...offered, receipt_id: null },
      { ...offered, offered_at: 'bad' },
    ])
      expect(isPrompt(value, outcome.conversation_id)).toBe(false);
    expect(studyKey('actor-a', outcome.conversation_id)).not.toEqual(
      studyKey('actor-b', outcome.conversation_id),
    );
    expect(studyKey('actor-a', outcome.conversation_id)).not.toEqual(
      studyKey('actor-a', 'another'),
    );
  });
});
