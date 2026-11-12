import type { Api } from '../../api.generated';

export const verifiedActor = {
  account_id: '00000000-0000-0000-0000-000000000001',
  account_status: 'active',
  membership_status: 'verified',
  verified_at: '2026-11-07T12:00:00Z',
  registration: null,
  email_challenge_id: null,
  csrf_token: 'fixture-csrf',
  capabilities: {
    can_verify_student_email: true,
    can_begin_onboarding: true,
    can_use_student_features: false,
  },
} as const satisfies Api['schemas']['IdentityResponse'];
