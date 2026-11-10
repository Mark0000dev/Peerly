import type { Api } from '../../../api.generated';

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
