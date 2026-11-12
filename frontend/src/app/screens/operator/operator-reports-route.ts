import type { ParamMap } from '@angular/router';
import { instant, uuid } from './operator-contract';
import { eventKinds, reportCategories } from './operator-reports-contract';
import type { EventFilters, ReportFilters } from './operator-reports-contract';

export const reportFields = [
  { key: 'reporter_id', label: 'Reporter ID', hint: 'Stored account UUID' },
  { key: 'target_id', label: 'Target ID', hint: 'Stored account UUID' },
  { key: 'context_id', label: 'Disclosure context ID', hint: 'Stored context UUID' },
  { key: 'submitted_from', label: 'Submitted from', hint: 'ISO time with timezone, inclusive' },
  { key: 'submitted_before', label: 'Submitted before', hint: 'ISO time with timezone, exclusive' },
] as const;
export const eventFields = [
  { key: 'subject_account_id', label: 'Subject account ID', hint: 'Stored account UUID' },
  { key: 'http_request_id', label: 'HTTP request ID', hint: 'Stored request UUID' },
  { key: 'action_id', label: 'Action ID', hint: 'Stored action UUID' },
  { key: 'trace_id', label: 'Trace ID', hint: '32 lowercase hexadecimal characters' },
  { key: 'occurred_from', label: 'Occurred from', hint: 'ISO time with timezone, inclusive' },
  { key: 'occurred_before', label: 'Occurred before', hint: 'ISO time with timezone, exclusive' },
] as const;
function dates(from: string | null, before: string | null): string | null {
  if ((from !== null && !instant(from)) || (before !== null && !instant(before)))
    return 'Dates need a valid ISO time with timezone.';
  return from !== null && before !== null && Date.parse(from) >= Date.parse(before)
    ? 'Before must be later than From.'
    : null;
}
function cursorError(cursor: string | null): string | null {
  return cursor !== null && (cursor.length === 0 || cursor.length > 1024)
    ? 'The page cursor is invalid. Return to the first page.'
    : null;
}
export function reportRoute(params: Readonly<ParamMap>) {
  const category = params.get('category');
  const validCategory = reportCategories.find((value) => value === category) ?? null;
  const filters: ReportFilters = {
    reporter_id: params.get('reporter_id'),
    target_id: params.get('target_id'),
    context_id: params.get('context_id'),
    category: validCategory,
    submitted_from: params.get('submitted_from'),
    submitted_before: params.get('submitted_before'),
    cursor: params.get('reports_cursor'),
  };
  const reportId = params.get('report');
  const error = [filters.reporter_id, filters.target_id, filters.context_id, reportId].some(
    (value) => value !== null && value !== undefined && !uuid(value),
  )
    ? 'Report, account and context IDs must be UUIDs.'
    : category !== null && validCategory === null
      ? 'Choose a stored report category.'
      : (dates(filters.submitted_from ?? null, filters.submitted_before ?? null) ??
        cursorError(filters.cursor ?? null));
  return { filters, reportId, error };
}
export function eventRoute(params: Readonly<ParamMap>) {
  const kind = params.get('event_kind');
  const validKind = eventKinds.find((value) => value === kind) ?? null;
  const filters: EventFilters = {
    subject_account_id: params.get('event_subject_account_id'),
    http_request_id: params.get('event_http_request_id'),
    action_id: params.get('event_action_id'),
    trace_id: params.get('event_trace_id'),
    kind: validKind,
    occurred_from: params.get('event_occurred_from'),
    occurred_before: params.get('event_occurred_before'),
    cursor: params.get('events_cursor'),
  };
  const eventId = params.get('event');
  const auditId = params.get('audit');
  const error = [
    filters.subject_account_id,
    filters.http_request_id,
    filters.action_id,
    eventId,
    auditId,
  ].some((value) => value !== null && value !== undefined && !uuid(value))
    ? 'Event, audit, account, request and action IDs must be UUIDs.'
    : kind !== null && validKind === null
      ? 'Choose a stored event kind.'
      : filters.trace_id !== null &&
          filters.trace_id !== undefined &&
          !/^[0-9a-f]{32}$/.test(filters.trace_id)
        ? 'Trace ID must contain 32 lowercase hexadecimal characters.'
        : (dates(filters.occurred_from ?? null, filters.occurred_before ?? null) ??
          cursorError(filters.cursor ?? null));
  return { filters, eventId, auditId, opened: params.get('timeline') === '1', error };
}
