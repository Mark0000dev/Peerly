import { HttpClient, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readJpeg } from './api-http';

const url = '/api/v1/people/fixture-person/photo/1';
const photo = new Blob([new Uint8Array([255, 216, 255])], { type: 'image/jpeg' });

describe('private abortable JPEG transport', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
  });
  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
    vi.restoreAllMocks();
  });
  it('returns only actual JPEG bytes, no object URL or application credentials', async () => {
    const result = readJpeg(TestBed.inject(HttpClient), url, new AbortController().signal);
    const request = TestBed.inject(HttpTestingController).expectOne(url);
    expect(request.request.responseType).toBe('blob');
    expect(request.request.method).toBe('GET');
    expect(request.request.headers.has('x-csrf-token')).toBe(false);
    expect(request.request.withCredentials).toBe(false);
    request.flush(photo, { headers: { 'Content-Type': 'image/jpeg; fixture=yes' } });
    await expect(result).resolves.toBe(photo);
  });
  for (const target of ['https://outside.invalid/photo', '//outside.invalid/photo', '/outside']) {
    it(`never sends a private read to ${target}`, async () => {
      await expect(
        readJpeg(TestBed.inject(HttpClient), target, new AbortController().signal),
      ).rejects.toMatchObject({ code: 'invalid_api_target' });
      TestBed.inject(HttpTestingController).expectNone(() => true);
    });
  }
  it('does not request bytes after cancellation', async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(
      readJpeg(TestBed.inject(HttpClient), url, controller.signal),
    ).rejects.toMatchObject({ name: 'AbortError' });
    TestBed.inject(HttpTestingController).expectNone(url);
  });
  it('unsubscribes the actual HTTP stream when cancelled in flight', async () => {
    const controller = new AbortController();
    const result = readJpeg(TestBed.inject(HttpClient), url, controller.signal);
    const rejected = expect(result).rejects.toMatchObject({ name: 'AbortError' });
    const request = TestBed.inject(HttpTestingController).expectOne(url);
    controller.abort();
    await rejected;
    expect(request.cancelled).toBe(true);
  });
  for (const scenario of [
    { body: photo, headers: {}, status: 200 },
    { body: photo, headers: { 'Content-Type': 'image/png' }, status: 200 },
    { body: new Blob(), headers: { 'Content-Type': 'image/jpeg' }, status: 200 },
    { body: null, headers: { 'Content-Type': 'image/jpeg' }, status: 200 },
    { body: photo, headers: { 'Content-Type': 'image/jpeg' }, status: 206 },
  ]) {
    it(`rejects a malformed JPEG response ${JSON.stringify(scenario.headers)} status${String(scenario.status)} size${String(scenario.body?.size)}`, async () => {
      const result = readJpeg(TestBed.inject(HttpClient), url, new AbortController().signal);
      const rejected = expect(result).rejects.toMatchObject({ code: 'invalid_response' });
      TestBed.inject(HttpTestingController).expectOne(url).flush(scenario.body, {
        status: scenario.status,
        statusText: 'Fixture',
        headers: scenario.headers,
      });
      await rejected;
    });
  }
  for (const mime of ['application/json', 'application/problem+json; charset=utf-8']) {
    it(`extracts only safe problem metadata from a ${mime} error blob`, async () => {
      const result = readJpeg(TestBed.inject(HttpClient), url, new AbortController().signal);
      const rejected = expect(result).rejects.toMatchObject({
        status: 503,
        code: 'media_storage_unavailable',
        requestId: 'fixture-request',
        retryAt: '2026-11-07T15:00:00Z',
        message: 'Request could not be completed',
      });
      const body = new Blob(
        [
          JSON.stringify({
            code: 'media_storage_unavailable',
            request_id: 'fixture-request',
            recovery: { retry_at: '2026-11-07T15:00:00Z' },
            detail: 'PRIVATE provider data',
          }),
        ],
        { type: mime },
      );
      TestBed.inject(HttpTestingController)
        .expectOne(url)
        .flush(body, { status: 503, statusText: 'Failure' });
      await rejected;
    });
  }
  for (const body of [
    new Blob(['not json'], { type: 'application/problem+json' }),
    new Blob(['PRIVATE HTML'], { type: 'text/html' }),
    new Blob(['x'.repeat(8193)], { type: 'application/json' }),
  ]) {
    it(`bounds and safely reduces an unreadable error blob ${body.type} size${String(body.size)}`, async () => {
      const result = readJpeg(TestBed.inject(HttpClient), url, new AbortController().signal);
      const rejected = expect(result).rejects.toMatchObject({
        status: 503,
        code: 'request_failed',
        requestId: null,
      });
      TestBed.inject(HttpTestingController)
        .expectOne(url)
        .flush(body, { status: 503, statusText: 'Failure' });
      await rejected;
    });
  }
  it('reduces a network failure to safe status0 metadata', async () => {
    const result = readJpeg(TestBed.inject(HttpClient), url, new AbortController().signal);
    const rejected = expect(result).rejects.toMatchObject({ status: 0, code: 'request_failed' });
    TestBed.inject(HttpTestingController).expectOne(url).error(new ProgressEvent('error'));
    await rejected;
  });
  it('handles a native error-body read failure without exposing its text', async () => {
    const body = new Blob(['{}'], { type: 'application/json' });
    vi.spyOn(body, 'text').mockRejectedValue(
      new DOMException('PRIVATE native detail', 'NotReadableError'),
    );
    const result = readJpeg(TestBed.inject(HttpClient), url, new AbortController().signal);
    const rejected = expect(result).rejects.toMatchObject({
      status: 503,
      code: 'request_failed',
      message: 'Request could not be completed',
    });
    TestBed.inject(HttpTestingController)
      .expectOne(url)
      .flush(body, { status: 503, statusText: 'Failure' });
    await rejected;
  });
  it('does not publish error metadata after its actor cancelled while the body was being decoded', async () => {
    const body = new Blob(['{}'], { type: 'application/json' });
    let resolve: (value: string) => void = () => {
      throw new Error('Missing body gate');
    };
    const pending = new Promise<string>((done) => {
      resolve = done;
    });
    const text = vi.spyOn(body, 'text').mockReturnValue(pending);
    const controller = new AbortController();
    const result = readJpeg(TestBed.inject(HttpClient), url, controller.signal);
    const rejected = expect(result).rejects.toMatchObject({ name: 'AbortError' });
    TestBed.inject(HttpTestingController)
      .expectOne(url)
      .flush(body, { status: 503, statusText: 'Failure' });
    await vi.waitFor(() => {
      expect(text).toHaveBeenCalledOnce();
    });
    controller.abort();
    resolve('{}');
    await rejected;
  });
});
