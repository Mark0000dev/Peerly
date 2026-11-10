import type { Api } from '../api.generated';

export function isPolicyReference(
  value: unknown,
): value is Api['schemas']['PolicyReferenceResponse'] {
  if (typeof value !== 'object' || value === null) return false;
  return (
    'id' in value &&
    typeof value.id === 'string' &&
    'version' in value &&
    typeof value.version === 'string' &&
    'published_at' in value &&
    typeof value.published_at === 'string' &&
    'kind' in value &&
    (value.kind === 'terms' || value.kind === 'privacy')
  );
}
