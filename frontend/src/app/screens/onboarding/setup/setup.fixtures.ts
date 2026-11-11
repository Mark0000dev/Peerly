import type { Api } from '../../../api.generated';

export const visibility = {
  hidden: false,
  version: 1,
  hidden_at: null,
  changed_at: '2026-11-07T12:00:00Z',
  completed_at: '2026-11-07T12:00:00Z',
} as const satisfies Api['schemas']['ProfileVisibilityResponse'];
export const ready = {
  registered: false,
  setup_complete: false,
  setup_requirements: [],
  restore_requirements: [],
  visibility: null,
  discovery_exposure: null,
  capabilities: {
    can_access_existing_chats: false,
    can_complete_registration: true,
    can_complete_setup: false,
    can_discover: false,
    can_hide_profile: false,
    can_make_new_contacts: false,
    can_manage_profile: true,
    can_restore_profile: false,
  },
} as const satisfies Api['schemas']['OnboardingStatusResponse'];
export const complete = {
  ...ready,
  registered: true,
  setup_complete: true,
  visibility,
  discovery_exposure: { paused: false, can_confirm: false, requirements: [] },
  capabilities: {
    ...ready.capabilities,
    can_complete_registration: false,
    can_discover: true,
    can_hide_profile: true,
    can_make_new_contacts: true,
    can_access_existing_chats: true,
  },
} as const satisfies Api['schemas']['OnboardingStatusResponse'];
export const context = {
  id: 'context-1',
  expires_at: '2026-11-07T13:00:00Z',
  notice_text: 'By continuing, you agree to the Terms of Use and Privacy Policy.',
  surface: 'onboarding_completion',
  terms: { id: 'terms-1', version: '1', published_at: '2026-11-07T12:00:00Z', kind: 'terms' },
  privacy: { id: 'privacy-1', version: '1', published_at: '2026-11-07T12:00:00Z', kind: 'privacy' },
} as const satisfies Api['schemas']['RegistrationContextResponse'];
export const receipt = {
  id: 'receipt-1',
  context_id: context.id,
  registered_at: '2026-11-07T12:10:00Z',
  notice_text: context.notice_text,
  surface: context.surface,
  terms: context.terms,
  privacy: context.privacy,
} as const satisfies Api['schemas']['RegistrationReceiptResponse'];
