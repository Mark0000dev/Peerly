import type { HttpClient } from '@angular/common/http';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { readJson } from '../../api-http';
import { instant, uuid } from './operator-contract';

type ReportParameters = Api['paths']['/api/v1/operator/reports']['get']['parameters'];
export type ReportFilters = {
  readonly [
    K in keyof ReportParameters as K extends `query:${infer Name}` ? Name : never
  ]: ReportParameters[K];
};
type EventParameters = Api['paths']['/api/v1/operator/events']['get']['parameters'];
export type EventFilters = {
  readonly [
    K in keyof EventParameters as K extends `query:${infer Name}` ? Name : never
  ]: EventParameters[K];
};

export const reportCategories = [
  'impersonation',
  'harassment',
  'inappropriate_content',
  'spam',
  'other',
] as const satisfies readonly Api['schemas']['ReportCategory'][];

export const eventKinds = [
  'goal.saved',
  'goal.completed',
  'profile.saved',
  'help.saved',
  'photo.published',
  'profile.ready',
  'profile.hidden',
  'profile.restored',
  'auth.email_confirmed',
  'ai_job.completed',
  'discovery.exposure_confirmed',
  'report.created',
  'block.changed',
  'discovery.pass_changed',
  'request.changed',
  'request.view_acknowledged',
  'message.confirmed',
  'message.cancelled',
  'conversation.read_acknowledged',
  'conversation.goal_shared',
  'operator.inspected',
  'study.reported',
  'feedback.saved',
  'study.prompt_offered',
  'account.lifecycle_changed',
] as const satisfies readonly Api['schemas']['OperatorEventKind'][];

const sourceKinds = [
  'account',
  'profile_revision',
  'help_revision',
  'photo_revision',
  'visibility_revision',
  'goal_revision',
  'subject',
  'ai_job',
  'profile_report',
  'block_revision',
  'private_pass_revision',
  'request_revision',
  'request_view_ack',
  'message_operation',
  'conversation_read',
  'goal_share',
  'operator_audit',
  'study_outcome',
  'feedback_revision',
  'study_prompt',
  'account_lifecycle_revision',
] as const satisfies readonly Api['schemas']['OperatorSourceKind'][];

const operatorActions = [
  'search_accounts',
  'search_events',
  'search_reports',
  'read_report',
  'read_media',
  'read_event',
  'read_audit',
  'read_account',
  'read_conversation_messages',
] as const satisfies readonly Api['schemas']['OperatorAction'][];

const resourceKinds = [
  'account',
  'conversation',
  'message',
  'event',
  'audit',
  'report',
  'profile_media',
] as const satisfies readonly Api['schemas']['OperatorResourceKind'][];

const aiKinds = [
  'clarify_goal',
  'suggest_subject',
  'assess_photo',
  'triage_report',
] as const satisfies readonly Api['schemas']['AiKind'][];

const aiFailures = [
  'transient',
  'invalid_output',
  'invalid_input',
  'timeout',
  'auth_unavailable',
  'rate_limited',
  'account_unavailable',
  'stale_source',
  'executor_lost',
] as const satisfies readonly Api['schemas']['Failure'][];

const jobStates = [
  'queued',
  'running',
  'succeeded',
  'failed',
  'cancelled',
  'expired',
] as const satisfies readonly Api['schemas']['JobState'][];

const requestStates = [
  'pending',
  'pending_decline',
  'declined',
  'withdrawn',
  'expired',
  'unavailable',
  'accepted',
] as const satisfies readonly Api['schemas']['RequestState'][];

function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function string(value: unknown): value is string {
  return typeof value === 'string';
}
function boolean(value: unknown): value is boolean {
  return typeof value === 'boolean';
}
function positive(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}
function nullable<T>(value: unknown, guard: (item: unknown) => item is T): value is T | null {
  return value === null || guard(value);
}
function member<T extends string>(value: unknown, values: readonly T[]): value is T {
  return values.some((item) => value === item);
}
function array<T>(
  value: unknown,
  guard: (item: unknown) => item is T,
  maximum: number,
): value is readonly T[] {
  return Array.isArray(value) && value.length <= maximum && value.every(guard);
}
function trace(value: unknown): value is string {
  return string(value) && /^[0-9a-f]{32}$/.test(value);
}
function span(value: unknown): value is string {
  return string(value) && /^[0-9a-f]{16}$/.test(value);
}
function origin(value: unknown): value is Api['schemas']['OperatorEventOriginResponse'] {
  return (
    record(value) &&
    nullable(value['http_request_id'], uuid) &&
    nullable(value['action_id'], uuid) &&
    nullable(value['trace_id'], trace) &&
    nullable(value['span_id'], span)
  );
}
function summary(value: unknown): value is Api['schemas']['OperatorReportSummaryResponse'] {
  return (
    record(value) &&
    uuid(value['id']) &&
    uuid(value['reporter_id']) &&
    uuid(value['target_id']) &&
    uuid(value['context_id']) &&
    (value['kind'] === 'profile' || value['kind'] === 'message_image') &&
    member(value['category'], reportCategories) &&
    instant(value['submitted_at']) &&
    boolean(value['has_comment'])
  );
}
export function isReports(value: unknown): value is Api['schemas']['OperatorReportsResponse'] {
  return (
    record(value) &&
    array(value['reports'], summary, 50) &&
    nullable(value['next_cursor'], string) &&
    instant(value['search_anchor_at'])
  );
}
function context(
  value: unknown,
): value is Api['schemas']['OperatorReportDetailResponse']['context'] {
  if (!(
    record(value) &&
    uuid(value['id']) &&
    uuid(value['reporter_id']) &&
    uuid(value['target_id']) &&
    instant(value['issued_at']) &&
    origin(value['origin'])
  ))
    return false;
  if (value['kind'] === 'profile')
    return (
      positive(value['profile_version']) &&
      positive(value['photo_version']) &&
      nullable(value['goal_id'], uuid) &&
      nullable(value['goal_version'], positive) &&
      nullable(value['help_version'], positive)
    );
  return (
    value['kind'] === 'message_image' &&
    uuid(value['conversation_id']) &&
    uuid(value['message_id']) &&
    uuid(value['client_message_id']) &&
    uuid(value['image_id']) &&
    positive(value['image_version']) &&
    uuid(value['image_attempt_id']) &&
    instant(value['message_sent_at'])
  );
}
function submission(value: unknown): value is Api['schemas']['OperatorReportSubmissionResponse'] {
  return (
    record(value) &&
    uuid(value['event_id']) &&
    uuid(value['report_id']) &&
    uuid(value['reporter_id']) &&
    instant(value['occurred_at']) &&
    origin(value['origin'])
  );
}
export function isReport(value: unknown): value is Api['schemas']['OperatorReportDetailResponse'] {
  if (
    !record(value) ||
    !summary(value['report']) ||
    !context(value['context']) ||
    !nullable(value['comment'], string) ||
    !nullable(value['submission'], submission)
  )
    return false;
  const report = value['report'];
  return (
    value['context'].kind === report.kind &&
    value['context'].id === report.context_id &&
    value['context'].reporter_id === report.reporter_id &&
    value['context'].target_id === report.target_id &&
    (value['submission'] === null ||
      (value['submission'].report_id === report.id &&
        value['submission'].reporter_id === report.reporter_id))
  );
}
function source(value: unknown): value is Api['schemas']['OperatorEventSourceResponse'] {
  return (
    record(value) &&
    member(value['kind'], sourceKinds) &&
    uuid(value['id']) &&
    nullable(value['owner_id'], uuid) &&
    nullable(value['version'], positive) &&
    nullable(value['conversation_id'], uuid) &&
    nullable(value['related_account_id'], uuid) &&
    nullable(value['operator_access_version'], positive)
  );
}
function facts(value: unknown): value is Api['schemas']['OperatorEventFactsResponse'] {
  return (
    record(value) &&
    nullable(value['topic_present'], boolean) &&
    nullable(value['shared_learning'], boolean) &&
    nullable(value['blocked'], boolean) &&
    nullable(value['passed'], boolean) &&
    (value['onboarding_task'] === null ||
      member(value['onboarding_task'], ['find_help', 'offer_help'])) &&
    (value['ai_kind'] === null || member(value['ai_kind'], aiKinds)) &&
    (value['ai_state'] === null || member(value['ai_state'], jobStates)) &&
    (value['ai_reason'] === null || member(value['ai_reason'], aiFailures)) &&
    (value['request_state'] === null || member(value['request_state'], requestStates)) &&
    (value['message_state'] === null ||
      member(value['message_state'], ['confirmed', 'cancelled'])) &&
    (value['study_answer'] === null ||
      member(value['study_answer'], ['yes', 'not_yet', 'did_not_work_out'])) &&
    (value['feedback_again'] === null || member(value['feedback_again'], ['yes', 'maybe', 'no'])) &&
    (value['operator_action'] === null || member(value['operator_action'], operatorActions)) &&
    (value['lifecycle_operation'] === null ||
      member(value['lifecycle_operation'], ['ban', 'unban', 'delete']))
  );
}
export function isEvent(value: unknown): value is Api['schemas']['OperatorEventResponse'] {
  return (
    record(value) &&
    uuid(value['id']) &&
    uuid(value['subject_account_id']) &&
    member(value['kind'], eventKinds) &&
    (value['schema_version'] === undefined || value['schema_version'] === 1) &&
    instant(value['occurred_at']) &&
    array(value['sources'], source, 2) &&
    value['sources'].length > 0 &&
    facts(value['facts']) &&
    origin(value['origin']) &&
    nullable(value['initiator_account_id'], uuid)
  );
}
export function isEvents(value: unknown): value is Api['schemas']['OperatorEventsResponse'] {
  return (
    record(value) &&
    array(value['events'], isEvent, 50) &&
    nullable(value['next_cursor'], string) &&
    instant(value['search_anchor_at']) &&
    (value['pagination'] === undefined ||
      value['pagination'] === 'anchored_search_not_commit_order')
  );
}
function result(value: unknown): value is Api['schemas']['OperatorAuditResultRefResponse'] {
  return record(value) && uuid(value['id']) && member(value['kind'], resourceKinds);
}
export function isAudit(value: unknown): value is Api['schemas']['OperatorAuditDetailResponse'] {
  return (
    record(value) &&
    uuid(value['id']) &&
    uuid(value['operator_id']) &&
    positive(value['operator_access_version']) &&
    instant(value['operator_access_changed_at']) &&
    instant(value['occurred_at']) &&
    member(value['action'], operatorActions) &&
    member(value['outcome'], ['search', 'read', 'not_found']) &&
    boolean(value['query_fingerprinted']) &&
    origin(value['origin']) &&
    (value['requested_kind'] === null || member(value['requested_kind'], resourceKinds)) &&
    nullable(value['requested_id'], uuid) &&
    nullable(value['requested_media_owner_id'], uuid) &&
    nullable(value['requested_media_attempt_id'], uuid) &&
    nullable(value['actual_source_upload_id'], uuid) &&
    (value['requested_media_kind'] === null ||
      member(value['requested_media_kind'], ['original', 'display'])) &&
    array(value['results'], result, 50)
  );
}
function query(filters: Readonly<Record<string, string | null | undefined>>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters))
    if (value !== null && value !== undefined) params.set(key, value);
  return params.toString();
}

export function reportsOptions(
  http: Readonly<HttpClient>,
  actor: string | null,
  filters: ReportFilters,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actor, 'operator', 'reports', filters] as const,
    enabled: enabled && actor !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(http, `/api/v1/operator/reports?${query(filters)}`, signal, isReports),
  });
}

export function eventsOptions(
  http: Readonly<HttpClient>,
  actor: string | null,
  filters: EventFilters,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actor, 'operator', 'events', filters] as const,
    enabled: enabled && actor !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(http, `/api/v1/operator/events?${query(filters)}`, signal, isEvents),
  });
}

export function reportOptions(
  http: Readonly<HttpClient>,
  actor: string | null,
  id: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actor, 'operator', 'reports', 'detail', id] as const,
    enabled: enabled && actor !== null && id !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/operator/reports/${encodeURIComponent(id ?? '')}`,
        signal,
        (value): value is Api['schemas']['OperatorReportDetailResponse'] =>
          isReport(value) && value.report.id === id,
      ),
  });
}

export function eventOptions(
  http: Readonly<HttpClient>,
  actor: string | null,
  id: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actor, 'operator', 'events', 'detail', id] as const,
    enabled: enabled && actor !== null && id !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/operator/events/${encodeURIComponent(id ?? '')}`,
        signal,
        (value): value is Api['schemas']['OperatorEventResponse'] =>
          isEvent(value) && value.id === id,
      ),
  });
}

export function auditOptions(
  http: Readonly<HttpClient>,
  actor: string | null,
  id: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actor, 'operator', 'audits', 'detail', id] as const,
    enabled: enabled && actor !== null && id !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/operator/audits/${encodeURIComponent(id ?? '')}`,
        signal,
        (value): value is Api['schemas']['OperatorAuditDetailResponse'] =>
          isAudit(value) && value.id === id,
      ),
  });
}
