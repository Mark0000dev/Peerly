import type { Api } from '../../../api.generated';

export type CanonicalChoice = Api['schemas']['CanonicalSubjectRequest'] &
  Pick<Api['schemas']['CanonicalSubjectResponse'], 'label'> &
  Partial<Pick<Api['schemas']['SubjectResponse'], 'aliases'>>;
export type SubjectChoice = CanonicalChoice | Api['schemas']['CustomSubjectRequest'];
export type CatalogueView = Omit<Api['schemas']['SubjectsResponse'], 'items'> & {
  readonly items: readonly CanonicalChoice[];
};

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
