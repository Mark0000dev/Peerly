import {
  HttpClient,
  HttpContext,
  HttpErrorResponse,
  provideHttpClient,
} from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { throwError } from 'rxjs';
import { ApiFailure, readJson, writeJson } from './api-http';
import { CLIENT_ACTION } from './observability/observation-context';
const empty = (value: unknown): value is null => value === null;

describe('same-origin JSON transport', () => {
  it('preserves explicit action context and unchanged command headers across deliberate replay', async () => {
    const action = {
      action: 'submit',
      actionId: '00000000-0000-4000-8000-000000000001',
      traceId: 'a'.repeat(32),
    } as const;
    const context = new HttpContext().set(CLIENT_ACTION, action);
    for (const method of ['PUT', 'PUT'] as const) {
      const pending = writeJson(
        TestBed.inject(HttpClient),
        '/api/v1/me/goal',
        { topic: 'owned draft' },
        { 'x-csrf-token': 'current', 'idempotency-key': 'same-intent' },
        empty,
        method,
        context,
      );
      const request = TestBed.inject(HttpTestingController).expectOne('/api/v1/me/goal');
      expect(request.request.context.get(CLIENT_ACTION)).toBe(action);
      expect(request.request.headers.get('idempotency-key')).toBe('same-intent');
      expect(request.request.headers.get('x-csrf-token')).toBe('current');
      request.flush(null);
      await pending;
    }
  });
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
  });
  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
  });
  for (const target of [
    'https://outside.invalid/api/v1/logout',
    '//outside.invalid/api/v1/logout',
    '/not-api',
  ]) {
    it(`never sends credentials or CSRF to ${target}`, async () => {
      await expect(
        writeJson(TestBed.inject(HttpClient), target, null, { 'x-csrf-token': 'fixture' }, empty),
      ).rejects.toMatchObject({ code: 'invalid_api_target' });
      await expect(
        readJson(TestBed.inject(HttpClient), target, new AbortController().signal, empty),
      ).rejects.toMatchObject({ code: 'invalid_api_target' });
      TestBed.inject(HttpTestingController).expectNone(() => true);
    });
  }
  it('sends only explicitly supplied write headers and accepts the actual 204 logout', async () => {
    const result = writeJson(
      TestBed.inject(HttpClient),
      '/api/v1/auth/logout',
      null,
      { 'x-csrf-token': 'fixture' },
      empty,
    );
    const request = TestBed.inject(HttpTestingController).expectOne('/api/v1/auth/logout');
    expect(request.request.headers.get('x-csrf-token')).toBe('fixture');
    expect(request.request.method).toBe('POST');
    expect(request.request.withCredentials).toBe(false);
    request.flush(null, { status: 204, statusText: 'No Content' });
    await expect(result).resolves.toBeNull();
  });
  it('rejects malformed command responses rather than inventing success', async () => {
    const result = writeJson(TestBed.inject(HttpClient), '/api/v1/auth/logout', null, {}, empty);
    const rejected = expect(result).rejects.toMatchObject({ code: 'invalid_response' });
    TestBed.inject(HttpTestingController)
      .expectOne('/api/v1/auth/logout')
      .flush({ unexpected: 'private' });
    await rejected;
  });
  for (const method of ['GET', 'POST', 'PUT'] as const) {
    it(`treats an Angular ${method} 2xx JSON decoding failure as an unknown outcome`, async () => {
      const response = new HttpErrorResponse({
        status: method === 'POST' ? 201 : 200,
        error: {
          error: new SyntaxError('SECRET malformed JSON'),
          text: 'SECRET',
          code: 'must_not_be_trusted',
          request_id: 'must_not_be_trusted',
        },
      });
      const http = TestBed.inject(HttpClient);
      vi.spyOn(http, 'request').mockReturnValue(throwError(() => response));
      const result =
        method === 'GET'
          ? readJson(http, '/api/v1/me', new AbortController().signal, empty)
          : writeJson(http, '/api/v1/reports', {}, {}, empty, method);
      await expect(result).rejects.toMatchObject({
        status: 0,
        code: 'invalid_response',
        requestId: null,
        retryAt: null,
      });
    });
  }
  for (const recovery of [
    null,
    'private',
    {},
    { retry_at: 0 },
    { retry_at: 'not-a-time' },
    { retry_at: '2026-11-07T12:00:00Z' },
  ]) {
    it(`retains only a valid server retry deadline ${JSON.stringify(recovery)}`, async () => {
      const result = writeJson(TestBed.inject(HttpClient), '/api/v1/auth/logout', null, {}, empty);
      const rejected = expect(result).rejects.toMatchObject({
        status: 429,
        code: 'rate_limited',
        retryAt:
          typeof recovery === 'object' &&
          recovery !== null &&
          'retry_at' in recovery &&
          recovery.retry_at === '2026-11-07T12:00:00Z'
            ? recovery.retry_at
            : null,
      });
      TestBed.inject(HttpTestingController)
        .expectOne('/api/v1/auth/logout')
        .flush(
          { code: 'rate_limited', recovery, private_text: 'SECRET' },
          { status: 429, statusText: 'Limit' },
        );
      await rejected;
    });
  }
  it('keeps unexpected decoder failures visible', async () => {
    const failure = new Error('Decoder failed');
    const result = readJson(
      TestBed.inject(HttpClient),
      '/api/v1/me',
      new AbortController().signal,
      (value: unknown): value is null => {
        if (value === null) throw failure;
        return false;
      },
    );
    const rejected = expect(result).rejects.toBe(failure);
    TestBed.inject(HttpTestingController).expectOne('/api/v1/me').flush(null);
    await rejected;
    expect(new ApiFailure(0, 'invalid_response', null).message).not.toContain('SECRET');
  });
});
