import { describe, expect, it } from 'vitest';
import { isNotificationMode, isPreference } from './notification-contract';

describe('Actual P02 enum and canonical revision', () => {
  it('uses exactly two choices, never an OS permission or analytics opt-out', () => {
    expect(isNotificationMode('messages_and_requests')).toBe(true);
    expect(isNotificationMode('all_updates')).toBe(true);
    for (const value of ['off', 'granted', true, {}, null])
      expect(isNotificationMode(value)).toBe(false);
  });
  it('distinguishes unchosen default from actual persisted revisions', () => {
    expect(isPreference({ mode: 'messages_and_requests', version: 0, changed_at: null })).toBe(
      true,
    );
    expect(
      isPreference({ mode: 'all_updates', version: 1, changed_at: '2026-11-09T08:00:00Z' }),
    ).toBe(true);
    for (const value of [
      null,
      {},
      { mode: 'off', version: 0, changed_at: null },
      { mode: 'all_updates', version: 0, changed_at: '2026-11-09T08:00:00Z' },
      { mode: 'all_updates', version: 1, changed_at: null },
      { mode: 'all_updates', version: -1, changed_at: null },
      { mode: 'all_updates', version: 1.5, changed_at: null },
      { mode: 'all_updates', version: 1, changed_at: 'bad' },
    ])
      expect(isPreference(value)).toBe(false);
  });
});
