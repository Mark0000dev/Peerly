import type { HttpClient } from '@angular/common/http';
import type { Query, QueryClient } from '@tanstack/angular-query-experimental';
import type { NativeAuthBoundary } from './native-login';
import { NativeLoginFailure } from './native-login';
import { sessionOptions } from '../../session';

// Reuse the actual shared canonical query and actor keys; no native identity store.
export function nativeQueryBoundary(
  http: Readonly<HttpClient>,
  client: Readonly<QueryClient>,
  cleanupFailure: (error: Readonly<NativeLoginFailure>) => void,
): NativeAuthBoundary {
  return {
    retirePrivateQueries: async (signal) => {
      signal.throwIfAborted();
      await client.cancelQueries({
        predicate: (query: Readonly<Query>) =>
          query.queryKey[0] === 'account' || query.queryKey[0] === 'session',
      });
      client.removeQueries({
        predicate: (query: Readonly<Query>) => query.queryKey[0] === 'account',
      });
      signal.throwIfAborted();
    },
    revalidateSession: async (signal) => {
      signal.throwIfAborted();
      const abort = (): void => {
        void client.cancelQueries({ queryKey: ['session'], exact: true }).catch(() => {
          cleanupFailure(new NativeLoginFailure('unavailable'));
        });
      };
      signal.addEventListener('abort', abort, { once: true });
      try {
        const identity = await client.query(sessionOptions(http, client));
        signal.throwIfAborted();
        if (identity === null) throw new NativeLoginFailure('unavailable');
      } catch (error: unknown) {
        signal.throwIfAborted();
        throw error;
      } finally {
        signal.removeEventListener('abort', abort);
      }
    },
  };
}
