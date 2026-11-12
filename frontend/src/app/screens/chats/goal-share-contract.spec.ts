import { describe, expect, it } from 'vitest';
import { isOwnGoal, isShareReceipt, isShares } from './goal-share-contract';
import { currentGoal, shareReceipt, shares } from './chats.fixtures';
describe('C04 actual versioned goal-sharing boundary', () => {
  it('validates nullable current goal and canonical/custom source without aliases', () => {
    expect(isOwnGoal({ goal: currentGoal })).toBe(true);
    expect(isOwnGoal({ goal: null })).toBe(true);
    expect(
      isOwnGoal({
        goal: {
          ...currentGoal,
          completed_at: currentGoal.updated_at,
          subject: { kind: 'custom', label: 'Logic' },
        },
      }),
    ).toBe(true);
    expect(isShareReceipt(shareReceipt)).toBe(true);
    expect(
      isShareReceipt({
        ...shareReceipt,
        source: { ...shareReceipt.source, subject: { label: 'Logic' } },
      }),
    ).toBe(true);
    expect(
      isShareReceipt({
        ...shareReceipt,
        source: { ...shareReceipt.source, subject: { id: 'subject', label: 'Logic' } },
      }),
    ).toBe(true);
    expect(
      isShareReceipt({
        ...shareReceipt,
        source: {
          ...shareReceipt.source,
          subject: { id: 'subject', label: 'Logic', kind: 'custom' },
        },
      }),
    ).toBe(false);
  });
  it('checks every retained receipt/source and current-goal field', () => {
    for (const [guard, value] of [
      [isShareReceipt, shareReceipt],
      [isOwnGoal, { goal: currentGoal }],
    ] as const) {
      expect(guard(null)).toBe(false);
      expect(guard({})).toBe(false);
      for (const key of Object.keys(value)) expect(guard({ ...value, [key]: [] })).toBe(false);
    }
    for (const key of Object.keys(currentGoal))
      expect(isOwnGoal({ goal: { ...currentGoal, [key]: [] } })).toBe(false);
    for (const key of Object.keys(shareReceipt.source))
      expect(
        isShareReceipt({ ...shareReceipt, source: { ...shareReceipt.source, [key]: [] } }),
      ).toBe(false);
    expect(
      isShareReceipt({ ...shareReceipt, source: { ...shareReceipt.source, owner_id: 'foreign' } }),
    ).toBe(false);
    expect(
      isShareReceipt({ ...shareReceipt, source: { ...shareReceipt.source, version: 0 } }),
    ).toBe(false);
    expect(isShareReceipt({ ...shareReceipt, context_version: 0 })).toBe(false);
    expect(isShareReceipt({ ...shareReceipt, shared_at: 'bad' })).toBe(false);
    expect(isOwnGoal({ goal: { ...currentGoal, version: 1.5 } })).toBe(false);
    expect(isOwnGoal({ goal: { ...currentGoal, version: -1 } })).toBe(false);
    expect(isOwnGoal({ goal: { ...currentGoal, version: 0 } })).toBe(false);
  });
  it('validates complete baseline/latest/history, optional defaults and nullable cursors', () => {
    const entry = { ...shareReceipt, can_complete: true };
    expect(isShares(shares)).toBe(true);
    expect(isShares({ ...shares, latest: entry, history: [entry], next_cursor: 'opaque' })).toBe(
      true,
    );
    expect(
      isShares({ ...shares, baseline: { ...shares.baseline, context_version: undefined } }),
    ).toBe(false);
    const { context_version, ...baseline } = shares.baseline;
    expect(context_version).toBe(0);
    expect(isShares({ ...shares, baseline })).toBe(true);
    expect(isShares(null)).toBe(false);
    for (const key of Object.keys(shares)) expect(isShares({ ...shares, [key]: {} })).toBe(false);
    for (const key of Object.keys(shares.baseline))
      expect(isShares({ ...shares, baseline: { ...shares.baseline, [key]: [] } })).toBe(false);
    expect(isShares({ ...shares, latest: shareReceipt })).toBe(false);
    expect(isShares({ ...shares, history: [shareReceipt] })).toBe(false);
  });
});
