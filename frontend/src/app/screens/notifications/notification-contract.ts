import type { Api } from '../../api.generated';

export function isNotificationMode(value: unknown): value is Api['schemas']['NotificationMode'] {
  return value === 'messages_and_requests' || value === 'all_updates';
}
export function isPreference(value: unknown): value is Api['schemas']['PreferenceResponse'] {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('mode' in value) ||
    !isNotificationMode(value.mode) ||
    !('version' in value) ||
    typeof value.version !== 'number' ||
    !Number.isSafeInteger(value.version) ||
    value.version < 0 ||
    !('changed_at' in value)
  )
    return false;
  return value.version === 0
    ? value.changed_at === null
    : typeof value.changed_at === 'string' && Number.isFinite(Date.parse(value.changed_at));
}
