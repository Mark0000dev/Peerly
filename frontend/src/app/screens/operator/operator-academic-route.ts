import type { ParamMap } from '@angular/router';
import type { GoalFilters } from './operator-academic-contract';
import { instant, uuid } from './operator-contract';

export function academicRoute(params: Readonly<ParamMap>, tab: 'goals' | 'help') {
  const state = params.get('goal_state');
  const from = params.get('goal_created_from');
  const before = params.get('goal_created_before');
  const cursor = params.get('goals_cursor');
  const goalId = params.get('goal');
  const goalCursor = params.get('goal_cursor');
  const helpCursor = params.get('help_cursor');
  const cursors = tab === 'goals' ? [cursor, goalCursor] : [helpCursor];
  const filters: GoalFilters = {
    state: state === 'active' || state === 'completed' ? state : null,
    created_from: from,
    created_before: before,
    cursor,
  };
  const error = cursors.some(
    (value) => value !== null && (value.length === 0 || value.length > 1024),
  )
    ? 'The page cursor is invalid. Return to the first page.'
    : tab === 'goals' && goalId !== null && !uuid(goalId)
      ? 'The selected goal ID must be a UUID.'
      : tab === 'goals' && state !== null && state !== 'active' && state !== 'completed'
        ? 'Choose an active or completed goal filter.'
        : tab === 'goals' &&
            ((from !== null && !instant(from)) || (before !== null && !instant(before)))
          ? 'Created filters need an ISO date and time with timezone.'
          : tab === 'goals' &&
              from !== null &&
              before !== null &&
              Date.parse(from) >= Date.parse(before)
            ? 'Created before must be later than created from.'
            : null;
  return { filters, goalId, goalCursor, helpCursor, error };
}

export const academicReset = {
  tab: null,
  goal: null,
  goal_state: null,
  goal_created_from: null,
  goal_created_before: null,
  goals_cursor: null,
  goal_cursor: null,
  help_cursor: null,
} as const;
