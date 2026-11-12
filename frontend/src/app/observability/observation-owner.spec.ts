import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { TestRequest } from '@angular/common/http/testing';
import {
  Component,
  EnvironmentInjector,
  createEnvironmentInjector,
  inject,
  provideEnvironmentInitializer,
  runInInjectionContext,
} from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../api.generated';
import { sessionOptions } from '../screens/session';
import { createObservationBridge } from './observation-bridge';
import type { ObservationBridge } from './observation-bridge';
import { CLIENT_OBSERVATIONS, CLIENT_RELEASE_ASSETS } from './observation-errors';
import { observationInterceptor } from './observation-http';
import { attachClientObservations } from './observation-owner';

@Component({ template: '' })
class Empty {}

const intake = '/api/v1/telemetry/events';
const actorA = {
  account_id: '10000000-0000-4000-8000-000000000001',
  account_status: 'active',
  membership_status: 'unverified',
  verified_at: null,
  registration: null,
  email_challenge_id: null,
  csrf_token: 'synthetic-owner-a',
  capabilities: {
    can_begin_onboarding: false,
    can_use_student_features: false,
    can_verify_student_email: true,
  },
} as const satisfies Api['schemas']['IdentityResponse'];
const actorB = {
  ...actorA,
  account_id: '10000000-0000-4000-8000-000000000002',
  csrf_token: 'synthetic-owner-b',
} as const satisfies Api['schemas']['IdentityResponse'];

function json(request: Readonly<TestRequest>): unknown {
  const raw: unknown = request.request.body;
  if (typeof raw !== 'string') throw new Error('Expected immutable observation JSON');
  const value: unknown = JSON.parse(raw);
  return value;
}
function events(request: Readonly<TestRequest>): readonly unknown[] {
  const value = json(request);
  if (
    typeof value !== 'object' ||
    value === null ||
    !('events' in value) ||
    !Array.isArray(value.events)
  )
    throw new Error('Missing actual observation batch events');
  const result: readonly unknown[] = value.events;
  return result;
}
function eventIds(request: Readonly<TestRequest>): readonly string[] {
  return events(request).map((event) => {
    if (
      typeof event !== 'object' ||
      event === null ||
      !('event_id' in event) ||
      typeof event.event_id !== 'string'
    )
      throw new Error('Missing submitted observation event ID');
    return event.event_id;
  });
}
function screens(request: Readonly<TestRequest>): readonly unknown[] {
  return events(request).filter(
    (event) =>
      typeof event === 'object' &&
      event !== null &&
      'kind' in event &&
      event.kind === 'screen.viewed',
  );
}
function acknowledge(request: Readonly<TestRequest>): void {
  request.flush({
    schema_version: 1,
    accepted: eventIds(request),
    duplicates: [],
    received_at: new Date().toISOString(),
  });
}

describe('actual observation owner injection scope and canonical session lifetime', () => {
  let client: QueryClient;
  let http: HttpClient;
  let backend: HttpTestingController;
  let router: Router;
  let bridge: ObservationBridge;
  let scope: EnvironmentInjector | null;

  beforeEach(async () => {
    scope = null;
    client = new QueryClient({
      defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
    });
    bridge = createObservationBridge();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([observationInterceptor])),
        provideHttpClientTesting(),
        provideTanStackQuery(client),
        { provide: CLIENT_OBSERVATIONS, useValue: bridge },
        { provide: CLIENT_RELEASE_ASSETS, useValue: () => null },
        provideRouter([
          { path: 'chats', component: Empty },
          { path: 'requests', component: Empty },
          {
            path: 'discover',
            component: Empty,
            providers: [
              provideEnvironmentInitializer(() => {
                scope = inject(EnvironmentInjector);
                attachClientObservations();
              }),
            ],
          },
        ]),
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    await router.navigateByUrl('/chats?draft=OWNER_PRIVATE_QUERY');
    // Advance monotonic batch deadlines with delivery timers; keep wall-clock Date native.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] });
  });
  function destroyScope(): void {
    const current = scope;
    scope = null;
    if (current !== null && !current.destroyed) current.destroy();
  }
  afterEach(() => {
    destroyScope();
    client.clear();
    backend.verify();
    TestBed.resetTestingModule();
    vi.useRealTimers();
  });
  function attach(): void {
    if (scope !== null) throw new Error('Owner is already attached');
    scope = createEnvironmentInjector([], TestBed.inject(EnvironmentInjector));
    runInInjectionContext(scope, attachClientObservations);
  }
  async function sent(): Promise<TestRequest> {
    await vi.advanceTimersByTimeAsync(250);
    const request = backend.expectOne(intake);
    expect(request.request.method).toBe('POST');
    return request;
  }
  async function pendingIdentity(): Promise<TestRequest> {
    return await vi.waitFor(() => backend.expectOne('/api/v1/me'));
  }

  it('does not queue guest/unknown activity and emits the first confirmed screen without a membership gate', async () => {
    attach();
    expect(bridge.epoch()).toBeNull();
    expect(bridge.observe({ kind: 'action.observed', action: 'submit', outcome: 'invoked' })).toBe(
      false,
    );
    client.setQueryData(['session'], null);
    client.setQueryData(['account', actorA.account_id, 'unrelated'], { private: 'NOT_TELEMETRY' });
    await vi.advanceTimersByTimeAsync(500);
    backend.expectNone(intake);
    client.setQueryData(['session'], actorA);
    const request = await sent();
    expect(json(request)).toMatchObject({ expected_actor_id: actorA.account_id });
    expect(screens(request)).toEqual([expect.objectContaining({ screen: 'chats' })]);
    expect(request.request.headers.get('x-csrf-token')).toBe(actorA.csrf_token);
    expect(request.request.body).not.toMatch(/OWNER_PRIVATE_QUERY|NOT_TELEMETRY/);
    acknowledge(request);
  });

  it('records the first screen once per confirmed epoch despite unrelated QueryCache notifications', async () => {
    client.setQueryData(['session'], actorA);
    attach();
    const epoch = bridge.epoch()?.id;
    expect(epoch).toBeDefined();
    client.setQueryData(['account', actorA.account_id, 'profile'], { private: 'PRIVATE_PROFILE' });
    client.setQueryData(['session'], { ...actorA, csrf_token: 'synthetic-same-owner-updated' });
    await client.invalidateQueries({ queryKey: ['account', actorA.account_id] });
    const first = await sent();
    expect(screens(first)).toEqual([expect.objectContaining({ screen: 'chats' })]);
    expect(bridge.epoch()?.id).toBe(epoch);
    acknowledge(first);
    await vi.advanceTimersByTimeAsync(0);
    client.setQueryData(['account', actorA.account_id, 'another'], { version: 1 });
    expect(bridge.observe({ kind: 'action.observed', action: 'cancel', outcome: 'invoked' })).toBe(
      true,
    );
    await vi.advanceTimersByTimeAsync(6100);
    const subsequent = backend.expectOne(intake);
    expect(screens(subsequent)).toEqual([]);
    expect(events(subsequent)).toContainEqual(
      expect.objectContaining({ kind: 'action.observed', action: 'cancel' }),
    );
    expect(bridge.epoch()?.id).toBe(epoch);
    acknowledge(subsequent);
  });

  it('a real pending /me fetch immediately aborts the old transport and discards cached-owner drafts before same-owner recovery', async () => {
    client.setQueryData(['session'], actorA);
    attach();
    const old = await sent();
    const oldIds = eventIds(old);
    const formerEpoch = bridge.epoch()?.id;
    const refreshed = client.query(sessionOptions(http, client));
    const identity = await pendingIdentity();
    expect(client.getQueryData<Api['schemas']['IdentityResponse']>(['session'])?.account_id).toBe(
      actorA.account_id,
    );
    expect(client.getQueryState(['session'])?.fetchStatus).toBe('fetching');
    expect(old.cancelled).toBe(true);
    expect(bridge.epoch()).toBeNull();
    expect(bridge.beginAction('retry')).toBeNull();
    expect(bridge.observe({ kind: 'action.observed', action: 'retry', outcome: 'invoked' })).toBe(
      false,
    );
    await vi.advanceTimersByTimeAsync(2000);
    backend.expectNone(intake);
    identity.flush({ ...actorA, csrf_token: 'synthetic-revalidated-a' });
    await refreshed;
    const fresh = await sent();
    expect(json(fresh)).toMatchObject({ expected_actor_id: actorA.account_id });
    expect(fresh.request.headers.get('x-csrf-token')).toBe('synthetic-revalidated-a');
    expect(screens(fresh)).toEqual([expect.objectContaining({ screen: 'chats' })]);
    expect(eventIds(fresh).some((id) => oldIds.includes(id))).toBe(false);
    expect(events(fresh)).not.toContainEqual(expect.objectContaining({ action: 'retry' }));
    expect(bridge.epoch()?.id).not.toBe(formerEpoch);
    acknowledge(fresh);
  });

  it('actual A-to-B /me replacement cannot send or report the previous owner queued activity', async () => {
    client.setQueryData(['session'], actorA);
    attach();
    expect(bridge.observe({ kind: 'action.observed', action: 'upload', outcome: 'invoked' })).toBe(
      true,
    );
    const replacement = client.query(sessionOptions(http, client));
    const identity = await pendingIdentity();
    expect(bridge.epoch()).toBeNull();
    backend.expectNone(intake);
    identity.flush(actorB);
    await replacement;
    const request = await sent();
    expect(json(request)).toMatchObject({ expected_actor_id: actorB.account_id });
    expect(request.request.headers.get('x-csrf-token')).toBe(actorB.csrf_token);
    expect(screens(request)).toEqual([expect.objectContaining({ screen: 'chats' })]);
    expect(events(request)).not.toContainEqual(expect.objectContaining({ action: 'upload' }));
    expect(events(request)).not.toContainEqual(
      expect.objectContaining({ kind: 'quality.observed' }),
    );
    expect(request.request.body).not.toContain(actorA.account_id);
    acknowledge(request);
    client.setQueryData(['session'], null);
    expect(bridge.epoch()).toBeNull();
    expect(bridge.beginAction('submit')).toBeNull();
    await vi.advanceTimersByTimeAsync(10000);
    backend.expectNone(intake);
  });

  it('destroying the real injection environment cancels in-flight delivery and removes cache/router producers', async () => {
    client.setQueryData(['session'], actorA);
    client.setQueryData(['account', actorA.account_id, 'business'], { version: 7 });
    attach();
    const request = await sent();
    destroyScope();
    expect(request.cancelled).toBe(true);
    expect(bridge.epoch()).toBeNull();
    expect(bridge.observe({ kind: 'screen.viewed' })).toBe(false);
    expect(client.getQueryData(['account', actorA.account_id, 'business'])).toEqual({ version: 7 });
    client.setQueryData(['session'], actorB);
    await router.navigateByUrl('/requests');
    await vi.advanceTimersByTimeAsync(65000);
    backend.expectNone(intake);
    expect(bridge.epoch()).toBeNull();
  });

  it('destroying before the first drain removes queued work without ever posting it', async () => {
    client.setQueryData(['session'], actorA);
    attach();
    bridge.observe({ kind: 'action.observed', action: 'submit', outcome: 'invoked' });
    destroyScope();
    client.setQueryData(['session'], actorB);
    await vi.advanceTimersByTimeAsync(10000);
    backend.expectNone(intake);
    expect(bridge.beginAction('submit')).toBeNull();
  });

  it('first attach inside actual route EnvironmentInitializer records the committed destination once', async () => {
    client.setQueryData(['session'], actorA);
    await router.navigateByUrl('/discover?private=OWNER_PRIVATE_QUERY');
    const request = await sent();
    expect(screens(request)).toEqual([expect.objectContaining({ screen: 'discover' })]);
    expect(request.request.body).not.toContain('OWNER_PRIVATE_QUERY');
    acknowledge(request);
    client.setQueryData(['account', actorA.account_id, 'later'], { version: 1 });
    expect(bridge.observe({ kind: 'action.observed', action: 'apply', outcome: 'invoked' })).toBe(
      true,
    );
    await vi.advanceTimersByTimeAsync(6100);
    const later = backend.expectOne(intake);
    expect(screens(later)).toEqual([]);
    acknowledge(later);
  });
  it('a normal completed navigation in the same epoch emits one destination view and route timing without owner duplication', async () => {
    client.setQueryData(['session'], actorA);
    attach();
    expect(scope?.get(QueryClient)).toBe(client);
    const first = await sent();
    const epoch = bridge.epoch()?.id;
    acknowledge(first);
    await vi.advanceTimersByTimeAsync(0);
    await router.navigateByUrl('/requests?private=OWNER_PRIVATE_QUERY');
    await vi.advanceTimersByTimeAsync(6100);
    const destination = backend.expectOne(intake);
    expect(screens(destination)).toEqual([expect.objectContaining({ screen: 'requests' })]);
    expect(events(destination)).toContainEqual(
      expect.objectContaining({ kind: 'performance.observed', metric: 'route_ready' }),
    );
    expect(bridge.epoch()?.id).toBe(epoch);
    expect(destination.request.body).not.toContain('OWNER_PRIVATE_QUERY');
    acknowledge(destination);
  });
});
