import type { Api } from '../../api.generated';

export const identity = {
  account_id: '10000000-0000-0000-0000-000000000001',
  account_status: 'active',
  membership_status: 'verified',
  verified_at: '2026-11-08T10:00:00Z',
  registration: null,
  email_challenge_id: null,
  csrf_token: 'discovery-test-csrf',
  capabilities: {
    can_begin_onboarding: true,
    can_use_student_features: true,
    can_verify_student_email: false,
  },
} as const satisfies Api['schemas']['IdentityResponse'];
export const card = {
  id: '10000000-0000-0000-0000-000000000002',
  display_name: 'Aiko Tanaka',
  about: 'I like drawing tables before writing a query.',
  version: 1,
  photo: {
    display_url: '/api/v1/people/10000000-0000-0000-0000-000000000002/photo/1',
    version: 1,
  },
  own_pass: {
    person_id: '10000000-0000-0000-0000-000000000002',
    passed: false,
    version: 0,
    changed_at: null,
  },
  relevance: {
    reason: 'can_help',
    same_topic: true,
    subject_id: '10000000-0000-0000-0000-000000000003',
    subject_label: 'SQL',
    topic: 'JOINs',
    reciprocal_subject_id: '10000000-0000-0000-0000-000000000004',
    reciprocal_subject_label: 'Calculus',
  },
} as const satisfies Api['schemas']['DiscoveryCardResponse'];
export const deck = {
  context: {
    mode: 'find_help',
    goal_id: '10000000-0000-0000-0000-000000000005',
    goal_version: 1,
  },
  people: [card],
  next_cursor: null,
  empty_reason: null,
  undo_pass: null,
} as const satisfies Api['schemas']['DiscoveryPageResponse'];
export const pass = {
  ...card.own_pass,
  passed: true,
  version: 1,
  changed_at: '2026-11-08T10:01:00Z',
} as const satisfies Api['schemas']['PrivatePassResponse'];

// Synthetic JPEG for HTTP-boundary tests; never production candidate data.
