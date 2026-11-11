import type { Api } from '../../../api.generated';

export const catalogue = {
  items: [
    {
      id: '00000000-0000-0000-0000-000000000010',
      name: 'Calculus',
      aliases: ['Calc 1', 'Differential calculus'],
    },
    { id: '00000000-0000-0000-0000-000000000011', name: 'SQL', aliases: ['Databases'] },
  ],
  next_cursor: null,
} as const satisfies Api['schemas']['SubjectsResponse'];
export const goal = {
  id: '00000000-0000-0000-0000-000000000021',
  version: 2,
  subject: { kind: 'canonical', id: catalogue.items[0].id, label: 'Calculus' },
  topic: 'Limits',
  context: 'Work through examples together',
  shared_learning: false,
  created_at: '2026-11-07T12:00:00Z',
  updated_at: '2026-11-07T12:00:00Z',
  completed_at: null,
} as const satisfies Api['schemas']['GoalResponse'];
export const ownGoal = { goal } as const satisfies Api['schemas']['OwnGoalResponse'];
