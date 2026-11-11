import type { Api } from '../../../api.generated';

export const supportActor: Api['schemas']['IdentityResponse'] = {
  account_id: '00000000-0000-4000-8000-000000000071',
  account_status: 'active',
  membership_status: 'unverified',
  verified_at: null,
  registration: null,
  email_challenge_id: null,
  csrf_token: 'synthetic-operator-support-csrf',
  capabilities: {
    can_begin_onboarding: false,
    can_use_student_features: false,
    can_verify_student_email: true,
  },
};
export const supportReceipt: Api['schemas']['SupportReceiptResponse'] = {
  case_id: '00000000-0000-4000-8000-000000000072',
  status: 'resolved',
  version: 3,
  received_at: '2026-11-01T04:00:00Z',
  changed_at: '2026-11-02T06:00:00Z',
};
export const supportCase: Api['schemas']['OperatorSupportResponse'] = {
  actor_id: null,
  topic: 'code_not_arriving',
  reply_address: 'synthetic-reply@example.test',
  message: 'Literal <b>message</b>\n  Original spacing',
  details: null,
  receipt: supportReceipt,
};
export const supportSummary: Api['schemas']['OperatorSupportSummaryResponse'] = {
  actor_id: supportCase.actor_id,
  case_id: supportReceipt.case_id,
  topic: supportCase.topic,
  status: supportReceipt.status,
  version: supportReceipt.version,
  received_at: supportReceipt.received_at,
  changed_at: supportReceipt.changed_at,
};
export const supportInbox: Api['schemas']['OperatorSupportInboxResponse'] = {
  cases: [supportSummary],
  next_cursor: null,
  metadata_anchor: '2026-11-02T04:00:00Z',
  status_semantics: 'current_at_each_request',
};
export const supportHistory: Api['schemas']['OperatorSupportHistoryResponse'] = {
  case_id: supportReceipt.case_id,
  anchor_version: 3,
  next_cursor: 'signed-support-history',
  revisions: [
    {
      version: 3,
      status: 'resolved',
      changed_at: '2026-11-02T06:00:00Z',
      changed_by_id: supportActor.account_id,
      operator_access_version: 2,
    },
    {
      version: 2,
      status: 'in_review',
      changed_at: '2026-11-02T05:00:00Z',
      changed_by_id: supportActor.account_id,
      operator_access_version: 1,
    },
    {
      version: 1,
      status: 'received',
      changed_at: supportReceipt.received_at,
      changed_by_id: null,
      operator_access_version: null,
    },
  ],
};
