import type { Api } from '../../../api.generated';

export function isRevision(value: unknown): value is Api['schemas']['ProfileRevisionResponse'] {
  if (typeof value !== 'object' || value === null) return false;
  return (
    'version' in value &&
    typeof value.version === 'number' &&
    Number.isInteger(value.version) &&
    value.version >= 1 &&
    'display_name' in value &&
    (value.display_name === null || typeof value.display_name === 'string') &&
    'about' in value &&
    (value.about === null || typeof value.about === 'string') &&
    'programme' in value &&
    (value.programme === null || typeof value.programme === 'string') &&
    'year_label' in value &&
    (value.year_label === null || typeof value.year_label === 'string') &&
    'languages' in value &&
    Array.isArray(value.languages) &&
    value.languages.every((item: unknown) => typeof item === 'string') &&
    'task' in value &&
    (value.task === 'find_help' || value.task === 'offer_help') &&
    'saved_at' in value &&
    typeof value.saved_at === 'string'
  );
}

export function isProfile(value: unknown): value is Api['schemas']['OwnProfileResponse'] {
  if (typeof value !== 'object' || value === null || !('profile' in value) || !('photo' in value))
    return false;
  if (!(value.profile === null || isRevision(value.profile))) return false;
  const photo = value.photo;
  return (
    photo === null ||
    (typeof photo === 'object' &&
      'upload_id' in photo &&
      typeof photo.upload_id === 'string' &&
      'version' in photo &&
      typeof photo.version === 'number' &&
      Number.isInteger(photo.version) &&
      photo.version >= 1 &&
      'display_url' in photo &&
      photo.display_url === `/api/v1/media/${encodeURIComponent(photo.upload_id)}/display`)
  );
}

export function isProfileReference(
  value: unknown,
): value is Api['schemas']['ProfileReferenceResponse'] {
  if (typeof value !== 'object' || value === null) return false;
  return (
    'languages' in value &&
    Array.isArray(value.languages) &&
    value.languages.every(
      (item: unknown) =>
        typeof item === 'object' &&
        item !== null &&
        'code' in item &&
        typeof item.code === 'string' &&
        /^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$/.test(item.code) &&
        'label' in item &&
        typeof item.label === 'string' &&
        item.label.trim().length > 0,
    ) &&
    new Set(value.languages.map((item: Readonly<{ readonly code: string }>) => item.code)).size ===
      value.languages.length &&
    'max_languages' in value &&
    typeof value.max_languages === 'number' &&
    Number.isInteger(value.max_languages) &&
    value.max_languages > 0 &&
    'min_display_name_length' in value &&
    typeof value.min_display_name_length === 'number' &&
    Number.isInteger(value.min_display_name_length) &&
    value.min_display_name_length > 0 &&
    'max_display_name_length' in value &&
    typeof value.max_display_name_length === 'number' &&
    Number.isInteger(value.max_display_name_length) &&
    value.max_display_name_length >= value.min_display_name_length &&
    'university' in value &&
    typeof value.university === 'string' &&
    value.university.trim().length > 0
  );
}
