import type { Api } from '../../api.generated';
import { account, operatorIdentity } from './operator.fixtures';

export const reportId = 'a1111111-1111-4111-8111-111111111111';
export const submissionEventId = 'a5555555-5555-4555-8555-555555555555';
export const eventId = 'a2222222-2222-4222-8222-222222222222';
export const auditId = 'a3333333-3333-4333-8333-333333333333';
const contextId = 'a4444444-4444-4444-8444-444444444444';
export const absentOrigin = {
  http_request_id: null,
  action_id: null,
  trace_id: null,
  span_id: null,
} as const;
export const storedOrigin = {
  http_request_id: reportId,
  action_id: eventId,
  trace_id: '1234567890abcdef1234567890abcdef',
  span_id: '1234567890abcdef',
} as const;
const reportSummary = {
  kind: 'profile',
  id: reportId,
  reporter_id: operatorIdentity.account_id,
  target_id: account.account_id,
  context_id: contextId,
  category: 'harassment',
  has_comment: true,
  submitted_at: '2026-11-01T12:00:00Z',
} as const satisfies Api['schemas']['OperatorReportSummaryResponse'];
export const reportDetail = {
  report: reportSummary,
  comment: '<script>literal & retained</script>\nSecond line.',
  context: {
    kind: 'profile',
    id: contextId,
    reporter_id: reportSummary.reporter_id,
    target_id: reportSummary.target_id,
    profile_version: 1,
    photo_version: 1,
    goal_id: null,
    goal_version: null,
    help_version: 1,
    issued_at: '2026-11-01T11:59:00Z',
    origin: storedOrigin,
  },
  submission: {
    event_id: submissionEventId,
    report_id: reportId,
    reporter_id: reportSummary.reporter_id,
    occurred_at: reportSummary.submitted_at,
    origin: absentOrigin,
  },
} as const satisfies Api['schemas']['OperatorReportDetailResponse'];
export const reportPage = {
  reports: [reportSummary],
  next_cursor: 'report-next',
  search_anchor_at: reportSummary.submitted_at,
} as const satisfies Api['schemas']['OperatorReportsResponse'];
export const retainedEvent = {
  id: eventId,
  subject_account_id: operatorIdentity.account_id,
  kind: 'operator.inspected',
  schema_version: 1,
  occurred_at: reportSummary.submitted_at,
  initiator_account_id: null,
  origin: storedOrigin,
  sources: [
    {
      kind: 'operator_audit',
      id: auditId,
      owner_id: operatorIdentity.account_id,
      version: null,
      conversation_id: null,
      related_account_id: null,
      operator_access_version: 1,
    },
  ],
  facts: {
    topic_present: null,
    shared_learning: null,
    onboarding_task: null,
    ai_kind: null,
    ai_state: null,
    ai_reason: null,
    blocked: null,
    passed: null,
    request_state: null,
    message_state: null,
    study_answer: null,
    feedback_again: null,
    operator_action: 'read_report',
    lifecycle_operation: null,
  },
} as const satisfies Api['schemas']['OperatorEventResponse'];
export const eventPage = {
  events: [retainedEvent],
  next_cursor: 'event-next',
  search_anchor_at: reportSummary.submitted_at,
  pagination: 'anchored_search_not_commit_order',
} as const satisfies Api['schemas']['OperatorEventsResponse'];
export const retainedAudit = {
  id: auditId,
  operator_id: operatorIdentity.account_id,
  operator_access_version: 1,
  operator_access_changed_at: reportSummary.submitted_at,
  action: 'read_report',
  outcome: 'read',
  occurred_at: reportSummary.submitted_at,
  query_fingerprinted: false,
  origin: absentOrigin,
  requested_kind: 'report',
  requested_id: reportId,
  requested_media_owner_id: null,
  requested_media_attempt_id: null,
  requested_media_kind: null,
  actual_source_upload_id: null,
  actual_source_image_id: null,
  requested_chat_attempt_id: null,
  requested_chat_kind: null,
  requested_chat_owner_id: null,
  results: [{ kind: 'report', id: reportId }],
} as const satisfies Api['schemas']['OperatorAuditDetailResponse'];

export const submissionEvent = {
  ...retainedEvent,
  id: submissionEventId,
  kind: 'report.created',
  origin: absentOrigin,
  sources: [
    {
      kind: 'profile_report',
      id: reportId,
      owner_id: reportSummary.reporter_id,
      version: null,
      conversation_id: null,
      related_account_id: null,
      operator_access_version: null,
    },
  ],
  facts: { ...retainedEvent.facts, operator_action: null },
} as const satisfies Api['schemas']['OperatorEventResponse'];
