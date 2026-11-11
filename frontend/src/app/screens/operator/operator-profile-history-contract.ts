import type { HttpClient } from '@angular/common/http';
import type { ParamMap } from '@angular/router';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../api.generated';
import { readJson } from '../../api-http';
import { instant, uuid } from './operator-contract';
function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function raw(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}
function revision(
  value: unknown,
): value is Api['schemas']['OperatorProfileHistoryRevisionResponse'] {
  return (
    record(value) &&
    uuid(value['account_id']) &&
    typeof value['version'] === 'number' &&
    Number.isSafeInteger(value['version']) &&
    value['version'] > 0 &&
    raw(value['display_name']) &&
    raw(value['about']) &&
    raw(value['programme']) &&
    raw(value['year_label']) &&
    Array.isArray(value['languages']) &&
    value['languages'].every((item: unknown) => typeof item === 'string') &&
    (value['task'] === 'find_help' || value['task'] === 'offer_help') &&
    instant(value['saved_at'])
  );
}
export function isProfileHistory(
  value: unknown,
): value is Api['schemas']['OperatorProfileHistoryResponse'] {
  if (
    !record(value) ||
    !uuid(value['account_id']) ||
    typeof value['anchor_version'] !== 'number' ||
    !Number.isSafeInteger(value['anchor_version']) ||
    value['anchor_version'] < 0 ||
    !(value['next_cursor'] === null || typeof value['next_cursor'] === 'string') ||
    !Array.isArray(value['revisions']) ||
    value['revisions'].length > 50
  )
    return false;
  const rows: readonly unknown[] = value['revisions'];
  const anchor = value['anchor_version'];
  return rows.every((row, index) => {
    const previous = rows[index - 1];
    return (
      revision(row) &&
      row.account_id === value['account_id'] &&
      row.version <= anchor &&
      (previous === undefined || (revision(previous) && previous.version > row.version))
    );
  });
}
export function profileHistoryRoute(params: Readonly<ParamMap>) {
  const open = params.get('profile_history') === 'open';
  const cursor = params.get('profile_cursor');
  const error =
    cursor !== null && (cursor.length === 0 || cursor.length > 1024)
      ? 'The profile history cursor is invalid. Return to the first page.'
      : null;
  return { open, cursor, error };
}
export function profileHistoryOptions(
  http: Readonly<HttpClient>,
  actor: string | null,
  account: string | null,
  cursor: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actor, 'operator', 'profile-history', account, cursor] as const,
    enabled: enabled && actor !== null && account !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/operator/accounts/${encodeURIComponent(account ?? '')}/profile-history${cursor === null ? '' : `?${new URLSearchParams({ cursor })}`}`,
        signal,
        (value): value is Api['schemas']['OperatorProfileHistoryResponse'] =>
          isProfileHistory(value) && value.account_id === account,
      ),
  });
}
