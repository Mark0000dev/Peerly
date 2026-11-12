import {
  HttpClient,
  HttpHeaders,
  HttpEventType,
  HttpRequest,
  HttpResponse,
  provideHttpClient,
  withInterceptors,
} from '@angular/common/http';
import type { HttpEvent } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { firstValueFrom, of, toArray } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';
import { NativeApiTransport, NativeTransportFailure } from './transport';
import type { NativeTransportPlugin } from './transport';
import { nativeCookieSession } from '../screens/onboarding/native-auth/cookie-session';

const epoch = '00000000-0000-4000-8000-000000000001';

function fixture() {
  const callback = signal<((event: unknown) => void) | null>(null);
  const request = signal<Parameters<NativeTransportPlugin['start']>[0] | null>(null);
  const remove = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
  const cancel = vi.fn<NativeTransportPlugin['cancel']>().mockResolvedValue(undefined);
  const advance = vi.fn<NativeTransportPlugin['advance']>().mockResolvedValue({ epoch });
  const start = vi.fn(async (input: Parameters<NativeTransportPlugin['start']>[0]) => {
    request.set(input);
    return Promise.resolve();
  });
  const addListener = vi.fn<NativeTransportPlugin['addListener']>(async (_name, accept) => {
    callback.set(accept);
    return Promise.resolve({ remove });
  });
  const plugin: NativeTransportPlugin = {
    configuration: () => Promise.resolve({}),
    advance,
    cancel,
    start,
    addListener,
  };
  const failure = vi.fn();
  const transport = new NativeApiTransport(plugin, failure);
  const emit = (type: string, fields: Readonly<Record<string, unknown>> = {}): void => {
    callback()?.({ id: request()?.id, epoch, type, ...fields });
  };
  return {
    transport,
    emit,
    callback,
    request,
    remove,
    cancel,
    advance,
    start,
    failure,
    addListener,
  };
}

async function waitRequest(context: Readonly<ReturnType<typeof fixture>>): Promise<void> {
  await vi.waitFor(() => {
    expect(context.request()).not.toBeNull();
  });
}

function responseBody(text: string): string {
  return btoa(text);
}

describe('native API transport contract (not device interoperability)', () => {
  it('requires initialized epoch and delegates unsigned uploads unchanged', async () => {
    const context = fixture();
    const denied = firstValueFrom(
      context.transport.intercept(new HttpRequest('GET', '/api/v1/me'), () => of()),
    );
    await expect(denied).rejects.toMatchObject({ status: 0 });
    const request = new HttpRequest('POST', 'https://uploads.example.test/target', new FormData(), {
      withCredentials: false,
    });
    const next = vi.fn(() => of(new HttpResponse({ status: 204 })));
    await firstValueFrom(context.transport.intercept(request, next));
    expect(next).toHaveBeenCalledWith(request);
    expect(context.start).not.toHaveBeenCalled();
  });

  it('maps ordinary JSON, Origin-independent logical paths and cleans resources', async () => {
    const context = fixture();
    await context.transport.advance(false);
    const result = firstValueFrom(
      context.transport
        .intercept(
          new HttpRequest(
            'POST',
            '/api/v1/example',
            { intent: 'synthetic' },
            {
              headers: new HttpHeaders({
                'x-csrf-token': 'synthetic-csrf',
                traceparent: '00-' + 'a'.repeat(32) + '-' + 'b'.repeat(16) + '-01',
                'x-action-id': epoch,
                'idempotency-key': 'synthetic-intent',
              }),
            },
          ),
          () => of(),
        )
        .pipe(toArray()),
    );
    await waitRequest(context);
    expect(context.request()?.path).toBe('/api/v1/example');
    expect(context.request()?.headers['content-type']).toBe('application/json');
    expect(context.request()?.headers['x-csrf-token']).toBe('synthetic-csrf');
    expect(context.request()?.headers['x-action-id']).toBe(epoch);
    expect(context.request()?.headers['traceparent']).toMatch(/^00-/);
    expect(context.request()?.headers['idempotency-key']).toBe('synthetic-intent');
    expect(atob(context.request()?.body ?? '')).toBe('{"intent":"synthetic"}');
    context.emit('headers', {
      status: 200,
      headers: { 'content-type': 'application/json', 'x-request-id': epoch },
    });
    context.emit('complete', { body: responseBody('{"ok":true}') });
    const events = await result;
    const final = events.at(-1);
    expect(final instanceof HttpResponse && final.body).toEqual({ ok: true });
    expect(final instanceof HttpResponse && final.headers.get('x-request-id')).toBe(epoch);
    await vi.waitFor(() => {
      expect(context.remove).toHaveBeenCalledOnce();
    });
    expect(context.cancel).toHaveBeenCalledOnce();
  });

  it('streams split UTF-8 and preserves cumulative SSE progress', async () => {
    const context = fixture();
    await context.transport.advance(false);
    const result = firstValueFrom(
      context.transport
        .intercept(
          new HttpRequest('GET', '/api/v1/events', {
            responseType: 'text',
            reportDownloadProgress: true,
          }),
          () => of(),
        )
        .pipe(toArray()),
    );
    await waitRequest(context);
    context.emit('headers', { status: 200, headers: { 'content-type': 'text/event-stream' } });
    context.emit('chunk', { body: btoa(String.fromCharCode(0xe2)) });
    context.emit('chunk', { body: btoa(String.fromCharCode(0x82, 0xac, 0x0a, 0x0a)) });
    context.emit('complete', { body: '' });
    const events = await result;
    const text = events
      .filter(
        (event: Readonly<HttpEvent<unknown>>) => event.type === HttpEventType.DownloadProgress,
      )
      .at(-1);
    expect(text?.partialText).toBe('€\n\n');
    const final = events.at(-1);
    expect(final instanceof HttpResponse && final.body).toBe('€\n\n');
  });

  it('returns JPEG bytes without interpreting them as UTF-8', async () => {
    const context = fixture();
    await context.transport.advance(false);
    const result = firstValueFrom(
      context.transport
        .intercept(new HttpRequest('GET', '/api/v1/photo', { responseType: 'blob' }), () => of())
        .pipe(toArray()),
    );
    await waitRequest(context);
    context.emit('headers', { status: 200, headers: { 'content-type': 'image/jpeg' } });
    context.emit('complete', { body: btoa(String.fromCharCode(255, 216, 255)) });
    const last = (await result).at(-1);
    if (!(last instanceof HttpResponse) || !(last.body instanceof Blob))
      throw new Error('Expected binary response');
    expect(Array.from(new Uint8Array(await last.body.arrayBuffer()))).toEqual([255, 216, 255]);
  });

  it('aborts old actor requests and ignores their late bodies', async () => {
    const context = fixture();
    await context.transport.advance(false);
    const result = firstValueFrom(
      context.transport.intercept(new HttpRequest('GET', '/api/v1/me'), () => of()).pipe(toArray()),
    );
    const rejected = expect(result).rejects.toMatchObject({ name: 'AbortError' });
    await waitRequest(context);
    await context.transport.advance(true);
    context.emit('headers', { status: 200, headers: {} });
    context.emit('complete', { body: responseBody('{"old_actor":true}') });
    await rejected;
    expect(context.advance).toHaveBeenLastCalledWith({ clearSession: true });
  });

  it.each([
    ['headers', { status: 200, headers: { 'set-cookie': 'never-enter-js' } }],
    ['headers', { status: 900, headers: {} }],
    ['complete', { body: '' }],
    ['chunk', { body: '' }],
    ['error', {}],
    ['unexpected', {}],
  ])(
    'rejects malformed or secret-bearing %s envelopes',
    async (type: string, data: Readonly<Record<string, unknown>>) => {
      const context = fixture();
      await context.transport.advance(false);
      const result = firstValueFrom(
        context.transport
          .intercept(new HttpRequest('GET', '/api/v1/me'), () => of())
          .pipe(toArray()),
      );
      const rejected = expect(result).rejects.toMatchObject({ status: 0 });
      await waitRequest(context);
      context.emit(type, data);
      await rejected;
    },
  );

  it('preserves ordinary HTTP authority errors', async () => {
    const context = fixture();
    await context.transport.advance(false);
    const result = firstValueFrom(
      context.transport.intercept(new HttpRequest('GET', '/api/v1/me'), () => of()).pipe(toArray()),
    );
    const rejected = expect(result).rejects.toMatchObject({
      status: 401,
      error: { code: 'unauthenticated' },
    });
    await waitRequest(context);
    context.emit('headers', { status: 401, headers: { 'content-type': 'application/json' } });
    context.emit('complete', { body: responseBody('{"code":"unauthenticated"}') });
    await rejected;
  });

  it('concrete exchange uses HttpClient and never returns session credentials', async () => {
    const context = fixture();
    await context.transport.advance(true);
    TestBed.configureTestingModule({
      providers: [provideHttpClient(withInterceptors([context.transport.intercept]))],
    });
    const cookies = nativeCookieSession(
      TestBed.inject(HttpClient),
      context.transport,
      context.failure,
    );
    await cookies.begin(new AbortController().signal);
    const result = cookies.exchange(
      'synthetic-attempt',
      'synthetic-verifier',
      new AbortController().signal,
    );
    await waitRequest(context);
    expect(context.request()?.path).toBe('/api/v1/auth/native/exchange');
    context.emit('headers', { status: 204, headers: {} });
    context.emit('complete', { body: '' });
    await expect(result).resolves.toBeUndefined();
  });

  it('cancelling concrete exchange retires native cookie epoch', async () => {
    const context = fixture();
    await context.transport.advance(true);
    TestBed.configureTestingModule({
      providers: [provideHttpClient(withInterceptors([context.transport.intercept]))],
    });
    const cookies = nativeCookieSession(
      TestBed.inject(HttpClient),
      context.transport,
      context.failure,
    );
    const controller = new AbortController();
    await cookies.begin(controller.signal);
    const result = cookies.exchange('synthetic-attempt', 'synthetic-verifier', controller.signal);
    const rejected = expect(result).rejects.toMatchObject({ name: 'AbortError' });
    await waitRequest(context);
    controller.abort();
    await rejected;
    expect(context.advance).toHaveBeenCalledTimes(3);
    expect(context.advance).toHaveBeenLastCalledWith({ clearSession: true });
  });
});

it.each([new Blob(['synthetic']), new TextEncoder().encode('synthetic').buffer])(
  'serializes in-memory API request bytes and returns array buffers',
  async (body) => {
    const context = fixture();
    await context.transport.advance(false);
    const result = firstValueFrom(
      context.transport
        .intercept(
          new HttpRequest('POST', '/api/v1/example', body, { responseType: 'arraybuffer' }),
          () => of(),
        )
        .pipe(toArray()),
    );
    await waitRequest(context);
    expect(atob(context.request()?.body ?? '')).toBe('synthetic');
    context.emit('headers', { status: 200, headers: {} });
    context.emit('complete', { body: btoa('ok') });
    const final = (await result).at(-1);
    if (!(final instanceof HttpResponse) || !(final.body instanceof ArrayBuffer))
      throw new Error('Expected bytes');
    expect(new TextDecoder().decode(final.body)).toBe('ok');
  },
);

it.each([new FormData(), 'x'.repeat(16 * 1024 * 1024 + 1)])(
  'rejects unsupported or oversized API bodies before native dispatch',
  async (body) => {
    const context = fixture();
    await context.transport.advance(false);
    const result = firstValueFrom(
      context.transport.intercept(new HttpRequest('POST', '/api/v1/example', body), () => of()),
    );
    await expect(result).rejects.toMatchObject({ status: 0 });
    expect(context.start).not.toHaveBeenCalled();
  },
);

it('rejects invalid epochs and prevents earlier initialization from replacing a newer epoch', async () => {
  const context = fixture();
  context.advance.mockResolvedValueOnce({ epoch: 'invalid' });
  await expect(context.transport.advance(false)).rejects.toBeInstanceOf(NativeTransportFailure);
  const resolve = signal<((value: Readonly<{ readonly epoch: string }>) => void) | null>(null);
  const pending = new Promise<Readonly<{ readonly epoch: string }>>((accept) => {
    resolve.set(accept);
  });
  context.advance.mockImplementationOnce(async () => await pending);
  const original = context.transport.advance(false);
  const rejected = expect(original).rejects.toMatchObject({ name: 'AbortError' });
  await context.transport.advance(true);
  resolve()?.({ epoch });
  await rejected;
});

it('releases a listener registered after the actor has retired', async () => {
  const context = fixture();
  await context.transport.advance(false);
  context.addListener.mockImplementationOnce(() => {
    subscription.unsubscribe();
    return Promise.resolve({ remove: context.remove });
  });
  const subscription = context.transport
    .intercept(new HttpRequest('GET', '/api/v1/me'), () => of())
    .subscribe();
  await vi.waitFor(() => {
    expect(context.remove).toHaveBeenCalledOnce();
  });
  expect(context.start).not.toHaveBeenCalled();
});

it('never starts a request unsubscribed during body serialization', async () => {
  const context = fixture();
  await context.transport.advance(false);
  const subscription = context.transport
    .intercept(new HttpRequest('GET', '/api/v1/me'), () => of())
    .subscribe();
  subscription.unsubscribe();
  await vi.waitFor(() => {
    expect(context.cancel).toHaveBeenCalledOnce();
  });
  expect(context.start).not.toHaveBeenCalled();
});

it('surfaces cleanup failures as fixed metadata errors', async () => {
  const context = fixture();
  await context.transport.advance(false);
  context.remove.mockRejectedValueOnce(new Error('synthetic private error'));
  const result = firstValueFrom(
    context.transport.intercept(new HttpRequest('GET', '/api/v1/me'), () => of()).pipe(toArray()),
  );
  await waitRequest(context);
  context.emit('headers', { status: 200, headers: {} });
  context.emit('complete', { body: btoa('{}') });
  await result;
  await vi.waitFor(() => {
    expect(context.failure).toHaveBeenCalledWith(new NativeTransportFailure());
  });
});

it('ignores unrelated native responses and rejects invalid JSON and oversized response envelopes', async () => {
  for (const encoded of [
    btoa('invalid JSON'),
    'a'.repeat(Math.ceil((16 * 1024 * 1024) / 3) * 4 + 1),
  ]) {
    const context = fixture();
    await context.transport.advance(false);
    const result = firstValueFrom(
      context.transport.intercept(new HttpRequest('GET', '/api/v1/me'), () => of()).pipe(toArray()),
    );
    const rejected = expect(result).rejects.toMatchObject({ status: 0 });
    await waitRequest(context);
    context.callback()?.(null);
    context.callback()?.({ id: 'other', epoch, type: 'complete', body: '' });
    context.emit('headers', { status: 200, headers: {} });
    context.emit('complete', { body: encoded });
    await rejected;
  }
});

it('rejects oversize cumulative streams', async () => {
  const context = fixture();
  await context.transport.advance(false);
  const result = firstValueFrom(
    context.transport
      .intercept(
        new HttpRequest('GET', '/api/v1/events', {
          responseType: 'text',
          reportDownloadProgress: true,
        }),
        () => of(),
      )
      .pipe(toArray()),
  );
  const rejected = expect(result).rejects.toMatchObject({ status: 0 });
  await waitRequest(context);
  context.emit('headers', { status: 200, headers: { 'content-type': 'text/event-stream' } });
  context.emit('chunk', { body: btoa('x'.repeat(1_048_577)) });
  await rejected;
});

it('does not classify a nonempty exchange response as successful session establishment', async () => {
  const context = fixture();
  await context.transport.advance(true);
  TestBed.configureTestingModule({
    providers: [provideHttpClient(withInterceptors([context.transport.intercept]))],
  });
  const cookies = nativeCookieSession(
    TestBed.inject(HttpClient),
    context.transport,
    context.failure,
  );
  const signal = new AbortController().signal;
  await cookies.begin(signal);
  const result = cookies.exchange('synthetic-attempt', 'synthetic-verifier', signal);
  const rejected = expect(result).rejects.toBeInstanceOf(NativeTransportFailure);
  await waitRequest(context);
  context.emit('headers', { status: 200, headers: {} });
  context.emit('complete', { body: btoa('{"unexpected":true}') });
  await rejected;
});

it('reports native cookie retirement failure without returning a token or private error', async () => {
  const context = fixture();
  await context.transport.advance(true);
  TestBed.configureTestingModule({
    providers: [provideHttpClient(withInterceptors([context.transport.intercept]))],
  });
  const cookies = nativeCookieSession(
    TestBed.inject(HttpClient),
    context.transport,
    context.failure,
  );
  const controller = new AbortController();
  await cookies.begin(controller.signal);
  const result = cookies.exchange('synthetic-attempt', 'synthetic-verifier', controller.signal);
  const rejected = expect(result).rejects.toBeInstanceOf(NativeTransportFailure);
  await waitRequest(context);
  context.advance.mockRejectedValueOnce(new NativeTransportFailure());
  controller.abort();
  await rejected;
  expect(context.failure).toHaveBeenCalledWith(new NativeTransportFailure());
});

it('retires native cookies and pending actor reads before publishing successful logout', async () => {
  const context = fixture();
  await context.transport.advance(false);
  const result = firstValueFrom(
    context.transport
      .intercept(new HttpRequest('POST', '/api/v1/auth/logout', null), () => of())
      .pipe(toArray()),
  );
  await waitRequest(context);
  context.emit('headers', { status: 204, headers: {} });
  context.emit('complete', { body: '' });
  const events = await result;
  expect(
    events.some(
      (event: Readonly<HttpEvent<unknown>>) =>
        event instanceof HttpResponse && event.status === 204,
    ),
  ).toBe(true);
  expect(context.advance).toHaveBeenLastCalledWith({ clearSession: true });
});

it('rejects an exchange from a retired proof epoch without making a request', async () => {
  const context = fixture();
  TestBed.configureTestingModule({
    providers: [provideHttpClient(withInterceptors([context.transport.intercept]))],
  });
  const cookies = nativeCookieSession(
    TestBed.inject(HttpClient),
    context.transport,
    context.failure,
  );
  const signal = new AbortController().signal;
  await cookies.begin(signal);
  context.advance.mockResolvedValueOnce({ epoch: '00000000-0000-4000-8000-000000000099' });
  await context.transport.advance(false);
  await expect(
    cookies.exchange('synthetic-attempt', 'synthetic-verifier', signal),
  ).rejects.toMatchObject({ name: 'AbortError' });
  expect(context.start).not.toHaveBeenCalled();
});
