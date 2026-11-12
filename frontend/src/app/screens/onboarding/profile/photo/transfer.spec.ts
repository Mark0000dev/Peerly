import { HttpClient, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { transferPhoto } from './transfer';

const target = '/api/v1/media/uploads/owned-id/access';
const ticket = {
  url: 'https://storage.invalid/upload',
  fields: { policy: 'opaque-policy', key: 'opaque-object' },
};

describe('private direct photo transfer', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
  });
  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });
  it('keeps application headers on the same-origin access request and sends only a form to storage', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetcher);
    const file = new Blob(['fixture-bytes'], { type: 'image/png' });
    const abort = new AbortController();
    const result = transferPhoto(
      TestBed.inject(HttpClient),
      'owned-id',
      'fixture-csrf',
      file,
      abort.signal,
      () => true,
    );
    const request = TestBed.inject(HttpTestingController).expectOne(target);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toBeNull();
    expect(request.request.headers.get('x-csrf-token')).toBe('fixture-csrf');
    expect(request.request.headers.has('idempotency-key')).toBe(false);
    request.flush(ticket);
    await expect(result).resolves.toBeUndefined();
    expect(fetcher).toHaveBeenCalledOnce();
    const call = fetcher.mock.calls[0];
    expect(call?.[0]).toBe(ticket.url);
    const options = call?.[1];
    expect(options).toMatchObject({
      method: 'POST',
      credentials: 'omit',
      redirect: 'error',
      referrerPolicy: 'no-referrer',
    });
    expect(options?.signal?.aborted).toBe(false);
    abort.abort();
    expect(options?.signal?.aborted).toBe(true);
    expect(options?.headers).toBeUndefined();
    const form = options?.body;
    if (!(form instanceof FormData)) throw new Error('Expected native multipart form');
    expect(Array.from(form.keys())).toEqual(['policy', 'key', 'file']);
    expect(form.get('policy')).toBe(ticket.fields.policy);
    const uploaded = form.get('file');
    if (!(uploaded instanceof File)) throw new Error('Expected native file');
    expect(await uploaded.text()).toBe('fixture-bytes');
    expect(uploaded.type).toBe('image/png');
  });
  it('does not even request a ticket when already cancelled', async () => {
    const abort = new AbortController();
    abort.abort();
    await expect(
      transferPhoto(
        TestBed.inject(HttpClient),
        'owned-id',
        'fixture',
        new Blob(),
        abort.signal,
        () => true,
      ),
    ).rejects.toMatchObject({ name: 'AbortError' });
    TestBed.inject(HttpTestingController).expectNone(target);
  });
  it('does not transfer after cancellation while the access request was pending', async () => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetcher);
    const abort = new AbortController();
    const result = transferPhoto(
      TestBed.inject(HttpClient),
      'owned-id',
      'fixture',
      new Blob(),
      abort.signal,
      () => true,
    );
    const rejected = expect(result).rejects.toMatchObject({ name: 'AbortError' });
    abort.abort();
    TestBed.inject(HttpTestingController).expectOne(target).flush(ticket);
    await rejected;
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('rejects an unsafe ticket before sending a file', async () => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetcher);
    const result = transferPhoto(
      TestBed.inject(HttpClient),
      'owned-id',
      'fixture',
      new Blob(),
      new AbortController().signal,
      () => true,
    );
    const rejected = expect(result).rejects.toMatchObject({ code: 'invalid_response' });
    TestBed.inject(HttpTestingController)
      .expectOne(target)
      .flush({ ...ticket, url: 'http://storage.invalid' });
    await rejected;
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('bounds a stalled native upload without claiming that S3 rejected its bytes', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn<typeof fetch>().mockImplementation(
      (_url: Readonly<RequestInfo | URL>, options?: Readonly<RequestInit>) =>
        new Promise((_resolve, reject) => {
          options?.signal?.addEventListener(
            'abort',
            () => {
              reject(new DOMException('Aborted', 'AbortError'));
            },
            { once: true },
          );
        }),
    );
    vi.stubGlobal('fetch', fetcher);
    const result = transferPhoto(
      TestBed.inject(HttpClient),
      'owned-id',
      'fixture',
      new Blob(),
      new AbortController().signal,
      () => true,
    );
    const rejected = expect(result).rejects.toMatchObject({
      status: 0,
      code: 'photo_transfer_unknown',
    });
    TestBed.inject(HttpTestingController).expectOne(target).flush(ticket);
    await vi.advanceTimersByTimeAsync(90_000);
    await rejected;
    expect(fetcher).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });
  it('reduces provider network failures to safe uncertain metadata', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockRejectedValue(new TypeError('sensitive signed URL')),
    );
    const result = transferPhoto(
      TestBed.inject(HttpClient),
      'owned-id',
      'fixture',
      new Blob(),
      new AbortController().signal,
      () => true,
    );
    const rejected = expect(result).rejects.toMatchObject({
      code: 'photo_transfer_unknown',
      status: 0,
    });
    TestBed.inject(HttpTestingController).expectOne(target).flush(ticket);
    await rejected;
  });
  it('never copies a failed storage response body into an application error', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response('PRIVATE STORAGE DETAILS', { status: 403 })),
    );
    const result = transferPhoto(
      TestBed.inject(HttpClient),
      'owned-id',
      'fixture',
      new Blob(),
      new AbortController().signal,
      () => true,
    );
    const rejected = expect(result).rejects.toMatchObject({
      code: 'photo_transfer_failed',
      status: 403,
    });
    TestBed.inject(HttpTestingController).expectOne(target).flush(ticket);
    await rejected;
  });
  it('distinguishes an actual transfer abort from an unknown network outcome', async () => {
    const abort = new AbortController();
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockImplementation(() => {
        abort.abort();
        return Promise.reject(new TypeError('cancelled'));
      }),
    );
    const result = transferPhoto(
      TestBed.inject(HttpClient),
      'owned-id',
      'fixture',
      new Blob(),
      abort.signal,
      () => true,
    );
    const rejected = expect(result).rejects.toMatchObject({ name: 'AbortError' });
    TestBed.inject(HttpTestingController).expectOne(target).flush(ticket);
    await rejected;
  });
  it('preserves unexpected programming errors', async () => {
    const failure = new Error('unexpected');
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockRejectedValue(failure));
    const result = transferPhoto(
      TestBed.inject(HttpClient),
      'owned-id',
      'fixture',
      new Blob(),
      new AbortController().signal,
      () => true,
    );
    const rejected = expect(result).rejects.toBe(failure);
    TestBed.inject(HttpTestingController).expectOne(target).flush(ticket);
    await rejected;
  });
});
