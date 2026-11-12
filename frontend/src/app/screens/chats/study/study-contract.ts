import type { HttpClient } from '@angular/common/http';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { readJson } from '../../../api-http';

type Outcome = Api['schemas']['StudyOutcomeResponse'];
type Receipt = Api['schemas']['FeedbackReceiptResponse'];
type Publication = Api['schemas']['FeedbackPublication'];
export type Prompt =
  Api['schemas']['OfferedStudyPromptResponse'] | Api['schemas']['NoStudyPromptResponse'];

function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function version(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}
function timestamp(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}
function publication(value: unknown): value is Publication | null {
  return value === null || value === 'eligible' || value === 'private_only' || value === 'removed';
}
export function isDescriptor(value: unknown): value is Api['schemas']['FeedbackDescriptor'] {
  return value === 'easy_to_communicate' || value === 'prepared' || value === 'supportive';
}
export function isOutcome(value: unknown): value is Outcome {
  return (
    record(value) &&
    typeof value['id'] === 'string' &&
    typeof value['conversation_id'] === 'string' &&
    version(value['version']) &&
    timestamp(value['changed_at']) &&
    (value['answer'] === 'yes' ||
      value['answer'] === 'not_yet' ||
      value['answer'] === 'did_not_work_out')
  );
}
export function isReceipt(value: unknown): value is Receipt {
  return (
    record(value) &&
    typeof value['id'] === 'string' &&
    typeof value['conversation_id'] === 'string' &&
    version(value['version']) &&
    timestamp(value['changed_at']) &&
    (value['again'] === 'yes' || value['again'] === 'maybe' || value['again'] === 'no') &&
    Array.isArray(value['descriptors']) &&
    value['descriptors'].length <= 3 &&
    value['descriptors'].every(isDescriptor) &&
    new Set(value['descriptors']).size === value['descriptors'].length &&
    (value['team_note'] === null ||
      (typeof value['team_note'] === 'string' && Array.from(value['team_note']).length <= 1000)) &&
    typeof value['worked_outcome_id'] === 'string' &&
    version(value['worked_outcome_version']) &&
    typeof value['captured_public_eligibility'] === 'boolean'
  );
}
export function isOwnOutcome(
  value: unknown,
  conversation: string,
): value is Api['schemas']['OwnStudyOutcomeResponse'] {
  return (
    record(value) &&
    (value['outcome'] === null ||
      (isOutcome(value['outcome']) && value['outcome'].conversation_id === conversation))
  );
}
export function isOwnFeedback(
  value: unknown,
  conversation: string,
): value is Api['schemas']['OwnFeedbackResponse'] {
  return (
    record(value) &&
    (value['current'] === null ||
      (isReceipt(value['current']) && value['current'].conversation_id === conversation)) &&
    typeof value['can_submit'] === 'boolean' &&
    publication(value['current_publication']) &&
    publication(value['submission_publication']) &&
    isOwnOutcome(value, conversation)
  );
}
export function isPrompt(value: unknown, conversation: string): value is Prompt {
  return (
    record(value) &&
    (value['outcome'] === 'no_offer' ||
      (value['outcome'] === 'offered' &&
        value['conversation_id'] === conversation &&
        typeof value['receipt_id'] === 'string' &&
        timestamp(value['offered_at'])))
  );
}
export function studyKey(actor: string | null, conversation: string) {
  return ['account', actor, 'chats', 'study', conversation] as const;
}
export function outcomeOptions(
  http: Readonly<HttpClient>,
  actor: string | null,
  conversation: string,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: [...studyKey(actor, conversation), 'outcome'] as const,
    enabled: enabled && actor !== null && conversation.length > 0,
    retry: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/conversations/${encodeURIComponent(conversation)}/study-outcome`,
        signal,
        (value): value is Api['schemas']['OwnStudyOutcomeResponse'] =>
          isOwnOutcome(value, conversation),
      ),
  });
}
export function feedbackOptions(
  http: Readonly<HttpClient>,
  actor: string | null,
  conversation: string,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: [...studyKey(actor, conversation), 'feedback'] as const,
    enabled: enabled && actor !== null && conversation.length > 0,
    retry: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/conversations/${encodeURIComponent(conversation)}/feedback`,
        signal,
        (value): value is Api['schemas']['OwnFeedbackResponse'] =>
          isOwnFeedback(value, conversation),
      ),
  });
}
