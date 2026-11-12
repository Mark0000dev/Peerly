import type { HttpClient } from '@angular/common/http';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { readJson } from '../../api-http';

type Mode = Api['schemas']['DiscoveryMode'];
type View = Api['schemas']['DiscoveryView'];
type Context = Api['schemas']['DiscoveryContextBody'];
type Page = Api['schemas']['DiscoveryPageResponse'];
type Pass = Api['schemas']['PrivatePassResponse'];
function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function version(value: unknown): boolean {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}
function nullableText(value: unknown): boolean {
  return value === null || typeof value === 'string';
}
export function discoveryMode(value: string | null): Mode | null {
  return value === 'find_help' || value === 'offer_help' || value === 'study_together'
    ? value
    : null;
}
export function discoveryView(value: string | null): View | null {
  return value === 'candidates' || value === 'passed' ? value : null;
}
export function isPass(value: unknown): value is Pass {
  return (
    record(value) &&
    typeof value['person_id'] === 'string' &&
    typeof value['passed'] === 'boolean' &&
    version(value['version']) &&
    nullableText(value['changed_at'])
  );
}
export function isContext(value: unknown): value is Context {
  if (!record(value)) return false;
  if (value['mode'] === 'offer_help') return version(value['help_version']);
  return (
    (value['mode'] === 'find_help' || value['mode'] === 'study_together') &&
    typeof value['goal_id'] === 'string' &&
    version(value['goal_version'])
  );
}
function isRelevance(value: unknown): value is Api['schemas']['DiscoveryRelevanceResponse'] {
  return (
    record(value) &&
    (value['reason'] === 'can_help' ||
      value['reason'] === 'you_can_help' ||
      value['reason'] === 'shared_goal') &&
    typeof value['same_topic'] === 'boolean' &&
    typeof value['subject_id'] === 'string' &&
    typeof value['subject_label'] === 'string' &&
    nullableText(value['topic']) &&
    nullableText(value['reciprocal_subject_id']) &&
    nullableText(value['reciprocal_subject_label'])
  );
}
function isCard(value: unknown): value is Api['schemas']['DiscoveryCardResponse'] {
  return (
    record(value) &&
    typeof value['id'] === 'string' &&
    typeof value['display_name'] === 'string' &&
    nullableText(value['about']) &&
    version(value['version']) &&
    isPass(value['own_pass']) &&
    value['own_pass'].person_id === value['id'] &&
    record(value['photo']) &&
    typeof value['photo']['display_url'] === 'string' &&
    version(value['photo']['version']) &&
    isRelevance(value['relevance'])
  );
}
export function isDiscoveryPage(value: unknown): value is Page {
  return (
    record(value) &&
    (value['context'] === null || isContext(value['context'])) &&
    Array.isArray(value['people']) &&
    value['people'].length <= 20 &&
    value['people'].every(isCard) &&
    new Set(value['people'].map((person) => person.id)).size === value['people'].length &&
    nullableText(value['next_cursor']) &&
    (value['empty_reason'] === null ||
      value['empty_reason'] === 'context_required' ||
      value['empty_reason'] === 'no_relevant_people' ||
      value['empty_reason'] === 'exhausted' ||
      value['empty_reason'] === 'no_available_passed_people') &&
    (value['undo_pass'] === null || isPass(value['undo_pass']))
  );
}
export function discoveryOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  mode: Mode,
  view: View,
  cursor: string | null,
  enabled: boolean,
) {
  const parameters = new URLSearchParams({ mode, view });
  if (cursor !== null) parameters.set('cursor', cursor);
  return queryOptions({
    queryKey: ['account', actorId, 'discovery', mode, view, cursor] as const,
    enabled,
    retry: false,
    staleTime: 0,
    gcTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>): Promise<Page> =>
      readJson(
        http,
        `/api/v1/discovery?${parameters.toString()}`,
        signal,
        (value): value is Page =>
          isDiscoveryPage(value) && (value.context === null || value.context.mode === mode),
      ),
  });
}
export function relevanceText(value: Api['schemas']['DiscoveryRelevanceResponse']): string {
  const subject =
    value.same_topic && value.topic !== null
      ? `${value.subject_label} · ${value.topic}`
      : value.subject_label;
  switch (value.reason) {
    case 'can_help':
      return `Can help with ${subject}`;
    case 'you_can_help':
      return `You can help with their ${subject} goal`;
    case 'shared_goal':
      return `Open to studying ${subject} together`;
  }
}
