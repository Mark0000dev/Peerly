import type { Api } from '../../api.generated';

export const actor = {
  account_id: '00000000-0000-0000-0000-000000000001',
  account_status: 'active',
  membership_status: 'unverified',
  verified_at: null,
  registration: null,
  email_challenge_id: null,
  csrf_token: 'fixture-csrf',
  capabilities: {
    can_verify_student_email: true,
    can_begin_onboarding: false,
    can_use_student_features: false,
  },
} as const satisfies Api['schemas']['IdentityResponse'];
export const verifiedActor = {
  ...actor,
  membership_status: 'verified',
  verified_at: '2026-11-07T12:00:00Z',
  capabilities: { ...actor.capabilities, can_begin_onboarding: true },
} as const satisfies Api['schemas']['IdentityResponse'];
export const pending = {
  ...actor,
  email_challenge_id: '00000000-0000-0000-0000-000000000002',
} as const;
export const challenge = {
  id: pending.email_challenge_id,
  email: 'student@mail.apu.edu.my',
  state: 'active',
  delivery: 'sent',
  verification_outcome: null,
  expires_at: '2026-11-07T12:10:00Z',
  resend_at: '2026-11-07T12:00:30Z',
  attempts_remaining: 5,
  can_verify: true,
  can_resend: false,
} as const satisfies Api['schemas']['ChallengeStatusResponse'];
