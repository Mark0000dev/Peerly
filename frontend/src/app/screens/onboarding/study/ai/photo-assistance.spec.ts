import { HttpClient } from '@angular/common/http';
import { sessionOptions } from '../../../session';
import type { Mutation, Query } from '@tanstack/angular-query-experimental';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import type { TestRequest } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../../../../api.generated';
import { ApiFailure } from '../../../../api-http';
import { appConfig } from '../../../../app.config';
import { verifiedActor } from '../../onboarding.fixtures';
import { click, host, shown } from '../../testing-host';
import { photoJob, photoSource } from './assistance-test-data';
import { PhotoAssistance } from './photo-assistance';

describe('O02 optional photo advice uses actual saved resource only', () => {
  let fixture: ComponentFixture<PhotoAssistance>;
  let backend: HttpTestingController;
  let client: QueryClient;
  let chosen: number;
  let expired: readonly Readonly<{ readonly actorId: string; readonly failure: ApiFailure }>[];
  const result: Api['schemas']['PhotoResultResponse'] = {
    blurred: 'yes',
    face_visible: 'no',
    multiple_people: 'uncertain',
  };
  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    client.setQueryData(['session'], verifiedActor);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(PhotoAssistance);
    fixture.componentRef.setInput('actor', verifiedActor);
    fixture.componentRef.setInput('source', photoSource);
    chosen = 0;
    expired = [];
    fixture.componentInstance.chooseAnother.subscribe(() => {
      chosen += 1;
    });
    fixture.componentInstance.expired.subscribe((value) => {
      expired = [...expired, value];
    });
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    try {
      fixture.destroy();
      client.clear();
      backend.verify({ ignoreCancelled: true });
    } finally {
      TestBed.resetTestingModule();
    }
  });
  function button(label: string): HTMLButtonElement {
    const element = Array.from(host(fixture).querySelectorAll('button')).find(
      (value: Readonly<HTMLButtonElement>) => value.textContent.trim() === label,
    );
    if (element === undefined) throw new Error('Missing photo tips action');
    return element;
  }
  async function start(label = 'Get photo tips'): Promise<TestRequest> {
    fixture.detectChanges();
    click(fixture, label);
    fixture.detectChanges();
    return await vi.waitFor(() => backend.expectOne('/api/v1/ai/jobs'));
  }
  async function ready(): Promise<void> {
    const request = await start();
    request.flush(photoJob({ state: 'succeeded', result, poll_after_ms: null }));
    await shown(fixture, 'Advice only');
  }
  it('offers tips without requests, activation requirements or photo writes', () => {
    expect(verifiedActor.capabilities.can_use_student_features).toBe(false);
    expect(button('Get photo tips').disabled).toBe(false);
    expect(fixture.componentInstance.hasRequest).toBe(false);
    expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
    backend.expectNone('/api/v1/ai/jobs');
    expect(chosen).toBe(0);
  });
  it('sends only assess_photo and current resource id/version, never display URL/file or upload revision metadata', async () => {
    fixture.componentRef.setInput('source', {
      ...photoSource,
      display_url: 'https://storage.invalid/private-original',
      upload_revision: { version: 2 },
    });
    const request = await start();
    expect(request.request.body).toEqual({ kind: 'assess_photo', source: photoSource });
    expect(request.request.headers.get('x-csrf-token')).toBe(verifiedActor.csrf_token);
    expect(request.request.headers.get('idempotency-key')).toBeTruthy();
    request.flush({ code: 'ai_unavailable' }, { status: 503, statusText: 'Unavailable' });
    await shown(fixture, 'Photo tips aren’t available right now');
    expect(button('Get photo tips').disabled).toBe(false);
    expect(chosen).toBe(0);
    backend.expectNone((pending) => !pending.url.startsWith('/api/v1/ai/jobs'));
  });
  it.each([429, 409, 422])(
    'keeps manual photo choices available after actual %s rejection',
    async (status: number) => {
      const request = await start();
      request.flush({ code: 'ai_unavailable' }, { status, statusText: 'Rejected' });
      await shown(
        fixture,
        status === 429
          ? 'AI assistance is busy'
          : status === 409
            ? 'saved photo is no longer available'
            : 'couldn’t get photo tips',
      );
      click(fixture, 'Keep choosing myself');
      fixture.detectChanges();
      expect(button('Get photo tips').disabled).toBe(false);
      expect(chosen).toBe(0);
    },
  );
  it('renders only actual bounded observations and lets the person keep the photo without saving, replacing or approving it', async () => {
    await ready();
    expect(host(fixture).textContent).toContain('A sharper photo may be easier to recognise.');
    expect(host(fixture).textContent).toContain('Consider a photo with your face clearly visible.');
    expect(host(fixture).textContent).toContain(
      'We couldn’t tell whether other people are in the photo.',
    );
    expect(host(fixture).textContent).not.toContain('approved');
    expect(chosen).toBe(0);
    click(fixture, 'Keep this photo');
    fixture.detectChanges();
    expect(chosen).toBe(0);
    expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
    backend.expectNone((pending) => !pending.url.startsWith('/api/v1/ai/jobs'));
  });
  it('requests a manual parent choice only on explicit action and retains advice until the parent acts', async () => {
    await ready();
    click(fixture, 'Choose another photo');
    fixture.detectChanges();
    expect(chosen).toBe(1);
    expect(host(fixture).textContent).toContain('Advice only');
    backend.expectNone((pending) => !pending.url.startsWith('/api/v1/ai/jobs'));
  });
  it('retains an existing intent across an unknown null photo projection, blocks Apply/new requests, and restores the same tips', async () => {
    await ready();
    const staleChoose = button('Choose another photo');
    fixture.componentRef.setInput('sourceChecking', true);
    fixture.componentRef.setInput('source', null);
    fixture.detectChanges();
    staleChoose.click();
    expect(chosen).toBe(0);
    const retained: boolean = fixture.componentInstance.hasRequest;
    expect(retained).toBe(true);
    expect(host(fixture).textContent).toContain('Checking your current saved photo');
    expect(host(fixture).textContent).not.toContain('different saved photo');
    expect(button('Get photo tips').disabled).toBe(true);
    backend.expectNone('/api/v1/ai/jobs');
    fixture.componentRef.setInput('source', photoSource);
    fixture.componentRef.setInput('sourceChecking', false);
    fixture.detectChanges();
    expect(host(fixture).textContent).toContain('Advice only');
    click(fixture, 'Choose another photo');
    expect(chosen).toBe(1);
  });
  it('withdraws tips on a confirmed missing photo and hides the idle widget after local dismissal', async () => {
    await ready();
    fixture.componentRef.setInput('source', null);
    fixture.detectChanges();
    expect(host(fixture).textContent).toContain('different saved photo');
    expect(host(fixture).textContent).not.toContain('Advice only');
    expect(button('Get tips for this photo').disabled).toBe(true);
    click(fixture, 'Dismiss earlier tips');
    fixture.detectChanges();
    expect(host(fixture).querySelector('section')).toBeNull();
    expect(fixture.componentInstance.hasRequest).toBe(false);
    expect(chosen).toBe(0);
  });
  it('withdraws old tips on a different current photo/version and explicitly asks with a fresh source and key', async () => {
    await ready();
    const oldAction = button('Choose another photo');
    const replacement = { ...photoSource, id: '00000000-0000-4000-8000-000000000071', version: 8 };
    fixture.componentRef.setInput('source', replacement);
    oldAction.click();
    fixture.detectChanges();
    expect(chosen).toBe(0);
    expect(host(fixture).textContent).toContain('different saved photo');
    const request = await start('Get tips for this photo');
    expect(request.request.body).toEqual({ kind: 'assess_photo', source: replacement });
    request.flush({ code: 'ai_unavailable' }, { status: 503, statusText: 'Unavailable' });
    await shown(fixture, 'Photo tips aren’t available');
  });
  it('replays only an explicitly retried unknown admission using the original source/body/key despite a new current photo', async () => {
    const first = await start();
    const body: unknown = first.request.body;
    const key = first.request.headers.get('idempotency-key');
    first.error(new ProgressEvent('error'));
    await shown(fixture, 'couldn’t confirm your photo tips request');
    fixture.componentRef.setInput('source', { ...photoSource, version: 8 });
    fixture.detectChanges();
    expect(button('Get photo tips').disabled).toBe(true);
    backend.expectNone('/api/v1/ai/jobs');
    const retry = await start('Retry the same photo tips request');
    expect(retry.request.body).toEqual(body);
    expect(retry.request.headers.get('idempotency-key')).toBe(key);
    retry.flush(photoJob({ state: 'succeeded', result, poll_after_ms: null }));
    await shown(fixture, 'different saved photo');
    expect(chosen).toBe(0);
  });
  it('rejects non-photo results instead of showing unvalidated advice', async () => {
    const request = await start();
    request.flush(
      photoJob({
        state: 'succeeded',
        result: { suggestion: 'Not photo advice' },
        poll_after_ms: null,
      }),
    );
    await shown(fixture, 'couldn’t confirm your photo tips request');
    expect(chosen).toBe(0);
    expect(host(fixture).textContent).not.toContain('Not photo advice');
  });
  it('blocks stale manual actions during pending/failed same-actor validation and retains advice until fresh authority', async () => {
    await ready();
    const action = button('Choose another photo');
    let release: ((actor: Api['schemas']['IdentityResponse']) => void) | undefined;
    const checking = client.query({
      queryKey: ['session'],
      staleTime: 0,
      retry: false,
      queryFn: () =>
        new Promise<Api['schemas']['IdentityResponse']>((resolve) => {
          release = resolve;
        }),
    });
    await vi.waitFor(() => {
      expect(release).toBeDefined();
    });
    action.click();
    fixture.detectChanges();
    expect(chosen).toBe(0);
    if (release === undefined) throw new Error('Missing session completion');
    release(verifiedActor);
    await checking;
    await expect(
      client.query({
        queryKey: ['session'],
        staleTime: 0,
        retry: false,
        queryFn: () => Promise.reject(new ApiFailure(503, 'session_unavailable', null)),
      }),
    ).rejects.toBeInstanceOf(ApiFailure);
    action.click();
    fixture.detectChanges();
    expect(chosen).toBe(0);
    client.setQueryData(['session'], verifiedActor);
    fixture.detectChanges();
    click(fixture, 'Choose another photo');
    expect(chosen).toBe(1);
  });
  it.each([401, 403])(
    'retires actual %s commands through an actor-bound parent event',
    async (status: number) => {
      const request = await start();
      request.flush({ code: 'account_unavailable' }, { status, statusText: 'Denied' });
      await vi.waitFor(() => {
        expect(expired).toHaveLength(1);
      });
      expect(expired[0]?.actorId).toBe(verifiedActor.account_id);
      expect(expired[0]?.failure.status).toBe(status);
      expect(chosen).toBe(0);
    },
  );
  it('ignores an old actor’s late result after actual logout/retirement', async () => {
    const request = await start();
    client.setQueryData(['session'], null);
    fixture.detectChanges();
    request.flush(photoJob({ state: 'succeeded', result, poll_after_ms: null }));
    await vi.waitFor(() => {
      expect(client.getMutationCache().getAll()).toHaveLength(0);
    });
    expect(host(fixture).textContent).not.toContain('Advice only');
    expect(chosen).toBe(0);
  });
  it('aborts an older poll before empty-body cancellation and preserves a result that already won', async () => {
    const request = await start();
    request.flush(photoJob({ poll_after_ms: 20 }));
    await shown(fixture, 'AI photo tips · waiting');
    const olderRead = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}`));
    click(fixture, 'Cancel photo tips');
    const cancel = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}/cancel`),
    );
    expect(olderRead.cancelled).toBe(true);
    expect(cancel.request.body).toBeNull();
    expect(cancel.request.headers.has('idempotency-key')).toBe(false);
    cancel.flush(photoJob({ state: 'succeeded', result, poll_after_ms: null }));
    await shown(fixture, 'Advice only');
    expect(host(fixture).textContent).not.toContain('Photo tips cancelled');
    expect(chosen).toBe(0);
  });
  it('explicitly retries unknown cancellation without changing a photo or promising cancellation', async () => {
    const request = await start();
    request.flush(photoJob());
    await shown(fixture, 'AI photo tips · waiting');
    click(fixture, 'Cancel photo tips');
    const cancel = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}/cancel`),
    );
    cancel.error(new ProgressEvent('error'));
    await shown(fixture, 'Cancellation isn’t confirmed');
    click(fixture, 'Retry photo tips cancellation');
    const retry = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}/cancel`),
    );
    retry.flush(photoJob({ state: 'cancelled', poll_after_ms: null }));
    await shown(fixture, 'Photo tips cancelled');
    expect(chosen).toBe(0);
  });
  it.each(['failed', 'expired', 'cancelled'] as const)(
    'allows only explicit fresh requests after known %s',
    async (state: 'failed' | 'expired' | 'cancelled') => {
      const first = await start();
      const key = first.request.headers.get('idempotency-key');
      first.flush(photoJob({ state, poll_after_ms: null }));
      await shown(fixture, 'Ask for photo tips again');
      backend.expectNone('/api/v1/ai/jobs');
      const second = await start('Ask for photo tips again');
      expect(second.request.headers.get('idempotency-key')).not.toBe(key);
      second.flush({ code: 'ai_unavailable' }, { status: 503, statusText: 'Unavailable' });
      await shown(fixture, 'Photo tips aren’t available');
    },
  );
  it('bounds polling by the actual deadline without fabricating expiry, and retires actual reads on destroy', async () => {
    const request = await start();
    request.flush(
      photoJob({
        created_at: new Date(Date.now() - 10_000).toISOString(),
        deadline: new Date(Date.now() - 1000).toISOString(),
      }),
    );
    await shown(fixture, 'Automatic checking has stopped');
    click(fixture, 'Check photo tips job');
    const read = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}`));
    fixture.destroy();
    expect(read.cancelled).toBe(true);
    expect(chosen).toBe(0);
  });
  it('blocks a queued admission when the saved photo starts checking, then asks only for the explicitly selected current resource', async () => {
    button('Get photo tips').click();
    fixture.componentRef.setInput('sourceChecking', true);
    fixture.detectChanges();
    await vi.waitFor(() => {
      expect(
        client
          .getMutationCache()
          .getAll()
          .some((mutation: Readonly<Mutation>) => mutation.state.status === 'error'),
      ).toBe(true);
    });
    backend.expectNone({ url: '/api/v1/ai/jobs', method: 'POST' });
    const replacement = { ...photoSource, version: photoSource.version + 1 };
    fixture.componentRef.setInput('source', replacement);
    fixture.componentRef.setInput('sourceChecking', false);
    await shown(fixture, 'You have a different saved photo');
    const current = button('Get tips for this photo');
    fixture.componentRef.setInput('sourceChecking', true);
    current.click();
    fixture.detectChanges();
    backend.expectNone({ url: '/api/v1/ai/jobs', method: 'POST' });
    fixture.componentRef.setInput('sourceChecking', false);
    fixture.detectChanges();
    const request = await start('Get tips for this photo');
    expect(request.request.body).toEqual({ kind: 'assess_photo', source: replacement });
    request.flush(photoJob({ source: replacement }));
    await shown(fixture, 'AI photo tips · waiting');
    expect(chosen).toBe(0);
  });
  it('does not dispatch a queued photo admission during real session revalidation and uses fresh CSRF only after a new explicit ask', async () => {
    button('Get photo tips').click();
    const validation = client.query(sessionOptions(TestBed.inject(HttpClient), client));
    const session = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    backend.expectNone({ url: '/api/v1/ai/jobs', method: 'POST' });
    const rotated = { ...verifiedActor, csrf_token: 'fresh-photo-ai-authority' };
    session.flush(rotated);
    await validation;
    await shown(fixture, 'We couldn’t get photo tips.');
    expect(expired).toEqual([]);
    expect(chosen).toBe(0);
    const request = await start();
    expect(request.request.headers.get('x-csrf-token')).toBe(rotated.csrf_token);
    request.flush({ code: 'ai_unavailable' }, { status: 503, statusText: 'Unavailable' });
    await shown(fixture, 'Photo tips aren’t available');
  });
  it('cold-checks the known photo job after actual same-actor session cache eviction without exposing the previous advice', async () => {
    await ready();
    const validation = client.query(sessionOptions(TestBed.inject(HttpClient), client));
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush(verifiedActor);
    await validation;
    const read = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}`));
    await shown(fixture, 'Checking your photo tips…');
    expect(host(fixture).textContent).not.toContain('Advice only');
    expect(chosen).toBe(0);
    read.flush(photoJob({ state: 'succeeded', result, poll_after_ms: null }));
    await shown(fixture, 'Advice only');
    backend.expectNone({ url: '/api/v1/ai/jobs', method: 'POST' });
    expect(chosen).toBe(0);
  });
  it('blocks stale manual Check and duplicate Cancel while cancelling and retains uncertainty when the manual read fails', async () => {
    const admission = await start();
    admission.flush(
      photoJob({
        created_at: new Date(Date.now() - 10_000).toISOString(),
        deadline: new Date(Date.now() - 1000).toISOString(),
      }),
    );
    await shown(fixture, 'Automatic checking has stopped');
    const check = button('Check photo tips job');
    const cancel = button('Cancel photo tips');
    cancel.click();
    check.click();
    cancel.click();
    fixture.detectChanges();
    const request = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}/cancel`),
    );
    backend.expectNone(`/api/v1/ai/jobs/${photoJob().id}`);
    request.flush({ code: 'unavailable' }, { status: 503, statusText: 'Unavailable' });
    await shown(fixture, 'Cancellation isn’t confirmed');
    click(fixture, 'Check photo tips job');
    (await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}`))).flush(
      { code: 'unavailable' },
      { status: 503, statusText: 'Unavailable' },
    );
    await vi.waitFor(() => {
      expect(
        client
          .getQueryCache()
          .findAll({ queryKey: ['account', verifiedActor.account_id, 'photo-assistance'] })
          .some((query: Readonly<Query>) => query.state.status === 'error'),
      ).toBe(true);
    });
    fixture.detectChanges();
    expect(host(fixture).textContent).toContain('Cancellation isn’t confirmed');
    expect(host(fixture).textContent).not.toContain('Photo tips cancelled');
    click(fixture, 'Check photo tips job');
    (await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}`))).flush(
      photoJob({ state: 'succeeded', result, poll_after_ms: null }),
    );
    await shown(fixture, 'Advice only');
    expect(chosen).toBe(0);
    backend.expectNone({ url: '/api/v1/ai/jobs', method: 'POST' });
  });
  for (const status of [401, 403])
    it(`reports current photo cancellation denial ${String(status)} for the actual owning actor`, async () => {
      const admission = await start();
      admission.flush(photoJob());
      await shown(fixture, 'AI photo tips · waiting');
      click(fixture, 'Cancel photo tips');
      (await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}/cancel`))).flush(
        { code: 'account_unavailable' },
        { status, statusText: 'Denied' },
      );
      await vi.waitFor(() => {
        expect(expired).toHaveLength(1);
      });
      expect(expired[0]?.actorId).toBe(verifiedActor.account_id);
      expect(expired[0]?.failure.status).toBe(status);
      expect(chosen).toBe(0);
    });
  for (const status of [200, 403])
    it(`ignores old photo cancellation ${String(status)} when actor input retires ownership before cached session changes`, async () => {
      const admission = await start();
      admission.flush(photoJob());
      await shown(fixture, 'AI photo tips · waiting');
      click(fixture, 'Cancel photo tips');
      const cancel = await vi.waitFor(() =>
        backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}/cancel`),
      );
      const replacement = { ...verifiedActor, account_id: 'photo-ai-replacement' };
      fixture.componentRef.setInput('actor', replacement);
      fixture.detectChanges();
      client.setQueryData(['session'], replacement);
      cancel.flush(
        status === 200
          ? photoJob({ state: 'succeeded', result, poll_after_ms: null })
          : { code: 'account_unavailable' },
        { status, statusText: 'Result' },
      );
      await fixture.whenStable();
      fixture.detectChanges();
      expect(host(fixture).textContent).not.toContain('Advice only');
      expect(expired).toEqual([]);
      expect(chosen).toBe(0);
      expect(
        client.getQueryCache().findAll({ queryKey: ['account', verifiedActor.account_id] }),
      ).toHaveLength(0);
      backend.expectNone({ url: '/api/v1/ai/jobs', method: 'POST' });
    });
  it('blocks a captured terminal Ask again while the current saved photo is checking', async () => {
    const admission = await start();
    admission.flush(photoJob({ state: 'failed', failure: 'timeout', poll_after_ms: null }));
    await shown(fixture, 'Ask for photo tips again');
    const again = button('Ask for photo tips again');
    fixture.componentRef.setInput('sourceChecking', true);
    again.click();
    fixture.detectChanges();
    backend.expectNone({ url: '/api/v1/ai/jobs', method: 'POST' });
    expect(chosen).toBe(0);
    fixture.componentRef.setInput('sourceChecking', false);
    fixture.detectChanges();
    const request = await start('Ask for photo tips again');
    request.flush(photoJob());
    await shown(fixture, 'AI photo tips · waiting');
  });
  it('rejects a stale Choose event after actual cached-job refetch failure and restores only explicitly rechecked advice', async () => {
    await ready();
    const choose = button('Choose another photo');
    const refresh = client.refetchQueries({
      queryKey: ['account', verifiedActor.account_id, 'photo-assistance'],
    });
    (await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}`))).flush(
      { code: 'unavailable' },
      { status: 503, statusText: 'Unavailable' },
    );
    await refresh;
    choose.click();
    fixture.detectChanges();
    expect(chosen).toBe(0);
    await shown(fixture, 'We couldn’t check these photo tips');
    click(fixture, 'Check photo tips again');
    (await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${photoJob().id}`))).flush(
      photoJob({ state: 'succeeded', result, poll_after_ms: null }),
    );
    await shown(fixture, 'Advice only');
    click(fixture, 'Choose another photo');
    expect(chosen).toBe(1);
    backend.expectNone({ url: '/api/v1/ai/jobs', method: 'POST' });
  });
  it('does not let an old dismiss event retire an explicitly requested replacement photo job', async () => {
    await ready();
    const replacement = { ...photoSource, version: photoSource.version + 1 };
    fixture.componentRef.setInput('source', replacement);
    await shown(fixture, 'You have a different saved photo');
    const dismiss = button('Dismiss earlier tips');
    button('Get tips for this photo').click();
    dismiss.click();
    fixture.detectChanges();
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/ai/jobs', method: 'POST' }),
    );
    expect(request.request.body).toEqual({ kind: 'assess_photo', source: replacement });
    request.flush(photoJob({ source: replacement }));
    await shown(fixture, 'AI photo tips · waiting');
    expect(chosen).toBe(0);
    backend.expectNone({ url: '/api/v1/ai/jobs', method: 'POST' });
  });
});
