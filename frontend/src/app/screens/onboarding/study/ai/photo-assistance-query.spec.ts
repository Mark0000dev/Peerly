import { HttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { CancelledError, QueryClient, QueryObserver } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../../app.config';
import { verifiedActor } from '../../onboarding.fixtures';
import { photoJob, photoSource } from './assistance-test-data';
import { photoJobKey, photoJobOptions } from './photo-assistance-query';
import type { PhotoIntent } from './photo-assistance-query';

describe('O02 photo-owned private polling', () => {
  let client: QueryClient;
  let http: HttpClient;
  let backend: HttpTestingController;
  let controller: AbortController;
  let intent: PhotoIntent;
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
      key: 'photo-unit-key',
      body: { kind: 'assess_photo', source: photoSource },
      signal: controller.signal,
    };
  });
  afterEach(() => {
    controller.abort();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
  });
  it('uses nonprivate idle identity and actor/current photo/version/job-bound keys for real jobs', () => {
    expect(photoJobKey(null, null)).toEqual(['photo-assistance-idle']);
    expect(photoJobKey(intent, null)).toEqual(['photo-assistance-idle']);
    expect(photoJobKey(intent, photoJob().id)).toEqual([
      'account',
      verifiedActor.account_id,
      'photo-assistance',
      photoSource.id,
      photoSource.version,
      photoJob().id,
    ]);
    expect(
      photoJobKey(
        { ...intent, body: { ...intent.body, source: { ...photoSource, version: 8 } } },
        photoJob().id,
      ),
    ).not.toEqual(photoJobKey(intent, photoJob().id));
  });
  it('prevents unbound, retired and non-authoritative photo job reads', async () => {
    await expect(
      client.query(photoJobOptions(http, client, null, photoJob().id, true)),
    ).rejects.toBeInstanceOf(CancelledError);
    await expect(
      client.query(photoJobOptions(http, client, intent, null, true)),
    ).rejects.toBeInstanceOf(CancelledError);
    client.setQueryData(['session'], null);
    await expect(
      client.query(photoJobOptions(http, client, intent, photoJob().id, true)),
    ).rejects.toBeInstanceOf(CancelledError);
    client.setQueryData(['session'], verifiedActor);
    controller.abort();
    await expect(
      client.query(photoJobOptions(http, client, intent, photoJob().id, true)),
    ).rejects.toBeInstanceOf(CancelledError);
    backend.expectNone(`/api/v1/ai/jobs/${photoJob().id}`);
  });
  it('rejects a different resource/version even when the server returns the requested job id', async () => {
    const pending = client.query(photoJobOptions(http, client, intent, photoJob().id, true));
    const rejected = expect(pending).rejects.toMatchObject({ status: 0, code: 'invalid_response' });
    backend
      .expectOne(`/api/v1/ai/jobs/${photoJob().id}`)
      .flush(photoJob({ source: { ...photoSource, version: 2 } }));
    await rejected;
  });
  it('consumes the actual polling hint then stops for a terminal observation result', async () => {
    const observer = new QueryObserver(
      client,
      photoJobOptions(http, client, intent, photoJob().id, true),
    );
    const stop = observer.subscribe(() => {
      /* Observe the genuine query lifecycle. */
    });
    try {
      backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}`).flush(photoJob({ poll_after_ms: 20 }));
      const read = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}`));
      read.flush(
        photoJob({
          state: 'succeeded',
          result: { blurred: 'uncertain', face_visible: 'yes', multiple_people: 'no' },
          poll_after_ms: null,
        }),
      );
      await vi.waitFor(() => {
        expect(observer.getCurrentResult().data?.state).toBe('succeeded');
      });
      backend.expectNone(`/api/v1/ai/jobs/${photoJob().id}`);
    } finally {
      stop();
      observer.destroy();
    }
  });
  it('aborts actual HTTP when the owning photo intent retires', async () => {
    const pending = client.query(photoJobOptions(http, client, intent, photoJob().id, true));
    const rejected = expect(pending).rejects.toBeInstanceOf(DOMException);
    const read = backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}`);
    controller.abort();
    await rejected;
    expect(read.cancelled).toBe(true);
  });
});
