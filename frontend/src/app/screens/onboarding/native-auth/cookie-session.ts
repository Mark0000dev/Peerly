import { signal as resourceSignal } from '@angular/core';
import type { HttpClient } from '@angular/common/http';
import { firstValueFrom, fromEvent, takeUntil, throwIfEmpty } from 'rxjs';
import type { NativeCookieSession } from './native-login';
import type { NativeApiTransport } from '../../../native-transport/transport';
import { NativeTransportFailure } from '../../../native-transport/transport';

// Concrete exchange over the same native transport as /me, writes, JPEGs and SSE.
// The native Set-Cookie path never returns a credential to JS.
export function nativeCookieSession(
  http: Readonly<HttpClient>,
  transport: Readonly<NativeApiTransport>,
  cleanupFailure: (error: Readonly<NativeTransportFailure>) => void,
): NativeCookieSession {
  const proofEpoch = resourceSignal<string | null>(null);
  return {
    begin: async (signal) => {
      signal.throwIfAborted();
      await transport.advance(true);
      signal.throwIfAborted();
      proofEpoch.set(transport.epoch());
    },
    exchange: async (attemptId, verifier, signal) => {
      signal.throwIfAborted();
      const epoch = proofEpoch();
      if (epoch === null || transport.epoch() !== epoch)
        throw new DOMException('Sign-in retired', 'AbortError');
      const retirement = resourceSignal<Promise<void> | null>(null);
      const abort = (): void => {
        if (transport.epoch() !== epoch) return;
        const pending = transport.advance(true);
        retirement.set(pending);
        void pending.catch(() => {
          cleanupFailure(new NativeTransportFailure());
        });
      };
      signal.addEventListener('abort', abort, { once: true });
      try {
        const response = await firstValueFrom(
          http
            .post<unknown>(
              '/api/v1/auth/native/exchange',
              { attempt_id: attemptId, verifier },
              { observe: 'response' },
            )
            .pipe(
              takeUntil(fromEvent(signal, 'abort')),
              throwIfEmpty(() => new DOMException('Request cancelled', 'AbortError')),
            ),
        );
        signal.throwIfAborted();
        if (response.status !== 204 || response.body !== null) throw new NativeTransportFailure();
      } finally {
        signal.removeEventListener('abort', abort);
        proofEpoch.set(null);
        const pending = retirement();
        if (pending !== null) await pending;
      }
    },
  };
}
