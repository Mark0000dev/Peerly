import { describe, expect, it } from 'vitest';
import { convertToParamMap } from '@angular/router';
import { isGoals, isGoalHistory, isHelpHistory } from './operator-academic-contract';
import { academicRoute } from './operator-academic-route';
import {
  academicGoal,
  academicGoals,
  academicRevision,
  academicHistory,
  academicSelection,
  academicHelp,
} from './operator-academic.fixtures';
import { account } from './operator.fixtures';

describe('Actual retained academic boundary and URL validation', () => {
  it('keeps literal historical fields and accepts absent sources/clears without current-catalogue rules', () => {
    expect(isGoals(academicGoals)).toBe(true);
    expect(
      isGoals({
        ...academicGoals,
        pagination: undefined,
        goals: [],
        next_cursor: 'opaque +/=cursor',
        anchor_created_at: null,
        anchor_goal_id: null,
      }),
    ).toBe(true);
    expect(isGoalHistory(academicHistory)).toBe(true);
    expect(
      isGoalHistory({
        ...academicHistory,
        next_cursor: 'opaque',
        revisions: [
          {
            ...academicRevision,
            subject_id: account.account_id,
            topic: null,
            topic_match_key: null,
            context: null,
            shared_learning: true,
            completed_at: academicRevision.saved_at,
          },
        ],
      }),
    ).toBe(true);
    expect(
      isGoals({
        ...academicGoals,
        goals: [{ ...academicGoal, completed_at: academicRevision.saved_at }],
      }),
    ).toBe(true);
    expect(isHelpHistory(academicHelp)).toBe(true);
    expect(
      isHelpHistory({ ...academicHelp, next_cursor: 'older', anchor_version: 0, revisions: [] }),
    ).toBe(true);
    expect(
      isHelpHistory({
        ...academicHelp,
        revisions: [
          {
            account_id: account.account_id,
            saved_at: academicRevision.saved_at,
            version: 1,
            selections: [{ ...academicSelection, topic_note: null, topic_match_key: null }],
          },
        ],
      }),
    ).toBe(true);
  });
  it('rejects malformed nested roots/revisions and cross-owner/cross-goal payloads', () => {
    for (const value of [null, 3, 'wrong', {}, []]) {
      expect(isGoals(value)).toBe(false);
      expect(isGoalHistory(value)).toBe(false);
      expect(isHelpHistory(value)).toBe(false);
    }
    for (const key of Object.keys(academicGoals).filter((key) => key !== 'pagination'))
      expect(isGoals({ ...academicGoals, [key]: undefined })).toBe(false);
    expect(isGoals({ ...academicGoals, pagination: 'snapshot' })).toBe(false);
    expect(isGoals({ ...academicGoals, goals: [null] })).toBe(false);
    for (const key of Object.keys(academicGoal))
      expect(isGoals({ ...academicGoals, goals: [{ ...academicGoal, [key]: undefined }] })).toBe(
        false,
      );
    expect(
      isGoals({ ...academicGoals, goals: [{ ...academicGoal, account_id: academicGoal.id }] }),
    ).toBe(false);
    expect(isGoals({ ...academicGoals, goals: [{ ...academicGoal, current_version: 0 }] })).toBe(
      false,
    );
    for (const key of Object.keys(academicHistory))
      expect(isGoalHistory({ ...academicHistory, [key]: undefined })).toBe(false);
    for (const key of Object.keys(academicRevision))
      expect(
        isGoalHistory({
          ...academicHistory,
          revisions: [{ ...academicRevision, [key]: undefined }],
        }),
      ).toBe(false);
    expect(
      isGoalHistory({
        ...academicHistory,
        revisions: [{ ...academicRevision, account_id: academicGoal.id }],
      }),
    ).toBe(false);
    expect(
      isGoalHistory({
        ...academicHistory,
        revisions: [{ ...academicRevision, goal_id: account.account_id }],
      }),
    ).toBe(false);
    expect(isGoalHistory({ ...academicHistory, anchor_version: 0 })).toBe(false);
    for (const key of Object.keys(academicHelp))
      expect(isHelpHistory({ ...academicHelp, [key]: undefined })).toBe(false);
    const help = {
      account_id: account.account_id,
      saved_at: academicRevision.saved_at,
      version: 1,
      selections: [academicSelection],
    };
    for (const key of Object.keys(help))
      expect(isHelpHistory({ ...academicHelp, revisions: [{ ...help, [key]: undefined }] })).toBe(
        false,
      );
    for (const key of Object.keys(academicSelection))
      expect(
        isHelpHistory({
          ...academicHelp,
          revisions: [{ ...help, selections: [{ ...academicSelection, [key]: undefined }] }],
        }),
      ).toBe(false);
    expect(
      isHelpHistory({ ...academicHelp, revisions: [{ ...help, account_id: academicGoal.id }] }),
    ).toBe(false);
    expect(isHelpHistory({ ...academicHelp, revisions: [{ ...help, selections: [null] }] })).toBe(
      false,
    );
    expect(
      isHelpHistory({
        ...academicHelp,
        revisions: [{ ...help, selections: [{ ...academicSelection, slot: -1 }] }],
      }),
    ).toBe(false);
    expect(isHelpHistory({ ...academicHelp, anchor_version: 1.5 })).toBe(false);
  });
  it('separates URL filters/cursors and rejects malformed active panel parameters before GET', () => {
    const read = (params: Readonly<Record<string, string>>, tab: 'goals' | 'help' = 'goals') =>
      academicRoute(convertToParamMap(params), tab);
    expect(read({}).error).toBeNull();
    expect(
      read({
        goal_state: 'active',
        goal_created_from: '2025-01-01T00:00:00Z',
        goal_created_before: '2026-01-01T00:00:00+08:00',
        goals_cursor: 'opaque',
        goal: academicGoal.id,
        goal_cursor: 'old',
      }).error,
    ).toBeNull();
    expect(read({ goal_state: 'completed' }).filters.state).toBe('completed');
    expect(read({ help_cursor: 'help', goal_state: 'invalid' }, 'help').error).toBeNull();
    for (const cursor of ['goals_cursor', 'goal_cursor']) {
      expect(read({ [cursor]: '' }).error).toContain('cursor');
      expect(read({ [cursor]: 'x'.repeat(1025) }).error).toContain('cursor');
    }
    expect(read({ help_cursor: '' }, 'help').error).toContain('cursor');
    expect(read({ goal: 'bad' }).error).toContain('UUID');
    expect(read({ goal_state: 'all' }).error).toContain('active or completed');
    expect(read({ goal_created_from: 'bad' }).error).toContain('timezone');
    expect(read({ goal_created_before: 'bad' }).error).toContain('timezone');
    expect(
      read({
        goal_created_from: '2026-01-01T00:00:00Z',
        goal_created_before: '2025-01-01T00:00:00Z',
      }).error,
    ).toContain('later');
  });
});
