import { describe, expect, it } from 'vitest';
import {
  discoveryMode,
  discoveryView,
  isContext,
  isDiscoveryPage,
  isPass,
  relevanceText,
} from './discovery-contract';
import { card, deck, pass } from './discovery.fixtures';

describe('Discovery actual readonly boundary', () => {
  it('accepts only URL modes and views supported by the API', () => {
    for (const mode of ['find_help', 'offer_help', 'study_together'])
      expect(discoveryMode(mode)).toBe(mode);
    for (const value of [null, '', 'teacher']) expect(discoveryMode(value)).toBeNull();
    expect(discoveryView('candidates')).toBe('candidates');
    expect(discoveryView('passed')).toBe('passed');
    for (const value of [null, '', 'all']) expect(discoveryView(value)).toBeNull();
  });
  it('validates exact tagged context prerequisites without creating defaults', () => {
    expect(isContext(deck.context)).toBe(true);
    expect(isContext({ ...deck.context, mode: 'study_together' })).toBe(true);
    expect(isContext({ mode: 'offer_help', help_version: 2 })).toBe(true);
    for (const value of [
      null,
      [],
      { mode: 'other' },
      { mode: 'offer_help' },
      { mode: 'offer_help', help_version: -1 },
      { mode: 'offer_help', help_version: 1.5 },
      { mode: 'offer_help', help_version: Infinity },
      { ...deck.context, goal_id: null },
      { ...deck.context, goal_version: '1' },
    ])
      expect(isContext(value)).toBe(false);
  });
  it('validates absent and retained own-pass revisions', () => {
    expect(isPass(pass)).toBe(true);
    expect(isPass(card.own_pass)).toBe(true);
    for (const value of [
      null,
      {},
      { ...pass, person_id: 1 },
      { ...pass, passed: 1 },
      { ...pass, version: -1 },
      { ...pass, changed_at: 42 },
    ])
      expect(isPass(value)).toBe(false);
  });
  it('validates every nested card field and opaque paging boundaries', () => {
    expect(isDiscoveryPage(deck)).toBe(true);
    expect(
      isDiscoveryPage({
        ...deck,
        context: null,
        people: [],
        empty_reason: 'context_required',
        undo_pass: pass,
        next_cursor: 'opaque+/=',
      }),
    ).toBe(true);
    for (const empty_reason of ['no_relevant_people', 'exhausted', 'no_available_passed_people'])
      expect(isDiscoveryPage({ ...deck, people: [], empty_reason })).toBe(true);
    for (const value of [
      null,
      {},
      { ...deck, context: {} },
      { ...deck, people: {} },
      { ...deck, people: Array.from({ length: 21 }, () => card) },
      { ...deck, people: [card, card] },
      { ...deck, next_cursor: 1 },
      { ...deck, empty_reason: 'none' },
      { ...deck, undo_pass: {} },
    ])
      expect(isDiscoveryPage(value)).toBe(false);
    for (const broken of [
      { ...card, id: null },
      { ...card, display_name: 4 },
      { ...card, about: {} },
      { ...card, version: -1 },
      { ...card, own_pass: {} },
      { ...card, own_pass: { ...pass, person_id: 'foreign' } },
      { ...card, photo: null },
      { ...card, photo: { ...card.photo, display_url: null } },
      { ...card, photo: { ...card.photo, version: '1' } },
      { ...card, relevance: null },
    ])
      expect(isDiscoveryPage({ ...deck, people: [broken] })).toBe(false);
    for (const [key, value] of [
      ['reason', 'fake_score'],
      ['same_topic', null],
      ['subject_id', null],
      ['subject_label', null],
      ['topic', 1],
      ['reciprocal_subject_id', {}],
      ['reciprocal_subject_label', 0],
    ] as const)
      expect(
        isDiscoveryPage({
          ...deck,
          people: [{ ...card, relevance: { ...card.relevance, [key]: value } }],
        }),
      ).toBe(false);
  });
  it('renders only grounded reasons and literal topic equality', () => {
    expect(relevanceText(card.relevance)).toBe('Can help with SQL · JOINs');
    expect(relevanceText({ ...card.relevance, same_topic: false })).toBe('Can help with SQL');
    expect(relevanceText({ ...card.relevance, topic: null })).toBe('Can help with SQL');
    expect(relevanceText({ ...card.relevance, reason: 'you_can_help' })).toBe(
      'You can help with their SQL · JOINs goal',
    );
    expect(relevanceText({ ...card.relevance, reason: 'shared_goal' })).toBe(
      'Open to studying SQL · JOINs together',
    );
  });
});
