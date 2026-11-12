import type { HttpClient } from '@angular/common/http';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { readJson } from '../../api-http';

type Peer = Api['schemas']['ChatParticipantResponse'];
type Context = Api['schemas']['AcademicContextResponse'];
type Message = Api['schemas']['MessageResponse'];

function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function nullableText(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}
function count(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}
function timestamp(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}
function goal(value: unknown): value is Api['schemas']['GoalContextResponse'] {
  return (
    record(value) &&
    typeof value['goal_id'] === 'string' &&
    typeof value['owner_id'] === 'string' &&
    typeof value['subject_id'] === 'string' &&
    typeof value['subject_label'] === 'string' &&
    nullableText(value['topic']) &&
    nullableText(value['context']) &&
    typeof value['shared_learning'] === 'boolean' &&
    count(value['version'])
  );
}
function help(value: unknown): value is Api['schemas']['HelpContextResponse'] {
  return (
    record(value) &&
    typeof value['owner_id'] === 'string' &&
    typeof value['subject_id'] === 'string' &&
    typeof value['subject_label'] === 'string' &&
    nullableText(value['topic_note']) &&
    count(value['version'])
  );
}
export function isContext(value: unknown): value is Context {
  if (!record(value)) return false;
  return (
    (value['sender_goal'] === null || goal(value['sender_goal'])) &&
    (value['recipient_goal'] === null || goal(value['recipient_goal'])) &&
    (value['sender_help'] === null || help(value['sender_help'])) &&
    (value['recipient_help'] === null || help(value['recipient_help'])) &&
    ((value['mode'] === 'find_help' &&
      goal(value['sender_goal']) &&
      help(value['recipient_help'])) ||
      (value['mode'] === 'offer_help' &&
        help(value['sender_help']) &&
        goal(value['recipient_goal'])) ||
      (value['mode'] === 'study_together' &&
        goal(value['sender_goal']) &&
        goal(value['recipient_goal'])))
  );
}
export function isPeer(value: unknown): value is Peer {
  return (
    record(value) &&
    typeof value['person_id'] === 'string' &&
    nullableText(value['display_name']) &&
    (value['photo_version'] === null || count(value['photo_version'])) &&
    (value['state'] === 'available' ||
      value['state'] === 'unavailable' ||
      value['state'] === 'deleted')
  );
}
function nullableImageId(value: unknown): value is string | null {
  return (
    value === null ||
    (typeof value === 'string' &&
      /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/iu.test(value))
  );
}
export function isMessage(value: unknown): value is Message {
  return (
    record(value) &&
    typeof value['author_id'] === 'string' &&
    typeof value['client_message_id'] === 'string' &&
    typeof value['conversation_id'] === 'string' &&
    typeof value['message_id'] === 'string' &&
    timestamp(value['sent_at']) &&
    count(value['sequence']) &&
    value['sequence'] > 0 &&
    nullableText(value['text']) &&
    nullableImageId(value['image_id']) &&
    (value['text'] !== null || value['image_id'] !== null)
  );
}
export function isReadPosition(
  value: unknown,
): value is Api['schemas']['ConversationReadPositionResponse'] {
  return (
    record(value) &&
    typeof value['conversation_id'] === 'string' &&
    count(value['through_sequence']) &&
    count(value['version']) &&
    timestamp(value['acknowledged_at'])
  );
}
function summary(value: unknown): value is Api['schemas']['ConversationSummaryResponse'] {
  return (
    record(value) &&
    typeof value['conversation_id'] === 'string' &&
    typeof value['request_id'] === 'string' &&
    timestamp(value['accepted_at']) &&
    timestamp(value['activity_at']) &&
    typeof value['can_send'] === 'boolean' &&
    count(value['unread_count']) &&
    isContext(value['original_context']) &&
    isPeer(value['peer']) &&
    (value['last_message'] === null ||
      (isMessage(value['last_message']) &&
        value['last_message'].conversation_id === value['conversation_id']))
  );
}
export function isConversationList(
  value: unknown,
): value is Api['schemas']['ConversationListResponse'] {
  return (
    record(value) &&
    Array.isArray(value['conversations']) &&
    value['conversations'].every(summary) &&
    nullableText(value['next_cursor'])
  );
}
export function isConversation(
  value: unknown,
): value is Api['schemas']['ConversationDetailsResponse'] {
  return (
    record(value) &&
    typeof value['conversation_id'] === 'string' &&
    typeof value['request_id'] === 'string' &&
    timestamp(value['accepted_at']) &&
    count(value['accepted_request_version']) &&
    count(value['last_confirmed_sequence']) &&
    count(value['unread_count']) &&
    typeof value['can_send'] === 'boolean' &&
    isPeer(value['peer']) &&
    isContext(value['original_context']) &&
    (value['read_position'] === null ||
      (isReadPosition(value['read_position']) &&
        value['read_position'].conversation_id === value['conversation_id'] &&
        value['read_position'].through_sequence <= value['last_confirmed_sequence']))
  );
}
export function isHistory(value: unknown): value is Api['schemas']['MessageHistoryResponse'] {
  if (!record(value)) return false;
  const messages: unknown = value['messages'];
  const anchor: unknown = value['anchor_sequence'];
  return (
    count(anchor) &&
    nullableText(value['next_cursor']) &&
    Array.isArray(messages) &&
    messages.every(isMessage) &&
    messages.every((message: Message) => message.sequence <= anchor) &&
    new Set(messages.map((message: Message) => message.sequence)).size === messages.length
  );
}
export function orderedMessages(messages: readonly Message[]): readonly Message[] {
  return messages.reduce<readonly Message[]>(
    (ordered, message) => [
      ...ordered.filter((item) => item.sequence < message.sequence),
      message,
      ...ordered.filter((item) => item.sequence > message.sequence),
    ],
    [],
  );
}
export function peerName(peer: Peer): string {
  if (peer.state === 'deleted') return 'Deleted account';
  if (peer.state === 'unavailable' || peer.display_name === null) return 'Profile unavailable';
  return peer.display_name;
}
export function contextSubject(context: Context): string {
  return context.sender_goal?.subject_label ?? context.recipient_goal?.subject_label ?? '';
}
export function listOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  cursor: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actorId, 'chats', 'list', cursor] as const,
    enabled: enabled && actorId !== null,
    retry: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/conversations${cursor === null ? '' : `?cursor=${encodeURIComponent(cursor)}`}`,
        signal,
        isConversationList,
      ),
  });
}
export function detailsOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  conversation: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actorId, 'chats', conversation, 'details'] as const,
    enabled: enabled && actorId !== null && conversation !== null,
    retry: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/conversations/${encodeURIComponent(conversation ?? '')}`,
        signal,
        (value): value is Api['schemas']['ConversationDetailsResponse'] =>
          isConversation(value) && value.conversation_id === conversation,
      ),
  });
}
export function historyOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  conversation: string | null,
  cursor: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actorId, 'chats', conversation, 'messages', cursor] as const,
    enabled: enabled && actorId !== null && conversation !== null,
    retry: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/conversations/${encodeURIComponent(conversation ?? '')}/messages${cursor === null ? '' : `?cursor=${encodeURIComponent(cursor)}`}`,
        signal,
        (value): value is Api['schemas']['MessageHistoryResponse'] =>
          isHistory(value) &&
          value.messages.every((message) => message.conversation_id === conversation),
      ),
  });
}
