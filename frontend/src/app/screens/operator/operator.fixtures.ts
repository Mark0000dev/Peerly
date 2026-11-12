import type { Api } from '../../api.generated';
export const operatorIdentity: Api['schemas']['IdentityResponse'] = {
  account_id: '00000000-0000-4000-8000-000000000001',
  account_status: 'active',
  membership_status: 'unverified',
  verified_at: null,
  csrf_token: 'operator-test',
  email_challenge_id: null,
  registration: null,
  capabilities: {
    can_begin_onboarding: true,
    can_use_student_features: false,
    can_verify_student_email: true,
  },
};
export const account: Api['schemas']['OperatorAccountResponse'] = {
  account_id: '00000000-0000-4000-8000-000000000002',
  created_at: '2026-10-12T02:09:00Z',
  banned_at: null,
  deleted_at: null,
  hidden_at: null,
  display_name: 'Maya Lee',
  profile_version: 1,
  google_link: {
    id: '00000000-0000-4000-8000-000000000003',
    issuer: 'https://accounts.google.com',
    subject: 'stored-google-subject',
    created_at: '2026-10-12T02:09:00Z',
  },
  membership: {
    email: 'maya@mail.apu.edu.my',
    verified_at: '2026-10-12T02:14:00Z',
    revoked_at: null,
  },
};
export const accounts: Api['schemas']['OperatorAccountsResponse'] = {
  accounts: [account],
  next_cursor: null,
};
export const detail: Api['schemas']['OperatorAccountDetailResponse'] = {
  account,
  profile: {
    display_name: 'Maya Lee',
    about: 'Comparing LEFT JOIN examples.',
    programme: 'Information Technology',
    year_label: 'Year 2',
    languages: ['English', 'Malay'],
    task: 'find_help',
    version: 1,
    saved_at: '2026-10-12T02:15:00Z',
  },
  goal: {
    id: '00000000-0000-4000-8000-000000000004',
    version: 2,
    subject: { id: '00000000-0000-4000-8000-000000000005', kind: 'canonical', label: 'Databases' },
    topic: 'SQL JOINs',
    context: 'Compare NULL rows.',
    shared_learning: true,
    created_at: '2026-10-12T02:15:00Z',
    updated_at: '2026-11-07T06:00:00Z',
    completed_at: null,
  },
  help_subjects: {
    version: 1,
    saved_at: '2026-10-12T02:15:00Z',
    subjects: [
      {
        subject_id: '00000000-0000-4000-8000-000000000006',
        label: 'Python',
        topic_note: 'Worked examples',
      },
    ],
  },
  photo: {
    version: 1,
    upload_id: '00000000-0000-4000-8000-000000000007',
    saved_at: '2026-10-12T02:15:00Z',
  },
  lifecycle: {
    completed_at: '2026-10-12T02:16:00Z',
    visibility_version: 1,
    hidden_at: null,
    changed_at: '2026-10-12T02:16:00Z',
  },
  exposure: {
    last_activity_at: '2026-11-07T06:00:00Z',
    confirmed_at: '2026-11-07T06:00:00Z',
    paused_at: null,
    inactivity_seconds: 2592000,
  },
  registration: {
    id: '00000000-0000-4000-8000-000000000008',
    context_id: '00000000-0000-4000-8000-000000000009',
    registered_at: '2026-10-12T02:16:00Z',
    surface: 'onboarding_completion',
    notice_text: 'By continuing you accept Terms and Privacy.',
    terms: {
      id: '00000000-0000-4000-8000-000000000010',
      kind: 'terms',
      version: '2026-10',
      published_at: '2026-10-01T00:00:00Z',
    },
    privacy: {
      id: '00000000-0000-4000-8000-000000000011',
      kind: 'privacy',
      version: '2026-10',
      published_at: '2026-10-01T00:00:00Z',
    },
  },
  links: [{ kind: 'google_identity', id: '00000000-0000-4000-8000-000000000003', version: null }],
};
export const nullableDetail: Api['schemas']['OperatorAccountDetailResponse'] = {
  account: {
    ...account,
    google_link: null,
    membership: null,
    profile_version: null,
    display_name: null,
  },
  profile: null,
  goal: null,
  help_subjects: null,
  photo: null,
  lifecycle: null,
  exposure: null,
  registration: null,
  links: [],
};
