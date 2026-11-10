import type { Api } from '../../api.generated';
export const notificationActorFixture: Api['schemas']['IdentityResponse'] = {
  account_id: '00000000-0000-4000-8000-000000000120',
  account_status: 'active',
  membership_status: 'verified',
  verified_at: '2026-11-09T08:00:00Z',
  csrf_token: 'notification-csrf',
  email_challenge_id: null,
  registration: null,
  capabilities: {
    can_begin_onboarding: true,
    can_use_student_features: false,
    can_verify_student_email: false,
  },
};
export const defaultPreference: Api['schemas']['PreferenceResponse'] = {
  mode: 'messages_and_requests',
  version: 0,
  changed_at: null,
};
export const savedPreference: Api['schemas']['PreferenceResponse'] = {
  mode: 'all_updates',
  version: 1,
  changed_at: '2026-11-09T08:00:00Z',
};
