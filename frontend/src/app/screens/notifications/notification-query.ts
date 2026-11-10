import type { HttpClient } from '@angular/common/http';
import { CancelledError, queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryClient, QueryFunctionContext } from '@tanstack/angular-query-experimental';
import { ApiFailure, readJson } from '../../api-http';
import { trustedVerifiedActor } from '../verified-actor';
import { isPreference } from './notification-contract';

export function preferenceOptions(
  http: Readonly<HttpClient>,
  client: Readonly<QueryClient>,
  actorId: string | null,
) {
  return queryOptions({
    queryKey:
      actorId === null
        ? (['notification-preference-idle'] as const)
        : (['account', actorId, 'notification-preference'] as const),
    enabled: actorId !== null,
    retry: false,
    gcTime: 0,
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) => {
      if (actorId === null || trustedVerifiedActor(client, actorId) === null)
        throw new CancelledError();
      return readJson(
        http,
        '/api/v1/me/notification-preference',
        AbortSignal.any([signal, AbortSignal.timeout(15_000)]),
        isPreference,
      );
    },
  });
}
export function preferenceUnknown(error: unknown): boolean {
  return (
    error instanceof ApiFailure &&
    (error.status === 0 || error.status === 408 || error.status >= 500)
  );
}
export function preferenceWrite<T>(request: Promise<T>, signal: Readonly<AbortSignal>): Promise<T> {
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
    if (signal.aborted) abort();
    void request.then(
      (value: T) => {
        cleanup();
        resolve(value);
      },
      (error: unknown) => {
        cleanup();
        reject(error instanceof Error ? error : new Error('Preference request failed'));
      },
    );
  });
}
