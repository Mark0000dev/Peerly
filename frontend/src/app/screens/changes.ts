import { HttpErrorResponse, HttpEventType } from '@angular/common/http';
import type { HttpClient, HttpEvent } from '@angular/common/http';
import type { DestroyRef } from '@angular/core';
import type { QueryClient, QueryCacheNotifyEvent } from '@tanstack/angular-query-experimental';
import { Subscription } from 'rxjs';
import { ApiFailure } from '../api-http';
import type { Api } from '../api.generated';
import { sessionOptions } from './session';

type Hint = Readonly<{ readonly cursor: string; readonly reset: boolean; readonly own: boolean }>;

function invalid(): ApiFailure {
  return new ApiFailure(0, 'invalid_change_stream', null);
}

function frame(text: string, actor: string): Hint | null {
  const lines = text.split('\n').filter((line) => line !== '' && !line.startsWith(':'));
  if (lines.length === 0) return null;
  if (lines.length !== 3) throw invalid();
  const fields = Object.fromEntries(
    lines.map((line) => {
      const separator = line.indexOf(':');
      return [line.slice(0, separator), line.slice(separator + 1).replace(/^ /, '')];
    }),
  );
  const id = fields['id'];
  const event = fields['event'];
  const raw = fields['data'];
  if (
    Object.keys(fields).length !== 3 ||
    id === undefined ||
    raw === undefined ||
    !/^(0|[1-9][0-9]{0,18})$/.test(id) ||
    BigInt(id) > 9223372036854775807n
  )
    throw invalid();
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    throw invalid();
  }
  if (typeof data !== 'object' || data === null || Array.isArray(data)) throw invalid();
  if (event === 'reset_required') {
    if (Object.keys(data).length !== 0) throw invalid();
    return { cursor: id, reset: true, own: false };
  }
  if (
    event !== 'resource.changed' ||
    id === '0' ||
    Object.keys(data).length !== 3 ||
    !('resource_type' in data) ||
    typeof data.resource_type !== 'string' ||
    !['account', 'request', 'conversation', 'ai_job'].includes(data.resource_type) ||
    !('resource_id' in data) ||
    typeof data.resource_id !== 'string' ||
    !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(data.resource_id) ||
    !('version' in data) ||
    !(
      data.version === null ||
      (typeof data.version === 'number' && Number.isInteger(data.version) && data.version > 0)
    )
  )
    throw invalid();
  return {
    cursor: id,
    reset: false,
    own: data.resource_type === 'account' && data.resource_id === actor,
  };
}

// HttpClient owns same-origin cookies and cancellation. Each connection is bounded:
// Angular's cumulative partialText must not grow for the lifetime of an open tab.
function connection(
  http: Readonly<HttpClient>,
  actor: string,
  cursor: string | null,
  signal: Readonly<AbortSignal>,
  accept: (hint: Hint) => void,
): Promise<void> {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const subscription = new Subscription();
    let consumed = 0;
    let pending = '';
    let ended = false;
    let errorResponse = false;
    const finish = (error: unknown = null): void => {
      if (ended) return;
      ended = true;
      signal.removeEventListener('abort', cancel);
      subscription.unsubscribe();
      if (error === null) resolve();
      else reject(error instanceof Error ? error : invalid());
    };
    const cancel = (): void => {
      finish();
    };
    const read = (text: string): void => {
      if (text.length < consumed) throw invalid();
      if (text.length > 1_048_576) {
        finish();
        return;
      }
      const combined = (pending + text.slice(consumed)).replaceAll('\r\n', '\n');
      consumed = text.length;
      const parts = combined.split('\n\n');
      if (parts.some((part) => part.length > 4096)) throw invalid();
      pending = parts.at(-1) ?? '';
      for (const part of parts.slice(0, -1)) {
        if (signal.aborted || ended) return;
        const hint = frame(part, actor);
        if (hint !== null) accept(hint);
      }
    };
    signal.addEventListener('abort', cancel, { once: true });
    subscription.add(
      http
        .get('/api/v1/events', {
          observe: 'events',
          responseType: 'text',
          reportDownloadProgress: true,
          headers: cursor === null ? {} : { 'Last-Event-ID': cursor },
        })
        .subscribe({
          next: (event: Readonly<HttpEvent<string>>) => {
            try {
              if (event.type === HttpEventType.ResponseHeader)
                errorResponse = event.status < 200 || event.status >= 300;
              // Angular delivers error-response headers/progress before HttpErrorResponse.
              // Only successful stream bodies are SSE; preserve the actual HTTP failure
              // for the auth/permanent/transient policy instead of treating JSON as wire.
              if (errorResponse) return;
              if (
                (event.type === HttpEventType.ResponseHeader ||
                  event.type === HttpEventType.Response) &&
                event.headers.get('Content-Type')?.split(';')[0]?.trim() !== 'text/event-stream'
              )
                throw invalid();
              if (event.type === HttpEventType.DownloadProgress && event.partialText !== undefined)
                read(event.partialText);
              if (event.type === HttpEventType.Response) {
                if (event.body !== null) read(event.body);
                if (pending.trim() !== '' && !pending.startsWith(':')) throw invalid();
              }
            } catch (error: unknown) {
              finish(error);
            }
          },
          complete: () => {
            finish();
          },
          error: (error: unknown) => {
            finish(
              error instanceof HttpErrorResponse
                ? new ApiFailure(error.status, 'change_stream_unavailable', null)
                : invalid(),
            );
          },
        }),
    );
  });
}

// One native transport per existing content QueryClient. The only retained state is
// its actor/cursor/network lifetime; domain data remains exclusively in Query cache.
export function watchChanges(
  http: Readonly<HttpClient>,
  client: Readonly<QueryClient>,
  destroy: Readonly<DestroyRef>,
): void {
  let owner: string | null = null;
  let cursor: string | null = null;
  let controller: AbortController | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let generation = 0;
  let failures = 0;
  let paused = false;
  // Identify this resource's own authority check, rather than mirroring query data/status.
  let confirmation: symbol | null = null;
  let disposed = false;
  const stop = (): void => {
    generation += 1;
    controller?.abort();
    controller = null;
    clearTimeout(timer);
    timer = undefined;
  };
  const sync = (): void => {
    if (disposed) return;
    const identity = client.getQueryData<Api['schemas']['IdentityResponse'] | null>(['session']);
    const actor = identity?.account_id ?? null;
    if (actor !== owner) {
      stop();
      owner = actor;
      cursor = null;
      failures = 0;
      paused = false;
    }
    const session = client.getQueryState(['session']);
    if (paused && confirmation === null && session?.fetchStatus === 'fetching') paused = false;
    if (
      owner === null ||
      session?.status !== 'success' ||
      session.fetchStatus !== 'idle' ||
      identity?.capabilities.can_use_student_features !== true
    ) {
      stop();
      return;
    }
    if (paused || controller !== null || timer !== undefined) return;
    const actorId = owner;
    const epoch = generation;
    const active = new AbortController();
    controller = active;
    const current = (): boolean => !disposed && epoch === generation && !active.signal.aborted;
    const finished = (error: unknown = null): void => {
      if (!current()) return;
      controller = null;
      if (error instanceof ApiFailure && [401, 403].includes(error.status)) {
        // Confirm identity once. A same-owner denial is not permission to loop
        // stream/auth GETs; a later independent /me read may resume the transport.
        paused = true;
        const token = Symbol();
        confirmation = token;
        void client
          .query(sessionOptions(http, client))
          .catch(() => undefined)
          .then(() => {
            if (confirmation === token) confirmation = null;
          });
        return;
      }
      if (
        error instanceof ApiFailure &&
        (error.code === 'invalid_change_stream' ||
          (error.status >= 400 && error.status < 500 && ![408, 429].includes(error.status)))
      ) {
        paused = true;
        return;
      }
      failures = error === null ? 0 : Math.min(failures + 1, 5);
      timer = setTimeout(
        () => {
          timer = undefined;
          sync();
        },
        Math.min(30_000, 1000 * 2 ** failures),
      );
    };
    void connection(http, actorId, cursor, active.signal, (hint) => {
      if (!current()) return;
      if (!hint.reset && cursor !== null && BigInt(hint.cursor) <= BigInt(cursor)) return;
      cursor = hint.cursor;
      void client.invalidateQueries({ queryKey: ['account', actorId] }, { cancelRefetch: false });
      if (hint.reset || hint.own)
        void client.invalidateQueries({ queryKey: ['session'] }, { cancelRefetch: false });
    }).then(
      () => {
        finished();
      },
      (error: unknown) => {
        finished(error);
      },
    );
  };
  const unsubscribe = client.getQueryCache().subscribe((event: Readonly<QueryCacheNotifyEvent>) => {
    const key: unknown = event.query.queryKey;
    if (Array.isArray(key) && key.length === 1 && key[0] === 'session') sync();
  });
  destroy.onDestroy(() => {
    disposed = true;
    unsubscribe();
    stop();
  });
  sync();
}
