import type { Api } from '../../../../api.generated';
import type { ApiFailure } from '../../../../api-http';

export interface GoalAssistanceDraft {
  readonly source: Api['schemas']['DraftSourceRequest'];
  readonly context: string;
  readonly topic: string;
  readonly areaLabel: string;
  readonly candidates: readonly Pick<Api['schemas']['SubjectResponse'], 'id' | 'name'>[];
}
export interface ApplyGoalText {
  readonly source: Api['schemas']['DraftSourceRequest'];
  readonly target: Api['schemas']['GoalTextTarget'];
  readonly value: string;
}
export interface ApplyGoalArea {
  readonly source: Api['schemas']['DraftSourceRequest'];
  readonly id: string;
}
export interface AssistanceExpired {
  readonly actorId: string;
  readonly failure: ApiFailure;
}
export type GoalRequest = Api['schemas']['ClarifyRequest'] | Api['schemas']['SuggestRequest'];

function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
export function isUuid(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);
}
export function boundedText(value: string, maximum: number, multiline = false): boolean {
  return (
    value.trim().length > 0 &&
    Array.from(value).length <= maximum &&
    !Array.from(value.trim()).some((character: string) => {
      const code = character.codePointAt(0);
      return (
        code === undefined ||
        (code < 32 && !(multiline && (code === 9 || code === 10))) ||
        (code >= 127 && code <= 159) ||
        (code >= 0xd800 && code <= 0xdfff)
      );
    })
  );
}
export function validDraft(draft: GoalAssistanceDraft): boolean {
  return (
    isUuid(draft.source.id) &&
    Number.isSafeInteger(draft.source.version) &&
    draft.source.version >= 1
  );
}
export function canClarify(draft: GoalAssistanceDraft): boolean {
  return validDraft(draft) && boundedText(draft.context, 240, true);
}
export function canSuggest(draft: GoalAssistanceDraft): boolean {
  return (
    validDraft(draft) &&
    boundedText(draft.areaLabel, 80) &&
    draft.candidates.length >= 1 &&
    draft.candidates.length <= 20 &&
    draft.candidates.every(
      (candidate: Readonly<Pick<Api['schemas']['SubjectResponse'], 'id' | 'name'>>) =>
        isUuid(candidate.id) && candidate.name.trim().length > 0,
    ) &&
    new Set(
      draft.candidates.map(
        (candidate: Readonly<Pick<Api['schemas']['SubjectResponse'], 'id' | 'name'>>) =>
          candidate.id,
      ),
    ).size === draft.candidates.length
  );
}
export function sameDraft(left: GoalAssistanceDraft, right: GoalAssistanceDraft): boolean {
  return (
    left.source.id === right.source.id &&
    left.source.version === right.source.version &&
    left.context === right.context &&
    left.topic === right.topic &&
    left.areaLabel === right.areaLabel &&
    left.candidates.length === right.candidates.length &&
    left.candidates.every(
      (
        candidate: Readonly<Pick<Api['schemas']['SubjectResponse'], 'id' | 'name'>>,
        index: number,
      ) => {
        const other = right.candidates[index];
        return candidate.id === other?.id && candidate.name === other.name;
      },
    )
  );
}
const failures: readonly Api['schemas']['Failure'][] = [
  'transient',
  'invalid_output',
  'invalid_input',
  'timeout',
  'auth_unavailable',
  'rate_limited',
  'account_unavailable',
  'stale_source',
  'executor_lost',
];

export function acceptsJob(
  value: unknown,
  body: GoalRequest,
  expected?: Readonly<{ readonly id: string; readonly hash: string }>,
): value is Api['schemas']['JobResponse'] {
  if (
    !record(value) ||
    !isUuid(value['id']) ||
    value['kind'] !== body.kind ||
    !record(value['source']) ||
    value['source']['kind'] !== 'draft' ||
    value['source']['id'] !== body.source.id ||
    value['source']['version'] !== body.source.version ||
    typeof value['source']['content_hash'] !== 'string' ||
    !/^[a-f0-9]{64}$/.test(value['source']['content_hash'])
  )
    return false;
  if (
    expected !== undefined &&
    (value['id'] !== expected.id || value['source']['content_hash'] !== expected.hash)
  )
    return false;
  if (
    value['target'] !== (body.kind === 'clarify_goal' ? (body.target ?? 'context') : null) ||
    typeof value['created_at'] !== 'string' ||
    !Number.isFinite(Date.parse(value['created_at'])) ||
    typeof value['deadline'] !== 'string' ||
    !Number.isFinite(Date.parse(value['deadline'])) ||
    Date.parse(value['deadline']) <= Date.parse(value['created_at'])
  )
    return false;
  if (value['state'] === 'queued' || value['state'] === 'running')
    return (
      value['result'] === null &&
      value['failure'] === null &&
      typeof value['poll_after_ms'] === 'number' &&
      Number.isSafeInteger(value['poll_after_ms']) &&
      value['poll_after_ms'] > 0
    );
  if (value['poll_after_ms'] !== null) return false;
  if (value['state'] === 'succeeded') {
    if (value['failure'] !== null || !record(value['result'])) return false;
    const result = value['result'];
    if (body.kind === 'clarify_goal')
      return (
        Object.keys(result).length === 1 &&
        typeof result['suggestion'] === 'string' &&
        boundedText(
          result['suggestion'],
          body.target === 'topic' ? 80 : 240,
          body.target !== 'topic',
        )
      );
    return (
      Object.keys(result).length === 1 &&
      Array.isArray(result['ids']) &&
      result['ids'].length <= 3 &&
      result['ids'].every((id: unknown) => isUuid(id) && body.candidate_ids.includes(id)) &&
      new Set(result['ids']).size === result['ids'].length
    );
  }
  if (value['result'] !== null) return false;
  if (value['state'] === 'cancelled') return value['failure'] === null;
  return (
    (value['state'] === 'failed' || value['state'] === 'expired') &&
    (value['failure'] === null ||
      failures.some((failure: Api['schemas']['Failure']) => failure === value['failure']))
  );
}
