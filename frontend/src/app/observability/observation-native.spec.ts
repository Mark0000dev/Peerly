import { TestBed } from '@angular/core/testing';
import {
  provideHttpClient,
  withInterceptors,
  HttpClient,
  HttpContext,
  HttpHeaders,
  HttpResponse,
} from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { firstValueFrom } from 'rxjs';
import { CLIENT_OBSERVATIONS, ObservationErrorHandler } from './observation-errors';
import { CLIENT_ACTION } from './observation-context';
import {
  observationInterceptor,
  observedApi,
  publicHttpRoute,
  traceparent,
} from './observation-http';
import { performanceValue } from './observation-performance';
import type { Epoch, ObservationInput, ObservationSink } from './observation-contract';
const id = '00000000-0000-4000-8000-000000000001';
describe('native client telemetry integration boundaries', () => {
  let backend: HttpTestingController;
  let http: HttpClient;
  let currentEpoch: Epoch | null;
  let observed: readonly ObservationInput[] = [];
  beforeEach(() => {
    currentEpoch = { id: 1, startedAt: 0 };
    observed = [];
    const sink: ObservationSink = {
      observe: (input) => {
        observed = [...observed, input];
        return true;
      },
      beginAction: () => null,
      epoch: () => currentEpoch,
    };
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([observationInterceptor])),
        provideHttpClientTesting(),
        { provide: CLIENT_OBSERVATIONS, useValue: sink },
        ObservationErrorHandler,
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    backend.verify();
    TestBed.resetTestingModule();
    vi.restoreAllMocks();
  });
  it('does not observe telemetry, guest or external signed requests, nor propagate correlation headers there', async () => {
    const intake = firstValueFrom(
      http.post('/api/v1/telemetry/events', { private: 'not inspected' }),
    );
    const telemetry = backend.expectOne('/api/v1/telemetry/events');
    expect(telemetry.request.headers.has('traceparent')).toBe(false);
    telemetry.flush({});
    await intake;
    const external = firstValueFrom(http.get('https://private-object.test/file?signature=secret'));
    const signed = backend.expectOne('https://private-object.test/file?signature=secret');
    expect(signed.request.headers.has('traceparent')).toBe(false);
    signed.flush({});
    await external;
    currentEpoch = null;
    const guest = firstValueFrom(http.get('/api/v1/me'));
    const check = backend.expectOne('/api/v1/me');
    expect(check.request.headers.has('traceparent')).toBe(false);
    check.flush({});
    await guest;
    expect(observed).toEqual([]);
  });
  it('reuses explicit logical action and valid server correlations without observing body/query/private error', async () => {
    const context = new HttpContext().set(CLIENT_ACTION, {
      action: 'submit',
      actionId: id,
      traceId: 'a'.repeat(32),
    });
    const value = firstValueFrom(
      http.put(
        '/api/v1/conversations/private-resource/messages?query=secret',
        { text: 'PRIVATE CHAT' },
        { context },
      ),
    );
    const pending = backend.expectOne(
      '/api/v1/conversations/private-resource/messages?query=secret',
    );
    expect(pending.request.headers.get('X-Action-ID')).toBe(id);
    expect(traceparent(pending.request.headers.get('traceparent'))?.traceId).toBe('a'.repeat(32));
    pending.flush({ text: 'PRIVATE RESPONSE' }, { headers: { 'X-Request-ID': id } });
    await value;
    expect(observed).toHaveLength(1);
    expect(observed[0]).toMatchObject({
      kind: 'http.observed',
      route: 'conversations',
      method: 'PUT',
      status_class: '2xx',
      request_id: id,
      action_id: id,
      trace_id: 'a'.repeat(32),
    });
    expect(JSON.stringify(observed)).not.toMatch(/PRIVATE|private-resource|secret|query|signature/);
  });
  it('preserves existing valid headers, original response and network errors', async () => {
    const parent = `00-${'b'.repeat(32)}-${'c'.repeat(16)}-01`;
    const result = firstValueFrom(
      http.get('/api/v1/me', {
        headers: new HttpHeaders({ 'X-Action-ID': id, traceparent: parent }),
        observe: 'response',
      }),
    );
    const read = backend.expectOne('/api/v1/me');
    expect(read.request.headers.get('traceparent')).toBe(parent);
    read.flush({ actual: 'body' });
    expect(await result).toBeInstanceOf(HttpResponse);
    expect(observed[0]).toMatchObject({ trace_id: 'b'.repeat(32) });
    const failed = firstValueFrom(http.get('/api/v1/me/profile'));
    const error = backend.expectOne('/api/v1/me/profile');
    const assertion = expect(failed).rejects.toMatchObject({ status: 503 });
    error.flush({ message: 'private failure' }, { status: 503, statusText: 'Unavailable' });
    await assertion;
    expect(observed[1]).toMatchObject({ status_class: '5xx', route: 'profile' });
    expect(JSON.stringify(observed)).not.toContain('private failure');
  });
  it('cancellation is observed, but late old-epoch responses never enter a new actor observation', async () => {
    const subscription = http.get('/api/v1/me/profile').subscribe();
    const pending = backend.expectOne('/api/v1/me/profile');
    subscription.unsubscribe();
    expect(pending.cancelled).toBe(true);
    expect(observed[0]).toMatchObject({ status_class: 'cancelled' });
    const late = firstValueFrom(http.get('/api/v1/me'));
    const old = backend.expectOne('/api/v1/me');
    currentEpoch = { id: 2, startedAt: performance.now() };
    old.flush({});
    await late;
    expect(observed).toHaveLength(1);
  });
  it('ErrorHandler always delegates the original diagnostic and exports only category', () => {
    const diagnostic = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const error = new Error('private email OTP and message');
    TestBed.inject(ObservationErrorHandler).handleError(error);
    expect(diagnostic).toHaveBeenCalledWith('ERROR', error);
    expect(observed).toEqual([{ kind: 'error.observed', category: 'javascript' }]);
  });
  it('keeps the original native diagnostic visible if the observation sink itself fails', () => {
    const diagnostic = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.spyOn(TestBed.inject(CLIENT_OBSERVATIONS), 'observe').mockImplementation(() => {
      throw new Error('synthetic observation sink failure');
    });
    const original = new Error('original diagnostic');
    TestBed.inject(ObservationErrorHandler).handleError(original);
    expect(diagnostic).toHaveBeenCalledWith('ERROR', original);
  });
  it('never serializes a non-Error diagnostic payload', () => {
    const diagnostic = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const original = { private: 'not an error, not telemetry' };
    TestBed.inject(ObservationErrorHandler).handleError(original);
    expect(diagnostic).toHaveBeenCalledWith('ERROR', original);
    expect(observed).toEqual([{ kind: 'error.observed', category: 'unknown' }]);
  });
  for (const status of [304, 403]) {
    it(`preserves an actual rejected HTTP ${String(status)} while retaining only its coarse status class`, async () => {
      const request = firstValueFrom(http.get('/api/v1/me/profile'));
      const rejected = expect(request).rejects.toMatchObject({ status });
      backend
        .expectOne('/api/v1/me/profile')
        .flush({ private: 'never exported' }, { status, statusText: 'Rejected' });
      await rejected;
      expect(observed).toEqual([
        expect.objectContaining({
          kind: 'http.observed',
          status_class: status === 304 ? '3xx' : '4xx',
        }),
      ]);
      expect(JSON.stringify(observed)).not.toContain('never exported');
    });
  }
  it('reports native network failure without retaining its ProgressEvent or response payload', async () => {
    const request = firstValueFrom(http.get('/api/v1/me'));
    const rejected = expect(request).rejects.toMatchObject({ status: 0 });
    backend.expectOne('/api/v1/me').error(new ProgressEvent('error'));
    await rejected;
    expect(observed).toEqual([
      expect.objectContaining({ kind: 'http.observed', status_class: 'network' }),
    ]);
  });
  it('extracts numeric navigation TTFB only for the current epoch and never prior or future entries', () => {
    const navigation = {
      entryType: 'navigation',
      name: 'private navigation URL',
      startTime: 100,
      duration: 20,
      responseStart: 145,
    };
    expect(performanceValue(navigation, { id: 1, startedAt: 0 }, 200)).toEqual({
      metric: 'ttfb',
      value: 45,
    });
    expect(performanceValue(navigation, { id: 2, startedAt: 101 }, 200)).toBeNull();
    expect(performanceValue(navigation, { id: 1, startedAt: 0 }, 99)).toBeNull();
    const malformed = { ...navigation, responseStart: 'private text' };
    expect(performanceValue(malformed, { id: 1, startedAt: 0 }, 200)).toBeNull();
    expect(
      performanceValue({ ...navigation, startTime: Number.NaN }, { id: 1, startedAt: 0 }, 200),
    ).toBeNull();
  });
  it('performance extraction drops prior actor entries and never calls event timing INP or copies element fields', () => {
    const epoch = { id: 1, startedAt: 100 };
    expect(
      performanceValue(
        { entryType: 'paint', name: 'first-contentful-paint', startTime: 80, duration: 0 },
        epoch,
        300,
      ),
    ).toBeNull();
    expect(
      performanceValue(
        { entryType: 'paint', name: 'first-contentful-paint', startTime: 150, duration: 0 },
        epoch,
        300,
      ),
    ).toEqual({ metric: 'fcp', value: 150 });
    expect(
      performanceValue(
        { entryType: 'largest-contentful-paint', name: 'private URL', startTime: 200, duration: 0 },
        epoch,
        300,
      ),
    ).toEqual({ metric: 'lcp', value: 200 });
    expect(
      performanceValue(
        {
          entryType: 'resource',
          name: 'https://s3.test/private?secret',
          startTime: 200,
          duration: 20,
        },
        epoch,
        300,
      ),
    ).toBeNull();
    expect(
      performanceValue(
        { entryType: 'event', name: 'input', startTime: 200, duration: 40 },
        epoch,
        300,
      ),
    ).toBeNull();
    expect(observedApi('/api/v1/telemetry/events?secret', location.origin)).toBeNull();
    expect(observedApi('/api/v1/events', location.origin)).toBeNull();
    expect(publicHttpRoute('/api/v1/auth/email-challenges')).toBe('verification');
  });
});
