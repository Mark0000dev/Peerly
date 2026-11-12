import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, input, output } from '@angular/core';
import { TuiRoot } from '@taiga-ui/core';
import type { Api } from '../../../api.generated';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import type { Mutation } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../app.config';
import { host, shown, control, submit, click } from '../testing-host';
import { verifiedActor } from '../onboarding.fixtures';
import { StudyGoal } from './goal';
import { catalogue, goal, ownGoal } from './goal.fixtures';

@Component({
  selector: 'peerly-goal-test-host',
  imports: [TuiRoot, StudyGoal],
  template:
    '<tui-root><peerly-study-goal [actor]="actor()" [checking]="checking()" (expired)="expired.emit()" /></tui-root>',
})
class GoalTestHost {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
  public readonly checking = input(false);
  public readonly expired = output();
}

const catalogueUrl = '/api/v1/subjects?query=&limit=20';

describe('actual study goal editor and catalogue selection', () => {
  let fixture: ComponentFixture<GoalTestHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(async () => {
    client = new QueryClient({
      defaultOptions: {
        queries: { retry: false, refetchOnWindowFocus: false },
        mutations: { retry: false },
      },
    });
    client.setQueryData(['session'], verifiedActor);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(GoalTestHost);
    fixture.componentRef.setInput('actor', verifiedActor);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    const request = await vi.waitFor(() => backend.expectOne(catalogueUrl));
    request.flush(catalogue);
  });
  afterEach(() => {
    try {
      fixture.destroy();
      client.clear();
      backend.verify();
    } finally {
      TestBed.resetTestingModule();
    }
  });
  async function load(
    value: Readonly<Record<string, unknown>> = ownGoal,
    status = 200,
  ): Promise<void> {
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'GET' }),
    );
    request.flush(value, { status, statusText: status === 200 ? 'OK' : 'Failure' });
    await shown(fixture, status === 200 ? 'Save goal' : 'We couldn’t load your goal');
  }
  async function formReady(): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      const region = host(fixture).querySelector('section[aria-label="Your study goal"]');
      expect(region?.querySelector('form #goal-subject')).toBeInstanceOf(HTMLInputElement);
      expect(region?.querySelector('form #goal-topic')).toBeInstanceOf(HTMLInputElement);
      expect(region?.querySelector('form #goal-context')).toBeInstanceOf(HTMLTextAreaElement);
    });
  }
  function edit(name: string, value: unknown): void {
    control(fixture, `#goal-${name}`).setValue(value);
    control(fixture, `#goal-${name}`).markAsDirty();
  }
  function choose(): void {
    edit('subject', {
      kind: 'canonical',
      id: catalogue.items[1].id,
      label: catalogue.items[1].name,
      aliases: catalogue.items[1].aliases,
    });
  }
  function search(text: string): void {
    edit('subject', text);
    fixture.detectChanges();
    const input = host(fixture).querySelector('#goal-subject');
    if (!(input instanceof HTMLInputElement)) throw new Error('Missing subject input');
    input.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
  }
  async function searched(
    query: string,
    value: Readonly<Record<string, unknown>> = catalogue,
    status = 200,
  ): Promise<void> {
    const request = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/subjects?query=${encodeURIComponent(query)}&limit=20`),
    );
    request.flush(value, { status, statusText: status === 200 ? 'OK' : 'Failure' });
    await formReady();
  }
  it('loads server goal and defaulted optional subject tags into an editable form', async () => {
    await shown(fixture, 'Loading your goal');
    await load();
    expect(control(fixture, '#goal-topic').value).toBe(goal.topic);
    expect(control(fixture, '#goal-context').value).toBe(goal.context);
    expect(control(fixture, '#goal-subject').value).toMatchObject({
      kind: 'canonical',
      id: goal.subject.id,
      label: 'Calculus',
    });
    expect(host(fixture).textContent).not.toContain('Make it clearer');
  });
  it('highlights a saved canonical id and selects another real Taiga option', async () => {
    await load();
    const input = host(fixture).querySelector('#goal-subject');
    if (!(input instanceof HTMLElement)) throw new Error('Missing subject input');
    input.click();
    await shown(fixture, 'Databases');
    expect(host(fixture).querySelectorAll('[aria-selected="true"]')).toHaveLength(1);
    const option = Array.from(
      host(fixture).querySelectorAll<HTMLButtonElement>('button[tuiOption]'),
    ).find((item: Readonly<HTMLButtonElement>) => item.textContent.includes('SQL'));
    if (option === undefined) throw new Error('Missing catalogue option');
    option.click();
    await searched('SQL');
    await formReady();
    expect(control(fixture, '#goal-subject').value).toMatchObject({
      kind: 'canonical',
      id: catalogue.items[1].id,
      label: 'SQL',
    });
  });
  it('keeps a failed catalogue search explicit and retries through the actual dropdown', async () => {
    await load();
    search('calc');
    await searched('calc', { code: 'unavailable' }, 503);
    await shown(fixture, 'We couldn’t load areas.');
    click(fixture, 'Retry areas');
    await searched('calc');
    await shown(fixture, 'Differential calculus');
  });
  it('saves only exact canonical request fields with the current goal identity/version', async () => {
    await load();
    choose();
    edit('topic', ' JOINs ');
    edit('context', ' Examples ');
    edit('shared', true);
    submit(fixture);
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
    );
    expect(save.request.body).toEqual({
      subject: { kind: 'canonical', id: catalogue.items[1].id },
      topic: 'JOINs',
      context: 'Examples',
      shared_learning: true,
      expected_goal_id: goal.id,
      expected_version: 2,
    });
    expect(save.request.headers.get('x-csrf-token')).toBe(verifiedActor.csrf_token);
    expect(save.request.headers.get('idempotency-key')).toMatch(/^[a-f0-9-]{36}$/);
    await shown(fixture, 'Saving…');
    save.flush({ ...goal, version: 3 });
    await load({ goal: { ...goal, version: 3 } });
    await shown(fixture, 'Goal saved.');
  });
  it('does not treat typed search text as a selected subject', async () => {
    await load();
    search('New course');
    await searched('New course', { items: [], next_cursor: null });
    submit(fixture);
    await shown(fixture, 'Choose an area from the list');
    backend.expectNone({ url: '/api/v1/me/goal', method: 'PUT' });
  });
  it('creates a custom subject only after explicit choice and sends a new-goal zero revision', async () => {
    await load({ goal: null });
    search('Distributed systems');
    await searched('Distributed systems', { items: [], next_cursor: null });
    click(fixture, 'Use this as another area');
    await shown(fixture, 'Another area isn’t linked');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
    );
    expect(save.request.body).toEqual({
      subject: { kind: 'custom', label: 'Distributed systems' },
      topic: null,
      context: null,
      shared_learning: false,
      expected_goal_id: null,
      expected_version: 0,
    });
    save.flush({ ...goal, subject: { kind: 'custom', label: 'Distributed systems' }, version: 1 });
    await load({
      goal: { ...goal, subject: { kind: 'custom', label: 'Distributed systems' }, version: 1 },
    });
    await shown(fixture, 'Goal saved.');
  });
  it('hydrates an existing custom goal with absent optional tags without inventing a canonical id', async () => {
    await load({
      goal: {
        ...goal,
        subject: { label: 'Other subject' },
        topic: null,
        context: null,
        shared_learning: true,
      },
    });
    expect(control(fixture, '#goal-subject').value).toEqual({
      kind: 'custom',
      label: 'Other subject',
    });
    expect(control(fixture, '#goal-shared').value).toBe(true);
  });
  it('rejects missing subject and oversized optional drafts before a command', async () => {
    await load({ goal: null });
    submit(fixture);
    await shown(fixture, 'Choose an area from the list');
    choose();
    edit('topic', 'a'.repeat(81));
    edit('context', 'a'.repeat(241));
    submit(fixture);
    await shown(fixture, 'Keep the topic within 80');
    await shown(fixture, 'Keep the context within 240');
    backend.expectNone({ url: '/api/v1/me/goal', method: 'PUT' });
  });
  it('does not offer overlong custom subject text as an enabled action', async () => {
    await load();
    search('x'.repeat(81));
    await searched('x'.repeat(81), { items: [], next_cursor: null });
    expect(
      Array.from(host(fixture).querySelectorAll<HTMLButtonElement>('button[tuiOption]')).find(
        (item: Readonly<HTMLButtonElement>) =>
          item.textContent.includes('Use this as another area'),
      )?.disabled,
    ).toBe(true);
  });
  it('includes the opaque server cursor in subsequent subject queries', async () => {
    await load();
    search('calc');
    await searched('calc', { ...catalogue, next_cursor: 'opaque cursor' });
    const input = host(fixture).querySelector('#goal-subject');
    if (!(input instanceof HTMLElement)) throw new Error('Missing subject');
    input.focus();
    fixture.detectChanges();
    await shown(fixture, 'Next areas');
    click(fixture, 'Next areas');
    const next = await vi.waitFor(() =>
      backend.expectOne('/api/v1/subjects?query=calc&limit=20&cursor=opaque%20cursor'),
    );
    next.flush({ items: [], next_cursor: null });
    await shown(fixture, 'No areas found.');
  });
  it('cancels the previous search when the actual input changes', async () => {
    await load();
    search('calc');
    const previous = await vi.waitFor(() =>
      backend.expectOne('/api/v1/subjects?query=calc&limit=20'),
    );
    search('sql');
    expect(previous.cancelled).toBe(true);
    await searched('sql');
  });
  for (const outcome of [0, 408, 503])
    it(`preserves the exact uncertain goal intent for explicit retry ${String(outcome)}`, async () => {
      await load();
      choose();
      submit(fixture);
      const save = await vi.waitFor(() =>
        backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
      );
      const body: unknown = save.request.body;
      const key = save.request.headers.get('idempotency-key');
      if (outcome === 0) save.error(new ProgressEvent('error'));
      else save.flush({ code: 'unavailable' }, { status: outcome, statusText: 'Unknown' });
      await shown(fixture, 'We couldn’t confirm your save');
      submit(fixture);
      const retry = await vi.waitFor(() =>
        backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
      );
      expect(retry.request.body).toEqual(body);
      expect(retry.request.headers.get('idempotency-key')).toBe(key);
      const saved = {
        ...goal,
        version: 3,
        subject: { kind: 'canonical', id: catalogue.items[1].id, label: catalogue.items[1].name },
      } as const;
      retry.flush(saved);
      await load({ goal: saved });
      await shown(fixture, 'Goal saved.');
    });
  it('preserves a conflicting draft and requires explicit saved-goal reload', async () => {
    await load();
    edit('topic', 'My draft');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
    );
    save.flush({ code: 'goal_version_conflict' }, { status: 409, statusText: 'Conflict' });
    await shown(fixture, 'Your goal changed elsewhere');
    expect(control(fixture, '#goal-topic').value).toBe('My draft');
    submit(fixture);
    backend.expectNone({ url: '/api/v1/me/goal', method: 'PUT' });
    click(fixture, 'Reload saved goal');
    await load({ goal: { ...goal, version: 4, topic: 'Other device' } });
    expect(control(fixture, '#goal-topic').value).toBe('Other device');
  });
  it('shows safe validation errors without private server text', async () => {
    await load();
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
    );
    save.flush(
      { code: 'unsupported_validation_code', title: 'PRIVATE' },
      { status: 422, statusText: 'Invalid' },
    );
    await shown(fixture, 'We couldn’t save your goal');
    expect(host(fixture).textContent).not.toContain('PRIVATE');
  });
  for (const [code, copy] of [
    ['subject_unavailable', 'This area is no longer available.'],
    ['idempotency_conflict', 'We couldn’t resolve this save.'],
  ] as const) {
    it(`preserves typed recovery for actual409 ${code}`, async () => {
      await load();
      submit(fixture);
      const save = await vi.waitFor(() =>
        backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
      );
      save.flush({ code }, { status: 409, statusText: 'Conflict' });
      await shown(fixture, copy);
      expect(host(fixture).textContent).not.toContain('Your goal changed elsewhere');
    });
  }
  it('retries a failed goal read only after explicit action', async () => {
    await load({ code: 'unavailable' }, 503);
    click(fixture, 'Try again');
    await load();
  });
  for (const status of [401, 403])
    it(`revalidates identity when saving is denied ${String(status)}`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      await load();
      submit(fixture);
      const save = await vi.waitFor(() =>
        backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
      );
      save.flush({ code: 'denied' }, { status, statusText: 'Denied' });
      await vi.waitFor(() => {
        expect(expired).toHaveBeenCalledOnce();
      });
      expect(control(fixture, '#goal-subject').value).toBeNull();
      expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
    });
  for (const status of [401, 403])
    it(`revalidates identity when catalogue read is denied ${String(status)}`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      await load();
      search('calc');
      await searched('calc', { code: 'denied' }, status);
      await vi.waitFor(() => {
        expect(expired).toHaveBeenCalledOnce();
      });
    });
  it('ignores old actor save completion after actor replacement', async () => {
    await load();
    edit('topic', 'Old draft');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
    );
    client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement' });
    fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'replacement' });
    fixture.detectChanges();
    const cat = await vi.waitFor(() => backend.expectOne(catalogueUrl));
    cat.flush(catalogue);
    await load({ goal: { ...goal, topic: 'Replacement' } });
    edit('topic', 'New draft');
    save.flush({ ...goal, topic: 'Old draft' });
    await formReady();
    expect(control(fixture, '#goal-topic').value).toBe('New draft');
    backend.expectNone({ url: '/api/v1/me/goal', method: 'GET' });
  });
  it('does not expire a replacement actor or erase its draft when an old save is denied', async () => {
    const expired = vi.fn();
    fixture.componentInstance.expired.subscribe(expired);
    await load();
    edit('topic', 'Old draft');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
    );
    client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement' });
    fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'replacement' });
    fixture.detectChanges();
    (await vi.waitFor(() => backend.expectOne(catalogueUrl))).flush(catalogue);
    await load({ goal: { ...goal, topic: 'Replacement' } });
    edit('topic', 'New private draft');
    client.setQueryData(['account', 'replacement', 'private'], { retained: true });
    save.flush({ code: 'denied' }, { status: 403, statusText: 'Denied' });
    await vi.waitFor(() => {
      expect(
        client
          .getMutationCache()
          .getAll()
          .some((entry: Readonly<Mutation>) => entry.state.status === 'error'),
      ).toBe(true);
    });
    fixture.detectChanges();
    expect(control(fixture, '#goal-topic').value).toBe('New private draft');
    expect(client.getQueryData(['account', 'replacement', 'private'])).toEqual({ retained: true });
    expect(expired).not.toHaveBeenCalled();
    backend.expectNone({ url: '/api/v1/me/goal', method: 'GET' });
  });
  it('pauses a queued goal write before dispatch and replays only its original intent after fresh authority', async () => {
    await load();
    edit('topic', 'Queued draft');
    submit(fixture);
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    await shown(fixture, 'We couldn’t confirm your save.');
    backend.expectNone({ url: '/api/v1/me/goal', method: 'PUT' });
    expect(control(fixture, '#goal-topic').value).toBe('Queued draft');
    const original = client
      .getMutationCache()
      .getAll()
      .find((entry: Readonly<Mutation>) => entry.state.status === 'error')?.state.variables;
    const rotated = { ...verifiedActor, csrf_token: 'fresh-after-goal-check' };
    client.setQueryData(['session'], rotated);
    fixture.componentRef.setInput('actor', rotated);
    fixture.componentRef.setInput('checking', false);
    fixture.detectChanges();
    // Re-enabling the same owner preserves fresh catalogue and canonical caches.
    await formReady();
    expect(control(fixture, '#goal-topic').value).toBe('Queued draft');
    backend.expectNone(catalogueUrl);
    backend.expectNone({ url: '/api/v1/me/goal', method: 'GET' });
    await shown(fixture, 'Retry same save');
    click(fixture, 'Retry same save');
    const retry = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
    );
    expect(retry.request.body).toMatchObject({
      topic: 'Queued draft',
      expected_goal_id: goal.id,
      expected_version: goal.version,
    });
    expect(original).toMatchObject({ key: retry.request.headers.get('idempotency-key') });
    expect(retry.request.headers.get('x-csrf-token')).toBe(rotated.csrf_token);
    const saved = { ...goal, version: 3, topic: 'Queued draft' };
    retry.flush(saved);
    await load({ goal: saved });
  });
  it('accepts its owned goal receipt during a sign-in check without issuing a new private read', async () => {
    await load();
    edit('topic', 'Committed draft');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
    );
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    save.flush({ ...goal, version: 3, topic: 'Committed draft' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(
        client
          .getMutationCache()
          .getAll()
          .some((entry: Readonly<Mutation>) => entry.state.status === 'success'),
      ).toBe(true);
    });
    expect(control(fixture, '#goal-topic').value).toBe('Committed draft');
    expect(client.getQueryState(['account', verifiedActor.account_id, 'goal'])?.isInvalidated).toBe(
      true,
    );
    backend.expectNone({ url: '/api/v1/me/goal', method: 'GET' });
  });
  it('never rolls a committed goal back to a lagging canonical revision', async () => {
    await load();
    edit('topic', 'Committed draft');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
    );
    save.flush({ ...goal, version: 3, topic: 'Committed draft' });
    await load({ goal: { ...goal, version: 1, topic: 'Lagging read' } });
    expect(control(fixture, '#goal-topic').value).toBe('Committed draft');
    submit(fixture);
    backend.expectNone({ url: '/api/v1/me/goal', method: 'PUT' });
  });
  it('resolves the original unknown goal intent even after a newer canonical goal is observed', async () => {
    await load();
    edit('topic', 'Original intent');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
    );
    const key = save.request.headers.get('idempotency-key');
    save.flush({ code: 'unavailable' }, { status: 503, statusText: 'Unavailable' });
    await shown(fixture, 'We couldn’t confirm your save.');
    const current = { ...goal, version: 4, topic: 'Newer canonical goal' };
    const refresh = client.refetchQueries({
      queryKey: ['account', verifiedActor.account_id, 'goal'],
    });
    (await vi.waitFor(() => backend.expectOne({ url: '/api/v1/me/goal', method: 'GET' }))).flush({
      goal: current,
    });
    await refresh;
    expect(control(fixture, '#goal-topic').value).toBe('Original intent');
    click(fixture, 'Retry same save');
    const retry = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
    );
    expect(retry.request.headers.get('idempotency-key')).toBe(key);
    expect(retry.request.body).toMatchObject({
      topic: 'Original intent',
      expected_version: goal.version,
    });
    retry.flush({ ...goal, version: 3, topic: 'Original intent' });
    await load({ goal: current });
    expect(control(fixture, '#goal-topic').value).toBe(current.topic);
  });
});
