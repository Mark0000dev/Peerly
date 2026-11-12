import { HttpClient, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { CancelledError, QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiFailure } from '../../api-http';
import { preferenceOptions, preferenceUnknown, preferenceWrite } from './notification-query';
import { defaultPreference, notificationActorFixture } from './notification-test-data';

afterEach(() => {
  vi.useRealTimers();
  TestBed.resetTestingModule();
});
describe('P02 authority, wire abort and bounded unknown writes', () => {
  it('keys a real canonical read by actor and rejects stale session authority', async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const http = TestBed.inject(HttpClient);
    const backend = TestBed.inject(HttpTestingController);
    const client = new QueryClient();
    const idle = preferenceOptions(http, client, null);
    expect(idle.queryKey).toEqual(['notification-preference-idle']);
    expect(idle.enabled).toBe(false);
    await expect(
      client.query(preferenceOptions(http, client, notificationActorFixture.account_id)),
    ).rejects.toBeInstanceOf(CancelledError);
    backend.expectNone('/api/v1/me/notification-preference');
    client.clear();
  });
  it('uses actual preactivation verified actor and aborts the owned HTTP subscription', async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const http = TestBed.inject(HttpClient);
    const backend = TestBed.inject(HttpTestingController);
    const client = new QueryClient();
    client.setQueryData(['session'], notificationActorFixture);
    const pending = client.query(
      preferenceOptions(http, client, notificationActorFixture.account_id),
    );
    const request = backend.expectOne('/api/v1/me/notification-preference');
    await client.cancelQueries({
      queryKey: ['account', notificationActorFixture.account_id, 'notification-preference'],
    });
    await expect(pending).rejects.toBeInstanceOf(CancelledError);
    expect(request.cancelled).toBe(true);
    client.clear();
    backend.verify();
  });
  it('reads actual DTO without a second preference cache', async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const http = TestBed.inject(HttpClient);
    const backend = TestBed.inject(HttpTestingController);
    const client = new QueryClient();
    client.setQueryData(['session'], notificationActorFixture);
    const pending = client.query(
      preferenceOptions(http, client, notificationActorFixture.account_id),
    );
    backend.expectOne('/api/v1/me/notification-preference').flush(defaultPreference);
    expect(await pending).toEqual(defaultPreference);
    client.clear();
    backend.verify();
  });
  it('classifies only ambiguous transport/server outcomes as unknown', () => {
    for (const status of [0, 408, 500, 503])
      expect(preferenceUnknown(new ApiFailure(status, 'failure', null))).toBe(true);
    for (const error of [
      new Error('failure'),
      new ApiFailure(409, 'conflict', null),
      new ApiFailure(429, 'quota', null),
    ])
      expect(preferenceUnknown(error)).toBe(false);
  });
  it('bounds missing response without claiming write cancellation and rejects after retirement', async () => {
    vi.useFakeTimers();
    let finish: (value: string) => void = () => {
      throw new Error('Missing pending resolver');
    };
    const pending = new Promise<string>((resolve) => {
      finish = resolve;
    });
    const controller = new AbortController();
    const wait = preferenceWrite(pending, controller.signal);
    const assertion = expect(wait).rejects.toMatchObject({ status: 0, code: 'outcome_unknown' });
    await vi.advanceTimersByTimeAsync(15_000);
    await assertion;
    finish('late receipt');
    const retired = new AbortController();
    retired.abort();
    await expect(preferenceWrite(Promise.resolve('late'), retired.signal)).rejects.toBeInstanceOf(
      CancelledError,
    );
    const current = new AbortController();
    const result = preferenceWrite(new Promise<string>(vi.fn()), current.signal);
    const rejected = expect(result).rejects.toBeInstanceOf(CancelledError);
    current.abort();
    await rejected;
  });
  it('preserves confirmed response and normalises a non-Error rejection', async () => {
    expect(await preferenceWrite(Promise.resolve('receipt'), new AbortController().signal)).toBe(
      'receipt',
    );
    const reject = vi.fn<() => Promise<string>>().mockRejectedValue('failure');
    await expect(preferenceWrite(reject(), new AbortController().signal)).rejects.toThrow(
      'Preference request failed',
    );
  });
});
