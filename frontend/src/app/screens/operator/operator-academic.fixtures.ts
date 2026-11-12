import type { Api } from '../../api.generated';
import { account } from './operator.fixtures';
export const academicGoal: Api['schemas']['OperatorGoalRootResponse'] = {
  id: '00000000-0000-4000-8000-000000000021',
  account_id: account.account_id,
  current_version: 2,
  created_at: '2025-01-02T03:04:05Z',
  completed_at: null,
};
export const academicRevision: Api['schemas']['OperatorGoalRevisionResponse'] = {
  goal_id: academicGoal.id,
  account_id: account.account_id,
  version: 2,
  subject_id: null,
  subject_label: 'Archived subject <literal>',
  topic: '  Stored topic  ',
  topic_match_key: 'ARCHIVE:key/unchanged',
  context: 'Stored\ncontext <b>literal</b>',
  shared_learning: false,
  saved_at: '2025-02-03T04:05:06Z',
  completed_at: null,
};
export const academicGoals: Api['schemas']['OperatorGoalsResponse'] = {
  account_id: account.account_id,
  goals: [academicGoal],
  next_cursor: null,
  anchor_created_at: academicGoal.created_at,
  anchor_goal_id: academicGoal.id,
  observed_at: '2026-11-08T06:20:00Z',
  pagination: 'anchored_search_not_commit_order',
};
export const academicHistory: Api['schemas']['OperatorGoalHistoryResponse'] = {
  goal: academicGoal,
  revisions: [academicRevision],
  next_cursor: null,
  anchor_version: 2,
  observed_at: academicGoals.observed_at,
};
export const academicSelection: Api['schemas']['OperatorHelpHistorySelectionResponse'] = {
  slot: 0,
  subject_id: '00000000-0000-4000-8000-000000000022',
  subject_label: 'Historical SQL <literal>',
  topic_note: '  Old\n note ',
  topic_match_key: 'old:KEY',
};
export const academicHelp: Api['schemas']['OperatorHelpHistoryResponse'] = {
  account_id: account.account_id,
  anchor_version: 2,
  next_cursor: null,
  revisions: [
    {
      account_id: account.account_id,
      version: 2,
      selections: [],
      saved_at: '2025-02-03T04:05:06Z',
    },
    {
      account_id: account.account_id,
      version: 1,
      selections: [academicSelection],
      saved_at: '2025-01-02T03:04:05Z',
    },
  ],
};
