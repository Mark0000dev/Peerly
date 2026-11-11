import { HttpClient, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createObservationDelivery } from './observation-delivery';
import type { ObservationIdentity } from './observation-delivery';
import type { Batch } from './observation-contract';
const actor = '00000000-0000-4000-8000-000000000001';
const body: Batch = {
  schema_version: 1,
  expected_actor_id: actor,
  release_id: null,
  events: [
    {
      kind: 'screen.viewed',
      event_id: '00000000-0000-4000-8000-000000000002',
      observed_at: '2026-11-10T10:00:00Z',
      screen: 'chats',
    },
  ],
};
const json = JSON.stringify(body);
const key = '00000000-0000-4000-8000-000000000003';
const path = '/api/v1/telemetry/events';
describe('actual head55 same-origin observation transport', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    backend.verify();
    TestBed.resetTestingModule();
  });
  for (const [header, expected] of [
    ['Tue, 10 Nov 2026 10:00:30 GMT', 30_000],
    ['Tue, 10 Nov 2026 09:59:00 GMT', 0],
    ['unparseable/private', undefined],
  ] as const) {
    it(`honors HTTP-date Retry-After without retaining the raw header (${String(expected ?? 'invalid')})`, async () => {
      const delivery = createObservationDelivery(
        http,
        () => ({ account_id: actor, csrf_token: 'current' }),
        () => Date.parse('2026-11-10T10:00:00Z'),
      );
      const sent = delivery.send({ key, body, json, signal: new AbortController().signal });
      backend
        .expectOne(path)
        .flush({}, { status: 429, statusText: 'Limit', headers: { 'Retry-After': header } });
      expect(await sent).toEqual({
        kind: 'failed',
        status: 429,
        ...(expected === undefined ? {} : { retryAfterMs: expected }),
      });
    });
  }
  it('does not post a retained batch without current canonical CSRF', async () => {
    const delivery = createObservationDelivery(
      http,
      () => ({ account_id: actor, csrf_token: '' }),
      Date.now,
    );
    await expect(
      delivery.send({ key, body, json, signal: new AbortController().signal }),
    ).rejects.toBeInstanceOf(TypeError);
    backend.expectNone(path);
  });
  it('uses exact stable rawJSON/idempotency and reads the current canonical CSRF at every explicit dispatch', async () => {
    let identity: ObservationIdentity = { account_id: actor, csrf_token: 'synthetic-one' };
    const delivery = createObservationDelivery(
      http,
      () => identity,
      () => Date.parse('2026-11-10T10:00:00Z'),
    );
    const first = delivery.send({ key, body, json, signal: new AbortController().signal });
    const request = backend.expectOne(path);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toBe(json);
    expect(request.request.headers.get('idempotency-key')).toBe(key);
    expect(request.request.headers.get('x-csrf-token')).toBe('synthetic-one');
    expect(request.request.headers.get('Content-Type')).toBe('application/json');
    expect(request.request.headers.has('Authorization')).toBe(false);
    expect(request.request.headers.has('Origin')).toBe(false);
    request.flush({}, { status: 503, statusText: 'Unavailable' });
    expect(await first).toEqual({ kind: 'failed', status: 503 });
    identity = { account_id: actor, csrf_token: 'synthetic-two' };
    const replay = delivery.send({ key, body, json, signal: new AbortController().signal });
    const retried = backend.expectOne(path);
    expect(retried.request.body).toBe(json);
    expect(retried.request.headers.get('idempotency-key')).toBe(key);
    expect(retried.request.headers.get('x-csrf-token')).toBe('synthetic-two');
    const receipt = {
      schema_version: 1,
      accepted: body.events.map((event) => event.event_id),
      duplicates: [],
      received_at: '2026-11-10T10:00:00Z',
    };
    retried.flush(receipt);
    expect(await replay).toEqual({ kind: 'received', receipt });
  });
  it('guest/replaced identity cannot post a queued actor body and AbortSignal cancels its native transport', async () => {
    const guest = createObservationDelivery(
      http,
      () => null,
      () => 0,
    );
    await expect(
      guest.send({ key, body, json, signal: new AbortController().signal }),
    ).rejects.toMatchObject({ name: 'AbortError' });
    backend.expectNone(path);
    const replacement = createObservationDelivery(
      http,
      () => ({ account_id: '00000000-0000-4000-8000-000000000009', csrf_token: 'synthetic' }),
      () => 0,
    );
    await expect(
      replacement.send({ key, body, json, signal: new AbortController().signal }),
    ).rejects.toMatchObject({ name: 'AbortError' });
    backend.expectNone(path);
    const controller = new AbortController();
    const active = createObservationDelivery(
      http,
      () => ({ account_id: actor, csrf_token: 'synthetic' }),
      () => 0,
    ).send({ key, body, json, signal: controller.signal });
    const assertion = expect(active).rejects.toMatchObject({ name: 'AbortError' });
    const request = backend.expectOne(path);
    controller.abort();
    await assertion;
    expect(request.cancelled).toBe(true);
  });
  it('returns bounded retry metadata without retaining raw problem bodies or misclassifying malformed2xx as definite failure', async () => {
    const delivery = createObservationDelivery(
      http,
      () => ({ account_id: actor, csrf_token: 'synthetic' }),
      () => Date.parse('2026-11-10T10:00:00Z'),
    );
    const limited = delivery.send({ key, body, json, signal: new AbortController().signal });
    backend
      .expectOne(path)
      .flush(
        { private: 'OTP email chat' },
        { status: 429, statusText: 'Limited', headers: { 'Retry-After': '60' } },
      );
    expect(await limited).toEqual({ kind: 'failed', status: 429, retryAfterMs: 60000 });
    const invalid = delivery.send({ key, body, json, signal: new AbortController().signal });
    const request = backend.expectOne(path);
    request.error(new ProgressEvent('error'), { status: 200, statusText: 'Parsing' });
    expect(await invalid).toEqual({ kind: 'failed', status: 0 });
  });
});
