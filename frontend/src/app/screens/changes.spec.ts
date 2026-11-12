import {
  HttpClient,
  HttpEventType,
  HttpHeaders,
  HttpHeaderResponse,
  provideHttpClient,
} from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { TestRequest } from '@angular/common/http/testing';
import { DestroyRef } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { QueryClient, QueryObserver } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../api.generated';
import { watchChanges } from './changes';
import { sessionOptions } from './session';

const actor = '10000000-0000-0000-0000-000000000001';
const peer = '10000000-0000-0000-0000-000000000002';
const key = ['account', actor, 'chats', 'list'] as const;
const identity = {
  account_id: actor,
  account_status: 'active',
  membership_status: 'verified',
  verified_at: '2026-11-08T06:00:00Z',
  email_challenge_id: null,
  csrf_token: 'synthetic-change-csrf',
  registration: {
    id: 'receipt',
    context_id: 'context',
    registered_at: '2026-11-08T06:00:00Z',
    notice_text: 'Fixture notice',
    surface: 'onboarding_completion',
    terms: { id: 'terms', kind: 'terms', version: 'v1', published_at: '2026-11-07T06:00:00Z' },
    privacy: {
      id: 'privacy',
      kind: 'privacy',
      version: 'v1',
      published_at: '2026-11-07T06:00:00Z',
    },
  },
  capabilities: {
    can_begin_onboarding: true,
    can_use_student_features: true,
    can_verify_student_email: false,
  },
} as const satisfies Api['schemas']['IdentityResponse'];
const headers = new HttpHeaders({ 'Content-Type': 'text/event-stream' });
function wire(id = '1', resource = 'conversation', owner = peer): string {
  return `id: ${id}\nevent: resource.changed\ndata: ${JSON.stringify({ resource_type: resource, resource_id: owner, version: null })}\n\n`;
}
function progress(request: Readonly<TestRequest>, text: string): void {
  request.event(new HttpHeaderResponse({ status: 200, headers }));
  request.event({ type: HttpEventType.DownloadProgress, loaded: text.length, partialText: text });
}

describe('single actor-owned canonical change stream', () => {
  let client: QueryClient;
  let http: HttpClient;
  let backend: HttpTestingController;
  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    watchChanges(http, client, TestBed.inject(DestroyRef));
  });
  afterEach(() => {
    TestBed.resetTestingModule();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    vi.useRealTimers();
    vi.restoreAllMocks();
  });
  function open(): TestRequest {
    client.setQueryData(['session'], identity);
    client.setQueryData(key, { canonical: 'preserved' });
    return backend.expectOne('/api/v1/events');
  }
  it('does not connect before a verified activated identity or for denied capabilities', () => {
    backend.expectNone('/api/v1/events');
    client.setQueryData(['session'], {
      ...identity,
      capabilities: { ...identity.capabilities, can_use_student_features: false },
    });
    backend.expectNone('/api/v1/events');
  });
  it('invalidates only the owning private prefix after a complete split CRLF frame without copying payloads', () => {
    const request = open();
    client.setQueryData(['account', peer, 'chats'], { other: 'untouched' });
    const text = wire().replaceAll('\n', '\r\n');
    progress(request, text.slice(0, -1));
    expect(client.getQueryState(key)?.isInvalidated).toBe(false);
    progress(request, text);
    expect(client.getQueryState(key)?.isInvalidated).toBe(true);
    expect(client.getQueryData(key)).toEqual({ canonical: 'preserved' });
    expect(client.getQueryState(['account', peer, 'chats'])?.isInvalidated).toBe(false);
    expect(request.request.reportDownloadProgress).toBe(true);
    expect(request.request.responseType).toBe('text');
    expect(request.request.url).toBe('/api/v1/events');
  });
  it.each(['account', 'request', 'conversation', 'ai_job'])(
    'accepts actual %s invalidation hints and ignores heartbeat comments',
    (resource) => {
      const request = open();
      progress(request, ': heartbeat\n\n');
      expect(client.getQueryState(key)?.isInvalidated).toBe(false);
      progress(request, ': heartbeat\n\n' + wire('1', resource));
      expect(client.getQueryState(key)?.isInvalidated).toBe(true);
    },
  );
  it('does not regress its cursor or reapply duplicate hints', () => {
    const request = open();
    progress(request, wire('2'));
    client.setQueryData(key, { canonical: 'fresh' });
    progress(request, wire('2') + wire('1') + wire('2'));
    expect(client.getQueryState(key)?.isInvalidated).toBe(false);
  });
  it('reconnects with exact 64-bit cursor and never sends commands or read ACKs', async () => {
    vi.useFakeTimers();
    const request = open();
    const text = wire('9223372036854775807');
    progress(request, text);
    request.flush(text, { headers });
    await vi.advanceTimersByTimeAsync(1000);
    const resumed = backend.expectOne('/api/v1/events');
    expect(resumed.request.headers.get('Last-Event-ID')).toBe('9223372036854775807');
    backend.expectNone((entry) => entry.method !== 'GET');
  });
  it.each([
    'event: resource.changed\ndata: {}\n\n',
    wire('01'),
    wire('0'),
    wire('9223372036854775808'),
    wire('1', 'unknown'),
    'id: 1\nevent: resource.changed\ndata: {broken}\n\n',
    'id: 1\nevent: reset_required\ndata: {"unexpected":true}\n\n',
    'id: 1\nevent: resource.changed\ndata: []\n\n',
    'id: 1\nevent: resource.changed\ndata: {"resource_type":"conversation","resource_id":"raw-secret","version":null}\n\n',
    'id: 1\nevent: resource.changed\ndata: {"resource_type":"conversation","resource_id":"' +
      peer +
      '","version":0}\n\n',
  ])(
    'rejects malformed wire data without advancing cursor or invalidating data (%#)',
    async (text) => {
      vi.useFakeTimers();
      const request = open();
      progress(request, text);
      expect(request.cancelled).toBe(true);
      expect(client.getQueryState(key)?.isInvalidated).toBe(false);
      await vi.advanceTimersByTimeAsync(2000);
      backend.expectNone('/api/v1/events');
    },
  );
  it('rejects an oversized partial frame without automatically retrying invalid protocol', async () => {
    vi.useFakeTimers();
    const request = open();
    progress(request, 'x'.repeat(4097));
    expect(request.cancelled).toBe(true);
    await vi.advanceTimersByTimeAsync(30_000);
    backend.expectNone('/api/v1/events');
  });
  it('bounds cumulative connection memory and resumes its safe GET after normal rotation', async () => {
    vi.useFakeTimers();
    const request = open();
    progress(request, ':'.repeat(1_048_577));
    expect(request.cancelled).toBe(true);
    await vi.advanceTimersByTimeAsync(1000);
    backend.expectOne('/api/v1/events');
  });
  it('rejects an HTML fallback even when final response has no progress header', async () => {
    vi.useFakeTimers();
    open().flush('<html>wrong origin</html>', { headers: { 'Content-Type': 'text/html' } });
    await vi.advanceTimersByTimeAsync(2000);
    backend.expectNone('/api/v1/events');
    expect(client.getQueryState(key)?.isInvalidated).toBe(false);
  });
  it('cancels a former actor and clears its resume cursor on account replacement/logout', () => {
    const request = open();
    progress(request, wire('10'));
    client.setQueryData(['session'], { ...identity, account_id: peer });
    expect(request.cancelled).toBe(true);
    const replacement = backend.expectOne('/api/v1/events');
    expect(replacement.request.headers.has('Last-Event-ID')).toBe(false);
    client.setQueryData(['session'], null);
    expect(replacement.cancelled).toBe(true);
  });
  it('cancels the owned connection and pending reconnect on application destruction', async () => {
    vi.useFakeTimers();
    const request = open();
    request.flush(': heartbeat\n\n', { headers });
    await Promise.resolve();
    TestBed.resetTestingModule();
    await vi.advanceTimersByTimeAsync(30_000);
    backend.expectNone('/api/v1/events');
  });
  it('revalidates actual identity after stream authentication failure and clears private data', async () => {
    const request = open();
    request.flush('denied', { status: 401, statusText: 'Unauthorized' });
    const me = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    me.flush({ code: 'unauthenticated' }, { status: 401, statusText: 'Unauthorized' });
    await vi.waitFor(() => {
      expect(client.getQueryData(['session'])).toBeNull();
    });
    expect(client.getQueryData(key)).toBeUndefined();
    backend.expectNone('/api/v1/events');
  });
  it('own-account/reset hints refresh actual /me rather than patching identity fields', async () => {
    const observer = new QueryObserver(client, sessionOptions(http, client));
    const unsubscribe = observer.subscribe(() => undefined);
    const me = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    me.flush(identity);
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/events'));
    progress(request, 'id: 0\nevent: reset_required\ndata: {}\n\n');
    const refreshed = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    expect(request.cancelled).toBe(true);
    refreshed.flush({
      ...identity,
      capabilities: { ...identity.capabilities, can_use_student_features: false },
    });
    await vi.waitFor(() => {
      expect(client.getQueryData(['session'])).toEqual({
        ...identity,
        capabilities: { ...identity.capabilities, can_use_student_features: false },
      });
    });
    backend.expectNone('/api/v1/events');
    unsubscribe();
  });
  it.each([
    null,
    true,
    3,
    'text',
    {},
    { resource_type: 'conversation', resource_id: peer },
    { resource_type: 42, resource_id: peer, version: null },
    { resource_type: 'conversation', resource_id: 3, version: null },
    { resource_type: 'conversation', resource_id: peer, version: '1' },
    { resource_type: 'conversation', resource_id: peer, version: 1, unexpected: true },
  ])(
    'rejects an unsupported invalidation shape without touching canonical data (%#)',
    async (data: unknown) => {
      vi.useFakeTimers();
      const request = open();
      progress(request, `id: 1\nevent: resource.changed\ndata: ${JSON.stringify(data)}\n\n`);
      expect(request.cancelled).toBe(true);
      expect(client.getQueryState(key)?.isInvalidated).toBe(false);
      await vi.advanceTimersByTimeAsync(2000);
      backend.expectNone('/api/v1/events');
    },
  );
  it('accepts positive version hints without applying that version to a cached DTO', () => {
    const request = open();
    progress(
      request,
      `id: 1\nevent: resource.changed\ndata: ${JSON.stringify({ resource_type: 'conversation', resource_id: peer, version: 2 })}\n\n`,
    );
    expect(client.getQueryState(key)?.isInvalidated).toBe(true);
    expect(client.getQueryData(key)).toEqual({ canonical: 'preserved' });
  });
  it('handles a completed response without download progress and a legal empty response', async () => {
    vi.useFakeTimers();
    open().flush(': heartbeat\n\n', { headers });
    await vi.advanceTimersByTimeAsync(1000);
    backend.expectOne('/api/v1/events').flush(null, { headers });
    await vi.advanceTimersByTimeAsync(1000);
    backend.expectOne('/api/v1/events');
    expect(client.getQueryState(key)?.isInvalidated).toBe(false);
  });
  it.each(['truncated', 'regressing'] as const)(
    'rejects %s transport data without background retry',
    async (mode) => {
      vi.useFakeTimers();
      const request = open();
      if (mode === 'truncated') request.flush('id: 1\nevent: resource.changed', { headers });
      else {
        progress(request, ': heartbeat\n\n');
        progress(request, ':');
        expect(request.cancelled).toBe(true);
      }
      await vi.advanceTimersByTimeAsync(30_000);
      backend.expectNone('/api/v1/events');
      expect(client.getQueryState(key)?.isInvalidated).toBe(false);
    },
  );
  it('keeps a failed identity revalidation canonical rather than reconnecting under stale authority', async () => {
    open().flush('denied', { status: 403, statusText: 'Forbidden' });
    const me = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    me.flush('unavailable', { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      expect(client.getQueryState(['session'])?.status).toBe('error');
    });
    expect(client.getQueryData(key)).toBeUndefined();
    backend.expectNone('/api/v1/events');
  });
  it('pauses the old stream during actual /me revalidation and resumes only verified authority', async () => {
    const request = open();
    const observer = new QueryObserver(client, sessionOptions(http, client));
    const unsubscribe = observer.subscribe(() => undefined);
    expect(request.cancelled).toBe(true);
    const me = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    backend.expectNone('/api/v1/events');
    me.flush(identity);
    await vi.waitFor(() => backend.expectOne('/api/v1/events'));
    unsubscribe();
  });
  it('refreshes own account hints and cancels the remainder of a stale-authority batch', async () => {
    const observer = new QueryObserver(client, sessionOptions(http, client));
    const unsubscribe = observer.subscribe(() => undefined);
    const me = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    me.flush(identity);
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/events'));
    progress(request, wire('1', 'account', actor) + wire('2'));
    const refreshed = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    expect(request.cancelled).toBe(true);
    refreshed.flush(identity);
    const resumed = await vi.waitFor(() => backend.expectOne('/api/v1/events'));
    expect(resumed.request.headers.get('Last-Event-ID')).toBe('1');
    unsubscribe();
  });
  it.each([400, 404, 422])(
    'does not retry permanent HTTP %i validation/topology failures',
    async (status) => {
      vi.useFakeTimers();
      open().flush('rejected', { status, statusText: 'Rejected' });
      await vi.advanceTimersByTimeAsync(30_000);
      backend.expectNone('/api/v1/events');
      backend.expectNone('/api/v1/me');
    },
  );
  it('does not spin stream/auth reads when /me confirms the same active actor after a denial', async () => {
    vi.useFakeTimers();
    open().flush('denied', { status: 403, statusText: 'Forbidden' });
    const me = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    me.flush(identity);
    await vi.advanceTimersByTimeAsync(30_000);
    backend.expectNone('/api/v1/events');
    backend.expectNone('/api/v1/me');
    const refreshed = client.query(sessionOptions(http, client));
    const manual = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    manual.flush(identity);
    await refreshed;
    backend.expectOne('/api/v1/events');
  });
  it('only resumes malformed streams after an independent authority read, preserving the last valid cursor', async () => {
    vi.useFakeTimers();
    const request = open();
    progress(request, wire('1'));
    progress(request, wire('1') + 'id: 2\nevent: unexpected\ndata: {}\n\n');
    expect(request.cancelled).toBe(true);
    await vi.advanceTimersByTimeAsync(30_000);
    backend.expectNone('/api/v1/events');
    const refreshed = client.query(sessionOptions(http, client));
    const me = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    me.flush(identity);
    await refreshed;
    expect(backend.expectOne('/api/v1/events').request.headers.get('Last-Event-ID')).toBe('1');
  });
  it.each([408, 429, 503])(
    'retries only transient HTTP %i GETs with the last validated cursor',
    async (status) => {
      vi.useFakeTimers();
      const first = open();
      first.flush(wire('10'), { headers });
      await vi.advanceTimersByTimeAsync(1000);
      const unavailable = backend.expectOne('/api/v1/events');
      expect(unavailable.request.headers.get('Last-Event-ID')).toBe('10');
      unavailable.event(
        new HttpHeaderResponse({
          status,
          headers: new HttpHeaders({ 'Content-Type': 'application/problem+json' }),
        }),
      );
      unavailable.event({
        type: HttpEventType.DownloadProgress,
        loaded: 18,
        partialText: 'Not an SSE frame\n\n',
      });
      unavailable.flush('unavailable', {
        status,
        statusText: 'Unavailable',
        headers: { 'Retry-After': '1' },
      });
      await vi.advanceTimersByTimeAsync(2000);
      const resumed = backend.expectOne('/api/v1/events');
      expect(resumed.request.method).toBe('GET');
      expect(resumed.request.headers.get('Last-Event-ID')).toBe('10');
      backend.expectNone((request) => request.method !== 'GET');
    },
  );
  it('distinguishes an interrupted socket from malformed protocol and retries only the safe GET', async () => {
    vi.useFakeTimers();
    const request = open();
    progress(request, wire('3'));
    request.error(new ProgressEvent('error'));
    await vi.advanceTimersByTimeAsync(2000);
    expect(backend.expectOne('/api/v1/events').request.headers.get('Last-Event-ID')).toBe('3');
    backend.expectNone((entry) => entry.method !== 'GET');
  });
});
