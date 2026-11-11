import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import type { HttpRequest, HttpHandlerFn } from '@angular/common/http';
import { throwError } from 'rxjs';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiFailure } from '../../../api-http';
import { transferImage } from './image-transfer';

describe('C03 ephemeral signed transfer', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  const access = '/api/v1/conversations/conversation/image-preparations/image/upload-access';
  const destination = 'https://media.example.test/private-form';
  const file = new Blob(['bytes'], { type: 'image/png' });
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    backend.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
  });
  it('uses bodyless CSRF access, omits cookies and referrer, rejects redirects and returns no ticket', async () => {
    const promise = transferImage(
      http,
      'conversation',
      'image',
      'csrf',
      file,
      new AbortController().signal,
    );
    const request = backend.expectOne(access);
    expect(request.request.body).toBeNull();
    expect(request.request.headers.get('x-csrf-token')).toBe('csrf');
    request.flush({ url: destination, fields: { policy: 'private-policy', key: 'private-key' } });
    const upload = await expectUpload();
    expect(upload.request.credentials).toBe('omit');
    expect(upload.request.withCredentials).toBe(false);
    expect(upload.request.redirect).toBe('error');
    expect(upload.request.referrerPolicy).toBe('no-referrer');
    expect(upload.request.referrer).toBe('');
    const body: unknown = upload.request.body;
    expect(body).toBeInstanceOf(FormData);
    if (!(body instanceof FormData)) throw new Error('Missing multipart form');
    expect(Array.from(body.keys())).toEqual(['policy', 'key', 'file']);
    expect(body.get('file')).toBeInstanceOf(Blob);
    upload.flush('', { status: 204, statusText: 'No Content' });
    await expect(promise).resolves.toBeUndefined();
  });
  async function expectUpload() {
    return vi.waitFor(() => backend.expectOne(destination));
  }
  it.each([
    null,
    {},
    { url: destination, fields: [] },
    { url: destination, fields: null },
    { url: destination, fields: { key: 1 } },
    { url: 'not a url', fields: {} },
    { url: 'file:///private', fields: {} },
    { url: 'https://user:secret@example.test', fields: {} },
    { url: 42, fields: {} },
  ])(
    'rejects malformed access without sending a provider request: %j',
    async (value: Readonly<Record<string, unknown>> | null) => {
      const promise = transferImage(
        http,
        'conversation',
        'image',
        'csrf',
        file,
        new AbortController().signal,
      );
      const checked = expect(promise).rejects.toBeInstanceOf(ApiFailure);
      backend.expectOne(access).flush(value);
      await checked;
      backend.expectNone(destination);
    },
  );
  it('normalizes a provider failure without exposing its body, URL or fields', async () => {
    const promise = transferImage(
      http,
      'conversation',
      'image',
      'csrf',
      file,
      new AbortController().signal,
    );
    const checked = expect(promise).rejects.toMatchObject({
      status: 503,
      code: 'image_transfer_unknown',
    });
    backend.expectOne(access).flush({ url: destination, fields: { policy: 'private-policy' } });
    (await expectUpload()).flush('private provider detail', {
      status: 503,
      statusText: 'Unavailable',
    });
    await checked;
  });
  it('aborts before requesting access', async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(
      transferImage(http, 'conversation', 'image', 'csrf', file, controller.signal),
    ).rejects.toMatchObject({ name: 'AbortError' });
    backend.expectNone(access);
  });
  it('retires a late access response without starting transfer', async () => {
    const controller = new AbortController();
    const promise = transferImage(http, 'conversation', 'image', 'csrf', file, controller.signal);
    const checked = expect(promise).rejects.toMatchObject({ name: 'AbortError' });
    controller.abort();
    backend.expectOne(access).flush({ url: destination, fields: {} });
    await checked;
    backend.expectNone(destination);
  });
  it('unsubscribes the actual in-flight provider HTTP request on retirement', async () => {
    const controller = new AbortController();
    const promise = transferImage(http, 'conversation', 'image', 'csrf', file, controller.signal);
    const checked = expect(promise).rejects.toMatchObject({ name: 'AbortError' });
    backend.expectOne(access).flush({ url: destination, fields: {} });
    const upload = await expectUpload();
    controller.abort();
    await checked;
    expect(upload.cancelled).toBe(true);
  });
  it('normalizes non-HTTP transport failures without exposing the provider detail', async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(
          withInterceptors([
            (request: Readonly<HttpRequest<unknown>>, next: HttpHandlerFn) =>
              request.url === destination
                ? throwError(() => new TypeError('private provider detail'))
                : next(request),
          ]),
        ),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    const promise = transferImage(
      http,
      'conversation',
      'image',
      'csrf',
      file,
      new AbortController().signal,
    );
    const checked = expect(promise).rejects.toMatchObject({
      status: 0,
      code: 'image_transfer_unknown',
    });
    backend.expectOne(access).flush({ url: destination, fields: {} });
    await checked;
  });
  it('unsubscribes when retirement races with provider subscription before the abort listener is attached', async () => {
    const controller = new AbortController();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(
          withInterceptors([
            (request: Readonly<HttpRequest<unknown>>, next: HttpHandlerFn) => {
              const result = next(request);
              if (request.url === destination) controller.abort();
              return result;
            },
          ]),
        ),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    const promise = transferImage(http, 'conversation', 'image', 'csrf', file, controller.signal);
    const checked = expect(promise).rejects.toMatchObject({ name: 'AbortError' });
    backend.expectOne(access).flush({ url: destination, fields: {} });
    const request = await expectUpload();
    await checked;
    expect(request.cancelled).toBe(true);
  });
});
