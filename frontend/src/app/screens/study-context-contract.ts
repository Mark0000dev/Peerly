import type { Api } from '../api.generated';

function isGoalSubject(value: unknown): value is Api['schemas']['GoalResponse']['subject'] {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('label' in value) ||
    typeof value.label !== 'string'
  )
    return false;
  if ('id' in value)
    return typeof value.id === 'string' && (!('kind' in value) || value.kind === 'canonical');
  return !('kind' in value) || value.kind === 'custom';
}
export function isGoal(value: unknown): value is Api['schemas']['GoalResponse'] {
  if (typeof value !== 'object' || value === null) return false;
  return (
    'id' in value &&
    typeof value.id === 'string' &&
    'version' in value &&
    typeof value.version === 'number' &&
    Number.isInteger(value.version) &&
    value.version >= 1 &&
    'subject' in value &&
    isGoalSubject(value.subject) &&
    'topic' in value &&
    (value.topic === null || typeof value.topic === 'string') &&
    'context' in value &&
    (value.context === null || typeof value.context === 'string') &&
    'shared_learning' in value &&
    typeof value.shared_learning === 'boolean' &&
    'created_at' in value &&
    typeof value.created_at === 'string' &&
    'updated_at' in value &&
    typeof value.updated_at === 'string' &&
    'completed_at' in value &&
    (value.completed_at === null || typeof value.completed_at === 'string')
  );
}
export function isOwnGoal(value: unknown): value is Api['schemas']['OwnGoalResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'goal' in value &&
    (value.goal === null || isGoal(value.goal))
  );
}
function isHelpSubject(value: unknown): value is Api['schemas']['HelpSubjectResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'subject_id' in value &&
    typeof value.subject_id === 'string' &&
    'label' in value &&
    typeof value.label === 'string' &&
    'topic_note' in value &&
    (value.topic_note === null || typeof value.topic_note === 'string')
  );
}

export function isHelp(value: unknown): value is Api['schemas']['HelpResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'version' in value &&
    typeof value.version === 'number' &&
    Number.isInteger(value.version) &&
    value.version >= 1 &&
    'saved_at' in value &&
    typeof value.saved_at === 'string' &&
    'subjects' in value &&
    Array.isArray(value.subjects) &&
    value.subjects.every(isHelpSubject)
  );
}

export function isOwnHelp(value: unknown): value is Api['schemas']['OwnHelpResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'selection' in value &&
    (value.selection === null || isHelp(value.selection))
  );
}
