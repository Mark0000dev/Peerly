import type { HttpClient } from '@angular/common/http';
import { queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { readJson } from '../../../api-http';
import { filterKeys, isSupportCase, isSupportHistory, isSupportInbox } from './support-contract';
import type { SupportFilters } from './support-contract';

export function inboxOptions(
  http: Readonly<HttpClient>,
  actor: string | null,
  filters: SupportFilters,
  enabled: boolean,
) {
  const params = new URLSearchParams();
  for (const key of filterKeys) {
    const value = filters[key];
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  return queryOptions({
    queryKey: ['account', actor, 'operator', 'support', 'inbox', filters] as const,
    enabled: enabled && actor !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/operator/cases${params.size === 0 ? '' : '?' + params.toString()}`,
        signal,
        isSupportInbox,
      ),
  });
}
export function caseOptions(
  http: Readonly<HttpClient>,
  actor: string | null,
  caseId: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actor, 'operator', 'support', 'case', caseId] as const,
    enabled: enabled && actor !== null && caseId !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/operator/cases/${encodeURIComponent(caseId ?? '')}`,
        signal,
        (value): value is Api['schemas']['OperatorSupportResponse'] =>
          isSupportCase(value) && value.receipt.case_id === caseId,
      ),
  });
}
export function historyOptions(
  http: Readonly<HttpClient>,
  actor: string | null,
  caseId: string | null,
  cursor: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: ['account', actor, 'operator', 'support', 'history', caseId, cursor] as const,
    enabled: enabled && actor !== null && caseId !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 0,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        `/api/v1/operator/cases/${encodeURIComponent(caseId ?? '')}/history${cursor === null ? '' : '?' + new URLSearchParams({ cursor }).toString()}`,
        signal,
        (value): value is Api['schemas']['OperatorSupportHistoryResponse'] =>
          isSupportHistory(value) && value.case_id === caseId,
      ),
  });
}
