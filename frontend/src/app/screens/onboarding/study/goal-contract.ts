import type { Api } from '../../../api.generated';

export type CanonicalChoice = Api['schemas']['CanonicalSubjectRequest'] &
  Pick<Api['schemas']['CanonicalSubjectResponse'], 'label'> &
  Partial<Pick<Api['schemas']['SubjectResponse'], 'aliases'>>;
export type SubjectChoice = CanonicalChoice | Api['schemas']['CustomSubjectRequest'];
export type CatalogueView = Omit<Api['schemas']['SubjectsResponse'], 'items'> & {
  readonly items: readonly CanonicalChoice[];
};

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
function isSubject(value: unknown): value is Api['schemas']['SubjectResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    typeof value.id === 'string' &&
    'name' in value &&
    typeof value.name === 'string' &&
    'aliases' in value &&
    Array.isArray(value.aliases) &&
    value.aliases.every((alias: unknown) => typeof alias === 'string')
  );
}
export function isCatalogue(value: unknown): value is Api['schemas']['SubjectsResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'items' in value &&
    Array.isArray(value.items) &&
    value.items.every(isSubject) &&
    'next_cursor' in value &&
    (value.next_cursor === null || typeof value.next_cursor === 'string')
  );
}
