import type { AbstractControl, ValidationErrors } from '@angular/forms';
import type { HttpClient } from '@angular/common/http';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { readJson } from '../../api-http';
import { isMessage } from './chats-contract';

export type MessageOperation =
  Api['paths']['/api/v1/conversations/{conversation_id}/message-operations/{client_message_id}']['get']['responses']['200'];
export type TerminalMessageOperation =
  Api['paths']['/api/v1/conversations/{conversation_id}/messages']['post']['responses']['200'];

export function isTerminalOperation(value: unknown): value is TerminalMessageOperation {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('conversation_id' in value) ||
    typeof value.conversation_id !== 'string' ||
    !('client_message_id' in value) ||
    typeof value.client_message_id !== 'string' ||
    !('operation_id' in value) ||
    typeof value.operation_id !== 'string'
  )
    return false;
  if ('message' in value)
    return (
      !('cancelled_at' in value) &&
      isMessage(value.message) &&
      value.message.conversation_id === value.conversation_id &&
      value.message.client_message_id === value.client_message_id &&
      (!('outcome' in value) || value.outcome === 'confirmed')
    );
  return (
    'cancelled_at' in value &&
    typeof value.cancelled_at === 'string' &&
    Number.isFinite(Date.parse(value.cancelled_at)) &&
    (!('outcome' in value) || value.outcome === 'cancelled')
  );
}
export function isOperation(value: unknown): value is MessageOperation {
  if (isTerminalOperation(value)) return true;
  return (
    typeof value === 'object' &&
    value !== null &&
    'conversation_id' in value &&
    typeof value.conversation_id === 'string' &&
    'client_message_id' in value &&
    typeof value.client_message_id === 'string' &&
    !('operation_id' in value) &&
    !('message' in value) &&
    !('cancelled_at' in value) &&
    (!('outcome' in value) || value.outcome === 'unobserved')
  );
}
export function messageProblem(text: string): string | null {
  if (text.trim().length === 0) return 'Enter a message.';
  if (Array.from(text).length > 2000) return 'Use at most 2000 characters.';
  if (/[\p{Cc}\p{Cs}]/u.test(text.replace(/[\n\t]/gu, '')))
    return 'Remove unsupported control characters.';
  return null;
}
export function messageValidator(
  control: Readonly<AbstractControl<string>>,
): ValidationErrors | null {
  const problem = messageProblem(control.value);
  return problem === null ? null : { message: problem };
}
export function operationOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  conversationId: string,
  clientMessageId: string | null,
) {
  return queryOptions({
    queryKey: ['account', actorId, 'chats', conversationId, 'operation', clientMessageId] as const,
    enabled: false,
    retry: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/conversations/${encodeURIComponent(conversationId)}/message-operations/${encodeURIComponent(clientMessageId ?? '')}`,
        signal,
        (value): value is MessageOperation =>
          isOperation(value) &&
          value.conversation_id === conversationId &&
          value.client_message_id === clientMessageId,
      ),
  });
}
