import type { HttpClient } from '@angular/common/http';
import { CancelledError, queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryClient, QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../../../api.generated';
import { readJson } from '../../../../api-http';
import { uuid } from '../../operator-contract';
import { cursorProblem, isReviewHistory } from './review-contract';

export function reviewKey(actorId: string | null, reportId: string | null) {
  return ['account', actorId, 'operator', 'report-review', reportId] as const;
}
export function reviewActor(
  client: Readonly<QueryClient>,
  actorId: string | null,
): Api['schemas']['IdentityResponse'] | null {
  const state = client.getQueryState(['session']);
  const actor = client.getQueryData<Api['schemas']['IdentityResponse'] | null>(['session']);
  return state?.status === 'success' &&
    state.fetchStatus === 'idle' &&
    actor?.account_id === actorId &&
    actor.account_status === 'active'
    ? actor
    : null;
}
export function historyOptions(
  http: Readonly<HttpClient>,
  client: Readonly<QueryClient>,
  actorId: string | null,
  reportId: string | null,
  cursor: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey: [...reviewKey(actorId, reportId), 'history', cursor] as const,
    enabled: enabled && actorId !== null && uuid(reportId) && cursorProblem(cursor) === null,
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) => {
      if (reviewActor(client, actorId) === null || reportId === null || !uuid(reportId))
        throw new CancelledError();
      return readJson(
        http,
        `/api/v1/operator/reports/${encodeURIComponent(reportId)}/reviews${cursor === null ? '' : `?cursor=${encodeURIComponent(cursor)}`}`,
        signal,
        (value): value is Api['schemas']['ReportReviewHistoryResponse'] =>
          isReviewHistory(value) && value.report_id === reportId,
      );
    },
  });
}
