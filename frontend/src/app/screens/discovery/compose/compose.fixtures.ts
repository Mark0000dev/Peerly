import type { Api } from '../../../api.generated';

export const actor: Api['schemas']['IdentityResponse'] = {
  account_id: '10000000-0000-4000-8000-000000000001',
  account_status: 'active',
  membership_status: 'verified',
  verified_at: '2026-11-08T00:00:00Z',
  csrf_token: 'compose-test-csrf',
  email_challenge_id: null,
  registration: null,
  capabilities: {
    can_begin_onboarding: false,
    can_verify_student_email: false,
    can_use_student_features: true,
  },
};
export const recipientId = '10000000-0000-4000-8000-000000000002';
const subjectId = '20000000-0000-4000-8000-000000000001';
function goal(ownerId: string, shared: boolean): Api['schemas']['GoalContextResponse'] {
  return {
    owner_id: ownerId,
    goal_id: `60000000${ownerId.slice(8)}`,
    version: 1,
    subject_id: subjectId,
    subject_label: 'SQL',
    topic: 'JOINs',
    context: 'Work through LEFT JOIN with NULLs.',
    shared_learning: shared,
  };
}
function help(ownerId: string): Api['schemas']['HelpContextResponse'] {
  return {
    owner_id: ownerId,
    version: 1,
    subject_id: subjectId,
    subject_label: 'SQL',
    topic_note: 'Relational queries',
  };
}
export function preview(
  mode: Api['schemas']['DiscoveryMode'] = 'find_help',
): Api['schemas']['PreviewResponse'] {
  return {
    preview_id: '30000000-0000-4000-8000-000000000001',
    created_at: '2026-11-08T00:00:00Z',
    outcome: 'preview',
    suggested_text: 'Could we work through SQL JOINs together?',
    checked_at: '2026-11-08T00:00:00Z',
    can_send: true,
    block_reason: null,
    cooldown_until: null,
    quota: {
      outgoing_pending: 0,
      successful_today: 0,
      outgoing_pending_limit: 5,
      daily_send_limit: 10,
      outgoing_pending_remaining: 5,
      daily_sends_remaining: 10,
      reset_at: '2026-11-08T16:00:00Z',
    },
    context:
      mode === 'find_help'
        ? {
            mode,
            sender_goal: goal(actor.account_id, false),
            recipient_help: help(recipientId),
            recipient_goal: null,
            sender_help: null,
          }
        : mode === 'offer_help'
          ? {
              mode,
              sender_goal: null,
              recipient_help: null,
              recipient_goal: goal(recipientId, false),
              sender_help: help(actor.account_id),
            }
          : {
              mode,
              sender_goal: goal(actor.account_id, true),
              recipient_goal: goal(recipientId, true),
              sender_help: null,
              recipient_help: null,
            },
  };
}
export const receipt: Api['schemas']['RequestMutationResponse'] = {
  request_id: '40000000-0000-4000-8000-000000000001',
  version: 1,
  outcome: 'sent',
  changed_at: '2026-11-08T00:00:00Z',
  conversation_id: null,
  undo_until: null,
};
export const connected: Api['schemas']['ConnectedResponse'] = {
  outcome: 'connected',
  request_id: receipt.request_id,
  conversation_id: '50000000-0000-4000-8000-000000000001',
};
