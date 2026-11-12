import {
  HttpEventType,
  HttpHeaders,
  HttpHeaderResponse,
  provideHttpClient,
} from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import {
  ApplicationRef,
  createEnvironmentInjector,
  EnvironmentInjector,
  PendingTasks,
} from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Api } from './api.generated';
import { contentRoutes } from './content.routes';

const identity = {
  account_id: '10000000-0000-0000-0000-000000000001',
  account_status: 'active',
  membership_status: 'verified',
  verified_at: '2026-11-08T06:00:00Z',
  registration: null,
  email_challenge_id: null,
  csrf_token: 'bootstrap-fixture-csrf',
  capabilities: {
    can_begin_onboarding: true,
    can_use_student_features: true,
    can_verify_student_email: false,
  },
} as const satisfies Api['schemas']['IdentityResponse'];

describe('content stream initial Angular boot barrier', () => {
  let scope: EnvironmentInjector;
  let client: QueryClient;
  let backend: HttpTestingController;
  let releaseBoot: () => void;
  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    backend = TestBed.inject(HttpTestingController);
    releaseBoot = TestBed.inject(PendingTasks).add();
    const route = contentRoutes[0];
    if (route?.providers === undefined) throw new Error('Missing actual content providers');
    scope = createEnvironmentInjector(route.providers, TestBed.inject(EnvironmentInjector));
    client = scope.get(QueryClient);
  });
  afterEach(() => {
    releaseBoot();
    if (!scope.destroyed) scope.destroy();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    vi.useRealTimers();
    TestBed.resetTestingModule();
  });
  it('waits for real pending bootstrap work, then starts the latest verified actor only', async () => {
    client.setQueryData(['account', identity.account_id, 'boot'], { source: 'former' });
    client.setQueryData(['account', '10000000-0000-0000-0000-000000000002', 'boot'], {
      source: 'latest',
    });
    client.setQueryData(['session'], identity);
    client.setQueryData(['session'], {
      ...identity,
      account_id: '10000000-0000-0000-0000-000000000002',
    });
    backend.expectNone('/api/v1/events');
    releaseBoot();
    const stream = await vi.waitFor(() => backend.expectOne('/api/v1/events'));
    expect(stream.request.method).toBe('GET');
    stream.event(
      new HttpHeaderResponse({
        status: 200,
        headers: new HttpHeaders({ 'Content-Type': 'text/event-stream' }),
      }),
    );
    const body =
      'id: 1\nevent: resource.changed\ndata: ' +
      JSON.stringify({
        resource_type: 'conversation',
        resource_id: '10000000-0000-0000-0000-000000000003',
        version: 1,
      }) +
      '\n\n';
    stream.event({ type: HttpEventType.DownloadProgress, loaded: body.length, partialText: body });
    expect(
      client.getQueryState(['account', '10000000-0000-0000-0000-000000000002', 'boot'])
        ?.isInvalidated,
    ).toBe(true);
    expect(client.getQueryState(['account', identity.account_id, 'boot'])?.isInvalidated).toBe(
      false,
    );
    client.setQueryData(['session'], null);
    expect(stream.cancelled).toBe(true);
    backend.expectNone('/api/v1/events');
  });
  it('does not attach a late actor transport after its actual route scope is destroyed during bootstrap', async () => {
    client.setQueryData(['session'], identity);
    scope.destroy();
    releaseBoot();
    await TestBed.inject(ApplicationRef).whenStable();
    await Promise.resolve();
    backend.expectNone('/api/v1/events');
  });
  it('reconnects after the one-shot barrier even while a later task keeps the app unstable', async () => {
    client.setQueryData(['session'], identity);
    releaseBoot();
    const stream = await vi.waitFor(() => backend.expectOne('/api/v1/events'));
    const releaseLater = TestBed.inject(PendingTasks).add();
    vi.useFakeTimers();
    try {
      stream.flush(': heartbeat\n\n', { headers: { 'Content-Type': 'text/event-stream' } });
      await vi.advanceTimersByTimeAsync(1000);
      backend.expectOne('/api/v1/events');
    } finally {
      releaseLater();
    }
  });
  it('does not start from an identity that lost its student capability before bootstrap completed', async () => {
    client.setQueryData(['session'], identity);
    client.setQueryData(['session'], {
      ...identity,
      capabilities: { ...identity.capabilities, can_use_student_features: false },
    });
    releaseBoot();
    await TestBed.inject(ApplicationRef).whenStable();
    await Promise.resolve();
    backend.expectNone('/api/v1/events');
  });
});
