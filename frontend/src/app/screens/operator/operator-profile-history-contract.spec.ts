import { convertToParamMap } from '@angular/router';
import { describe, expect, it } from 'vitest';
import { isProfileHistory, profileHistoryRoute } from './operator-profile-history-contract';
import { profilePage, storedProfile } from './operator-profile-history.fixtures';
describe('M06 raw retained profile history boundary', () => {
  it('preserves raw null/empty fields, language slots, descending retained versions and empty history', () => {
    expect(isProfileHistory(profilePage)).toBe(true);
    expect(
      isProfileHistory({ ...profilePage, anchor_version: 0, revisions: [], next_cursor: null }),
    ).toBe(true);
    expect(
      isProfileHistory({
        ...profilePage,
        revisions: Array.from({ length: 50 }, (_, i) => storedProfile(53 - i)),
      }),
    ).toBe(true);
  });
  it('rejects malformed owner/version/order without applying current profile catalogues', () => {
    for (const value of [
      null,
      {},
      { ...profilePage, account_id: 'bad' },
      { ...profilePage, anchor_version: -1 },
      { ...profilePage, anchor_version: 0.5 },
      { ...profilePage, next_cursor: 4 },
      { ...profilePage, revisions: [storedProfile(54)] },
      { ...profilePage, revisions: [storedProfile(1), storedProfile(2)] },
      { ...profilePage, revisions: [storedProfile(1), storedProfile(1)] },
      { ...profilePage, revisions: Array.from({ length: 51 }, (_, i) => storedProfile(53 - i)) },
    ])
      expect(isProfileHistory(value)).toBe(false);
    for (const [key, value] of Object.entries({
      account_id: profilePage.account_id.replace('2', '3'),
      version: 0,
      display_name: 5,
      about: 5,
      programme: 5,
      year_label: 5,
      languages: [3],
      task: 'unknown',
      saved_at: 'bad',
    }))
      expect(
        isProfileHistory({ ...profilePage, revisions: [{ ...storedProfile(1), [key]: value }] }),
      ).toBe(false);
  });
  it('requires explicit URL open and bounds opaque cursor', () => {
    expect(profileHistoryRoute(convertToParamMap({}))).toEqual({
      open: false,
      cursor: null,
      error: null,
    });
    expect(
      profileHistoryRoute(convertToParamMap({ profile_history: 'open', profile_cursor: 'opaque' })),
    ).toEqual({ open: true, cursor: 'opaque', error: null });
    expect(profileHistoryRoute(convertToParamMap({ profile_history: 'other' })).open).toBe(false);
    for (const cursor of ['', 'x'.repeat(1025)])
      expect(
        profileHistoryRoute(convertToParamMap({ profile_cursor: cursor })).error,
      ).not.toBeNull();
  });
});
