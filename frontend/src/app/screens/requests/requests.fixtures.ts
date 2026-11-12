import type { Api } from '../../api.generated';

export const identity: Api['schemas']['IdentityResponse'] = {
  account_id: '10000000-0000-4000-8000-000000000001',
  account_status: 'active',
  csrf_token: 'requests-test-csrf',
  membership_status: 'verified',
  verified_at: '2026-11-07T10:00:00Z',
  email_challenge_id: null,
  registration: null,
  capabilities: {
    can_begin_onboarding: false,
    can_verify_student_email: false,
    can_use_student_features: true,
  },
};
export const request: Api['schemas']['RequestSummaryResponse'] = {
  request_id: '20000000-0000-4000-8000-000000000001',
  version: 1,
  peer: {
    person_id: '10000000-0000-4000-8000-000000000002',
    display_name: 'Maya Lim',
    state: 'public',
    photo_version: 1,
  },
  mode: 'find_help',
  subject_id: '30000000-0000-4000-8000-000000000001',
  subject_label: 'SQL',
  topic: 'JOINs',
  text: 'Could we work through LEFT JOIN with NULLs together?',
  note: 'I have tried the lab example.',
  state: 'pending',
  unread: true,
  sent_at: '2026-11-07T10:00:00Z',
  expires_at: '2026-11-14T10:00:00Z',
  observed_at: '2026-11-08T00:00:00Z',
  undo_until: null,
  cooldown_until: null,
  conversation_id: null,
  capabilities: {
    accept: true,
    decline: true,
    undo_decline: false,
    withdraw: false,
    view_profile: true,
    open_conversation: false,
  },
};
export const page: Api['schemas']['RequestPageResponse'] = {
  requests: [request],
  observed_at: request.observed_at,
  next_cursor: null,
  unread_received: 1,
  outgoing_pending: 0,
  outgoing_pending_limit: 5,
  successful_today: 0,
  daily_send_limit: 10,
};
export const detail: Api['schemas']['RequestDetailResponse'] = {
  request,
  disclosure_id: '40000000-0000-4000-8000-000000000001',
  disclosed_at: request.observed_at,
  disclosed_version: request.version,
  text: request.text,
  note: request.note,
  context: {
    mode: 'find_help',
    sender_help: null,
    recipient_goal: null,
    sender_goal: {
      owner_id: request.peer.person_id,
      goal_id: '50000000-0000-4000-8000-000000000001',
      version: 1,
      subject_id: request.subject_id,
      subject_label: request.subject_label,
      topic: request.topic,
      context: 'INNER JOIN works; LEFT JOIN with NULLs is confusing.',
      shared_learning: false,
    },
    recipient_help: {
      owner_id: identity.account_id,
      version: 1,
      subject_id: request.subject_id,
      subject_label: request.subject_label,
      topic_note: 'Joins and relational queries',
    },
  },
};
export const receipt: Api['schemas']['RequestMutationResponse'] = {
  request_id: request.request_id,
  version: 2,
  outcome: 'accepted',
  changed_at: request.observed_at,
  undo_until: null,
  conversation_id: '60000000-0000-4000-8000-000000000001',
};
export const viewed: Api['schemas']['ViewedResponse'] = {
  request_id: request.request_id,
  disclosure_id: detail.disclosure_id,
  stored_version: 1,
  acknowledgement_id: '70000000-0000-4000-8000-000000000001',
  acknowledged_at: request.observed_at,
};
export const declined: Api['schemas']['RequestSummaryResponse'] = {
  ...request,
  state: 'pending_decline',
  version: 2,
  unread: false,
  undo_until: '2026-11-08T00:00:10Z',
  capabilities: { ...request.capabilities, accept: false, decline: false, undo_decline: true },
};
