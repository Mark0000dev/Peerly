import { provideHttpClient, HttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { QueryClient } from '@tanstack/angular-query-experimental';
import { describe, expect, it, vi } from 'vitest';
import { nativeQueryBoundary } from './query-boundary';
import { NativeLoginFailure } from './native-login';

function fixture() {
  TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    client,
    controller: TestBed.inject(HttpTestingController),
    boundary: nativeQueryBoundary(TestBed.inject(HttpClient), client, vi.fn()),
  };
}

describe('actual canonical Query session adoption', () => {
  it('retires actor data while retaining unrelated public cache', async () => {
    const context = fixture();
    context.client.setQueryData(['account', 'old', 'messages'], { private: 'synthetic' });
    context.client.setQueryData(['public-catalogue'], ['public']);
    await context.boundary.retirePrivateQueries(new AbortController().signal);
    expect(context.client.getQueryData(['account', 'old', 'messages'])).toBeUndefined();
    expect(context.client.getQueryData(['public-catalogue'])).toEqual(['public']);
    context.client.clear();
  });

  it('adopts only actual /me identity and does not derive APU membership', async () => {
    const context = fixture();
    const result = context.boundary.revalidateSession(new AbortController().signal);
    const request = await vi.waitFor(() => context.controller.expectOne('/api/v1/me'));
    const identity = {
      account_id: 'synthetic-actor',
      account_status: 'active',
      membership_status: 'unverified',
      verified_at: null,
      csrf_token: 'synthetic-csrf',
      email_challenge_id: null,
      registration: null,
      capabilities: {
        can_begin_onboarding: false,
        can_use_student_features: false,
        can_verify_student_email: true,
      },
    };
    request.flush(identity);
    await result;
    expect(context.client.getQueryData(['session'])).toEqual(identity);
    context.controller.verify();
    context.client.clear();
  });

  it('does not count an anonymous /me as native login success', async () => {
    const context = fixture();
    const result = context.boundary.revalidateSession(new AbortController().signal);
    const rejected = expect(result).rejects.toBeInstanceOf(NativeLoginFailure);
    const request = await vi.waitFor(() => context.controller.expectOne('/api/v1/me'));
    request.flush({ code: 'unauthenticated' }, { status: 401, statusText: 'Unauthorized' });
    await rejected;
    expect(context.client.getQueryData(['session'])).toBeNull();
    context.controller.verify();
    context.client.clear();
  });

  it('cancels canonical adoption on actor retirement', async () => {
    const context = fixture();
    const controller = new AbortController();
    const result = context.boundary.revalidateSession(controller.signal);
    const rejected = expect(result).rejects.toMatchObject({ name: 'AbortError' });
    const request = await vi.waitFor(() => context.controller.expectOne('/api/v1/me'));
    controller.abort();
    await rejected;
    expect(request.cancelled).toBe(true);
    context.controller.verify();
    context.client.clear();
  });
});
