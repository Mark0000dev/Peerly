import { describe, expect, it } from 'vitest';
import { isCatalogue } from './goal-contract';
import { isGoal, isOwnGoal } from '../../study-context-contract';
import { catalogue, goal, ownGoal } from './goal.fixtures';

describe('actual goal and catalogue boundary', () => {
  for (const value of [null, false, 'private', {}, [], { goal: false }])
    it(`rejects malformed own goal ${JSON.stringify(value)}`, () => {
      expect(isOwnGoal(value)).toBe(false);
    });
  it('accepts nullable own goal and schema-optional response tags without injecting defaults', () => {
    expect(isOwnGoal({ goal: null })).toBe(true);
    expect(isOwnGoal(ownGoal)).toBe(true);
    expect(isGoal({ ...goal, subject: { id: goal.subject.id, label: 'Calculus' } })).toBe(true);
    expect(
      isGoal({
        ...goal,
        subject: { kind: 'custom', label: 'Something else' },
        topic: null,
        context: null,
        completed_at: '2026-11-07T12:00:00Z',
      }),
    ).toBe(true);
    expect(isGoal({ ...goal, subject: { label: 'Something else' } })).toBe(true);
  });
  for (const key of Object.keys(goal))
    it(`requires goal field ${key}`, () => {
      expect(
        isGoal(
          Object.fromEntries(
            Object.entries(goal).filter((entry: readonly [string, unknown]) => entry[0] !== key),
          ),
        ),
      ).toBe(false);
      expect(isGoal({ ...goal, [key]: key === 'shared_learning' ? 0 : false })).toBe(false);
    });
  for (const subject of [
    null,
    false,
    {},
    { kind: 'unknown', label: 'Private' },
    { id: 0, label: 'Private' },
    { id: 'id', kind: 'custom', label: 'Private' },
    { kind: 'canonical', label: 'Missing id' },
    { id: 'id', label: 0 },
  ])
    it(`rejects malformed subject ${JSON.stringify(subject)}`, () => {
      expect(isGoal({ ...goal, subject })).toBe(false);
    });
  for (const version of [0, 1.1, -1])
    it(`rejects invalid goal revision ${String(version)}`, () => {
      expect(isGoal({ ...goal, version })).toBe(false);
    });
  for (const value of [
    null,
    false,
    'private',
    {},
    { items: null, next_cursor: null },
    { items: [null], next_cursor: null },
    { items: [{ id: 'id', name: 'Name' }], next_cursor: null },
    { items: [{ id: 0, name: 'Name', aliases: [] }], next_cursor: null },
    { items: [{ id: 'id', name: 0, aliases: [] }], next_cursor: null },
    { items: [{ id: 'id', name: 'Name', aliases: [1] }], next_cursor: null },
    { items: [], next_cursor: 0 },
  ])
    it(`rejects malformed catalogue ${JSON.stringify(value)}`, () => {
      expect(isCatalogue(value)).toBe(false);
    });
  it('accepts real aliases and optional pagination without client-side relevance guesses', () => {
    expect(isCatalogue(catalogue)).toBe(true);
    expect(isCatalogue({ items: [], next_cursor: 'opaque cursor' })).toBe(true);
  });
});
