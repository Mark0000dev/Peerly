import { HttpClient, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import { QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionOptions } from './session';
import { ApiFailure as SessionFailure } from '../api-http';

const identity = {
  account_id: '00000000-0000-0000-0000-000000000001',
  account_status: 'active',
  membership_status: 'unverified',
  verified_at: null,
  registration: null,
  email_challenge_id: null,
  csrf_token: 'synthetic-csrf',
  capabilities: {
    can_begin_onboarding: false,
    can_use_student_features: false,
    can_verify_student_email: true,
  },
};

const policy = {
  id: 'synthetic-policy',
  kind: 'terms',
  version: 'test-v1',
  published_at: '2026-11-07T00:00:00Z',
};
const receipt = {
  id: 'synthetic-receipt',
  context_id: 'synthetic-context',
  registered_at: '2026-11-07T00:00:00Z',
  notice_text: 'Synthetic notice',
  surface: 'onboarding_completion',
  terms: policy,
  privacy: { ...policy, kind: 'privacy' },
};

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const http = TestBed.inject(HttpClient);
  return {
    client,
    options: sessionOptions(http, client),
    backend: TestBed.inject(HttpTestingController),
  };
}

describe('session bootstrap boundary', () => {
  beforeEach(() =>
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }),
  );
  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
  });

  it('loads the actual identity and keeps CSRF only in the query cache', async () => {
    const { client, options, backend } = setup();
    client.setQueryData(['account', 'old', 'profile'], { private: 'old' });
    const result = client.query(options);
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    request.flush(identity);
    await expect(result).resolves.toEqual(identity);
    expect(client.getQueryData(['account', 'old', 'profile'])).toBeUndefined();
    client.clear();
  });

  it('cancels old private work before replacing the cached account', async () => {
    const { client, options, backend } = setup();
    client.setQueryData(['session'], { ...identity, account_id: 'previous-account' });
    const oldWork = client.query({
      queryKey: ['account', 'previous-account', 'fixture'],
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
        new Promise<never>((_resolve, reject) => {
          signal.addEventListener(
            'abort',
            () => {
              reject(new DOMException('Cancelled', 'AbortError'));
            },
            { once: true },
          );
        }),
    });
    const cancelled = expect(oldWork).rejects.toThrow();
    const replacement = client.query(options);
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    await cancelled;
    expect(client.getQueryData(['account', 'previous-account', 'fixture'])).toBeUndefined();
    request.flush(identity);
    await expect(replacement).resolves.toEqual(identity);
    expect(client.getQueryData(['session'])).toEqual(identity);
    client.clear();
  });

  it('aborts in-flight HTTP when the query is cancelled', async () => {
    const { client, options, backend } = setup();
    const result = client.query(options);
    const rejected = expect(result).rejects.toThrow();
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    await client.cancelQueries({ queryKey: ['session'] });
    await rejected;
    expect(request.cancelled).toBe(true);
    client.clear();
  });

  it('does not send HTTP for an already-aborted query', async () => {
    const { client, options, backend } = setup();
    const controller = new AbortController();
    controller.abort();
    if (typeof options.queryFn !== 'function') throw new Error('Missing query function');
    await expect(
      options.queryFn({
        client,
        queryKey: ['session'],
        signal: controller.signal,
        meta: undefined,
      }),
    ).rejects.toMatchObject({ name: 'AbortError' });
    backend.expectNone('/api/v1/me');
    client.clear();
  });

  it('does not send HTTP after cancellation during private-cache cleanup', async () => {
    const { client, options, backend } = setup();
    const controller = new AbortController();
    if (typeof options.queryFn !== 'function') throw new Error('Missing query function');
    const result = options.queryFn({
      client,
      queryKey: ['session'],
      signal: controller.signal,
      meta: undefined,
    });
    controller.abort();
    await expect(result).rejects.toMatchObject({ name: 'AbortError' });
    backend.expectNone('/api/v1/me');
    client.clear();
  });

  it('sanitises an untrusted problem instead of retaining arbitrary content', async () => {
    const { client, options, backend } = setup();
    const result = client.query(options);
    const rejected = expect(result).rejects.toMatchObject({
      status: 503,
      code: 'request_failed',
      requestId: null,
      message: 'Request could not be completed',
    });
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    request.flush(
      { code: 'PRIVATE BODY!', request_id: 'sensitive @mail.apu.edu.my' },
      { status: 503, statusText: 'Failure' },
    );
    await rejected;
    client.clear();
  });

  for (const value of [
    identity,
    { ...identity, registration: receipt },
    { ...identity, email_challenge_id: '00000000-0000-0000-0000-000000000002' },
    {
      ...identity,
      account_status: 'banned',
      membership_status: 'verified',
      verified_at: '2026-11-07T00:00:00Z',
    },
  ]) {
    it(`accepts server ${value.account_status} capability state without deriving permissions`, async () => {
      const { client, options, backend } = setup();
      const result = client.query(options);
      const request = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
      request.flush(value);
      await expect(result).resolves.toEqual(value);
      client.clear();
    });
  }

  for (const value of [
    null,
    [],
    { ...identity, email_challenge_id: 12 },
    Object.fromEntries(
      Object.entries(identity).filter(
        ([name]: readonly [string, unknown]) => name !== 'email_challenge_id',
      ),
    ),
    { ...identity, registration: false },
    { ...identity, registration: { ...receipt, surface: 'unknown' } },
    { ...identity, registration: { ...receipt, terms: null } },
    { ...identity, registration: { ...receipt, privacy: { ...policy, kind: 'unknown' } } },
    ...Object.keys(receipt).flatMap((key) => [
      {
        ...identity,
        registration: Object.fromEntries(
          Object.entries(receipt).filter(([name]: readonly [string, unknown]) => name !== key),
        ),
      },
      { ...identity, registration: { ...receipt, [key]: 0 } },
    ]),
    ...Object.keys(policy).flatMap((key) => [
      {
        ...identity,
        registration: {
          ...receipt,
          terms: Object.fromEntries(
            Object.entries(policy).filter(([name]: readonly [string, unknown]) => name !== key),
          ),
        },
      },
      { ...identity, registration: { ...receipt, terms: { ...policy, [key]: 0 } } },
    ]),
    {},
    { ...identity, account_id: 1 },
    { ...identity, account_status: 'deleted' },
    { ...identity, account_status: ['active'] },
    { ...identity, membership_status: ['unverified'] },
    { ...identity, membership_status: 'unknown' },
    { ...identity, verified_at: 3 },
    { ...identity, csrf_token: '' },
    { ...identity, capabilities: null },
    { ...identity, capabilities: {} },
    { ...identity, capabilities: { ...identity.capabilities, can_begin_onboarding: 0 } },
    { ...identity, capabilities: { ...identity.capabilities, can_use_student_features: 0 } },
    { ...identity, capabilities: { ...identity.capabilities, can_verify_student_email: 0 } },
  ]) {
    it(`rejects malformed bootstrap ${JSON.stringify(value)}`, async () => {
      const { client, options, backend } = setup();
      const result = client.query(options);
      const rejected = expect(result).rejects.toMatchObject({ code: 'invalid_response' });
      const request = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
      request.flush(value);
      await rejected;
      client.clear();
    });
  }

  for (const status of [401, 403, 503, 0]) {
    it(`handles HTTP ${String(status)} without retries or private error bodies`, async () => {
      const { client, options, backend } = setup();
      const result = client.query(options);
      const assertion =
        status === 401
          ? expect(result).resolves.toBeNull()
          : expect(result).rejects.toBeInstanceOf(SessionFailure);
      const request = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
      if (status === 0) request.error(new ProgressEvent('error'));
      else
        request.flush(
          {
            code: 'safe_error',
            request_id: 'synthetic-request',
            title: 'PRIVATE',
            detail: 'SECRET',
          },
          { status, statusText: 'Failure' },
        );
      await assertion;
      expect(backend.match('/api/v1/me')).toHaveLength(0);
      client.clear();
    });
  }
});
