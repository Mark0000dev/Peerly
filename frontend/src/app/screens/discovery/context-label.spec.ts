import { describe, expect, it } from 'vitest';
import type { Api } from '../../api.generated';
import { contextLabel } from './context-label';

const goal: Api['schemas']['GoalResponse'] = {
  id: 'goal-one',
  version: 2,
  subject: { kind: 'custom', label: 'SQL' },
  topic: 'JOINs',
  context: null,
  shared_learning: true,
  created_at: '2026-11-12T00:00:00Z',
  updated_at: '2026-11-12T00:00:00Z',
  completed_at: null,
};
const context = { mode: 'find_help', goal_id: goal.id, goal_version: goal.version } as const;

describe('Discovery context labels use only matching actor-owned versions', () => {
  it('shows the actual goal and optional topic in both goal modes', () => {
    expect(contextLabel(context, { goal }, undefined)).toBe('SQL · JOINs');
    expect(
      contextLabel(
        { ...context, mode: 'study_together' },
        { goal: { ...goal, topic: null } },
        undefined,
      ),
    ).toBe('SQL');
  });
  it('does not substitute missing, stale or unrelated goals', () => {
    expect(contextLabel(null, { goal }, undefined)).toBeNull();
    expect(contextLabel(undefined, { goal }, undefined)).toBeNull();
    expect(contextLabel(context, undefined, undefined)).toBeNull();
    expect(contextLabel(context, { goal: null }, undefined)).toBeNull();
    expect(contextLabel({ ...context, goal_id: 'another' }, { goal }, undefined)).toBeNull();
    expect(contextLabel({ ...context, goal_version: 3 }, { goal }, undefined)).toBeNull();
  });
  it('shows only the matching help selection', () => {
    const selection = {
      version: 4,
      saved_at: goal.created_at,
      subjects: [
        { subject_id: 'sql', label: 'SQL', topic_note: 'Queries' },
        { subject_id: 'math', label: 'Mathematics', topic_note: null },
      ],
    };
    const helpContext = { mode: 'offer_help', help_version: 4 } as const;
    expect(contextLabel(helpContext, { goal }, { selection })).toBe('SQL · Mathematics');
    expect(
      contextLabel(helpContext, { goal }, { selection: { ...selection, version: 5 } }),
    ).toBeNull();
    expect(
      contextLabel(helpContext, { goal }, { selection: { ...selection, subjects: [] } }),
    ).toBeNull();
    expect(contextLabel(helpContext, { goal }, { selection: null })).toBeNull();
    expect(contextLabel(helpContext, { goal }, undefined)).toBeNull();
  });
});
