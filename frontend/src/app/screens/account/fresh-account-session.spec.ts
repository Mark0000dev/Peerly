import { HttpClient, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import { QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../../api.generated';
import { readJson } from '../../api-http';
import { sessionOptions } from '../session';

const previousAccount = '00000000-0000-4000-8000-000000000021';
const freshIdentity: Api['schemas']['IdentityResponse'] = {
  account_id: '00000000-0000-4000-8000-000000000022',
  account_status: 'active',
  membership_status: 'unverified',
  verified_at: null,
  registration: null,
  email_challenge_id: null,
  csrf_token: 'synthetic-new-account-csrf',
  capabilities: {
    can_begin_onboarding: false,
    can_use_student_features: false,
    can_verify_student_email: true,
  },
};
const previousIdentity: Api['schemas']['IdentityResponse'] = {
  ...freshIdentity,
  account_id: previousAccount,
  membership_status: 'verified',
  verified_at: '2026-11-01T04:00:00Z',
  csrf_token: 'synthetic-previous-account-csrf',
  email_challenge_id: '00000000-0000-4000-8000-000000000023',
  capabilities: {
    can_begin_onboarding: true,
    can_use_student_features: false,
    can_verify_student_email: false,
  },
};

// Controlled /me responses exercise the existing client boundary only. Real Google
// callback, deleted/banned lineage and receipt-proof authority are backend tests.
describe('fresh account canonical session retires the previous account lifetime', () => {
  let client: QueryClient;
  let backend: HttpTestingController;
  let http: HttpClient;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    backend = TestBed.inject(HttpTestingController);
    http = TestBed.inject(HttpClient);
  });
  afterEach(() => {
    client.clear();
    backend.verify();
    TestBed.resetTestingModule();
  });
  function retainPreviousLifetime(): void {
    client.setQueryData(['session'], previousIdentity);
    client.setQueryData(['account', previousAccount, 'profile'], {
      retained: 'synthetic old profile',
    });
    client.setQueryData(['account', previousAccount, 'chats', 'list', null], {
      retained: 'synthetic old chats',
    });
    client.setQueryData(['account', previousAccount, 'deletion', 'status'], {
      retained: 'synthetic receipt-only result',
    });
  }
  it('aborts actual old private HTTP and removes private caches before accepting fresh identity or CSRF', async () => {
    retainPreviousLifetime();
    client.setQueryData(['profile-reference-data'], { retained: 'public reference data' });
    const oldRead = client.query({
      queryKey: ['account', previousAccount, 'profile', 'pending'] as const,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
        // No profile body is supplied: this real HttpClient read must be aborted.
        readJson(
          http,
          '/api/v1/me/profile',
          signal,
          (value): value is unknown => value !== undefined,
        ),
    });
    const rejected = expect(oldRead).rejects.toThrow();
    const oldRequest = await vi.waitFor(() => backend.expectOne('/api/v1/me/profile'));
    const next = client.query(sessionOptions(http, client));
    const identityRequest = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    await rejected;
    expect(oldRequest.cancelled).toBe(true);
    expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
    identityRequest.flush(freshIdentity);
    await expect(next).resolves.toEqual(freshIdentity);
    expect(client.getQueryData(['session'])).toEqual(freshIdentity);
    expect(
      client.getQueryData<Api['schemas']['IdentityResponse']>(['session'])?.csrf_token,
    ).not.toBe(previousIdentity.csrf_token);
    expect(
      client.getQueryData<Api['schemas']['IdentityResponse']>(['session'])?.account_id,
    ).not.toBe(previousAccount);
    expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
    expect(client.getQueryData(['profile-reference-data'])).toEqual({
      retained: 'public reference data',
    });
    backend.expectNone('/api/v1/me/profile');
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('uses only the new canonical challenge and capabilities on subsequent session checks', async () => {
    retainPreviousLifetime();
    const initial = client.query(sessionOptions(http, client));
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush(freshIdentity);
    await initial;
    const freshChallenge = '00000000-0000-4000-8000-000000000024';
    const checking = client.query(sessionOptions(http, client));
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush({
      ...freshIdentity,
      email_challenge_id: freshChallenge,
    });
    await expect(checking).resolves.toMatchObject({
      account_id: freshIdentity.account_id,
      registration: null,
      membership_status: 'unverified',
      verified_at: null,
      email_challenge_id: freshChallenge,
      capabilities: {
        can_begin_onboarding: false,
        can_use_student_features: false,
        can_verify_student_email: true,
      },
    });
    expect(
      client.getQueryData<Api['schemas']['IdentityResponse']>(['session'])?.email_challenge_id,
    ).not.toBe(previousIdentity.email_challenge_id);
    expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('a canonical unauthenticated response cannot recover authentication from cached old deletion receipt data', async () => {
    retainPreviousLifetime();
    const checking = client.query(sessionOptions(http, client));
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush(
      { code: 'unauthenticated' },
      { status: 401, statusText: 'Unauthorized' },
    );
    await expect(checking).resolves.toBeNull();
    expect(client.getQueryData(['session'])).toBeNull();
    expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
    backend.expectNone((request) => request.url.includes('/deletion'));
    backend.expectNone('/api/v1/me/profile');
    backend.expectNone((request) => request.method !== 'GET');
  });
});
