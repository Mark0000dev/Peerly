import type { Api } from '../../../api.generated';
import { isPolicyReference } from '../../policy-reference';

function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function date(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}
function requirement(value: unknown): value is Api['schemas']['OnboardingRequirement'] {
  return (
    value === 'display_name' ||
    value === 'photo' ||
    value === 'study_goal' ||
    value === 'help_subjects'
  );
}
function restoreRequirement(value: unknown): value is Api['schemas']['RestoreRequirement'] {
  return value === 'photo' || value === 'study_context';
}
export function isVisibility(value: unknown): value is Api['schemas']['ProfileVisibilityResponse'] {
  return (
    record(value) &&
    typeof value['hidden'] === 'boolean' &&
    typeof value['version'] === 'number' &&
    Number.isSafeInteger(value['version']) &&
    value['version'] >= 1 &&
    date(value['changed_at']) &&
    date(value['completed_at']) &&
    (value['hidden_at'] === null || date(value['hidden_at']))
  );
}
function exposure(value: unknown): value is Api['schemas']['DiscoveryExposureResponse'] {
  return (
    record(value) &&
    typeof value['paused'] === 'boolean' &&
    typeof value['can_confirm'] === 'boolean' &&
    Array.isArray(value['requirements']) &&
    value['requirements'].every(restoreRequirement)
  );
}
export function isSetupStatus(value: unknown): value is Api['schemas']['OnboardingStatusResponse'] {
  if (!record(value) || !record(value['capabilities'])) return false;
  const caps = value['capabilities'];
  return (
    typeof value['registered'] === 'boolean' &&
    typeof value['setup_complete'] === 'boolean' &&
    Array.isArray(value['setup_requirements']) &&
    value['setup_requirements'].every(requirement) &&
    Array.isArray(value['restore_requirements']) &&
    value['restore_requirements'].every(restoreRequirement) &&
    (value['visibility'] === null || isVisibility(value['visibility'])) &&
    (value['discovery_exposure'] === null || exposure(value['discovery_exposure'])) &&
    typeof caps['can_access_existing_chats'] === 'boolean' &&
    typeof caps['can_complete_registration'] === 'boolean' &&
    typeof caps['can_complete_setup'] === 'boolean' &&
    typeof caps['can_discover'] === 'boolean' &&
    typeof caps['can_hide_profile'] === 'boolean' &&
    typeof caps['can_make_new_contacts'] === 'boolean' &&
    typeof caps['can_manage_profile'] === 'boolean' &&
    typeof caps['can_restore_profile'] === 'boolean'
  );
}
export function isRegistrationContext(
  value: unknown,
): value is Api['schemas']['RegistrationContextResponse'] {
  return (
    record(value) &&
    typeof value['id'] === 'string' &&
    value['id'].length > 0 &&
    date(value['expires_at']) &&
    typeof value['notice_text'] === 'string' &&
    value['notice_text'].length > 0 &&
    value['surface'] === 'onboarding_completion' &&
    isPolicyReference(value['terms']) &&
    value['terms'].kind === 'terms' &&
    isPolicyReference(value['privacy']) &&
    value['privacy'].kind === 'privacy'
  );
}
export function isRegistrationReceipt(
  value: unknown,
): value is Api['schemas']['RegistrationReceiptResponse'] {
  return (
    record(value) &&
    typeof value['id'] === 'string' &&
    typeof value['context_id'] === 'string' &&
    date(value['registered_at']) &&
    typeof value['notice_text'] === 'string' &&
    value['surface'] === 'onboarding_completion' &&
    isPolicyReference(value['terms']) &&
    value['terms'].kind === 'terms' &&
    isPolicyReference(value['privacy']) &&
    value['privacy'].kind === 'privacy'
  );
}
