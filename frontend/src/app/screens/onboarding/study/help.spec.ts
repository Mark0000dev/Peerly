import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, input, output } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TuiRoot } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import type { Mutation } from '@tanstack/angular-query-experimental';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../../../api.generated';
import { appConfig } from '../../../app.config';
import { host, shown, control, click, submit } from '../testing-host';
import { verifiedActor } from '../onboarding.fixtures';
import { HelpSubjects } from './help';
import { ownHelp, helpSelection } from './help.fixtures';
import { catalogue } from './goal.fixtures';

@Component({
  selector: 'peerly-help-test-host',
  imports: [TuiRoot, HelpSubjects],
  template:
    '<tui-root><peerly-help-subjects [actor]="actor()" [checking]="checking()" (expired)="expired.emit()" /></tui-root>',
})
class HelpTestHost {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
  public readonly checking = input(false);
  public readonly expired = output();
}

describe('real helper selection forms and query boundary', () => {
  let fixture: ComponentFixture<HelpTestHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
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
    fixture = TestBed.createComponent(HelpTestHost);
    fixture.componentRef.setInput('actor', verifiedActor);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
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
    value: Readonly<Record<string, unknown>> = ownHelp,
    status = 200,
  ): Promise<void> {
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/help-subjects', method: 'GET' }),
    );
    request.flush(value, { status, statusText: status === 200 ? 'OK' : 'Failure' });
    await shown(
      fixture,
      status === 200 ? 'Changes apply after you save.' : 'We couldn’t load your help areas',
    );
    if (status === 200)
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(host(fixture).textContent).not.toContain('Refreshing your saved areas.');
      });
  }
  async function saveRequest() {
    submit(fixture);
    return await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/help-subjects', method: 'PUT' }),
    );
  }
  async function open(
    value: Readonly<Record<string, unknown>> = catalogue,
    status = 200,
  ): Promise<void> {
    click(fixture, 'Add an area');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/subjects?query=&limit=20'));
    request.flush(value, { status, statusText: status === 200 ? 'OK' : 'Failure' });
    await shown(fixture, status === 200 ? 'Search areas' : 'We couldn’t load areas');
  }
  function edit(value: string): void {
    control(fixture, '#help-note-0').setValue(value);
    control(fixture, '#help-note-0').markAsDirty();
  }
  it('loads actual note and opens no catalogue before explicit Add', async () => {
    await shown(fixture, 'Loading your help areas');
    backend.expectNone('/api/v1/subjects?query=&limit=20');
    await load();
    expect(control(fixture, '#help-note-0').value).toBe('Limits');
  });
  it('saves closed current-revision fields and reloads after success', async () => {
    await load();
    edit('  Derivatives  ');
    const request = await saveRequest();
    submit(fixture);
    expect(request.request.body).toEqual({
      expected_version: 2,
      subjects: [{ subject_id: helpSelection.subjects[0].subject_id, topic_note: 'Derivatives' }],
    });
    expect(request.request.headers.get('x-csrf-token')).toBe(verifiedActor.csrf_token);
    expect(request.request.headers.get('idempotency-key')).toMatch(/^[a-f0-9-]{36}$/);
    request.flush({ ...helpSelection, version: 3 });
    await load({ selection: { ...helpSelection, version: 3 } });
    await shown(fixture, 'Help areas saved.');
  });
  it('allows an explicitly saved empty selection without inventing activation', async () => {
    await load({ selection: null });
    const request = await saveRequest();
    expect(request.request.body).toEqual({ expected_version: 0, subjects: [] });
    request.flush({ ...helpSelection, version: 1, subjects: [] });
    await load({ selection: { ...helpSelection, version: 1, subjects: [] } });
    await shown(fixture, 'Helping is always optional.');
  });
  it('removes an existing subject only in the local draft until Save', async () => {
    await load();
    click(fixture, 'Remove Calculus');
    await shown(fixture, '0 of 5');
    backend.expectNone({ url: '/api/v1/me/help-subjects', method: 'PUT' });
    const request = await saveRequest();
    expect(request.request.body).toEqual({ expected_version: 2, subjects: [] });
    request.flush({ ...helpSelection, subjects: [] });
    await load({ selection: { ...helpSelection, subjects: [] } });
  });
  it('rejects an overlong optional note before sending anything', async () => {
    await load();
    edit('x'.repeat(81));
    submit(fixture);
    await shown(fixture, 'Keep each topic note within 80 characters.');
    backend.expectNone({ url: '/api/v1/me/help-subjects', method: 'PUT' });
  });
  it('uses a real modal canonical choice and preserves ordered ids with null blank notes', async () => {
    await load();
    await open();
    await shown(fixture, 'SQL');
    const option = Array.from(host(fixture).querySelectorAll<HTMLButtonElement>('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.includes('SQL'),
    );
    if (option === undefined) throw new Error('Missing actual SQL option');
    option.click();
    await shown(fixture, '2 of 5');
    edit(' ');
    const request = await saveRequest();
    expect(request.request.body).toEqual({
      expected_version: 2,
      subjects: [
        { subject_id: helpSelection.subjects[0].subject_id, topic_note: null },
        { subject_id: catalogue.items[1].id, topic_note: null },
      ],
    });
    request.flush(helpSelection);
    await load();
  });
  it('marks the existing choice disabled rather than allowing a duplicate', async () => {
    await load();
    await open();
    await vi.waitFor(() => {
      fixture.detectChanges();
      const selected = Array.from(host(fixture).querySelectorAll<HTMLButtonElement>('button')).find(
        (item: Readonly<HTMLButtonElement>) =>
          item.getAttribute('aria-label')?.includes('Already added') === true,
      );
      expect(selected?.disabled).toBe(true);
    });
    click(fixture, 'Cancel');
  });
  it('does not offer a sixth subject and retains current order', async () => {
    await load({
      selection: {
        ...helpSelection,
        subjects: Array.from({ length: 5 }, (_, index) => ({
          subject_id: String(index),
          label: `Subject ${String(index)}`,
          topic_note: null,
        })),
      },
    });
    await shown(fixture, 'Remove one to add another.');
    expect(host(fixture).textContent).not.toContain('Add an area');
  });
  it('reads next catalogue cursor and cancels superseded search', async () => {
    await load();
    await open({ items: catalogue.items, next_cursor: 'opaque' });
    await shown(fixture, 'Next areas');
    click(fixture, 'Next areas');
    const next = await vi.waitFor(() =>
      backend.expectOne('/api/v1/subjects?query=&limit=20&cursor=opaque'),
    );
    next.flush({ items: [], next_cursor: null });
    await shown(fixture, 'No areas found.');
    const input = host(fixture).querySelector('#help-subject-search');
    if (!(input instanceof HTMLInputElement)) throw new Error('Missing search');
    control(fixture, '#help-subject-search').setValue('sql');
    input.dispatchEvent(new Event('input', { bubbles: true }));
    const search = await vi.waitFor(() => backend.expectOne('/api/v1/subjects?query=sql&limit=20'));
    control(fixture, '#help-subject-search').setValue('calc');
    input.dispatchEvent(new Event('input', { bubbles: true }));
    expect(search.cancelled).toBe(true);
    const current = await vi.waitFor(() =>
      backend.expectOne('/api/v1/subjects?query=calc&limit=20'),
    );
    current.flush(catalogue);
    await shown(fixture, 'Calculus');
  });
  it('retries a catalogue error only through explicit action', async () => {
    await load();
    await open({ code: 'unavailable' }, 503);
    click(fixture, 'Retry areas');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/subjects?query=&limit=20'));
    request.flush(catalogue);
    await shown(fixture, 'SQL');
  });
  it('retries a failed own selection read without leaking problem titles', async () => {
    await load({ code: 'unavailable', title: 'PRIVATE' }, 503);
    expect(host(fixture).textContent).not.toContain('PRIVATE');
    click(fixture, 'Try again');
    await load();
  });
  for (const status of [0, 408, 503])
    it(`replays exact uncertain helper intent ${String(status)}`, async () => {
      await load();
      edit('Draft');
      const request = await saveRequest();
      const body: unknown = request.request.body;
      const key = request.request.headers.get('idempotency-key');
      if (status === 0) request.error(new ProgressEvent('error'));
      else request.flush({ code: 'unavailable' }, { status, statusText: 'Unknown' });
      await shown(fixture, 'We couldn’t confirm your save.');
      const retry = await saveRequest();
      expect(retry.request.body).toEqual(body);
      expect(retry.request.headers.get('idempotency-key')).toBe(key);
      retry.flush(helpSelection);
      await load();
    });
  for (const [status, code, copy] of [
    [409, 'help_version_conflict', 'Your help areas changed elsewhere.'],
    [409, 'subject_unavailable', 'An area is no longer available.'],
    [409, 'idempotency_conflict', 'We couldn’t resolve this save.'],
    [422, 'invalid', 'We couldn’t save your areas.'],
  ] as const)
    it(`keeps a safe explicit ${code} recovery`, async () => {
      await load();
      edit('Local draft');
      const request = await saveRequest();
      request.flush({ code, title: 'PRIVATE' }, { status, statusText: 'Failed' });
      await shown(fixture, copy);
      expect(host(fixture).textContent).not.toContain('PRIVATE');
      expect(control(fixture, '#help-note-0').value).toBe('Local draft');
      click(fixture, 'Reload saved areas');
      await load();
      expect(control(fixture, '#help-note-0').value).toBe('Limits');
    });
  for (const status of [401, 403])
    it(`clears private data when save is denied ${String(status)}`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      await load();
      const request = await saveRequest();
      request.flush({ code: 'denied' }, { status, statusText: 'Denied' });
      await vi.waitFor(() => {
        expect(expired).toHaveBeenCalledOnce();
      });
      expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
    });
  for (const status of [200, 401])
    it(`ignores old actor save outcome ${String(status)}`, async () => {
      await load();
      const request = await saveRequest();
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement' });
      fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'replacement' });
      fixture.detectChanges();
      await load();
      edit('Replacement draft');
      request.flush(status === 200 ? helpSelection : { code: 'denied' }, {
        status,
        statusText: 'Result',
      });
      await shown(fixture, 'Changes apply after you save.');
      expect(control(fixture, '#help-note-0').value).toBe('Replacement draft');
      expect(expired).not.toHaveBeenCalled();
      backend.expectNone({ url: '/api/v1/me/help-subjects', method: 'GET' });
    });
  it('retains a queued helper draft across a sign-in pause and retries the same intent with fresh CSRF', async () => {
    await load();
    edit('Queued helper draft');
    submit(fixture);
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    await shown(fixture, 'Your save paused during a sign-in check.');
    backend.expectNone({ url: '/api/v1/me/help-subjects', method: 'PUT' });
    const original = client
      .getMutationCache()
      .getAll()
      .find((entry: Readonly<Mutation>) => entry.state.status === 'error')?.state.variables;
    const rotated = { ...verifiedActor, csrf_token: 'fresh-after-helper-check' };
    client.setQueryData(['session'], rotated);
    fixture.componentRef.setInput('actor', rotated);
    fixture.componentRef.setInput('checking', false);
    fixture.detectChanges();
    // The same-owner canonical selection remains fresh through this checking pause.
    expect(control(fixture, '#help-note-0').value).toBe('Queued helper draft');
    backend.expectNone({ url: '/api/v1/me/help-subjects', method: 'GET' });
    await shown(fixture, 'Your save paused during a sign-in check.');
    click(fixture, 'Retry same save');
    const retry = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/help-subjects', method: 'PUT' }),
    );
    expect(retry.request.headers.get('x-csrf-token')).toBe(rotated.csrf_token);
    expect(original).toMatchObject({ key: retry.request.headers.get('idempotency-key') });
    expect(retry.request.body).toEqual({
      expected_version: 2,
      subjects: [
        { subject_id: helpSelection.subjects[0].subject_id, topic_note: 'Queued helper draft' },
      ],
    });
    const saved = {
      ...helpSelection,
      version: 3,
      subjects: [{ ...helpSelection.subjects[0], topic_note: 'Queued helper draft' }],
    };
    retry.flush(saved);
    await load({ selection: saved });
  });
  it('does not refetch private helper state while an owned save receipt arrives during a sign-in check', async () => {
    await load();
    edit('Committed helper draft');
    const save = await saveRequest();
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    save.flush({
      ...helpSelection,
      version: 3,
      subjects: [{ ...helpSelection.subjects[0], topic_note: 'Committed helper draft' }],
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(
        client
          .getMutationCache()
          .getAll()
          .some((entry: Readonly<Mutation>) => entry.state.status === 'success'),
      ).toBe(true);
    });
    expect(control(fixture, '#help-note-0').value).toBe('Committed helper draft');
    expect(
      client.getQueryState(['account', verifiedActor.account_id, 'help-subjects'])?.isInvalidated,
    ).toBe(true);
    backend.expectNone({ url: '/api/v1/me/help-subjects', method: 'GET' });
  });
  it('never rolls a committed helper selection back to a lagging canonical revision', async () => {
    await load();
    edit('Committed helper draft');
    const save = await saveRequest();
    save.flush({
      ...helpSelection,
      version: 3,
      subjects: [{ ...helpSelection.subjects[0], topic_note: 'Committed helper draft' }],
    });
    await load({ selection: { ...helpSelection, version: 1 } });
    expect(control(fixture, '#help-note-0').value).toBe('Committed helper draft');
    submit(fixture);
    backend.expectNone({ url: '/api/v1/me/help-subjects', method: 'PUT' });
  });
  it('adopts an authoritative empty helper projection after a confirmed save rather than keeping optimistic rows', async () => {
    await load();
    edit('Committed helper draft');
    const save = await saveRequest();
    save.flush({ ...helpSelection, version: 3 });
    await load({ selection: null });
    await shown(fixture, 'Helping is always optional.');
    expect(host(fixture).querySelector('#help-note-0')).toBeNull();
    backend.expectNone({ url: '/api/v1/me/help-subjects', method: 'PUT' });
  });
  it('preserves a dirty helper draft after an actual newer canonical read and reloads only explicitly', async () => {
    await load();
    edit('Unsaved local note');
    const current = {
      ...helpSelection,
      version: 3,
      subjects: [{ ...helpSelection.subjects[0], topic_note: 'Changed elsewhere' }],
    };
    const refresh = client.refetchQueries({
      queryKey: ['account', verifiedActor.account_id, 'help-subjects'],
    });
    (
      await vi.waitFor(() => backend.expectOne({ url: '/api/v1/me/help-subjects', method: 'GET' }))
    ).flush({ selection: current });
    await refresh;
    await shown(fixture, 'Your help areas changed elsewhere.');
    expect(control(fixture, '#help-note-0').value).toBe('Unsaved local note');
    submit(fixture);
    backend.expectNone({ url: '/api/v1/me/help-subjects', method: 'PUT' });
    click(fixture, 'Reload saved areas');
    await load({ selection: current });
    expect(control(fixture, '#help-note-0').value).toBe('Changed elsewhere');
  });
  it('replays the original unknown helper intent against a newer canonical revision without overwriting that newer state', async () => {
    await load();
    edit('Original helper intent');
    const save = await saveRequest();
    const key = save.request.headers.get('idempotency-key');
    save.flush({ code: 'unavailable' }, { status: 503, statusText: 'Unavailable' });
    await shown(fixture, 'We couldn’t confirm your save.');
    const current = {
      ...helpSelection,
      version: 4,
      subjects: [{ ...helpSelection.subjects[0], topic_note: 'Newer canonical note' }],
    };
    const refresh = client.refetchQueries({
      queryKey: ['account', verifiedActor.account_id, 'help-subjects'],
    });
    (
      await vi.waitFor(() => backend.expectOne({ url: '/api/v1/me/help-subjects', method: 'GET' }))
    ).flush({ selection: current });
    await refresh;
    await shown(fixture, 'Your help areas changed elsewhere.');
    click(fixture, 'Retry same save');
    const retry = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/help-subjects', method: 'PUT' }),
    );
    expect(retry.request.headers.get('idempotency-key')).toBe(key);
    expect(retry.request.body).toEqual({
      expected_version: 2,
      subjects: [
        { subject_id: helpSelection.subjects[0].subject_id, topic_note: 'Original helper intent' },
      ],
    });
    retry.flush({ ...helpSelection, version: 3 });
    await load({ selection: current });
    expect(control(fixture, '#help-note-0').value).toBe('Newer canonical note');
  });
  it('cancels the old actor catalogue before binding the replacement helper editor', async () => {
    await load();
    click(fixture, 'Add an area');
    const old = await vi.waitFor(() => backend.expectOne('/api/v1/subjects?query=&limit=20'));
    const replacement = { ...verifiedActor, account_id: 'replacement-helper-actor' };
    client.setQueryData(['session'], replacement);
    fixture.componentRef.setInput('actor', replacement);
    fixture.detectChanges();
    expect(old.cancelled).toBe(true);
    await load();
    expect(control(fixture, '#help-note-0').value).toBe('Limits');
    backend.expectNone('/api/v1/subjects?query=&limit=20');
    backend.expectNone({ url: '/api/v1/me/help-subjects', method: 'PUT' });
  });
});
