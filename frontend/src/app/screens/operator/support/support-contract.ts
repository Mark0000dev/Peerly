import type { Api } from '../../../api.generated';
import { instant, uuid } from '../operator-contract';

type Parameters = Api['paths']['/api/v1/operator/cases']['get']['parameters'];
export type SupportFilters = {
  readonly [K in keyof Parameters as K extends `query:${infer Name}` ? Name : never]: Parameters[K];
};
export const supportStatuses: readonly Api['schemas']['SupportStatus'][] = [
  'received',
  'in_review',
  'resolved',
];
export const supportTopics: readonly Api['schemas']['SupportTopic'][] = [
  'cannot_sign_in',
  'email_not_accepted',
  'code_not_arriving',
  'email_already_in_use',
  'deleted_account',
  'other',
];
export const filterKeys = [
  'case_id',
  'actor_id',
  'topic',
  'status',
  'anonymous',
  'received_from',
  'received_before',
  'cursor',
] as const;
function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function keys(value: Readonly<Record<string, unknown>>, allowed: readonly string[]): boolean {
  return Object.keys(value).every((key) => allowed.includes(key));
}
function integer(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 1;
}
function cursor(value: unknown): value is string | null {
  return value === null || (typeof value === 'string' && value.length >= 1 && value.length <= 1024);
}
export function isSupportStatus(value: unknown): value is Api['schemas']['SupportStatus'] {
  return supportStatuses.some((status) => status === value);
}
export function isSupportTopic(value: unknown): value is Api['schemas']['SupportTopic'] {
  return supportTopics.some((topic) => topic === value);
}
export function statusText(value: Api['schemas']['SupportStatus']): string {
  switch (value) {
    case 'received':
      return 'Received';
    case 'in_review':
      return 'In review';
    case 'resolved':
      return 'Resolved';
  }
}
export function topicText(value: Api['schemas']['SupportTopic']): string {
  switch (value) {
    case 'cannot_sign_in':
      return 'Cannot sign in';
    case 'email_not_accepted':
      return 'APU email not accepted';
    case 'code_not_arriving':
      return 'Code not arriving';
    case 'email_already_in_use':
      return 'Email already in use';
    case 'deleted_account':
      return 'Deleted account';
    case 'other':
      return 'Other';
  }
}
export function isSupportReceipt(
  value: unknown,
): value is Api['schemas']['SupportReceiptResponse'] {
  return (
    record(value) &&
    keys(value, ['case_id', 'status', 'version', 'received_at', 'changed_at']) &&
    uuid(value['case_id']) &&
    isSupportStatus(value['status']) &&
    integer(value['version']) &&
    instant(value['received_at']) &&
    instant(value['changed_at']) &&
    Date.parse(value['changed_at']) >= Date.parse(value['received_at'])
  );
}
function summary(value: unknown): value is Api['schemas']['OperatorSupportSummaryResponse'] {
  return (
    record(value) &&
    keys(value, [
      'case_id',
      'actor_id',
      'topic',
      'received_at',
      'status',
      'version',
      'changed_at',
    ]) &&
    uuid(value['case_id']) &&
    (value['actor_id'] === null || uuid(value['actor_id'])) &&
    isSupportTopic(value['topic']) &&
    isSupportStatus(value['status']) &&
    integer(value['version']) &&
    instant(value['received_at']) &&
    instant(value['changed_at']) &&
    Date.parse(value['changed_at']) >= Date.parse(value['received_at'])
  );
}
export function isSupportInbox(
  value: unknown,
): value is Api['schemas']['OperatorSupportInboxResponse'] {
  if (
    !record(value) ||
    !keys(value, ['cases', 'metadata_anchor', 'next_cursor', 'status_semantics']) ||
    !instant(value['metadata_anchor']) ||
    !cursor(value['next_cursor']) ||
    (value['status_semantics'] !== undefined &&
      value['status_semantics'] !== 'current_at_each_request') ||
    !Array.isArray(value['cases']) ||
    value['cases'].length > 50
  )
    return false;
  const rows: readonly unknown[] = value['cases'];
  const anchor = value['metadata_anchor'];
  return (
    rows.every((row) => summary(row) && Date.parse(row.received_at) <= Date.parse(anchor)) &&
    new Set(rows.filter(summary).map((row) => row.case_id)).size === rows.length
  );
}
export function isSupportCase(value: unknown): value is Api['schemas']['OperatorSupportResponse'] {
  return (
    record(value) &&
    keys(value, ['actor_id', 'details', 'message', 'receipt', 'reply_address', 'topic']) &&
    (value['actor_id'] === null || uuid(value['actor_id'])) &&
    (value['details'] === undefined ||
      value['details'] === null ||
      typeof value['details'] === 'string') &&
    typeof value['message'] === 'string' &&
    typeof value['reply_address'] === 'string' &&
    isSupportTopic(value['topic']) &&
    isSupportReceipt(value['receipt'])
  );
}
function revision(
  value: unknown,
): value is Api['schemas']['OperatorSupportHistoryRevisionResponse'] {
  return (
    record(value) &&
    keys(value, ['changed_at', 'changed_by_id', 'operator_access_version', 'status', 'version']) &&
    instant(value['changed_at']) &&
    (value['changed_by_id'] === null || uuid(value['changed_by_id'])) &&
    (value['operator_access_version'] === null || integer(value['operator_access_version'])) &&
    isSupportStatus(value['status']) &&
    integer(value['version'])
  );
}
export function isSupportHistory(
  value: unknown,
): value is Api['schemas']['OperatorSupportHistoryResponse'] {
  if (
    !record(value) ||
    !keys(value, ['anchor_version', 'case_id', 'next_cursor', 'revisions']) ||
    !uuid(value['case_id']) ||
    !integer(value['anchor_version']) ||
    !cursor(value['next_cursor']) ||
    !Array.isArray(value['revisions']) ||
    value['revisions'].length > 50
  )
    return false;
  const rows: readonly unknown[] = value['revisions'];
  const anchor = value['anchor_version'];
  return rows.every((row, index) => {
    const previous = rows[index - 1];
    return (
      revision(row) &&
      row.version <= anchor &&
      (previous === undefined || (revision(previous) && previous.version > row.version))
    );
  });
}
