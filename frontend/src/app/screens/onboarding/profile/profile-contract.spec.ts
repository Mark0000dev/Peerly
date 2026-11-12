import { describe, expect, it } from 'vitest';
import { isProfile, isRevision, isProfileReference } from './profile-contract';
import { ownProfile, revision, profileReference } from './profile.fixtures';

describe('actual own profile transport boundary', () => {
  for (const value of [
    null,
    false,
    'private',
    {},
    [],
    { profile: null },
    { photo: null },
    { profile: false, photo: null },
  ]) {
    it(`rejects malformed profile ${JSON.stringify(value)}`, () => {
      expect(isProfile(value)).toBe(false);
    });
  }
  for (const key of Object.keys(revision)) {
    it(`requires valid revision field ${key}`, () => {
      expect(isRevision({ ...revision, [key]: key === 'version' ? '1' : 0 })).toBe(false);
      expect(
        isRevision(
          Object.fromEntries(
            Object.entries(revision).filter(
              (entry: readonly [string, unknown]) => entry[0] !== key,
            ),
          ),
        ),
      ).toBe(false);
    });
  }
  for (const value of [
    null,
    false,
    'private',
    { ...revision, version: 0 },
    { ...revision, version: 1.1 },
    { ...revision, languages: [1] },
    { ...revision, task: 'invented' },
  ]) {
    it(`rejects invalid revision ${JSON.stringify(value)}`, () => {
      expect(isRevision(value)).toBe(false);
    });
  }
  it('accepts nullable optional profile values without synthesizing readiness', () => {
    expect(isProfile({ profile: null, photo: null })).toBe(true);
    expect(isProfile(ownProfile)).toBe(true);
    expect(
      isRevision({
        ...revision,
        display_name: null,
        about: null,
        programme: null,
        year_label: null,
      }),
    ).toBe(true);
    expect(isRevision({ ...revision, task: 'offer_help' })).toBe(true);
  });
  const photo = {
    upload_id: '00000000-0000-0000-0000-000000000003',
    version: 1,
    display_url: '/api/v1/media/00000000-0000-0000-0000-000000000003/display',
  } as const;
  it('accepts only the exact private same-origin display path', () => {
    expect(isProfile({ ...ownProfile, photo })).toBe(true);
    for (const invalid of [
      false,
      {},
      { ...photo, upload_id: 0 },
      { ...photo, version: '1' },
      { ...photo, version: 0 },
      { ...photo, version: 1.1 },
      { ...photo, display_url: 'https://outside.invalid/photo' },
    ])
      expect(isProfile({ ...ownProfile, photo: invalid })).toBe(false);
  });
});

describe('authenticated profile reference transport boundary', () => {
  it('accepts the actual reference projection without manufacturing options', () => {
    expect(isProfileReference(profileReference)).toBe(true);
    expect(isProfileReference({ ...profileReference, languages: [] })).toBe(true);
  });
  for (const value of [
    null,
    false,
    {},
    { ...profileReference, languages: null },
    { ...profileReference, languages: [null] },
    { ...profileReference, languages: [{ code: 1, label: 'English' }] },
    { ...profileReference, languages: [{ code: 'EN', label: 'English' }] },
    { ...profileReference, languages: [{ code: 'en', label: 0 }] },
    { ...profileReference, languages: [{ code: 'en', label: '  ' }] },
    {
      ...profileReference,
      languages: [profileReference.languages[0], profileReference.languages[0]],
    },
    { ...profileReference, max_languages: 0 },
    { ...profileReference, max_languages: 1.5 },
    { ...profileReference, min_display_name_length: 0 },
    { ...profileReference, max_display_name_length: 1 },
    { ...profileReference, university: '' },
  ])
    it(`rejects invalid language/reference projection ${JSON.stringify(value)}`, () => {
      expect(isProfileReference(value)).toBe(false);
    });
});
