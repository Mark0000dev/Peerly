import {
  HttpErrorResponse,
  HttpEventType,
  HttpHeaderResponse,
  HttpHeaders,
  HttpResponse,
} from '@angular/common/http';
import type {
  HttpEvent,
  HttpInterceptorFn,
  HttpRequest,
  HttpHandlerFn,
} from '@angular/common/http';
import { computed, signal } from '@angular/core';
import { Observable } from 'rxjs';
import type { Subscriber } from 'rxjs';

interface Listener {
  readonly remove: () => Promise<void>;
}
export interface NativeTransportPlugin {
  readonly configuration: () => Promise<unknown>;
  readonly advance: (
    input: Readonly<{ readonly clearSession: boolean }>,
  ) => Promise<Readonly<{ readonly epoch: string }>>;
  readonly addListener: (name: 'response', accept: (event: unknown) => void) => Promise<Listener>;
  readonly start: (
    input: Readonly<{
      readonly id: string;
      readonly epoch: string;
      readonly path: string;
      readonly method: string;
      readonly mode: 'text' | 'binary' | 'stream';
      readonly headers: Readonly<Record<string, string>>;
      readonly body: string;
    }>,
  ) => Promise<void>;
  readonly cancel: (
    input: Readonly<{ readonly id: string; readonly epoch: string }>,
  ) => Promise<void>;
}

export class NativeTransportFailure extends Error {
  public constructor() {
    super('Native transport unavailable');
  }
}

function httpFailure(): HttpErrorResponse {
  // Preserve existing status-zero uncertain-write handling without a raw URL/error.
  return new HttpErrorResponse({
    status: 0,
    statusText: 'Native transport unavailable',
    error: null,
  });
}

const responseHeaderNames = new Set([
  'content-type',
  'retry-after',
  'etag',
  'cache-control',
  'x-request-id',
]);
const maxBytes = 16 * 1024 * 1024;

function decode(encoded: string): Uint8Array<ArrayBuffer> {
  if (encoded.length > Math.ceil(maxBytes / 3) * 4) throw new NativeTransportFailure();
  return Uint8Array.from(atob(encoded), (character) => character.charCodeAt(0));
}

function encode(bytes: Readonly<Uint8Array>): string {
  if (bytes.length > maxBytes) throw new NativeTransportFailure();
  return btoa(
    Array.from({ length: Math.ceil(bytes.length / 8192) }, (_, index) =>
      String.fromCharCode(...bytes.slice(index * 8192, (index + 1) * 8192)),
    ).join(''),
  );
}

async function requestBody(request: Readonly<HttpRequest<unknown>>): Promise<string> {
  const body = request.serializeBody();
  if (body === null) return '';
  if (typeof body === 'string') return encode(new TextEncoder().encode(body));
  if (body instanceof ArrayBuffer) return encode(new Uint8Array(body));
  if (body instanceof Blob) return encode(new Uint8Array(await body.arrayBuffer()));
  throw new NativeTransportFailure(); // API FormData is not used; signed uploads go to next().
}

function headers(value: unknown): HttpHeaders {
  if (typeof value !== 'object' || value === null || Array.isArray(value))
    throw new NativeTransportFailure();
  return Object.entries(value).reduce(
    (result: Readonly<HttpHeaders>, [key, item]: readonly [string, unknown]) => {
      if (!responseHeaderNames.has(key.toLowerCase()) || typeof item !== 'string')
        throw new NativeTransportFailure();
      return result.set(key, item);
    },
    new HttpHeaders(),
  );
}

// This holds transport lifetimes only. Session/domain data stay in TanStack Query.
export class NativeApiTransport {
  private readonly state = signal<Readonly<{
    readonly epoch: string;
    readonly controller: AbortController;
  }> | null>(null);
  private readonly generation = signal('');
  public readonly epoch = computed(() => this.state()?.epoch ?? null);
  public constructor(
    private readonly plugin: Readonly<NativeTransportPlugin>,
    private readonly cleanupFailure: (error: Readonly<NativeTransportFailure>) => void,
  ) {}

  public async advance(clearSession: boolean): Promise<void> {
    const generation = crypto.randomUUID();
    this.generation.set(generation);
    this.state()?.controller.abort();
    this.state.set(null);
    const result = await this.plugin.advance({ clearSession });
    if (this.generation() !== generation) throw new DOMException('Epoch retired', 'AbortError');
    if (!/^[a-f0-9-]{36}$/.test(result.epoch)) throw new NativeTransportFailure();
    this.state.set({ epoch: result.epoch, controller: new AbortController() });
  }

  public readonly intercept: HttpInterceptorFn = (
    request: Readonly<HttpRequest<unknown>>,
    next: HttpHandlerFn,
  ) => {
    // Only the logical same-origin API namespace is native. S3 remains credentials:omit.
    if (!request.url.startsWith('/api/v1/')) return next(request);
    return this.handle(request);
  };

  private handle(request: Readonly<HttpRequest<unknown>>): Observable<HttpEvent<unknown>> {
    return new Observable((subscriber: Readonly<Subscriber<HttpEvent<unknown>>>) => {
      const state = this.state();
      if (state === null) {
        subscriber.error(httpFailure());
        return;
      }
      const id = crypto.randomUUID();
      let listener: Listener | null = null;
      const stopped = new AbortController();
      const isStopped = (): boolean => stopped.signal.aborted;
      let status: number | null = null;
      let responseHeaders = new HttpHeaders();
      let partial = '';
      let completingLogout = false;
      const decoder = new TextDecoder('utf-8', { fatal: true });
      const reportCleanup = (): void => {
        this.cleanupFailure(new NativeTransportFailure());
      };
      const abort = (): void => {
        if (!completingLogout)
          subscriber.error(new DOMException('Request cancelled', 'AbortError'));
      };
      state.controller.signal.addEventListener('abort', abort, { once: true });
      const stream = request.reportDownloadProgress && request.responseType === 'text';
      const accept = (event: unknown): void => {
        if (
          stopped.signal.aborted ||
          typeof event !== 'object' ||
          event === null ||
          !('id' in event) ||
          event.id !== id ||
          !('epoch' in event) ||
          event.epoch !== state.epoch
        )
          return;
        try {
          if (!('type' in event)) throw new NativeTransportFailure();
          if (event.type === 'error') throw new NativeTransportFailure();
          if (event.type === 'headers') {
            if (
              !('status' in event) ||
              typeof event.status !== 'number' ||
              !Number.isInteger(event.status) ||
              event.status < 100 ||
              event.status > 599 ||
              !('headers' in event) ||
              status !== null
            )
              throw new NativeTransportFailure();
            status = event.status;
            responseHeaders = headers(event.headers);
            subscriber.next(new HttpHeaderResponse({ status, headers: responseHeaders }));
          } else if (event.type === 'chunk') {
            if (!stream || status === null || !('body' in event) || typeof event.body !== 'string')
              throw new NativeTransportFailure();
            partial += decoder.decode(decode(event.body), { stream: true });
            if (partial.length > 1_048_576) throw new NativeTransportFailure();
            subscriber.next({
              type: HttpEventType.DownloadProgress,
              loaded: partial.length,
              partialText: partial,
            });
          } else if (event.type === 'complete') {
            if (status === null || !('body' in event) || typeof event.body !== 'string')
              throw new NativeTransportFailure();
            const bytes = decode(event.body);
            const text =
              request.responseType === 'blob' || request.responseType === 'arraybuffer'
                ? ''
                : partial + decoder.decode(bytes);
            const success = status >= 200 && status < 300;
            const body: unknown =
              request.responseType === 'blob'
                ? new Blob([bytes], {
                    type: responseHeaders.get('content-type') ?? '',
                  })
                : request.responseType === 'arraybuffer'
                  ? bytes.buffer
                  : request.responseType === 'json'
                    ? text === ''
                      ? null
                      : JSON.parse(text)
                    : text;
            if (!success)
              subscriber.error(
                new HttpErrorResponse({
                  status,
                  headers: responseHeaders,
                  error: body,
                }),
              );
            else {
              const responseStatus = status;
              const finish = (): void => {
                subscriber.next(
                  new HttpResponse({ status: responseStatus, headers: responseHeaders, body }),
                );
                subscriber.complete();
              };
              if (request.url === '/api/v1/auth/logout') {
                completingLogout = true;
                void this.advance(true)
                  .then(finish)
                  .catch(() => {
                    subscriber.error(httpFailure());
                  });
              } else {
                finish();
              }
            }
          } else throw new NativeTransportFailure();
        } catch {
          subscriber.error(httpFailure());
        }
      };
      const start = async (): Promise<void> => {
        const body = await requestBody(request);
        if (isStopped()) return;
        const registered = await this.plugin.addListener('response', accept);
        listener = registered;
        if (isStopped()) {
          await registered.remove();
          listener = null;
          return;
        }
        const contentType = request.detectContentTypeHeader();
        const outgoing = request.headers.keys().reduce<Record<string, string>>(
          (result: Readonly<Record<string, string>>, key) => ({
            ...result,
            [key.toLowerCase()]: request.headers.get(key) ?? '',
          }),
          {},
        );
        subscriber.next({ type: HttpEventType.Sent });
        await this.plugin.start({
          id,
          epoch: state.epoch,
          path: request.urlWithParams,
          method: request.method,
          mode: stream
            ? 'stream'
            : request.responseType === 'blob' || request.responseType === 'arraybuffer'
              ? 'binary'
              : 'text',
          body,
          headers: contentType === null ? outgoing : { 'content-type': contentType, ...outgoing },
        });
      };
      void start().catch(() => {
        subscriber.error(httpFailure());
      });
      return () => {
        stopped.abort();
        state.controller.signal.removeEventListener('abort', abort);
        void this.plugin.cancel({ id, epoch: state.epoch }).catch(reportCleanup);
        if (listener !== null) void listener.remove().catch(reportCleanup);
      };
    });
  }
}
