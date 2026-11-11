import { HttpErrorResponse } from '@angular/common/http';
import type { HttpClient } from '@angular/common/http';
import { firstValueFrom, fromEvent, takeUntil, throwIfEmpty } from 'rxjs';
import type { Api } from '../api.generated';
import type { Delivery } from './observation-contract';

// Reads canonical fresh session at EACH dispatch; no token/account copy in a store.
export type ObservationIdentity = Readonly<
  Pick<Api['schemas']['IdentityResponse'], 'account_id' | 'csrf_token'>
>;
function retryAfter(value: string | null, now: number): number | undefined {
  if (value === null) return undefined;
  if (/^\d{1,9}$/.test(value)) return Number(value) * 1000;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? Math.max(0, timestamp - now) : undefined;
}
export function createObservationDelivery(
  http: Readonly<HttpClient>,
  identity: () => ObservationIdentity | null,
  wall: () => number,
): Delivery {
  return {
    send: async (intent) => {
      intent.signal.throwIfAborted();
      const current = identity();
      if (current?.account_id !== intent.body.expected_actor_id)
        throw new DOMException('Observation owner retired', 'AbortError');
      if (
        current.csrf_token === '' ||
        JSON.stringify(intent.body) !== intent.json ||
        new TextEncoder().encode(intent.json).byteLength > 16384 ||
        intent.body.events.length < 1 ||
        intent.body.events.length > 20
      )
        throw new TypeError('Invalid observation intent');
      try {
        const response = await firstValueFrom(
          http
            .post<unknown>('/api/v1/telemetry/events', intent.json, {
              observe: 'response',
              headers: {
                'Content-Type': 'application/json',
                'x-csrf-token': current.csrf_token,
                'idempotency-key': intent.key,
              },
            })
            .pipe(
              takeUntil(fromEvent(intent.signal, 'abort')),
              throwIfEmpty(() => new DOMException('Observation delivery cancelled', 'AbortError')),
            ),
        );
        intent.signal.throwIfAborted();
        // The buffer owns closed receipt validation and exact submitted-ID partition.
        return { kind: 'received', receipt: response.body };
      } catch (error: unknown) {
        intent.signal.throwIfAborted();
        if (error instanceof HttpErrorResponse) {
          // As with canonical transport, a malformed2xx body is an UNKNOWN outcome.
          const status = error.status >= 200 && error.status < 300 ? 0 : error.status;
          const retry = retryAfter(error.headers.get('Retry-After'), wall());
          return {
            kind: 'failed',
            status,
            ...(retry === undefined ? {} : { retryAfterMs: retry }),
          };
        }
        throw error;
      }
    },
  };
}
