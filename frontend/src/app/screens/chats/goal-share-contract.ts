import type { HttpClient } from '@angular/common/http';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { readJson } from '../../api-http';
import { isContext } from './chats-contract';

function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function nullableText(value: unknown): value is string | null {
  return typeof value === 'string' || value === null;
}
function integer(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}
function date(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}
function subject(
  value: unknown,
): value is
  Api['schemas']['SharedCanonicalSubjectResponse'] | Api['schemas']['SharedCustomSubjectResponse'] {
  return (
    record(value) &&
    typeof value['label'] === 'string' &&
    ((typeof value['id'] === 'string' && (!('kind' in value) || value['kind'] === 'canonical')) ||
      (!('id' in value) && (!('kind' in value) || value['kind'] === 'custom')))
  );
}
function source(value: unknown): value is Api['schemas']['SharedGoalSourceResponse'] {
  return (
    record(value) &&
    typeof value['goal_id'] === 'string' &&
    typeof value['owner_id'] === 'string' &&
    integer(value['version']) &&
    value['version'] > 0 &&
    typeof value['shared_learning'] === 'boolean' &&
    nullableText(value['topic']) &&
    nullableText(value['context']) &&
    subject(value['subject']) &&
    date(value['goal_created_at']) &&
    date(value['goal_updated_at'])
  );
}
export function isShareReceipt(
  value: unknown,
): value is Api['schemas']['ConversationGoalShareReceiptResponse'] {
  return (
    record(value) &&
    typeof value['conversation_id'] === 'string' &&
    typeof value['owner_id'] === 'string' &&
    typeof value['share_id'] === 'string' &&
    integer(value['context_version']) &&
    value['context_version'] > 0 &&
    date(value['shared_at']) &&
    source(value['source']) &&
    value['source'].owner_id === value['owner_id']
  );
}
function entry(value: unknown): value is Api['schemas']['ConversationGoalShareEntryResponse'] {
  return (
    isShareReceipt(value) && 'can_complete' in value && typeof value.can_complete === 'boolean'
  );
}
export function isShares(
  value: unknown,
): value is Api['schemas']['ConversationGoalSharePageResponse'] {
  if (!record(value)) return false;
  const baseline = value['baseline'];
  return (
    integer(value['anchor_version']) &&
    integer(value['current_context_version']) &&
    record(baseline) &&
    typeof baseline['request_id'] === 'string' &&
    integer(baseline['accepted_request_version']) &&
    (!('context_version' in baseline) || baseline['context_version'] === 0) &&
    isContext(baseline['context']) &&
    typeof baseline['sender_goal_can_complete'] === 'boolean' &&
    typeof baseline['recipient_goal_can_complete'] === 'boolean' &&
    (value['latest'] === null || entry(value['latest'])) &&
    Array.isArray(value['history']) &&
    value['history'].every(entry) &&
    nullableText(value['next_cursor'])
  );
}
export function isOwnGoal(value: unknown): value is Api['schemas']['OwnGoalResponse'] {
  if (!record(value)) return false;
  const goal = value['goal'];
  return (
    goal === null ||
    (record(goal) &&
      typeof goal['id'] === 'string' &&
      integer(goal['version']) &&
      goal['version'] > 0 &&
      nullableText(goal['context']) &&
      nullableText(goal['topic']) &&
      typeof goal['shared_learning'] === 'boolean' &&
      subject(goal['subject']) &&
      date(goal['created_at']) &&
      date(goal['updated_at']) &&
      (goal['completed_at'] === null || date(goal['completed_at'])))
  );
}
export function sharesOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  conversationId: string,
  cursor: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actorId, 'chats', conversationId, 'goal-shares', cursor] as const,
    enabled: enabled && actorId !== null,
    retry: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/conversations/${encodeURIComponent(conversationId)}/goal-shares${cursor === null ? '' : `?cursor=${encodeURIComponent(cursor)}`}`,
        signal,
        (value): value is Api['schemas']['ConversationGoalSharePageResponse'] =>
          isShares(value) &&
          (value.latest === null || value.latest.conversation_id === conversationId) &&
          value.history.every((item) => item.conversation_id === conversationId),
      ),
  });
}
export function currentGoalOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actorId, 'chats', 'current-goal'] as const,
    enabled: enabled && actorId !== null,
    retry: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(http, '/api/v1/me/goal', signal, isOwnGoal),
  });
}
