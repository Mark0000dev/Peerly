import { describe, expect, it, vi } from 'vitest';
import {
  commentProblem,
  isBlock,
  isBlocks,
  isProfile,
  isReceipt,
  languageName,
} from './person-contract';
import { person, blocked, receipt } from './person.fixtures';

describe('public language code labels', () => {
  it('keeps an unknown code readable when the locale provider has no label', () => {
    const lookup = vi.spyOn(Intl.DisplayNames.prototype, 'of').mockReturnValue(undefined);
    expect(languageName('zz')).toBe('zz');
    lookup.mockRestore();
  });
  it('labels actual language codes without claiming academic verification', () => {
    expect(languageName('en')).toBe('English');
    expect(languageName('ja')).toBe('Japanese');
    expect(languageName('English')).toBe('English');
    expect(languageName('')).toBe('');
  });
});

describe('actual person boundary guards', () => {
  it('accepts the deeply readonly public projection and optional public fields', () => {
    expect(isProfile(person)).toBe(true);
    expect(isProfile({ ...person, goal: { ...person.goal, subject: { label: 'Custom' } } })).toBe(
      true,
    );
    expect(
      isProfile({
        ...person,
        about: null,
        programme: null,
        year_label: null,
        goal: null,
        help_subjects: null,
        languages: [],
      }),
    ).toBe(true);
    expect(
      isProfile({
        ...person,
        goal: { ...person.goal, subject: { kind: 'custom', label: 'Custom' } },
      }),
    ).toBe(true);
    expect(
      isProfile({ ...person, goal: { ...person.goal, subject: { id: 'id', label: 'Canonical' } } }),
    ).toBe(true);
  });
  it.each([
    null,
    false,
    [],
    'raw',
    {},
    { ...person, id: 2 },
    { ...person, display_name: null },
    { ...person, access_context_id: null },
    { ...person, version: -1 },
    { ...person, about: 1 },
    { ...person, programme: false },
    { ...person, year_label: false },
    { ...person, languages: [2] },
    { ...person, photo: null },
    { ...person, photo: { display_url: 1, version: 1 } },
    { ...person, photo: { display_url: '/', version: 0.5 } },
    { ...person, own_block: { ...blocked, person_id: 'different' } },
    { ...person, goal: {} },
    { ...person, help_subjects: {} },
  ])('rejects malformed public response %#', (value: unknown) => {
    expect(isProfile(value)).toBe(false);
  });
  it.each([
    'id',
    'version',
    'created_at',
    'updated_at',
    'completed_at',
    'context',
    'topic',
    'shared_learning',
  ])('validates goal %s', (field) => {
    expect(isProfile({ ...person, goal: { ...person.goal, [field]: undefined } })).toBe(false);
  });
  it.each([
    null,
    { label: 1 },
    { kind: 'unknown', label: 'x' },
    { kind: 'canonical', label: 'x', id: false },
  ])('rejects malformed subject %#', (subject: unknown) => {
    expect(isProfile({ ...person, goal: { ...person.goal, subject } })).toBe(false);
  });
  it.each([
    { version: -1 },
    { saved_at: null },
    { subjects: null },
    { subjects: [{}] },
    { subjects: [{ subject_id: 'x', label: 1, topic_note: null }] },
    { subjects: [{ subject_id: 'x', label: 'SQL', topic_note: 1 }] },
  ])('rejects malformed help %#', (fields: Readonly<Record<string, unknown>>) => {
    expect(isProfile({ ...person, help_subjects: { ...person.help_subjects, ...fields } })).toBe(
      false,
    );
  });
  it('checks own block revision and cursor pages without deriving absence', () => {
    expect(isBlock(blocked)).toBe(true);
    expect(
      isBlocks({
        people: [{ block: blocked, deleted: false, display_name: 'Aiko' }],
        next_cursor: 'opaque',
      }),
    ).toBe(true);
    expect(
      isBlocks({
        people: [{ block: blocked, deleted: true, display_name: null }],
        next_cursor: null,
      }),
    ).toBe(true);
    expect(isBlocks({ people: [], next_cursor: null })).toBe(true);
  });
  it.each([
    null,
    {},
    { ...blocked, person_id: null },
    { ...blocked, blocked: 1 },
    { ...blocked, version: Infinity },
    { ...blocked, changed_at: 1 },
  ])('rejects malformed block %#', (value: unknown) => {
    expect(isBlock(value)).toBe(false);
  });
  it.each([
    null,
    {},
    { people: [], next_cursor: 1 },
    { people: [{}], next_cursor: null },
    { people: [{ block: blocked, deleted: null, display_name: null }], next_cursor: null },
    { people: [{ block: blocked, deleted: false, display_name: 2 }], next_cursor: null },
  ])('rejects malformed page %#', (value: unknown) => {
    expect(isBlocks(value)).toBe(false);
  });
  it('accepts receipt with the default discriminator omitted', () => {
    expect(isReceipt(receipt)).toBe(true);
    expect(isReceipt({ ...receipt, kind: undefined })).toBe(true);
  });
  it.each([
    null,
    {},
    { ...receipt, id: null },
    { ...receipt, context_id: null },
    { ...receipt, submitted_at: null },
    { ...receipt, kind: 'message' },
  ])('rejects malformed receipt %#', (value: unknown) => {
    expect(isReceipt(value)).toBe(false);
  });
  it('counts Unicode codepoints and requires an explanation for Other', () => {
    expect(commentProblem('other', ' \n ')).toContain('Explain');
    expect(commentProblem('spam', '')).toBeNull();
    expect(commentProblem('other', '😀'.repeat(1000))).toBeNull();
    expect(commentProblem('harassment', '😀'.repeat(1001))).toContain('1000');
  });
});
