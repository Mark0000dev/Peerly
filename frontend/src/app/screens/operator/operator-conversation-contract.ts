import type { HttpClient } from '@angular/common/http';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { ParamMap } from '@angular/router';
import type { Api } from '../../api.generated';
import { readJson } from '../../api-http';
import { instant, uuid } from './operator-contract';

function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function integer(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}
function message(value: unknown): value is Api['schemas']['MessageResponse'] {
  return (
    record(value) &&
    uuid(value['message_id']) &&
    uuid(value['client_message_id']) &&
    uuid(value['conversation_id']) &&
    uuid(value['author_id']) &&
    integer(value['sequence']) &&
    (value['text'] === null || typeof value['text'] === 'string') &&
    (value['image_id'] === null || uuid(value['image_id'])) &&
    (value['text'] !== null || value['image_id'] !== null) &&
    instant(value['sent_at'])
  );
}
export function isOperatorMessages(
  value: unknown,
): value is Api['schemas']['OperatorMessagesResponse'] {
  if (
    !record(value) ||
    !uuid(value['conversation_id']) ||
    !uuid(value['relationship_id']) ||
    !uuid(value['request_id']) ||
    !uuid(value['low_id']) ||
    !uuid(value['high_id']) ||
    value['low_id'] === value['high_id'] ||
    !integer(value['accepted_request_version']) ||
    typeof value['anchor_sequence'] !== 'number' ||
    !Number.isSafeInteger(value['anchor_sequence']) ||
    value['anchor_sequence'] < 0 ||
    !(value['next_cursor'] === null || typeof value['next_cursor'] === 'string') ||
    !Array.isArray(value['messages']) ||
    value['messages'].length > 50
  )
    return false;
  const rows: readonly unknown[] = value['messages'];
  const anchor = value['anchor_sequence'];
  return rows.every((row, index) => {
    const previous = rows[index - 1];
    return (
      message(row) &&
      row.conversation_id === value['conversation_id'] &&
      (row.author_id === value['low_id'] || row.author_id === value['high_id']) &&
      row.sequence <= anchor &&
      (previous === undefined || (message(previous) && previous.sequence < row.sequence)) &&
      rows.filter((other) => message(other) && other.message_id === row.message_id).length === 1
    );
  });
}
export function conversationRoute(params: Readonly<ParamMap>) {
  const id = params.get('conversation');
  const cursor = params.get('cursor');
  const error =
    id !== null && !uuid(id)
      ? 'Conversation ID must be a UUID.'
      : cursor !== null && (id === null || cursor.length === 0 || cursor.length > 1024)
        ? 'The page cursor is invalid. Return to the first page.'
        : null;
  return { id, cursor, error };
}
export function operatorMessagesOptions(
  http: Readonly<HttpClient>,
  actor: string | null,
  id: string | null,
  cursor: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actor, 'operator', 'conversation', id, cursor] as const,
    enabled: enabled && actor !== null && id !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/operator/conversations/${encodeURIComponent(id ?? '')}/messages${cursor === null ? '' : `?${new URLSearchParams({ cursor })}`}`,
        signal,
        (value): value is Api['schemas']['OperatorMessagesResponse'] =>
          isOperatorMessages(value) && value.conversation_id === id,
      ),
  });
}
