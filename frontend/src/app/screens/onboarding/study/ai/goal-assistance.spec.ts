import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import type { TestRequest } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { provideTanStackQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../../../../api.generated';
import { ApiFailure } from '../../../../api-http';
import { appConfig } from '../../../../app.config';
import { verifiedActor } from '../../onboarding.fixtures';
import { click, host, shown } from '../../testing-host';
import { draft, job } from './assistance-test-data';
import { GoalAssistance } from './goal-assistance';
import type {
  ApplyGoalArea,
  ApplyGoalText,
  AssistanceExpired,
  GoalAssistanceDraft,
} from './goal-assistance-contract';

describe('G01 optional actual AI job lifecycle', () => {
  let fixture: ComponentFixture<GoalAssistance>;
  let backend: HttpTestingController;
  let client: QueryClient;
  let texts: readonly ApplyGoalText[];
  let areas: readonly ApplyGoalArea[];
  let expired: readonly AssistanceExpired[];
  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    client.setQueryData(['session'], verifiedActor);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(GoalAssistance);
    fixture.componentRef.setInput('actor', verifiedActor);
    fixture.componentRef.setInput('draft', draft);
    texts = [];
    areas = [];
    expired = [];
    fixture.componentInstance.applyText.subscribe((value: ApplyGoalText) => {
      texts = [...texts, value];
    });
    fixture.componentInstance.applyArea.subscribe((value: ApplyGoalArea) => {
      areas = [...areas, value];
    });
    fixture.componentInstance.expired.subscribe((value: AssistanceExpired) => {
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
    const value = Array.from(host(fixture).querySelectorAll('button')).find(
      (element: Readonly<HTMLButtonElement>) => element.textContent.trim() === label,
    );
    if (value === undefined) throw new Error('Missing action');
    return value;
  }
  function edit(value: GoalAssistanceDraft): void {
    fixture.componentRef.setInput('draft', value);
    fixture.detectChanges();
  }
  async function start(label = 'Suggest clearer wording'): Promise<TestRequest> {
    click(fixture, label);
    fixture.detectChanges();
    return await vi.waitFor(() => backend.expectOne({ url: '/api/v1/ai/jobs', method: 'POST' }));
  }
  async function admit(value: Api['schemas']['JobResponse'] = job()): Promise<void> {
    const request = await start();
    request.flush(value);
    await shown(
      fixture,
      value.state === 'succeeded' ? 'Review before using' : 'AI assistance · waiting',
    );
  }
  async function ready(): Promise<void> {
    await admit(
      job({
        state: 'succeeded',
        result: { suggestion: 'Please help me understand LEFT JOIN with NULLs.' },
        poll_after_ms: null,
      }),
    );
  }
  async function pendingSession(): Promise<Readonly<{ readonly finish: () => Promise<void> }>> {
    let release: ((value: Api['schemas']['IdentityResponse']) => void) | undefined;
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
    return {
      finish: async () => {
        if (release === undefined) throw new Error('Missing session check');
        release(verifiedActor);
        await checking;
        fixture.detectChanges();
      },
    };
  }

  it('offers optional assistance to verified preactivation actors and sends nothing before explicit ask', () => {
    expect(verifiedActor.capabilities.can_use_student_features).toBe(false);
    expect(button('Suggest clearer wording').disabled).toBe(false);
    expect(button('Suggest a knowledge area').disabled).toBe(false);
    backend.expectNone('/api/v1/ai/jobs');
    expect(texts).toEqual([]);
    expect(areas).toEqual([]);
  });
  it('keeps idle observers outside private account queries before binding and after clearing advice', async () => {
    expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
    await ready();
    expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(1);
    click(fixture, 'Keep mine');
    fixture.detectChanges();
    expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
    client.removeQueries({ queryKey: ['account'] });
    fixture.detectChanges();
    expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
    expect(button('Suggest clearer wording').disabled).toBe(false);
    backend.expectNone('/api/v1/ai/jobs');
  });
  it('blocks blank/overlong context and missing or overlong catalogue input without writes', () => {
    for (const context of ['', ' ', 'x'.repeat(241)]) {
      edit({ ...draft, context });
      expect(button('Suggest clearer wording').disabled).toBe(true);
      button('Suggest clearer wording').click();
    }
    for (const value of [
      { ...draft, candidates: [] },
      { ...draft, areaLabel: 'x'.repeat(81) },
    ]) {
      edit(value);
      expect(button('Suggest a knowledge area').disabled).toBe(true);
    }
    backend.expectNone('/api/v1/ai/jobs');
  });
  it('submits only the actual context request, with CSRF and an immutable key, without changing the parent draft', async () => {
    const request = await start();
    expect(request.request.body).toEqual({
      kind: 'clarify_goal',
      source: draft.source,
      target: 'context',
      text: draft.context,
    });
    expect(request.request.headers.get('x-csrf-token')).toBe(verifiedActor.csrf_token);
    expect(request.request.headers.get('idempotency-key')).toBeTruthy();
    expect(host(fixture).textContent).toContain('Requesting AI assistance');
    request.flush({ code: 'ai_unavailable' }, { status: 503, statusText: 'Unavailable' });
    await shown(fixture, 'AI assistance isn’t available right now');
    expect(host(fixture).textContent).toContain('write and save as usual');
    expect(fixture.componentInstance.draft()).toEqual(draft);
    expect(texts).toEqual([]);
    expect(button('Suggest clearer wording').disabled).toBe(false);
    click(fixture, 'Keep writing myself');
    fixture.detectChanges();
    expect(host(fixture).textContent).not.toContain('isn’t available');
  });
  it.each([429, 409, 422])(
    'keeps manual inputs and never retries a known %s rejection automatically',
    async (status: number) => {
      const request = await start();
      request.flush({ code: 'ai_unavailable' }, { status, statusText: 'Rejected' });
      await shown(
        fixture,
        status === 429
          ? 'AI assistance is busy'
          : status === 409
            ? 'no longer matches'
            : 'couldn’t get a suggestion',
      );
      backend.expectNone('/api/v1/ai/jobs');
      expect(texts).toEqual([]);
      expect(areas).toEqual([]);
    },
  );
  it('keeps a known unavailable response honest after editing instead of claiming an earlier suggestion exists', async () => {
    const request = await start();
    request.flush({ code: 'ai_unavailable' }, { status: 503, statusText: 'Unavailable' });
    await shown(fixture, 'AI assistance isn’t available right now');
    edit({ ...draft, context: 'My own updated context.', source: { ...draft.source, version: 4 } });
    expect(host(fixture).textContent).toContain('AI assistance isn’t available right now');
    expect(host(fixture).textContent).not.toContain('earlier version');
    expect(button('Suggest clearer wording').disabled).toBe(false);
    backend.expectNone('/api/v1/ai/jobs');
    expect(texts).toEqual([]);
  });
  it('replays only the exact uncertain body/key after explicit retry, even after editing the source', async () => {
    const first = await start();
    const body: unknown = first.request.body;
    const key = first.request.headers.get('idempotency-key');
    first.error(new ProgressEvent('error'));
    await shown(fixture, 'couldn’t confirm this request');
    edit({ ...draft, context: 'New text', source: { ...draft.source, version: 4 } });
    expect(button('Suggest clearer wording').disabled).toBe(true);
    backend.expectNone('/api/v1/ai/jobs');
    const second = await start('Retry the same AI request');
    expect(second.request.body).toEqual(body);
    expect(second.request.headers.get('idempotency-key')).toBe(key);
    second.flush(
      job({ state: 'succeeded', result: { suggestion: 'Old advice' }, poll_after_ms: null }),
    );
    await shown(fixture, 'You changed the goal after asking');
    expect(texts).toEqual([]);
    click(fixture, 'Dismiss earlier suggestion');
    fixture.detectChanges();
    expect(button('Suggest clearer wording').disabled).toBe(false);
  });
  it('rejects wrong-kind admission as an unknown response instead of applying fabricated advice', async () => {
    const request = await start();
    request.flush(job({ kind: 'assess_photo', result: null }));
    await shown(fixture, 'couldn’t confirm this request');
    expect(texts).toEqual([]);
  });
  it('applies a successful suggestion only on explicit Use and never writes a goal', async () => {
    await ready();
    expect(texts).toEqual([]);
    click(fixture, 'Use suggestion');
    fixture.detectChanges();
    expect(texts).toEqual([
      {
        source: draft.source,
        target: 'context',
        value: 'Please help me understand LEFT JOIN with NULLs.',
      },
    ]);
    backend.expectNone('/api/v1/me/goal');
    expect(fixture.componentInstance.draft()).toEqual(draft);
    expect(host(fixture).textContent).not.toContain('Review before using');
  });
  it('keeps mine without applying a suggestion', async () => {
    await ready();
    click(fixture, 'Keep mine');
    fixture.detectChanges();
    expect(texts).toEqual([]);
    expect(button('Suggest clearer wording').disabled).toBe(false);
  });
  it('retains text and area advice while parent CAS locks Apply and uses it only after explicit unlocked action', async () => {
    await ready();
    const textAction = button('Use suggestion');
    fixture.componentRef.setInput('applyDisabled', true);
    textAction.click();
    fixture.detectChanges();
    expect(texts).toEqual([]);
    expect(button('Use suggestion').disabled).toBe(true);
    expect(host(fixture).textContent).toContain('Please help me understand LEFT JOIN with NULLs.');
    fixture.componentRef.setInput('applyDisabled', false);
    fixture.detectChanges();
    click(fixture, 'Use suggestion');
    fixture.detectChanges();
    expect(texts).toHaveLength(1);
    expect(button('Suggest a knowledge area').disabled).toBe(false);
    const request = await start('Suggest a knowledge area');
    request.flush(
      job({
        kind: 'suggest_subject',
        target: null,
        state: 'succeeded',
        poll_after_ms: null,
        result: { ids: [draft.candidates[0]?.id ?? ''] },
      }),
    );
    await shown(fixture, 'Use Computing');
    const areaAction = button('Use Computing');
    fixture.componentRef.setInput('applyDisabled', true);
    areaAction.click();
    fixture.detectChanges();
    expect(areas).toEqual([]);
    expect(button('Use Computing').disabled).toBe(true);
    expect(host(fixture).textContent).toContain('Review before using');
    fixture.componentRef.setInput('applyDisabled', false);
    fixture.detectChanges();
    click(fixture, 'Use Computing');
    expect(areas).toHaveLength(1);
    backend.expectNone('/api/v1/me/goal');
  });
  it('offers only captured actual catalogue names/IDs and never invents a topic', async () => {
    const request = await start('Suggest a knowledge area');
    expect(request.request.body).toEqual({
      kind: 'suggest_subject',
      source: draft.source,
      label: draft.areaLabel,
      candidate_ids: draft.candidates.map(
        (value: Readonly<Pick<Api['schemas']['SubjectResponse'], 'id' | 'name'>>) => value.id,
      ),
    });
    request.flush(
      job({
        kind: 'suggest_subject',
        target: null,
        state: 'succeeded',
        poll_after_ms: null,
        result: { ids: [draft.candidates[0]?.id ?? ''] },
      }),
    );
    await shown(fixture, 'Use Computing');
    expect(areas).toEqual([]);
    click(fixture, 'Use Computing');
    fixture.detectChanges();
    expect(areas).toEqual([{ source: draft.source, id: draft.candidates[0]?.id }]);
    expect(texts).toEqual([]);
  });
  it('shows a genuine empty catalogue result with a manual route', async () => {
    const request = await start('Suggest a knowledge area');
    request.flush(
      job({
        kind: 'suggest_subject',
        target: null,
        state: 'succeeded',
        poll_after_ms: null,
        result: { ids: [] },
      }),
    );
    await shown(fixture, 'No knowledge area was suggested');
    expect(areas).toEqual([]);
    click(fixture, 'Keep mine');
  });
  it('withdraws Use when context, candidate labels or parent revision changes', async () => {
    await ready();
    const stale = button('Use suggestion');
    edit({ ...draft, source: { ...draft.source, version: 4 } });
    stale.click();
    expect(texts).toEqual([]);
    expect(host(fixture).textContent).toContain('earlier version');
  });
  it('blocks a stale DOM Use during pending and failed same-actor revalidation, then permits only after fresh success', async () => {
    await ready();
    const stale = button('Use suggestion');
    const session = await pendingSession();
    stale.click();
    fixture.detectChanges();
    expect(texts).toEqual([]);
    expect(host(fixture).textContent).toContain('current verified session');
    await session.finish();
    await expect(
      client.query({
        queryKey: ['session'],
        staleTime: 0,
        retry: false,
        queryFn: () => Promise.reject(new ApiFailure(503, 'session_unavailable', null)),
      }),
    ).rejects.toBeInstanceOf(ApiFailure);
    stale.click();
    fixture.detectChanges();
    expect(texts).toEqual([]);
    client.setQueryData(['session'], verifiedActor);
    fixture.detectChanges();
    click(fixture, 'Use suggestion');
    expect(texts).toHaveLength(1);
  });
  it('blocks requests from stale DOM buttons while authority is being checked', async () => {
    const stale = button('Suggest clearer wording');
    const session = await pendingSession();
    stale.click();
    backend.expectNone('/api/v1/ai/jobs');
    await session.finish();
  });
  it.each([401, 403])(
    'emits the actual actor-bound %s failure and retires the feature without private output',
    async (status: number) => {
      const request = await start();
      request.flush({ code: 'account_unavailable' }, { status, statusText: 'Denied' });
      await vi.waitFor(() => {
        expect(expired).toHaveLength(1);
      });
      expect(expired[0]?.actorId).toBe(verifiedActor.account_id);
      expect(expired[0]?.failure.status).toBe(status);
      expect(texts).toEqual([]);
    },
  );
  it('retires accepted advice on actual logout and actor replacement', async () => {
    await ready();
    const stale = button('Use suggestion');
    client.setQueryData(['session'], null);
    stale.click();
    fixture.detectChanges();
    expect(texts).toEqual([]);
    const replacement = { ...verifiedActor, account_id: '00000000-0000-4000-8000-000000000055' };
    fixture.componentRef.setInput('actor', replacement);
    client.setQueryData(['session'], replacement);
    fixture.detectChanges();
    expect(host(fixture).textContent).not.toContain('Review before using');
    const request = await start();
    request.flush(job());
    await shown(fixture, 'AI assistance · waiting');
  });
  it('ignores an old actor’s late admission and removes owned mutation data', async () => {
    const request = await start();
    client.setQueryData(['session'], {
      ...verifiedActor,
      account_id: '00000000-0000-4000-8000-000000000077',
    });
    fixture.detectChanges();
    request.flush(
      job({ state: 'succeeded', result: { suggestion: 'Late old actor' }, poll_after_ms: null }),
    );
    await vi.waitFor(() => {
      expect(client.getMutationCache().getAll()).toHaveLength(0);
    });
    expect(texts).toEqual([]);
    expect(host(fixture).textContent).not.toContain('Late old actor');
  });
  it('cancels an owned queued job with empty body and no invented idempotency key', async () => {
    await admit();
    click(fixture, 'Cancel AI job');
    const cancel = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${job().id}/cancel`));
    expect(cancel.request.body).toBeNull();
    expect(cancel.request.headers.has('idempotency-key')).toBe(false);
    expect(cancel.request.headers.get('x-csrf-token')).toBe(verifiedActor.csrf_token);
    cancel.flush(job({ state: 'cancelled', poll_after_ms: null }));
    await shown(fixture, 'AI suggestion cancelled');
    expect(texts).toEqual([]);
  });
  it('aborts an older in-flight poll before canonical cancellation can be overwritten', async () => {
    await admit(job({ poll_after_ms: 20 }));
    const olderRead = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${job().id}`));
    click(fixture, 'Cancel AI job');
    const cancel = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${job().id}/cancel`));
    cancel.flush(job({ state: 'cancelled', poll_after_ms: null }));
    await shown(fixture, 'AI suggestion cancelled');
    expect(olderRead.cancelled).toBe(true);
    expect(texts).toEqual([]);
  });
  it('accepts a result that won before cancellation without claiming it was undone', async () => {
    await admit();
    click(fixture, 'Cancel AI job');
    const cancel = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${job().id}/cancel`));
    cancel.flush(
      job({
        state: 'succeeded',
        result: { suggestion: 'Completed before cancel' },
        poll_after_ms: null,
      }),
    );
    await shown(fixture, 'Completed before cancel');
    expect(host(fixture).textContent).not.toContain('suggestion cancelled');
    expect(texts).toEqual([]);
    click(fixture, 'Use suggestion');
    expect(texts).toHaveLength(1);
  });
  it('retries only explicit uncertain cancellation and treats a later server result canonically', async () => {
    await admit();
    click(fixture, 'Cancel AI job');
    const first = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${job().id}/cancel`));
    first.error(new ProgressEvent('error'));
    await shown(fixture, 'Cancellation isn’t confirmed');
    backend.expectNone(`/api/v1/ai/jobs/${job().id}/cancel`);
    click(fixture, 'Retry cancellation');
    const retry = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${job().id}/cancel`));
    expect(retry.request.body).toBeNull();
    retry.flush(job({ state: 'cancelled', poll_after_ms: null }));
    await shown(fixture, 'AI suggestion cancelled');
  });
  it.each(['failed', 'expired'] as const)(
    'renders actual terminal %s without applying or automatically creating another job',
    async (state: 'failed' | 'expired') => {
      const request = await start();
      request.flush(job({ state, failure: 'timeout', poll_after_ms: null }));
      await shown(fixture, state === 'expired' ? 'AI job expired' : 'couldn’t get a suggestion');
      expect(texts).toEqual([]);
      backend.expectNone('/api/v1/ai/jobs');
      click(fixture, 'Keep mine');
    },
  );
  it('polls the actual hint, rejects changed source proof, and requires explicit read retry', async () => {
    await admit(job({ poll_after_ms: 20 }));
    const read = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${job().id}`));
    read.flush(job({ source: { ...draft.source, content_hash: '2'.repeat(64) } }));
    await shown(fixture, 'couldn’t check this AI job');
    expect(texts).toEqual([]);
    click(fixture, 'Check AI job again');
    const retry = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${job().id}`));
    retry.flush(
      job({ state: 'succeeded', result: { suggestion: 'Checked result' }, poll_after_ms: null }),
    );
    await shown(fixture, 'Checked result');
  });
  it('lets the student stop viewing a failed known job read without falsely cancelling or resubmitting it', async () => {
    await admit(job({ poll_after_ms: 20 }));
    const read = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${job().id}`));
    read.flush({ code: 'ai_job_unavailable' }, { status: 404, statusText: 'Unavailable' });
    await shown(fixture, 'couldn’t check this AI job');
    click(fixture, 'Keep writing myself');
    fixture.detectChanges();
    expect(button('Suggest clearer wording').disabled).toBe(false);
    expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
    expect(host(fixture).textContent).not.toContain('suggestion cancelled');
    backend.expectNone(`/api/v1/ai/jobs/${job().id}/cancel`);
    backend.expectNone('/api/v1/ai/jobs');
    expect(fixture.componentInstance.draft()).toEqual(draft);
  });
  it('lets the student leave an unconfirmed cancellation without claiming that server processing stopped', async () => {
    await admit();
    click(fixture, 'Cancel AI job');
    const cancel = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${job().id}/cancel`));
    cancel.error(new ProgressEvent('error'));
    await shown(fixture, 'Cancellation isn’t confirmed');
    click(fixture, 'Keep writing myself');
    fixture.detectChanges();
    expect(button('Suggest clearer wording').disabled).toBe(false);
    expect(host(fixture).textContent).not.toContain('suggestion cancelled');
    backend.expectNone(`/api/v1/ai/jobs/${job().id}/cancel`);
    backend.expectNone('/api/v1/ai/jobs');
    expect(texts).toEqual([]);
  });
  it('creates a fresh request only after an explicit Ask again for a known terminal job', async () => {
    const first = await start();
    const body: unknown = first.request.body;
    const key = first.request.headers.get('idempotency-key');
    first.flush(job({ state: 'failed', failure: 'transient', poll_after_ms: null }));
    await shown(fixture, 'couldn’t get a suggestion');
    backend.expectNone('/api/v1/ai/jobs');
    const retry = await start('Ask again');
    expect(retry.request.body).toEqual(body);
    expect(retry.request.headers.get('idempotency-key')).not.toBe(key);
    retry.flush(
      job({
        id: '00000000-0000-4000-8000-000000000021',
        state: 'succeeded',
        poll_after_ms: null,
        result: { suggestion: 'A fresh suggestion.' },
      }),
    );
    await shown(fixture, 'A fresh suggestion.');
    expect(texts).toEqual([]);
  });
  it('stops automatic polling at the actual deadline without inventing a server expired state', async () => {
    await admit(
      job({
        created_at: new Date(Date.now() - 10_000).toISOString(),
        deadline: new Date(Date.now() - 1000).toISOString(),
      }),
    );
    await shown(fixture, 'Automatic checking has stopped');
    backend.expectNone(`/api/v1/ai/jobs/${job().id}`);
    click(fixture, 'Check AI job');
    const read = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${job().id}`));
    read.flush(job({ state: 'expired', poll_after_ms: null }));
    await shown(fixture, 'AI job expired');
  });
  it('aborts an actual in-flight poll on destroy and ignores late admission outputs', async () => {
    await admit(job({ poll_after_ms: 20 }));
    const read = await vi.waitFor(() => backend.expectOne(`/api/v1/ai/jobs/${job().id}`));
    fixture.destroy();
    expect(read.cancelled).toBe(true);
    expect(texts).toEqual([]);
    expect(areas).toEqual([]);
  });
});
