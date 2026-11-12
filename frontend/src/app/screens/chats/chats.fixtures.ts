import type { Api } from '../../api.generated';
export const identity: Api['schemas']['IdentityResponse'] = {
  account_id: '00000000-0000-4000-8000-000000000001',
  account_status: 'active',
  membership_status: 'verified',
  verified_at: '2026-11-07T00:00:00Z',
  csrf_token: 'chat-test-csrf',
  email_challenge_id: null,
  registration: null,
  capabilities: {
    can_begin_onboarding: false,
    can_use_student_features: true,
    can_verify_student_email: false,
  },
};
export const peer: Api['schemas']['ChatParticipantResponse'] = {
  person_id: '00000000-0000-4000-8000-000000000002',
  display_name: 'Maya Lim',
  photo_version: null,
  state: 'available',
};
export const context: Api['schemas']['AcademicContextResponse'] = {
  mode: 'find_help',
  sender_goal: {
    goal_id: '00000000-0000-4000-8000-000000000010',
    owner_id: identity.account_id,
    shared_learning: false,
    subject_id: '00000000-0000-4000-8000-000000000011',
    subject_label: 'Databases',
    topic: 'SQL JOINs',
    context: 'Compare LEFT JOIN examples',
    version: 1,
  },
  recipient_help: {
    owner_id: peer.person_id,
    subject_id: '00000000-0000-4000-8000-000000000011',
    subject_label: 'Databases',
    topic_note: 'Worked examples',
    version: 1,
  },
  recipient_goal: null,
  sender_help: null,
};
export const message = {
  author_id: peer.person_id,
  client_message_id: '00000000-0000-4000-8000-000000000030',
  conversation_id: '00000000-0000-4000-8000-000000000020',
  message_id: '00000000-0000-4000-8000-000000000031',
  sent_at: '2026-11-08T06:12:00Z',
  sequence: 1,
  text: 'Try moving the condition into ON.',
  image_id: null,
} as const satisfies Api['schemas']['MessageResponse'];
export const conversation: Api['schemas']['ConversationDetailsResponse'] = {
  conversation_id: message.conversation_id,
  request_id: '00000000-0000-4000-8000-000000000021',
  accepted_at: '2026-11-07T06:00:00Z',
  accepted_request_version: 2,
  can_send: true,
  last_confirmed_sequence: 1,
  original_context: context,
  peer,
  read_position: null,
  unread_count: 1,
};
export const summary: Api['schemas']['ConversationSummaryResponse'] = {
  accepted_at: conversation.accepted_at,
  activity_at: message.sent_at,
  can_send: true,
  conversation_id: conversation.conversation_id,
  last_message: message,
  original_context: context,
  peer,
  request_id: conversation.request_id,
  unread_count: 1,
};
export const page: Api['schemas']['ConversationListResponse'] = {
  conversations: [summary],
  next_cursor: null,
};
export const history: Api['schemas']['MessageHistoryResponse'] = {
  anchor_sequence: 1,
  messages: [message],
  next_cursor: null,
};

export const currentGoal: Api['schemas']['GoalResponse'] = {
  id: '00000000-0000-4000-8000-000000000050',
  version: 2,
  subject: { kind: 'canonical', id: '00000000-0000-4000-8000-000000000011', label: 'Databases' },
  topic: 'Transactions',
  context: 'Compare transaction isolation examples',
  shared_learning: true,
  created_at: '2026-11-07T06:00:00Z',
  updated_at: '2026-11-08T06:00:00Z',
  completed_at: null,
};
export const shares: Api['schemas']['ConversationGoalSharePageResponse'] = {
  anchor_version: 0,
  current_context_version: 0,
  baseline: {
    accepted_request_version: 2,
    context,
    context_version: 0,
    recipient_goal_can_complete: false,
    sender_goal_can_complete: false,
    request_id: conversation.request_id,
  },
  history: [],
  latest: null,
  next_cursor: null,
};
export const shareReceipt: Api['schemas']['ConversationGoalShareReceiptResponse'] = {
  conversation_id: conversation.conversation_id,
  context_version: 1,
  owner_id: identity.account_id,
  share_id: '00000000-0000-4000-8000-000000000051',
  shared_at: '2026-11-08T06:13:00Z',
  source: {
    goal_id: currentGoal.id,
    owner_id: identity.account_id,
    version: currentGoal.version,
    subject: currentGoal.subject,
    topic: currentGoal.topic,
    context: currentGoal.context,
    shared_learning: currentGoal.shared_learning,
    goal_created_at: currentGoal.created_at,
    goal_updated_at: currentGoal.updated_at,
  },
};
