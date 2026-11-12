import { describe, expect, it } from 'vitest';
import { isCatalogue } from './help-contract';
import { isHelp, isOwnHelp } from '../../study-context-contract';
import { helpSelection, ownHelp } from './help.fixtures';
import { catalogue } from './goal.fixtures';

describe('actual readonly helper selection contracts', () => {
  it('accepts actual saved, empty and nullable note selections', () => {
    expect(isHelp(helpSelection)).toBe(true);
    expect(isHelp({ ...helpSelection, subjects: [] })).toBe(true);
    expect(
      isHelp({ ...helpSelection, subjects: [{ ...helpSelection.subjects[0], topic_note: null }] }),
    ).toBe(true);
    expect(isOwnHelp(ownHelp)).toBe(true);
    expect(isOwnHelp({ selection: null })).toBe(true);
    expect(isCatalogue(catalogue)).toBe(true);
    expect(isCatalogue({ items: [], next_cursor: 'opaque' })).toBe(true);
  });
  for (const value of [
    null,
    [],
    'PRIVATE',
    {},
    { version: true },
    { ...helpSelection, version: 0 },
    { ...helpSelection, version: 1.5 },
    { ...helpSelection, saved_at: 1 },
    { ...helpSelection, subjects: null },
    { ...helpSelection, subjects: [null] },
    { ...helpSelection, subjects: [{}] },
    { ...helpSelection, subjects: [{ subject_id: 1, label: 'SQL', topic_note: null }] },
    { ...helpSelection, subjects: [{ subject_id: 'id', label: 1, topic_note: null }] },
    { ...helpSelection, subjects: [{ subject_id: 'id', label: 'SQL', topic_note: false }] },
  ]) {
    it(`rejects malformed saved selection ${JSON.stringify(value)}`, () => {
      expect(isHelp(value)).toBe(false);
    });
  }
  for (const value of [null, false, {}, { selection: false }]) {
    it(`rejects malformed own selection ${JSON.stringify(value)}`, () => {
      expect(isOwnHelp(value)).toBe(false);
    });
  }
  for (const value of [
    null,
    false,
    {},
    { items: [], next_cursor: 1 },
    { items: [null], next_cursor: null },
    { items: [{}], next_cursor: null },
    { items: [{ id: 'id', name: 'SQL', aliases: [false] }], next_cursor: null },
  ]) {
    it(`rejects malformed picker catalogue ${JSON.stringify(value)}`, () => {
      expect(isCatalogue(value)).toBe(false);
    });
  }
});
