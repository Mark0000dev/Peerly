import type { Api } from '../../api.generated';

export const actor = {
  account_id: '00000000-0000-0000-0000-000000000001',
  account_status: 'active',
  membership_status: 'verified',
  verified_at: '2026-11-07T12:00:00Z',
  registration: null,
  email_challenge_id: null,
  csrf_token: 'person-fixture-csrf',
  capabilities: {
    can_begin_onboarding: true,
    can_use_student_features: true,
    can_verify_student_email: false,
  },
} as const satisfies Api['schemas']['IdentityResponse'];
export const person = {
  id: '00000000-0000-0000-0000-000000000002',
  version: 1,
  access_context_id: '00000000-0000-0000-0000-000000000003',
  display_name: 'Aiko Tanaka',
  about: 'I like drawing tables on paper before writing a query.',
  programme: 'Software Engineering',
  year_label: 'Year 3',
  languages: ['en', 'ja'],
  photo: { display_url: '/api/v1/people/00000000-0000-0000-0000-000000000002/photo/1', version: 1 },
  own_block: {
    person_id: '00000000-0000-0000-0000-000000000002',
    blocked: false,
    version: 0,
    changed_at: null,
  },
  goal: {
    id: '00000000-0000-0000-0000-000000000004',
    version: 1,
    subject: { kind: 'canonical', id: '00000000-0000-0000-0000-000000000005', label: 'Calculus' },
    topic: 'Integration by parts',
    context: 'Practice examples together',
    shared_learning: true,
    created_at: '2026-11-07T12:00:00Z',
    updated_at: '2026-11-07T12:00:00Z',
    completed_at: null,
  },
  help_subjects: {
    version: 1,
    saved_at: '2026-11-07T12:00:00Z',
    subjects: [
      {
        subject_id: '00000000-0000-0000-0000-000000000006',
        label: 'SQL',
        topic_note: 'JOINs and subqueries',
      },
      { subject_id: '00000000-0000-0000-0000-000000000007', label: 'Python', topic_note: null },
    ],
  },
} as const satisfies Api['schemas']['PublicProfileResponse'];
export const blocked = {
  ...person.own_block,
  blocked: true,
  version: 1,
  changed_at: '2026-11-07T12:01:00Z',
} as const;
export const receipt = {
  id: '00000000-0000-0000-0000-000000000008',
  kind: 'profile',
  context_id: person.access_context_id,
  submitted_at: '2026-11-07T12:02:00Z',
} as const satisfies Api['schemas']['ProfileReportReceipt'];
