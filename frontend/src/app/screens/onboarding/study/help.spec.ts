import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, input, output } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TuiRoot } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
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
    '<tui-root><peerly-help-subjects [actor]="actor()" (expired)="expired.emit()" /></tui-root>',
})
class HelpTestHost {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
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
});
