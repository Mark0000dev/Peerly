import type { HttpClient } from '@angular/common/http';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { readJson } from '../../api-http';
import { instant, uuid } from './operator-contract';

type Parameters = Api['paths']['/api/v1/operator/accounts/{account_id}/goals']['get']['parameters'];
export type GoalFilters = {
  readonly [K in keyof Parameters as K extends `query:${infer Name}` ? Name : never]: Parameters[K];
};
function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function string(value: unknown): value is string {
  return typeof value === 'string';
}
function integer(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}
function positive(value: unknown): value is number {
  return integer(value) && value > 0;
}
function nullable<T>(value: unknown, guard: (item: unknown) => item is T): value is T | null {
  return value === null || guard(value);
}
function array<T>(value: unknown, guard: (item: unknown) => item is T): value is readonly T[] {
  return Array.isArray(value) && value.every(guard);
}
function root(value: unknown): value is Api['schemas']['OperatorGoalRootResponse'] {
  return (
    record(value) &&
    uuid(value['id']) &&
    uuid(value['account_id']) &&
    positive(value['current_version']) &&
    instant(value['created_at']) &&
    nullable(value['completed_at'], instant)
  );
}
function revision(value: unknown): value is Api['schemas']['OperatorGoalRevisionResponse'] {
  return (
    record(value) &&
    uuid(value['goal_id']) &&
    uuid(value['account_id']) &&
    positive(value['version']) &&
    nullable(value['subject_id'], uuid) &&
    string(value['subject_label']) &&
    nullable(value['topic'], string) &&
    nullable(value['topic_match_key'], string) &&
    nullable(value['context'], string) &&
    typeof value['shared_learning'] === 'boolean' &&
    instant(value['saved_at']) &&
    nullable(value['completed_at'], instant)
  );
}
function selection(
  value: unknown,
): value is Api['schemas']['OperatorHelpHistorySelectionResponse'] {
  return (
    record(value) &&
    integer(value['slot']) &&
    uuid(value['subject_id']) &&
    string(value['subject_label']) &&
    nullable(value['topic_note'], string) &&
    nullable(value['topic_match_key'], string)
  );
}
function helpRevision(
  value: unknown,
): value is Api['schemas']['OperatorHelpHistoryRevisionResponse'] {
  return (
    record(value) &&
    uuid(value['account_id']) &&
    positive(value['version']) &&
    instant(value['saved_at']) &&
    array(value['selections'], selection)
  );
}
export function isGoals(value: unknown): value is Api['schemas']['OperatorGoalsResponse'] {
  return (
    record(value) &&
    uuid(value['account_id']) &&
    array(value['goals'], root) &&
    nullable(value['next_cursor'], string) &&
    nullable(value['anchor_created_at'], instant) &&
    nullable(value['anchor_goal_id'], uuid) &&
    instant(value['observed_at']) &&
    (value['pagination'] === undefined ||
      value['pagination'] === 'anchored_search_not_commit_order') &&
    value['goals'].every((goal) => goal.account_id === value['account_id'])
  );
}
export function isGoalHistory(
  value: unknown,
): value is Api['schemas']['OperatorGoalHistoryResponse'] {
  if (
    !record(value) ||
    !root(value['goal']) ||
    !array(value['revisions'], revision) ||
    !positive(value['anchor_version']) ||
    !instant(value['observed_at']) ||
    !nullable(value['next_cursor'], string)
  )
    return false;
  const goal = value['goal'];
  return value['revisions'].every(
    (row) => row.account_id === goal.account_id && row.goal_id === goal.id,
  );
}
export function isHelpHistory(
  value: unknown,
): value is Api['schemas']['OperatorHelpHistoryResponse'] {
  return (
    record(value) &&
    uuid(value['account_id']) &&
    array(value['revisions'], helpRevision) &&
    integer(value['anchor_version']) &&
    nullable(value['next_cursor'], string) &&
    value['revisions'].every((row) => row.account_id === value['account_id'])
  );
}
function query(filters: Readonly<Record<string, string | null | undefined>>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null) params.set(key, value);
  }
  return params.toString();
}
export function goalsOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  accountId: string | null,
  filters: GoalFilters,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actorId, 'operator', 'academic', accountId, 'goals', filters] as const,
    enabled: enabled && actorId !== null && accountId !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/operator/accounts/${encodeURIComponent(accountId ?? '')}/goals?${query(filters)}`,
        signal,
        (value): value is Api['schemas']['OperatorGoalsResponse'] =>
          isGoals(value) && value.account_id === accountId,
      ),
  });
}
export function goalHistoryOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  accountId: string | null,
  goalId: string | null,
  cursor: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: [
      'account',
      actorId,
      'operator',
      'academic',
      accountId,
      'goal-history',
      goalId,
      cursor,
    ] as const,
    enabled: enabled && actorId !== null && accountId !== null && goalId !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/operator/accounts/${encodeURIComponent(accountId ?? '')}/goals/${encodeURIComponent(goalId ?? '')}/history?${query({ cursor })}`,
        signal,
        (value): value is Api['schemas']['OperatorGoalHistoryResponse'] =>
          isGoalHistory(value) && value.goal.account_id === accountId && value.goal.id === goalId,
      ),
  });
}
export function helpHistoryOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  accountId: string | null,
  cursor: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: [
      'account',
      actorId,
      'operator',
      'academic',
      accountId,
      'help-history',
      cursor,
    ] as const,
    enabled: enabled && actorId !== null && accountId !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/operator/accounts/${encodeURIComponent(accountId ?? '')}/help-history?${query({ cursor })}`,
        signal,
        (value): value is Api['schemas']['OperatorHelpHistoryResponse'] =>
          isHelpHistory(value) && value.account_id === accountId,
      ),
  });
}
