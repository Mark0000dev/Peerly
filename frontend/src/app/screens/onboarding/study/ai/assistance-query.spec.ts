import { trustedVerifiedActor as trustedActor } from '../../../verified-actor';
import { HttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { CancelledError, QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../../app.config';
import { ApiFailure } from '../../../../api-http';
import { verifiedActor } from '../../onboarding.fixtures';
import { boundedWrite, jobKey, jobOptions, unknownAdmission } from './assistance-query';
import type { AssistanceIntent } from './assistance-query';
import { clarify, draft, job } from './assistance-test-data';

describe('G01 private query and bounded uncertain writes', () => {
  let client: QueryClient;
  let http: HttpClient;
  let backend: HttpTestingController;
  let controller: AbortController;
  let intent: AssistanceIntent;
  beforeEach(() => {
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(['session'], verifiedActor);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    controller = new AbortController();
    intent = {
      actorId: verifiedActor.account_id,
      body: clarify,
      draft,
      key: 'fixed-unit-key',
      signal: controller.signal,
    };
  });
  afterEach(() => {
    controller.abort();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
    vi.useRealTimers();
  });
  it('requires actual success+idle verified active authority, without activation capability', async () => {
    expect(trustedActor(client, verifiedActor.account_id)).toEqual(verifiedActor);
    expect(trustedActor(client, 'other')).toBeNull();
    for (const actor of [
      null,
      { ...verifiedActor, account_status: 'banned' },
      { ...verifiedActor, membership_status: 'unverified' },
      { ...verifiedActor, membership_status: 'revoked' },
    ]) {
      client.setQueryData(['session'], actor);
      expect(trustedActor(client, verifiedActor.account_id)).toBeNull();
    }
    client.setQueryData(['session'], verifiedActor);
    await expect(
      client.query({
        queryKey: ['session'],
        retry: false,
        staleTime: 0,
        queryFn: () => Promise.reject(new Error('Offline')),
      }),
    ).rejects.toThrow('Offline');
    expect(trustedActor(client, verifiedActor.account_id)).toBeNull();
    client.removeQueries({ queryKey: ['session'] });
    expect(trustedActor(client, verifiedActor.account_id)).toBeNull();
  });
  it('keys actor, source ID/revision, job and original returned hash separately', () => {
    const reference = { id: job().id, hash: '1'.repeat(64) };
    expect(jobKey(intent, reference)).toEqual([
      'account',
      verifiedActor.account_id,
      'goal-assistance',
      draft.source.id,
      draft.source.version,
      reference.id,
      reference.hash,
    ]);
    expect(jobKey(null, null)).toEqual(['goal-assistance-idle']);
    expect(jobKey(intent, null)).toEqual(['goal-assistance-idle']);
    expect(
      jobKey(
        { ...intent, draft: { ...draft, source: { ...draft.source, version: 4 } } },
        reference,
      ),
    ).not.toEqual(jobKey(intent, reference));
  });
  it('reads only the actual owned job and validates its immutable source proof', async () => {
    const reference = { id: job().id, hash: '1'.repeat(64) };
    const loading = client.query(jobOptions(http, client, intent, reference, true));
    const read = backend.expectOne(`/api/v1/ai/jobs/${reference.id}`);
    expect(read.request.method).toBe('GET');
    read.flush(job());
    expect(await loading).toMatchObject({ id: reference.id, state: 'queued' });
  });
  it('aborts and unsubscribes actual HTTP reads when the owning intent retires', async () => {
    const reference = { id: job().id, hash: '1'.repeat(64) };
    const loading = client.query(jobOptions(http, client, intent, reference, true));
    const rejected = expect(loading).rejects.toBeInstanceOf(DOMException);
    const read = backend.expectOne(`/api/v1/ai/jobs/${reference.id}`);
    controller.abort();
    await rejected;
    expect(read.cancelled).toBe(true);
  });
  it('prevents private reads without a current intent/reference/authority or after abort', async () => {
    const reference = { id: job().id, hash: '1'.repeat(64) };
    await expect(
      client.query(jobOptions(http, client, null, reference, true)),
    ).rejects.toBeInstanceOf(CancelledError);
    await expect(client.query(jobOptions(http, client, intent, null, true))).rejects.toBeInstanceOf(
      CancelledError,
    );
    controller.abort();
    await expect(
      client.query(jobOptions(http, client, intent, reference, true)),
    ).rejects.toBeInstanceOf(CancelledError);
    client.setQueryData(['session'], null);
    await expect(
      client.query(
        jobOptions(
          http,
          client,
          { ...intent, signal: new AbortController().signal },
          reference,
          true,
        ),
      ),
    ).rejects.toBeInstanceOf(CancelledError);
    backend.expectNone(`/api/v1/ai/jobs/${reference.id}`);
  });
  it('distinguishes actual hard-OFF rejection from uncertain transport/admission outcomes', () => {
    for (const error of [
      new ApiFailure(0, 'invalid_response', null),
      new ApiFailure(408, 'timeout', null),
      new ApiFailure(502, 'upstream', null),
      new ApiFailure(503, 'request_failed', null),
    ])
      expect(unknownAdmission(error)).toBe(true);
    for (const error of [
      null,
      new Error('Private failure'),
      new ApiFailure(503, 'ai_unavailable', null),
      new ApiFailure(429, 'ai_quota_exceeded', null),
      new ApiFailure(422, 'invalid_request', null),
    ])
      expect(unknownAdmission(error)).toBe(false);
  });
  it('settles successful and failed writes and removes local deadline/abort listeners', async () => {
    const remove = vi.spyOn(controller.signal, 'removeEventListener');
    expect(await boundedWrite(Promise.resolve('receipt'), controller.signal)).toBe('receipt');
    expect(remove).toHaveBeenCalledWith('abort', expect.any(Function));
    await expect(
      boundedWrite(Promise.reject(new ApiFailure(503, 'ai_unavailable', null)), controller.signal),
    ).rejects.toMatchObject({ status: 503, code: 'ai_unavailable' });
    await expect(
      boundedWrite(
        vi.fn<() => Promise<void>>().mockRejectedValue('PRIVATE MODEL TEXT')(),
        controller.signal,
      ),
    ).rejects.toThrow('AI request failed');
  });
  it('times out locally as UNKNOWN and ignores late completion without claiming a server failure', async () => {
    vi.useFakeTimers();
    const waiting = boundedWrite(
      new Promise<void>(() => {
        /* Deliberately never settles. */
      }),
      controller.signal,
      50,
    );
    const rejected = expect(waiting).rejects.toMatchObject({
      status: 0,
      code: 'ai_response_unknown',
    });
    await vi.advanceTimersByTimeAsync(50);
    await rejected;
    expect(vi.getTimerCount()).toBe(0);
  });
  it('retires a pending local write wait, including an already-aborted lifetime, without leaking a timer', async () => {
    vi.useFakeTimers();
    const waiting = boundedWrite(
      new Promise<void>(() => {
        /* Simulate an unanswered command. */
      }),
      controller.signal,
    );
    const rejected = expect(waiting).rejects.toBeInstanceOf(DOMException);
    controller.abort();
    await rejected;
    expect(vi.getTimerCount()).toBe(0);
    await expect(boundedWrite(Promise.resolve('late'), controller.signal)).rejects.toBeInstanceOf(
      DOMException,
    );
    expect(vi.getTimerCount()).toBe(0);
  });
});
