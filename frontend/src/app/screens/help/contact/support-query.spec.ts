import { provideHttpClient, HttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { CancelledError, QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiFailure } from '../../../api-http';
import {
  recentSupportOptions,
  supportActor,
  supportOutcomeUnknown,
  supportWrite,
} from './support-query';
import { supportActorFixture } from './support-test-data';

afterEach(() => {
  vi.useRealTimers();
  TestBed.resetTestingModule();
});
describe('Support authority and genuine wire cancellation boundaries', () => {
  it('does not turn pending/error session into authority but permits unverified/banned support', () => {
    const client = new QueryClient();
    expect(supportActor(client)).toBeUndefined();
    client.setQueryData(['session'], null);
    expect(supportActor(client)).toBeNull();
    client.setQueryData(['session'], {
      ...supportActorFixture,
      account_status: 'banned',
      membership_status: 'unverified',
    });
    expect(supportActor(client)?.account_status).toBe('banned');
    client.clear();
  });
  it('keeps unknown write outcomes distinct from definitive rejection', () => {
    for (const status of [0, 408, 500, 503])
      expect(supportOutcomeUnknown(new ApiFailure(status, 'failure', null))).toBe(true);
    for (const error of [
      new Error('network'),
      new ApiFailure(422, 'invalid', null),
      new ApiFailure(429, 'quota', null),
    ])
      expect(supportOutcomeUnknown(error)).toBe(false);
  });
  it('bounds a lost write without claiming server cancellation, and ignores a late receipt', async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    let finish: (value: string) => void = () => {
      throw new Error('Missing resolver');
    };
    const underlying = new Promise<string>((resolve) => {
      finish = resolve;
    });
    const promise = supportWrite(underlying, controller.signal);
    const assertion = expect(promise).rejects.toMatchObject({ status: 0, code: 'outcome_unknown' });
    await vi.advanceTimersByTimeAsync(15_000);
    await assertion;
    finish('late');
    await Promise.resolve();
  });
  it('retirement rejects local wait and handles non-Error rejection without swallowing it', async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(supportWrite(Promise.resolve('value'), controller.signal)).rejects.toBeInstanceOf(
      CancelledError,
    );
    await expect(
      supportWrite(
        vi.fn<() => Promise<string>>().mockRejectedValue('failure')(),
        new AbortController().signal,
      ),
    ).rejects.toThrow('Support request failed');
    expect(await supportWrite(Promise.resolve('receipt'), new AbortController().signal)).toBe(
      'receipt',
    );
  });
  it('actual owned read consumes cancellation and never creates proof or case', async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const http = TestBed.inject(HttpClient);
    const backend = TestBed.inject(HttpTestingController);
    const client = new QueryClient();
    const promise = client.query(recentSupportOptions(http, supportActorFixture.account_id, true));
    const pending = backend.expectOne('/api/v1/me/support-cases');
    await client.cancelQueries({
      queryKey: ['account', supportActorFixture.account_id, 'support-recovery'],
    });
    await expect(promise).rejects.toBeInstanceOf(CancelledError);
    expect(pending.cancelled).toBe(true);
    client.clear();
    backend.verify();
  });
});
