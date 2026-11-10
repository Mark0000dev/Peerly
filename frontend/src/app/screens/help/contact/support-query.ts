import type { HttpClient } from '@angular/common/http';
import { CancelledError, queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryClient, QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { ApiFailure, readJson } from '../../../api-http';
import { isRecentSupport } from './support-contract';

// Support deliberately accepts real banned/unverified identities; it grants no student capability.
export function supportActor(
  client: Readonly<QueryClient>,
): Api['schemas']['IdentityResponse'] | null | undefined {
  const state = client.getQueryState(['session']);
  return state?.status === 'success' && state.fetchStatus === 'idle'
    ? client.getQueryData<Api['schemas']['IdentityResponse'] | null>(['session'])
    : undefined;
}
export function recentSupportOptions(
  http: Readonly<HttpClient>,
  actorId: string | null,
  enabled: boolean,
) {
  return queryOptions({
    queryKey:
      actorId === null
        ? (['support-recovery', 'anonymous'] as const)
        : (['account', actorId, 'support-recovery'] as const),
    enabled,
    retry: false,
    gcTime: 0,
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(
        http,
        actorId === null ? '/api/v1/support-cases' : '/api/v1/me/support-cases',
        AbortSignal.any([signal, AbortSignal.timeout(15_000)]),
        isRecentSupport,
      ),
  });
}
export async function supportWrite<T>(
  request: Promise<T>,
  signal: Readonly<AbortSignal>,
): Promise<T> {
  if (signal.aborted) throw new CancelledError();
  return new Promise<T>((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timer);
      signal.removeEventListener('abort', abort);
    };
    const abort = () => {
      cleanup();
      reject(new CancelledError());
    };
    const timer = setTimeout(() => {
      cleanup();
      reject(new ApiFailure(0, 'outcome_unknown', null));
    }, 15_000);
    signal.addEventListener('abort', abort, { once: true });
    void request.then(
      (value: T) => {
        cleanup();
        resolve(value);
      },
      (error: unknown) => {
        cleanup();
        reject(error instanceof Error ? error : new Error('Support request failed'));
      },
    );
  });
}
export function supportOutcomeUnknown(error: unknown): boolean {
  return (
    error instanceof ApiFailure &&
    (error.status === 0 || error.status === 408 || error.status >= 500)
  );
}
