import type { Api } from '../../../../api.generated';
import { instant, uuid } from '../../operator-contract';

type Review = Api['schemas']['ReportReviewResponse'];
type History = Api['schemas']['ReportReviewHistoryResponse'];
const maximumVersion = 2147483647;
function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function version(value: unknown, minimum = 0): value is number {
  return (
    typeof value === 'number' &&
    Number.isSafeInteger(value) &&
    value >= minimum &&
    value <= maximumVersion
  );
}
function nullableUuid(value: unknown): boolean {
  return value === null || uuid(value);
}
function nullableHex(value: unknown, length: number): boolean {
  return (
    value === null ||
    (typeof value === 'string' && value.length === length && /^[0-9a-f]+$/u.test(value))
  );
}
export function isReviewAction(value: unknown): value is Api['schemas']['ReportReviewAction'] {
  return value === 'dismiss' || value === 'escalate';
}
export function reasonProblem(value: string): string | null {
  const normalized = value.trim();
  if (normalized.length === 0) return 'Add a documented reason.';
  if (Array.from(value).length > 1000) return 'Keep the reason within 1,000 characters.';
  if (/[\p{Cc}\p{Cs}]/u.test(normalized.replace(/[\n\t]/gu, '')))
    return 'Use plain text without unsupported control characters.';
  return null;
}
export function cursorProblem(value: string | null): string | null {
  return value !== null && (value.length === 0 || value.length > 1024)
    ? 'The review-history cursor is invalid. Return to the first page.'
    : null;
}
export function isReview(value: unknown): value is Review {
  return (
    record(value) &&
    uuid(value['id']) &&
    uuid(value['report_id']) &&
    version(value['version'], 1) &&
    value['previous_version'] === (value['version'] === 1 ? null : value['version'] - 1) &&
    isReviewAction(value['action']) &&
    typeof value['reason'] === 'string' &&
    reasonProblem(value['reason']) === null &&
    uuid(value['operator_id']) &&
    version(value['operator_access_version'], 1) &&
    uuid(value['actor_session_id']) &&
    instant(value['reviewed_at']) &&
    uuid(value['event_id']) &&
    nullableUuid(value['http_request_id']) &&
    nullableUuid(value['action_id']) &&
    nullableHex(value['trace_id'], 32) &&
    nullableHex(value['span_id'], 16)
  );
}
export function isReviewHistory(value: unknown): value is History {
  if (
    !record(value) ||
    !uuid(value['report_id']) ||
    (value['kind'] !== 'profile' && value['kind'] !== 'message_image') ||
    !uuid(value['reporter_id']) ||
    !uuid(value['target_id']) ||
    !uuid(value['context_id']) ||
    !version(value['anchor_version']) ||
    (value['current'] !== null && !isReview(value['current'])) ||
    !Array.isArray(value['revisions']) ||
    value['revisions'].length > 50 ||
    !value['revisions'].every(isReview) ||
    (value['next_cursor'] !== null &&
      (typeof value['next_cursor'] !== 'string' || cursorProblem(value['next_cursor']) !== null))
  )
    return false;
  const current = value['current'];
  const rows: readonly Review[] = value['revisions'];
  const anchor = value['anchor_version'];
  return (
    (current === null
      ? anchor === 0
      : current.report_id === value['report_id'] && current.version >= anchor) &&
    rows.every(
      (row, index) =>
        row.report_id === value['report_id'] &&
        row.version <= anchor &&
        (index === 0 || row.version < (rows[index - 1]?.version ?? 0)) &&
        (row.version !== current?.version || row.id === current.id),
    ) &&
    new Set(rows.map((row) => row.id)).size === rows.length &&
    (value['next_cursor'] === null || rows.length > 0)
  );
}
