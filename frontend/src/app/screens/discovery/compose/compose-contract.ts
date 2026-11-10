import type { AbstractControl, ValidationErrors } from '@angular/forms';
import type { Api } from '../../../api.generated';

export type PreviewResult = Api['paths']['/api/v1/requests/preview']['post']['responses']['200'];
export type SendResult = Api['paths']['/api/v1/requests']['post']['responses']['200'];
export interface ComposerSelection {
  readonly actorId: string;
  readonly recipientId: string;
  readonly mode: Api['schemas']['DiscoveryMode'];
}
export interface DraftSource extends ComposerSelection {
  readonly previewId: string | null;
}
function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function text(value: unknown): value is string {
  return typeof value === 'string';
}
function nullableText(value: unknown): boolean {
  return value === null || text(value);
}
function version(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}
function count(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}
function date(value: unknown): value is string {
  return text(value) && Number.isFinite(Date.parse(value));
}
function mode(value: unknown): boolean {
  return value === 'find_help' || value === 'offer_help' || value === 'study_together';
}
function goal(value: unknown): value is Api['schemas']['GoalContextResponse'] {
  return (
    record(value) &&
    text(value['owner_id']) &&
    text(value['goal_id']) &&
    version(value['version']) &&
    text(value['subject_id']) &&
    text(value['subject_label']) &&
    nullableText(value['topic']) &&
    nullableText(value['context']) &&
    typeof value['shared_learning'] === 'boolean'
  );
}
function help(value: unknown): value is Api['schemas']['HelpContextResponse'] {
  return (
    record(value) &&
    text(value['owner_id']) &&
    version(value['version']) &&
    text(value['subject_id']) &&
    text(value['subject_label']) &&
    nullableText(value['topic_note'])
  );
}
export function isAcademicContext(
  value: unknown,
): value is Api['schemas']['AcademicContextResponse'] {
  if (!record(value) || !mode(value['mode'])) return false;
  if (value['mode'] === 'find_help')
    return (
      goal(value['sender_goal']) &&
      help(value['recipient_help']) &&
      value['recipient_goal'] === null &&
      value['sender_help'] === null
    );
  if (value['mode'] === 'offer_help')
    return (
      goal(value['recipient_goal']) &&
      help(value['sender_help']) &&
      value['sender_goal'] === null &&
      value['recipient_help'] === null
    );
  return (
    goal(value['sender_goal']) &&
    goal(value['recipient_goal']) &&
    value['sender_help'] === null &&
    value['recipient_help'] === null &&
    value['sender_goal'].shared_learning &&
    value['recipient_goal'].shared_learning &&
    value['sender_goal'].subject_id === value['recipient_goal'].subject_id
  );
}
export function contextBelongsTo(
  value: Api['schemas']['AcademicContextResponse'],
  selection: ComposerSelection,
): boolean {
  return (
    value.mode === selection.mode &&
    [value.sender_goal, value.sender_help].every(
      (source) => source === null || source.owner_id === selection.actorId,
    ) &&
    [value.recipient_goal, value.recipient_help].every(
      (source) => source === null || source.owner_id === selection.recipientId,
    )
  );
}
export function isPreview(value: unknown): value is Api['schemas']['PreviewResponse'] {
  return (
    record(value) &&
    (value['outcome'] === undefined || value['outcome'] === 'preview') &&
    text(value['preview_id']) &&
    date(value['created_at']) &&
    isAcademicContext(value['context']) &&
    text(value['suggested_text']) &&
    requestTextProblem(value['suggested_text'], true) === null &&
    date(value['checked_at']) &&
    quota(value['quota']) &&
    typeof value['can_send'] === 'boolean' &&
    (value['block_reason'] === null ||
      (text(value['block_reason']) &&
        [
          'existing_outgoing',
          'incoming',
          'connected',
          'cooldown',
          'source_changed',
          'unavailable',
          'outgoing_pending_limit',
          'daily_send_limit',
        ].includes(value['block_reason']))) &&
    (value['cooldown_until'] === null || date(value['cooldown_until'])) &&
    value['can_send'] === (value['block_reason'] === null) &&
    (value['block_reason'] === 'cooldown') === (value['cooldown_until'] !== null)
  );
}
function quota(value: unknown): boolean {
  return (
    record(value) &&
    version(value['outgoing_pending_limit']) &&
    version(value['daily_send_limit']) &&
    count(value['outgoing_pending']) &&
    count(value['successful_today']) &&
    count(value['outgoing_pending_remaining']) &&
    count(value['daily_sends_remaining']) &&
    date(value['reset_at'])
  );
}
export function sameContext(
  first: Api['schemas']['AcademicContextResponse'],
  second: Api['schemas']['AcademicContextResponse'],
): boolean {
  return (
    first.mode === second.mode &&
    sameGoal(first.sender_goal, second.sender_goal) &&
    sameGoal(first.recipient_goal, second.recipient_goal) &&
    sameHelp(first.sender_help, second.sender_help) &&
    sameHelp(first.recipient_help, second.recipient_help)
  );
}
function sameGoal(
  first: Api['schemas']['GoalContextResponse'] | null,
  second: Api['schemas']['GoalContextResponse'] | null,
): boolean {
  return first === null || second === null
    ? first === second
    : (
        [
          'owner_id',
          'goal_id',
          'version',
          'subject_id',
          'subject_label',
          'topic',
          'context',
          'shared_learning',
        ] as const
      ).every((key) => first[key] === second[key]);
}
function sameHelp(
  first: Api['schemas']['HelpContextResponse'] | null,
  second: Api['schemas']['HelpContextResponse'] | null,
): boolean {
  return first === null || second === null
    ? first === second
    : (['owner_id', 'version', 'subject_id', 'subject_label', 'topic_note'] as const).every(
        (key) => first[key] === second[key],
      );
}
function isConnected(value: unknown): value is Api['schemas']['ConnectedResponse'] {
  return (
    record(value) &&
    (value['outcome'] === undefined || value['outcome'] === 'connected') &&
    text(value['request_id']) &&
    text(value['conversation_id']) &&
    !('version' in value) &&
    !('preview_id' in value)
  );
}
function isRequestResult(value: unknown): value is Api['schemas']['RequestMutationResponse'] {
  return (
    record(value) &&
    text(value['request_id']) &&
    version(value['version']) &&
    date(value['changed_at']) &&
    nullableText(value['conversation_id']) &&
    (value['undo_until'] === null || date(value['undo_until'])) &&
    (value['outcome'] === 'sent' ||
      value['outcome'] === 'existing_outgoing' ||
      value['outcome'] === 'incoming')
  );
}
export function isSendResult(value: unknown): value is SendResult {
  return isConnected(value) || isRequestResult(value);
}
export function isPreviewResult(value: unknown): value is PreviewResult {
  return isPreview(value) || (isSendResult(value) && value.outcome !== 'sent');
}
export function requestParameters(value: SendResult): Readonly<Record<string, string>> {
  return {
    request: value.request_id,
    ...(value.outcome === 'incoming'
      ? { box: 'received' }
      : value.outcome === 'existing_outgoing' || value.outcome === 'sent'
        ? { box: 'sent' }
        : {}),
  };
}
export function codePoints(value: string): number {
  return Array.from(value).length;
}
export function requestTextProblem(value: string, required: boolean): string | null {
  if (required && value.trim().length === 0) return 'Write a request before sending.';
  if (codePoints(value) > 240)
    return 'Keep this field within 240 characters. Your text has not been cut.';
  if (/[\p{Cs}\p{Cc}]/u.test(value.replace(/[\n\t]/g, '')))
    return 'Remove unsupported control characters from this field.';
  return null;
}
export function requestTextValidator(
  required: boolean,
): (control: Readonly<AbstractControl<unknown>>) => ValidationErrors | null {
  return (control: Readonly<AbstractControl<unknown>>): ValidationErrors | null => {
    const problem =
      typeof control.value === 'string'
        ? requestTextProblem(control.value, required)
        : 'Enter plain text.';
    return problem === null ? null : { requestText: problem };
  };
}
