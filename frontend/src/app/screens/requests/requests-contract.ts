import type { HttpClient } from '@angular/common/http';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { readJson } from '../../api-http';

type Summary = Api['schemas']['RequestSummaryResponse'];
type Detail = Api['schemas']['RequestDetailResponse'];
type Page = Api['schemas']['RequestPageResponse'];
type Box = Api['schemas']['RequestBox'];
type View = Api['schemas']['RequestListView'];
export type RequestAction = 'accept' | 'decline' | 'undo-decline' | 'withdraw';

function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function text(value: unknown): value is string {
  return typeof value === 'string';
}
function nullableText(value: unknown): boolean {
  return value === null || text(value);
}
function integer(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}
function date(value: unknown): value is string {
  return text(value) && Number.isFinite(Date.parse(value));
}
function nullableDate(value: unknown): boolean {
  return value === null || date(value);
}
function mode(value: unknown): boolean {
  return value === 'find_help' || value === 'offer_help' || value === 'study_together';
}
export function requestBox(value: string | null): Box {
  return value === 'sent' ? 'sent' : 'received';
}
export function requestView(value: string | null, box: Box): View {
  if (value === 'history') return value;
  return value === 'recently_declined' && box === 'received' ? value : 'active';
}
function capabilities(value: unknown): boolean {
  return (
    record(value) &&
    ['accept', 'decline', 'undo_decline', 'withdraw', 'view_profile', 'open_conversation'].every(
      (key) => typeof value[key] === 'boolean',
    )
  );
}
function peer(value: unknown): boolean {
  return (
    record(value) &&
    text(value['person_id']) &&
    nullableText(value['display_name']) &&
    (value['photo_version'] === null || integer(value['photo_version'])) &&
    (value['state'] === 'public' ||
      value['state'] === 'unavailable' ||
      value['state'] === 'deleted') &&
    (value['state'] === 'public' ||
      (value['display_name'] === null && value['photo_version'] === null))
  );
}
export function isRequest(value: unknown): value is Summary {
  return (
    record(value) &&
    capabilities(value['capabilities']) &&
    peer(value['peer']) &&
    text(value['request_id']) &&
    integer(value['version']) &&
    value['version'] > 0 &&
    mode(value['mode']) &&
    text(value['subject_id']) &&
    text(value['subject_label']) &&
    text(value['text']) &&
    nullableText(value['note']) &&
    nullableText(value['topic']) &&
    date(value['sent_at']) &&
    date(value['expires_at']) &&
    date(value['observed_at']) &&
    nullableDate(value['undo_until']) &&
    nullableDate(value['cooldown_until']) &&
    nullableText(value['conversation_id']) &&
    typeof value['unread'] === 'boolean' &&
    text(value['state']) &&
    [
      'pending',
      'pending_decline',
      'accepted',
      'declined',
      'withdrawn',
      'expired',
      'closed',
    ].includes(value['state'])
  );
}
function goal(value: unknown): boolean {
  return (
    value === null ||
    (record(value) &&
      text(value['goal_id']) &&
      text(value['owner_id']) &&
      integer(value['version']) &&
      text(value['subject_id']) &&
      text(value['subject_label']) &&
      nullableText(value['topic']) &&
      nullableText(value['context']) &&
      typeof value['shared_learning'] === 'boolean')
  );
}
function help(value: unknown): boolean {
  return (
    value === null ||
    (record(value) &&
      text(value['owner_id']) &&
      integer(value['version']) &&
      text(value['subject_id']) &&
      text(value['subject_label']) &&
      nullableText(value['topic_note']))
  );
}
function context(value: unknown): value is Api['schemas']['AcademicContextResponse'] {
  return (
    record(value) &&
    mode(value['mode']) &&
    goal(value['sender_goal']) &&
    goal(value['recipient_goal']) &&
    help(value['sender_help']) &&
    help(value['recipient_help'])
  );
}
export function isRequestDetail(value: unknown): value is Detail {
  return (
    record(value) &&
    isRequest(value['request']) &&
    context(value['context']) &&
    value['context'].mode === value['request'].mode &&
    text(value['disclosure_id']) &&
    date(value['disclosed_at']) &&
    integer(value['disclosed_version']) &&
    value['disclosed_version'] > 0 &&
    text(value['text']) &&
    nullableText(value['note'])
  );
}
export function isRequestPage(value: unknown): value is Page {
  return (
    record(value) &&
    Array.isArray(value['requests']) &&
    value['requests'].length <= 20 &&
    value['requests'].every(isRequest) &&
    new Set(value['requests'].map((item) => item.request_id)).size === value['requests'].length &&
    nullableText(value['next_cursor']) &&
    date(value['observed_at']) &&
    [
      'daily_send_limit',
      'outgoing_pending',
      'outgoing_pending_limit',
      'successful_today',
      'unread_received',
    ].every((key) => integer(value[key]))
  );
}
export function isRequestReceipt(
  value: unknown,
): value is Api['schemas']['RequestMutationResponse'] {
  return (
    record(value) &&
    text(value['request_id']) &&
    integer(value['version']) &&
    value['version'] > 0 &&
    date(value['changed_at']) &&
    nullableDate(value['undo_until']) &&
    nullableText(value['conversation_id']) &&
    text(value['outcome']) &&
    [
      'sent',
      'existing_outgoing',
      'incoming',
      'accepted',
      'declined',
      'undo_decline',
      'withdrawn',
    ].includes(value['outcome'])
  );
}
export function isViewedReceipt(value: unknown): value is Api['schemas']['ViewedResponse'] {
  return (
    record(value) &&
    text(value['request_id']) &&
    text(value['disclosure_id']) &&
    text(value['acknowledgement_id']) &&
    date(value['acknowledged_at']) &&
    integer(value['stored_version']) &&
    value['stored_version'] > 0
  );
}
export function requestOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  box: Box,
  view: View,
  cursor: string | null,
  enabled: boolean,
) {
  const parameters = new URLSearchParams({ box, view });
  if (cursor !== null) parameters.set('cursor', cursor);
  return queryOptions({
    queryKey: ['account', actorId, 'requests', 'list', box, view, cursor] as const,
    enabled,
    retry: false,
    staleTime: 0,
    gcTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>): Promise<Page> =>
      readJson(http, `/api/v1/requests?${parameters.toString()}`, signal, isRequestPage),
  });
}
export function requestDetailOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  id: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actorId, 'requests', 'detail', id] as const,
    enabled: enabled && id !== null,
    retry: false,
    staleTime: 0,
    gcTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>): Promise<Detail> =>
      readJson(
        http,
        `/api/v1/requests/${encodeURIComponent(id ?? '')}`,
        signal,
        (value): value is Detail => isRequestDetail(value) && value.request.request_id === id,
      ),
  });
}
export function peerName(value: Summary): string {
  return value.peer.state === 'public' && value.peer.display_name !== null
    ? value.peer.display_name
    : value.peer.state === 'deleted'
      ? 'Deleted account'
      : 'Profile unavailable';
}
export function requestReason(value: Summary): string {
  switch (value.mode) {
    case 'find_help':
      return `Would like help with ${value.subject_label}`;
    case 'offer_help':
      return `Offers help with ${value.subject_label}`;
    case 'study_together':
      return `Would like to study ${value.subject_label} together`;
  }
}
export function undoRemaining(value: Summary, receivedAt: number, now: number): number {
  if (!value.capabilities.undo_decline || value.undo_until === null) return 0;
  return Math.max(
    0,
    Math.ceil(
      (Date.parse(value.undo_until) -
        Date.parse(value.observed_at) -
        Math.max(0, now - receivedAt)) /
        1000,
    ),
  );
}

export function sentWhen(value: Summary): string {
  const seconds = Math.max(0, (Date.parse(value.observed_at) - Date.parse(value.sent_at)) / 1000);
  if (seconds < 60) return 'Just now';
  if (seconds < 3600) return `${String(Math.floor(seconds / 60))} min ago`;
  if (seconds < 86400) return `${String(Math.floor(seconds / 3600))} h ago`;
  const days = Math.floor(seconds / 86400);
  return `${String(days)} ${days === 1 ? 'day' : 'days'} ago`;
}
export function expiresWhen(value: Summary): string {
  const days = Math.ceil((Date.parse(value.expires_at) - Date.parse(value.observed_at)) / 86400000);
  return days <= 0
    ? 'Check current availability'
    : `up to ${String(days)} more ${days === 1 ? 'day' : 'days'}`;
}
