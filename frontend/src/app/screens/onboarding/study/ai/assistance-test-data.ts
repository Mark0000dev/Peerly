import type { Api } from '../../../../api.generated';
import type { GoalAssistanceDraft } from './goal-assistance-contract';

export const draft: GoalAssistanceDraft = {
  source: { kind: 'draft', id: '00000000-0000-4000-8000-000000000010', version: 3 },
  context: 'LEFT JOIN with NULLs gives duplicate rows.',
  topic: 'SQL JOINs',
  areaLabel: 'database joins',
  candidates: [
    { id: '00000000-0000-4000-8000-000000000011', name: 'Computing' },
    { id: '00000000-0000-4000-8000-000000000012', name: 'Mathematics' },
  ],
};
export const clarify: Api['schemas']['ClarifyRequest'] = {
  kind: 'clarify_goal',
  source: draft.source,
  target: 'context',
  text: draft.context,
};
export const suggest: Api['schemas']['SuggestRequest'] = {
  kind: 'suggest_subject',
  source: draft.source,
  label: draft.areaLabel,
  candidate_ids: draft.candidates.map(
    (candidate: Readonly<Pick<Api['schemas']['SubjectResponse'], 'id' | 'name'>>) => candidate.id,
  ),
};
export function job(
  overrides: Partial<Api['schemas']['JobResponse']> = {},
): Api['schemas']['JobResponse'] {
  return {
    id: '00000000-0000-4000-8000-000000000020',
    kind: 'clarify_goal',
    source: { ...draft.source, content_hash: '1'.repeat(64) },
    target: 'context',
    state: 'queued',
    created_at: new Date(Date.now() - 1000).toISOString(),
    deadline: new Date(Date.now() + 60_000).toISOString(),
    result: null,
    failure: null,
    poll_after_ms: 10_000,
    ...overrides,
  };
}

export const photoSource: Api['schemas']['ResourceSourceRequest'] = {
  kind: 'resource',
  id: '00000000-0000-4000-8000-000000000070',
  version: 7,
};
export function photoJob(
  overrides: Partial<Api['schemas']['JobResponse']> = {},
): Api['schemas']['JobResponse'] {
  return job({ kind: 'assess_photo', source: photoSource, target: null, ...overrides });
}
