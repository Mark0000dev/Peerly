import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { HttpClient } from '@angular/common/http';
import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TuiRoot, TuiDialogService } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../app.config';
import type { Api } from '../../../api.generated';
import type { ApiFailure } from '../../../api-http';
import { sessionOptions } from '../../session';
import { conversation, identity } from '../chats.fixtures';
import { studyKey } from './study-contract';
import { StudyProgress } from './study-progress';
import { offered, outcome, ownFeedback, receipt } from './study.fixtures';

@Component({
  selector: 'study-test-host',
  imports: [TuiRoot, StudyProgress],
  template:
    '<tui-root><app-study-progress [actor]="actor()" [conversationId]="conversation()" [peerLabel]="\'Maya Lim\'" [contextLabel]="\'Databases · SQL JOINs\'" [manualOpen]="manual()" [visit]="visit()" (closed)="closed.update(increment)" (sessionFailure)="failure($event)" /></tui-root>',
})
class StudyHost {
  public readonly actor = signal(identity);
  public readonly conversation = signal(conversation.conversation_id);
  public readonly manual = signal(0);
  public readonly visit = signal<Readonly<{ readonly id: string }> | null>(null);
  public readonly closed = signal(0);
  public readonly failures = signal<readonly ApiFailure[]>([]);
  public readonly increment = (value: number): number => value + 1;
  public failure(error: Readonly<ApiFailure>): void {
    this.failures.update((values) => [...values, error]);
  }
}

describe('F01/F02 explicit foreground study progress', () => {
  let fixture: ComponentFixture<StudyHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  const base = `/api/v1/conversations/${conversation.conversation_id}`;
  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: {
        queries: { retry: false, refetchOnWindowFocus: false },
        mutations: { retry: false },
      },
    });
    client.setQueryData(['session'], identity);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(StudyHost);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    vi.restoreAllMocks();
    TestBed.resetTestingModule();
  });
  function host(): HTMLElement {
    const value: unknown = fixture.nativeElement;
    if (!(value instanceof HTMLElement)) throw new Error('Missing host');
    return value;
  }
  function button(name: string): HTMLButtonElement {
    const value = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.trim() === name,
    );
    if (value === undefined) throw new Error(`Missing button ${name}`);
    return value;
  }
  function click(name: string): void {
    button(name).click();
    fixture.detectChanges();
  }
  async function shown(text: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain(text);
    });
  }
  async function request(method: string, suffix: string) {
    return vi.waitFor(() =>
      backend.expectOne((value) => value.method === method && value.url === `${base}/${suffix}`),
    );
  }
  async function open(
    value: Api['schemas']['StudyOutcomeResponse'] | null = outcome,
  ): Promise<void> {
    fixture.componentInstance.manual.update((value) => value + 1);
    fixture.detectChanges();
    (await request('GET', 'study-outcome')).flush({ outcome: value });
    await shown('Have you started working');
  }
  async function feedback(
    value: Api['schemas']['OwnFeedbackResponse'] = ownFeedback,
  ): Promise<void> {
    await open();
    click('Give feedback');
    (await request('GET', 'feedback')).flush(value);
    await shown(
      value.outcome?.answer !== 'yes'
        ? 'Have you worked on'
        : value.can_submit
          ? 'Would you study together again?'
          : 'Feedback is unavailable',
    );
  }
  async function refresh(
    value: Api['schemas']['OwnFeedbackResponse'] = ownFeedback,
  ): Promise<void> {
    (await request('GET', 'study-outcome')).flush({ outcome: value.outcome });
    (await request('GET', 'feedback')).flush(value);
  }
  function radio(value: string): HTMLInputElement {
    const element = host().querySelector(`input[type="radio"][value="${value}"]`);
    if (!(element instanceof HTMLInputElement)) throw new Error('Missing radio');
    return element;
  }
  function note(value: string): void {
    const element = host().querySelector('textarea');
    if (!(element instanceof HTMLTextAreaElement)) throw new Error('Missing note');
    Reflect.set(element, 'value', value);
    element.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
  }
  it('does nothing on render; manual reads/refetch never offer, dismiss or submit', async () => {
    backend.expectNone((value) => value.url.startsWith(base));
    await open(null);
    await client.invalidateQueries({ queryKey: ['not-this-query'] });
    click('Dismiss');
    expect(fixture.componentInstance.closed()).toBe(1);
    backend.expectNone((value) => value.method !== 'GET');
    fixture.componentInstance.manual.update((value) => value + 1);
    fixture.detectChanges();
    (await request('GET', 'study-outcome')).flush({ outcome });
    await shown('You said you’ve started');
    backend.expectNone((value) => value.method !== 'GET');
  });
  it('admits only the explicit visit, uses its exact key/empty body and ignores repeated token/refetch', async () => {
    fixture.componentInstance.visit.set({ id: 'explicit-visit-1' });
    fixture.detectChanges();
    const post = await request('POST', 'study-prompt-visits');
    expect(post.request.body).toEqual({});
    expect(post.request.headers.get('Idempotency-Key')).toBe('explicit-visit-1');
    expect(post.request.headers.get('X-CSRF-Token')).toBe(identity.csrf_token);
    post.flush(offered);
    (await request('GET', 'study-outcome')).flush({ outcome: null });
    await shown('Have you started working');
    fixture.componentInstance.visit.set({ id: 'explicit-visit-1' });
    fixture.detectChanges();
    click('Dismiss');
    backend.expectNone((value) => value.method === 'POST');
  });
  it('keeps no_offer invisible and retries an unknown admission with its original visit key', async () => {
    fixture.componentInstance.visit.set({ id: 'explicit-visit-2' });
    fixture.detectChanges();
    (await request('POST', 'study-prompt-visits')).error(new ProgressEvent('error'));
    fixture.componentInstance.manual.set(1);
    fixture.detectChanges();
    (await request('GET', 'study-outcome')).flush({ outcome: null });
    await shown('couldn’t confirm');
    click('Retry same action');
    const retry = await request('POST', 'study-prompt-visits');
    expect(retry.request.headers.get('Idempotency-Key')).toBe('explicit-visit-2');
    retry.flush({ outcome: 'no_offer' });
    await vi.waitFor(() => {
      expect(client.getMutationCache().getAll()).toHaveLength(0);
    });
    await shown('Have you started working');
  });
  it('keeps an ordinary no_offer completely hidden', async () => {
    fixture.componentInstance.visit.set({ id: 'explicit-visit-3' });
    fixture.detectChanges();
    (await request('POST', 'study-prompt-visits')).flush({ outcome: 'no_offer' });
    await vi.waitFor(() => {
      expect(client.getMutationCache().getAll()).toHaveLength(0);
    });
    fixture.detectChanges();
    expect(host().textContent).not.toContain('Study progress');
    backend.expectNone((value) => value.method === 'GET');
  });
  it.each(['yes', 'not_yet', 'did_not_work_out'] as const)(
    'records only the explicit %s answer with the own outcome version',
    async (answer) => {
      await open(null);
      click(answer === 'yes' ? 'Yes' : answer === 'not_yet' ? 'Not yet' : 'It didn’t work out');
      const put = await request('PUT', 'study-outcome');
      expect(put.request.body).toEqual({ answer, expected_version: 0 });
      put.flush({ ...outcome, answer, version: 1 });
      (await request('GET', 'study-outcome')).flush({
        outcome: { ...outcome, answer, version: 1 },
      });
      await shown(
        answer === 'yes'
          ? 'You said you’ve started'
          : answer === 'not_yet'
            ? 'Got it'
            : 'Thanks for letting us know',
      );
      backend.expectNone((value) => value.url.endsWith('/feedback'));
      expect(
        client.getQueryData([
          ...studyKey(identity.account_id, conversation.conversation_id),
          'outcome',
        ]),
      ).toEqual({ outcome: { ...outcome, answer, version: 1 } });
    },
  );
  it('keeps original outcome payload/key across an unknown write and prevents edited/new writes', async () => {
    await open();
    click('Not yet');
    const first = await request('PUT', 'study-outcome');
    const key = first.request.headers.get('Idempotency-Key');
    const body: unknown = first.request.body;
    first.error(new ProgressEvent('error'));
    await shown('couldn’t confirm');
    expect(button('Yes').matches(':disabled')).toBe(true);
    click('Yes');
    backend.expectNone((value) => value.method === 'PUT');
    click('Retry same action');
    const retry = await request('PUT', 'study-outcome');
    expect(retry.request.body).toEqual(body);
    expect(retry.request.headers.get('Idempotency-Key')).toBe(key);
    retry.flush({ ...outcome, answer: 'not_yet', version: 4 });
    (await request('GET', 'study-outcome')).flush({
      outcome: { ...outcome, answer: 'not_yet', version: 4 },
    });
    await shown('Got it');
  });
  it('hydrates current feedback and updates independent feedback CAS without multiplying records', async () => {
    await feedback();
    expect(radio('maybe').checked).toBe(true);
    expect(host().querySelector('textarea')?.value).toBe(receipt.team_note);
    radio('no').click();
    note('A team-only update.');
    click('Update feedback');
    const put = await request('PUT', 'feedback');
    expect(put.request.body).toEqual({
      again: 'no',
      descriptors: ['supportive'],
      team_note: 'A team-only update.',
      expected_version: 7,
    });
    put.flush({ ...receipt, version: 8, again: 'no', team_note: 'A team-only update.' });
    await refresh({ ...ownFeedback, current: { ...receipt, version: 8, again: 'no' } });
    await shown('It counts once');
    expect(client.getMutationCache().getAll()).toHaveLength(0);
    click('Back to chat');
    expect(fixture.componentInstance.closed()).toBe(1);
  });
  it('saves a private-only new record and keeps optional fields optional', async () => {
    await feedback({
      ...ownFeedback,
      current: null,
      current_publication: null,
      submission_publication: 'private_only',
    });
    await shown('This goes to the team only');
    click('Send to the team');
    await shown('Choose Yes, Maybe or No.');
    backend.expectNone((value) => value.method === 'PUT');
    radio('yes').click();
    click('Send to the team');
    const put = await request('PUT', 'feedback');
    expect(put.request.body).toEqual({
      again: 'yes',
      descriptors: [],
      team_note: null,
      expected_version: 0,
    });
    put.flush({
      ...receipt,
      again: 'yes',
      version: 1,
      descriptors: [],
      team_note: null,
      captured_public_eligibility: false,
    });
    await refresh({ ...ownFeedback, current_publication: 'private_only' });
    await shown('It goes to the team only');
  });
  it('validates Unicode note length and all three optional descriptors', async () => {
    await feedback();
    note('🙂'.repeat(1001));
    click('Update feedback');
    await shown('Keep your note within');
    backend.expectNone((value) => value.method === 'PUT');
    note('🙂'.repeat(1000));
    for (const value of Array.from(host().querySelectorAll('input[type="checkbox"]')))
      if (value instanceof HTMLInputElement && !value.checked) value.click();
    click('Update feedback');
    const put = await request('PUT', 'feedback');
    expect(put.request.body).toEqual(
      expect.objectContaining({ descriptors: ['easy_to_communicate', 'prepared', 'supportive'] }),
    );
    put.flush({
      ...receipt,
      descriptors: ['easy_to_communicate', 'prepared', 'supportive'],
      team_note: '🙂'.repeat(1000),
    });
    await refresh();
    await shown('Thanks, your feedback is saved');
  });
  it('performs a separate actual worked confirmation before feedback and never automatically submits feedback', async () => {
    await feedback({ ...ownFeedback, outcome: null, current: null });
    click('Yes, we worked together');
    const put = await request('PUT', 'study-outcome');
    expect(put.request.body).toEqual({ answer: 'yes', expected_version: 3 });
    put.flush({ ...outcome, version: 4 });
    (await request('GET', 'study-outcome')).flush({ outcome: { ...outcome, version: 4 } });
    (await request('GET', 'feedback')).flush({
      ...ownFeedback,
      outcome: { ...outcome, version: 4 },
      current: null,
    });
    await shown('Would you study together again?');
    backend.expectNone((value) => value.method === 'PUT');
  });
  it('Not yet in feedback confirms no rating and returns to check-in', async () => {
    await feedback({ ...ownFeedback, outcome: null });
    click('Not yet');
    (await request('PUT', 'study-outcome')).flush({ ...outcome, answer: 'not_yet', version: 4 });
    (await request('GET', 'study-outcome')).flush({
      outcome: { ...outcome, answer: 'not_yet', version: 4 },
    });
    await shown('Got it');
    backend.expectNone((value) => value.url.endsWith('/feedback') && value.method === 'PUT');
  });
  it.each(['feedback_version_conflict', 'worked_confirmation_required'])(
    'preserves the draft on %s and requires explicit refresh before a new intent',
    async (code) => {
      await feedback();
      note('Keep this draft');
      click('Update feedback');
      const first = await request('PUT', 'feedback');
      const key = first.request.headers.get('Idempotency-Key');
      first.flush({ code }, { status: 409, statusText: 'Conflict' });
      await shown('Your draft is kept');
      expect(button('Update feedback').disabled).toBe(true);
      click('Reload current record');
      await refresh({ ...ownFeedback, current: { ...receipt, version: 9 } });
      await shown('Would you study together again?');
      expect(host().querySelector('textarea')?.value).toBe('Keep this draft');
      await shown('Saved answers changed');
      click('Keep my answers');
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(button('Update feedback').disabled).toBe(false);
      });
      click('Update feedback');
      const next = await request('PUT', 'feedback');
      expect(next.request.body).toEqual(expect.objectContaining({ expected_version: 9 }));
      expect(next.request.headers.get('Idempotency-Key')).not.toBe(key);
      next.flush({ ...receipt, version: 10 });
      await refresh();
      await shown('Thanks, your feedback is saved');
    },
  );
  it('keeps feedback exact on unknown write and retry, including original note and feedback CAS', async () => {
    await feedback();
    note('Uncertain note');
    click('Update feedback');
    const first = await request('PUT', 'feedback');
    const body: unknown = first.request.body;
    const key = first.request.headers.get('Idempotency-Key');
    first.error(new ProgressEvent('error'));
    await shown('couldn’t confirm');
    expect(host().querySelector('textarea')?.readOnly).toBe(true);
    click('Retry same action');
    const next = await request('PUT', 'feedback');
    expect(next.request.body).toEqual(body);
    expect(next.request.headers.get('Idempotency-Key')).toBe(key);
    next.flush({ ...receipt, version: 8, team_note: 'Uncertain note' });
    await refresh();
    await shown('Thanks, your feedback is saved');
  });
  it.each([401, 403, 404, 422, 503])(
    'handles actual read failure %i without a write and supports explicit recovery',
    async (status) => {
      fixture.componentInstance.manual.set(1);
      fixture.detectChanges();
      (await request('GET', 'study-outcome')).flush(
        { code: 'unavailable' },
        { status, statusText: 'Unavailable' },
      );
      await shown(
        status === 401
          ? 'session needs'
          : status === 403 || status === 404
            ? 'unavailable for this conversation'
            : status === 422
              ? 'could not be accepted'
              : 'couldn’t load or save',
      );
      expect(fixture.componentInstance.failures().length).toBe(
        status === 401 || status === 403 ? 1 : 0,
      );
      click('Reload current record');
      (await request('GET', 'study-outcome')).flush({ outcome });
      await shown('You said you’ve started');
      backend.expectNone((value) => value.method !== 'GET');
    },
  );
  it('respects can_submit and server removed publication without inferring from peer/messages', async () => {
    await feedback({ ...ownFeedback, can_submit: false });
    await shown('Feedback is unavailable');
    expect(host().querySelector('form')).toBeNull();
    const refreshed = client.invalidateQueries({
      queryKey: studyKey(identity.account_id, conversation.conversation_id),
    });
    await refresh({
      ...ownFeedback,
      current_publication: 'removed',
      submission_publication: 'private_only',
    });
    await refreshed;
    await shown('removed from the public summary');
  });
  it('retires draft, pending reads and mutations on conversation/actor replacement and logout', async () => {
    await feedback();
    note('Must not leak');
    click('Update feedback');
    const pending = await request('PUT', 'feedback');
    fixture.componentInstance.conversation.set('00000000-0000-4000-8000-000000000099');
    fixture.detectChanges();
    pending.flush(receipt);
    await vi.waitFor(() => {
      expect(client.getMutationCache().getAll()).toHaveLength(0);
    });
    fixture.detectChanges();
    expect(host().textContent).not.toContain('Must not leak');
    expect(host().querySelector('textarea')).toBeNull();
    const replacement = { ...identity, account_id: '00000000-0000-4000-8000-000000000098' };
    client.setQueryData(['session'], replacement);
    fixture.componentInstance.actor.set(replacement);
    fixture.detectChanges();
    await vi.waitFor(() => {
      expect(host().querySelector('section')).toBeNull();
    });
    client.setQueryData(['session'], null);
    fixture.detectChanges();
    await vi.waitFor(() => {
      expect(host().querySelector('section')).toBeNull();
    });
  });
  it('cancels active GET on destroy instead of allowing late private data to reappear', async () => {
    fixture.componentInstance.manual.set(1);
    fixture.detectChanges();
    const pending = await request('GET', 'study-outcome');
    fixture.destroy();
    expect(pending.cancelled).toBe(true);
  });
  it('ignores duplicate visit tokens while admission is pending and preserves composer focus', async () => {
    const composer = document.createElement('textarea');
    document.body.append(composer);
    composer.focus();
    fixture.componentInstance.visit.set({ id: 'visit-focus' });
    fixture.detectChanges();
    const pending = await request('POST', 'study-prompt-visits');
    fixture.componentInstance.visit.set({ id: 'visit-focus' });
    fixture.detectChanges();
    backend.expectNone((value) => value.method === 'POST');
    pending.flush(offered);
    (await request('GET', 'study-outcome')).flush({ outcome: null });
    await shown('Have you started working');
    expect(document.activeElement).toBe(composer);
    composer.remove();
  });
  it.each([401, 403, 404, 422])(
    'preserves feedback draft on rejected write %i and reauthorizes only actual authority failures',
    async (status) => {
      await feedback();
      note('Rejected draft');
      click('Update feedback');
      (await request('PUT', 'feedback')).flush(
        { code: 'write_unavailable' },
        { status, statusText: 'Unavailable' },
      );
      await shown(
        status === 401
          ? 'session needs'
          : status === 403 || status === 404
            ? 'unavailable for this conversation'
            : 'could not be accepted',
      );
      expect(host().querySelector('textarea')?.value).toBe('Rejected draft');
      expect(fixture.componentInstance.failures()).toHaveLength(
        status === 401 || status === 403 ? 1 : 0,
      );
      backend.expectNone((value) => value.method === 'PUT');
    },
  );
  it('treats a malformed committed response as unknown and retains the original write intent', async () => {
    await feedback();
    click('Update feedback');
    const first = await request('PUT', 'feedback');
    const key = first.request.headers.get('Idempotency-Key');
    first.flush({ ...receipt, conversation_id: 'wrong-conversation' });
    await shown('couldn’t confirm');
    click('Retry same action');
    const retry = await request('PUT', 'feedback');
    expect(retry.request.headers.get('Idempotency-Key')).toBe(key);
    retry.flush(receipt);
    await refresh({ ...ownFeedback, current_publication: 'removed' });
    await shown('Your current feedback is removed');
  });
  it('renders feedback read failure locally, recovers explicitly and keeps form draft on later refresh', async () => {
    await open();
    click('Give feedback');
    (await request('GET', 'feedback')).flush(
      { code: 'unavailable' },
      { status: 503, statusText: 'Unavailable' },
    );
    await shown('couldn’t load or save');
    click('Reload current record');
    await refresh();
    await shown('Would you study together again?');
    note('Keep local draft');
    const editing = host().querySelector('textarea');
    editing?.focus();
    const refreshed = client.invalidateQueries({
      queryKey: studyKey(identity.account_id, conversation.conversation_id),
    });
    await refresh({ ...ownFeedback, current: { ...receipt, team_note: 'Server changed' } });
    await refreshed;
    await shown('Would you study together again?');
    expect(host().querySelector('textarea')?.value).toBe('Keep local draft');
    expect(document.activeElement).toBe(editing);
  });
  it('does not write when cached identity lacks current student authority', async () => {
    await open();
    client.setQueryData(['session'], {
      ...identity,
      capabilities: { ...identity.capabilities, can_use_student_features: false },
    });
    fixture.detectChanges();
    expect(button('Give feedback').disabled).toBe(true);
    click('Give feedback');
    backend.expectNone((value) => value.method !== 'GET');
  });
  it('never replays the previous actor’s visit token on actor replacement', async () => {
    fixture.componentInstance.visit.set({ id: 'old-actor-visit' });
    fixture.detectChanges();
    (await request('POST', 'study-prompt-visits')).flush({ outcome: 'no_offer' });
    await vi.waitFor(() => {
      expect(client.getMutationCache().getAll()).toHaveLength(0);
    });
    const next = { ...identity, account_id: '00000000-0000-4000-8000-000000000096' };
    client.setQueryData(['session'], next);
    fixture.componentInstance.actor.set(next);
    fixture.detectChanges();
    backend.expectNone((value) => value.method === 'POST');
    await vi.waitFor(() => {
      expect(host().querySelector('section')).toBeNull();
    });
  });
  it('checks current authority at action time even before a stale DOM control rerenders', async () => {
    await feedback();
    const save = button('Update feedback');
    client.setQueryData(['session'], {
      ...identity,
      capabilities: { ...identity.capabilities, can_use_student_features: false },
    });
    save.click();
    fixture.detectChanges();
    backend.expectNone((value) => value.method === 'PUT');
    expect(save.disabled).toBe(true);
  });
  it('does not let a queued save race a background projection refresh', async () => {
    await feedback();
    note('Draft while refreshing');
    const save = button('Update feedback');
    const refreshed = client.invalidateQueries({
      queryKey: studyKey(identity.account_id, conversation.conversation_id),
    });
    save.click();
    backend.expectNone((value) => value.method === 'PUT');
    await refresh();
    await refreshed;
    fixture.detectChanges();
    expect(host().querySelector('textarea')?.value).toBe('Draft while refreshing');
  });
  it('rechecks authority inside a queued mutation and never sends after capability revocation', async () => {
    await open();
    click('Not yet');
    client.setQueryData(['session'], {
      ...identity,
      capabilities: { ...identity.capabilities, can_use_student_features: false },
    });
    await shown('couldn’t load or save');
    backend.expectNone((value) => value.method === 'PUT');
  });
  it.each(['outcome', 'feedback'] as const)(
    'does not reopen a closed view when the pending %s write settles',
    async (kind) => {
      if (kind === 'outcome') {
        await open();
        click('Not yet');
      } else {
        await feedback();
        click('Update feedback');
      }
      const pending = await request('PUT', kind === 'outcome' ? 'study-outcome' : 'feedback');
      click('Close');
      pending.flush(
        kind === 'outcome'
          ? { ...outcome, answer: 'not_yet', version: 4 }
          : { ...receipt, version: 8 },
      );
      await vi.waitFor(() => {
        expect(client.getMutationCache().getAll()).toHaveLength(0);
      });
      fixture.detectChanges();
      await vi.waitFor(() => {
        expect(host().querySelector('section')).toBeNull();
      });
      backend.expectNone((value) => value.method === 'GET');
    },
  );
  it('never resurrects a dismissed manual view when the earlier automatic offer finally arrives', async () => {
    fixture.componentInstance.visit.set({ id: 'delayed-offer' });
    fixture.detectChanges();
    const pending = await request('POST', 'study-prompt-visits');
    await open(null);
    click('Dismiss');
    pending.flush(offered);
    await vi.waitFor(() => {
      expect(client.getMutationCache().getAll()).toHaveLength(0);
    });
    fixture.detectChanges();
    await vi.waitFor(() => {
      expect(host().querySelector('section')).toBeNull();
    });
    backend.expectNone((value) => value.method === 'GET');
  });
  it('pins a draft to its hydrated version until the student explicitly keeps their answers against the reviewed record', async () => {
    await feedback();
    note('My unsaved answers');
    const refreshed = client.invalidateQueries({
      queryKey: studyKey(identity.account_id, conversation.conversation_id),
    });
    await refresh({
      ...ownFeedback,
      current: { ...receipt, version: 8, again: 'no', team_note: 'A newer saved answer' },
    });
    await refreshed;
    await shown('Saved answers changed');
    expect(button('Update feedback').disabled).toBe(true);
    expect(host().querySelector('textarea')?.value).toBe('My unsaved answers');
    expect(host().querySelector('[aria-label="Latest saved feedback"]')?.textContent).toContain(
      'A newer saved answer',
    );
    click('Keep my answers');
    backend.expectNone((value) => value.method === 'PUT');
    expect(host().querySelector('textarea')?.value).toBe('My unsaved answers');
    click('Update feedback');
    const put = await request('PUT', 'feedback');
    expect(put.request.body).toEqual(
      expect.objectContaining({
        expected_version: 8,
        again: 'maybe',
        team_note: 'My unsaved answers',
      }),
    );
    put.flush({ ...receipt, version: 9, team_note: 'My unsaved answers' });
    await refresh();
    await shown('Thanks, your feedback is saved');
  });
  it('loads saved answers only by an explicit choice and rejects a queued review decision during another refresh', async () => {
    await feedback();
    note('Keep my draft until I choose');
    const first = client.invalidateQueries({
      queryKey: studyKey(identity.account_id, conversation.conversation_id),
    });
    await refresh({
      ...ownFeedback,
      current: { ...receipt, version: 8, again: 'no', team_note: 'Saved version eight' },
    });
    await first;
    await shown('Saved answers changed');
    const keep = button('Keep my answers');
    const next = client.invalidateQueries({
      queryKey: studyKey(identity.account_id, conversation.conversation_id),
    });
    keep.click();
    await refresh({
      ...ownFeedback,
      current: {
        ...receipt,
        version: 9,
        again: 'yes',
        descriptors: ['prepared'],
        team_note: 'Saved version nine',
      },
    });
    await next;
    await shown('Saved version nine');
    expect(button('Update feedback').disabled).toBe(true);
    expect(host().querySelector('textarea')?.value).toBe('Keep my draft until I choose');
    click('Load saved answers');
    expect(host().querySelector('textarea')?.value).toBe('Saved version nine');
    expect(radio('yes').checked).toBe(true);
    backend.expectNone((value) => value.method === 'PUT');
    expect(button('Update feedback').disabled).toBe(false);
  });
  it('requires another review when a background update arrives after Keep my answers', async () => {
    await feedback();
    note('My version stays mine');
    const first = client.invalidateQueries({
      queryKey: studyKey(identity.account_id, conversation.conversation_id),
    });
    await refresh({ ...ownFeedback, current: { ...receipt, version: 8 } });
    await first;
    await shown('Saved answers changed');
    click('Keep my answers');
    const next = client.invalidateQueries({
      queryKey: studyKey(identity.account_id, conversation.conversation_id),
    });
    await refresh({
      ...ownFeedback,
      current: { ...receipt, version: 9, team_note: 'Another device saved again' },
    });
    await next;
    await shown('Saved answers changed');
    expect(button('Update feedback').disabled).toBe(true);
    expect(host().querySelector('textarea')?.value).toBe('My version stays mine');
    backend.expectNone((value) => value.method === 'PUT');
  });
  it('never treats an old idempotent outcome receipt as current after a newer canonical read', async () => {
    await open({ ...outcome, version: 1 });
    click('Not yet');
    const first = await request('PUT', 'study-outcome');
    const key = first.request.headers.get('Idempotency-Key');
    first.error(new ProgressEvent('error'));
    await shown('couldn’t confirm');
    const newer = { ...outcome, version: 3, answer: 'did_not_work_out' as const };
    const refreshed = client.invalidateQueries({
      queryKey: [...studyKey(identity.account_id, conversation.conversation_id), 'outcome'],
    });
    (await request('GET', 'study-outcome')).flush({ outcome: newer });
    await refreshed;
    await shown('Thanks for letting us know');
    click('Retry same action');
    const replay = await request('PUT', 'study-outcome');
    expect(replay.request.headers.get('Idempotency-Key')).toBe(key);
    replay.flush({ ...outcome, version: 2, answer: 'not_yet' });
    await vi.waitFor(() => {
      expect(client.getMutationCache().getAll()).toHaveLength(0);
    });
    expect(
      client.getQueryData([
        ...studyKey(identity.account_id, conversation.conversation_id),
        'outcome',
      ]),
    ).toEqual({ outcome: newer });
    (await request('GET', 'study-outcome')).flush({ outcome: newer });
    await shown('Thanks for letting us know');
  });
  it('retains a known successful feedback command while the same actor is being revalidated', async () => {
    await feedback();
    click('Update feedback');
    const pending = await request('PUT', 'feedback');
    const recheck = client.query({
      ...sessionOptions(TestBed.inject(HttpClient), client),
      staleTime: 0,
    });
    const me = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    pending.flush({ ...receipt, version: 8 });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).not.toContain('Saving study progress…');
    });
    me.flush(identity);
    await recheck;
    await refresh({ ...ownFeedback, current: { ...receipt, version: 8 } });
    await shown('Thanks, your feedback is saved');
    backend.expectNone((value) => value.method === 'PUT');
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });
  it('keeps automatic check-in inline and opens one native feedback dialog only after Give feedback', async () => {
    const dialogs = vi.spyOn(TestBed.inject(TuiDialogService), 'open');
    fixture.componentInstance.visit.set({ id: 'explicit-dialog-boundary' });
    fixture.detectChanges();
    (await request('POST', 'study-prompt-visits')).flush(offered);
    (await request('GET', 'study-outcome')).flush({ outcome });
    await shown('Give feedback');
    expect(dialogs).not.toHaveBeenCalled();
    click('Give feedback');
    (await request('GET', 'feedback')).flush(ownFeedback);
    await shown('Would you study together again?');
    await vi.waitFor(() => {
      expect(dialogs).toHaveBeenCalledTimes(1);
    });
    click('Update feedback');
    (await request('PUT', 'feedback')).flush({ ...receipt, version: 8 });
    await refresh({ ...ownFeedback, current: { ...receipt, version: 8 } });
    await shown('Thanks, your feedback is saved');
    expect(dialogs).toHaveBeenCalledTimes(1);
    backend.expectNone((request) => request.method === 'POST' && request.url.endsWith('/messages'));
    backend.expectNone((request) => request.url.endsWith('/read-position'));
  });
});
