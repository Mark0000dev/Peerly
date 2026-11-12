import type { Api } from '../../../api.generated';
export const supportActorFixture: Api['schemas']['IdentityResponse'] = {
  account_id: '00000000-0000-4000-8000-000000000110',
  account_status: 'active',
  membership_status: 'verified',
  verified_at: '2026-11-09T08:00:00Z',
  csrf_token: 'session-csrf',
  email_challenge_id: null,
  registration: null,
  capabilities: {
    can_begin_onboarding: true,
    can_use_student_features: false,
    can_verify_student_email: false,
  },
};
export const supportReceiptFixture: Api['schemas']['SupportReceiptResponse'] = {
  case_id: '00000000-0000-4000-8000-000000000101',
  status: 'received',
  version: 1,
  received_at: '2026-11-09T08:00:00Z',
  changed_at: '2026-11-09T08:00:00Z',
};
export function supportProofFixture(): Api['schemas']['SupportPreparationResponse'] {
  return { csrf_token: 'proof-csrf', expires_at: new Date(Date.now() + 60_000).toISOString() };
}
