import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TuiRoot } from '@taiga-ui/core';
import {
  QueryClient,
  QueryObserver,
  provideTanStackQuery,
} from '@tanstack/angular-query-experimental';
import type { Mutation } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../../../api.generated';
import { appConfig } from '../../../app.config';
import { RequestComposer } from './compose';
import type { ComposerSelection, SendResult } from './compose-contract';
import { actor, recipientId, preview, receipt, connected } from './compose.fixtures';

@Component({
  selector: 'compose-test-host',
  imports: [TuiRoot, RequestComposer],
  template: `<tui-root
    ><app-request-composer
      [actor]="identity()"
      [recipientId]="recipient()"
      [mode]="mode()"
      [recipientName]="name()"
      [open]="shown()"
      (closed)="shown.set(false)"
      (expired)="expired()"
      (sent)="sent($event); shown.set(false)"
      (reconciliation)="reconciliation($event)"
  /></tui-root>`,
})
class ComposeHost {
  public readonly identity = signal(actor);
  public readonly recipient = signal(recipientId);
  public readonly name = signal<string | null>('Aiko Tan');
  public readonly mode = signal<Api['schemas']['DiscoveryMode']>('find_help');
  public readonly shown = signal(true);
  public readonly expired = vi.fn<() => void>();
  public readonly sent = vi.fn<(value: SendResult) => void>();
  public readonly reconciliation = vi.fn<(value: ComposerSelection) => void>();
}

describe('D03 one feature-owned form and actual explicit send', () => {
  let fixture: ComponentFixture<ComposeHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: {
        queries: { retry: false, refetchOnWindowFocus: false },
        mutations: { retry: false },
      },
    });
    client.setQueryData(['session'], actor);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(ComposeHost);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    try {
      fixture.destroy();
      client.clear();
      backend.verify({ ignoreCancelled: true });
    } finally {
      vi.restoreAllMocks();
      TestBed.resetTestingModule();
    }
  });
  function body(): HTMLElement {
    return document.body;
  }
  async function shown(text: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(body().textContent).toContain(text);
    });
  }
  function button(name: string): HTMLButtonElement {
    const value = Array.from(body().querySelectorAll('button')).find(
      (element: Readonly<HTMLButtonElement>) =>
        (element.getAttribute('aria-label') ?? element.textContent.trim()) === name,
    );
    if (value === undefined) throw new Error(`Missing button: ${name}`);
    return value;
  }
  function click(name: string): void {
    fixture.detectChanges();
    button(name).click();
    fixture.detectChanges();
  }
  function textarea(id: string): HTMLTextAreaElement {
    const value = body().querySelector(`#${id}`);
    if (!(value instanceof HTMLTextAreaElement)) throw new Error(`Missing textarea: ${id}`);
    return value;
  }
  function enter(id: string, value: string): void {
    const field = textarea(id);
    Reflect.set(field, 'value', value);
    field.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
  }
  async function checked(value: Api['schemas']['PreviewResponse'] = preview()): Promise<void> {
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/requests/preview').flush(value);
    });
    await shown('Saved academic context');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(textarea('request-text').value).toBe(value.suggested_text);
    });
  }
  async function command(path: string) {
    return vi.waitFor(() => backend.expectOne(path));
  }
  async function focusedError(id: string, message: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      const field = textarea(id);
      expect(document.activeElement).toBe(field);
      const described = field.getAttribute('aria-describedby');
      if (described === null || described.length === 0)
        throw new Error('Missing actual linked error');
      expect(document.getElementById(described)?.textContent).toContain(message);
      expect(field.getAttribute('aria-details')).toBe(`${id}-hint`);
      expect(document.getElementById(`${id}-hint`)?.textContent).toContain('/ 240 characters.');
    });
  }
  it('initial explicit review obtains server suggestion and source without sending', async () => {
    const check = await command('/api/v1/requests/preview');
    expect(check.request.body).toEqual({ person_id: recipientId, mode: 'find_help' });
    expect(check.request.headers.get('X-CSRF-Token')).toBe(actor.csrf_token);
    expect(check.request.headers.get('Idempotency-Key')).toMatch(/^[\da-f-]{36}$/);
    check.flush(preview());
    await shown('Saved academic context');
    expect(textarea('request-text').value).toBe(preview().suggested_text);
    backend.expectNone('/api/v1/requests');
  });
  it('shows actual reset and cooldown in consistent Kuala Lumpur time', async () => {
    await checked({
      ...preview(),
      can_send: false,
      block_reason: 'cooldown',
      cooldown_until: '2026-11-09T16:00:00Z',
    });
    await shown('Daily allowance resets at 00:00 Kuala Lumpur time.');
    expect(body().textContent).toMatch(
      /Available after Nov 10, 2026, 12:00:00\sAM Kuala Lumpur time\./,
    );
    backend.expectNone('/api/v1/requests');
  });
  it('native dialog close reads current pending policy after preview settles', async () => {
    await shown('Checking the current pair and academic context');
    click('Close');
    expect(fixture.componentInstance.shown()).toBe(true);
    await checked();
    click('Close');
    await vi.waitFor(() => {
      expect(fixture.componentInstance.shown()).toBe(false);
    });
    backend.expectNone('/api/v1/requests');
  });
  for (const mode of ['offer_help', 'study_together'] as const)
    it(`${mode} renders the actual source and server default`, async () => {
      await checked();
      fixture.componentInstance.mode.set(mode);
      fixture.detectChanges();
      await shown('Your draft belongs to another person or mode');
      click('Discard draft and review this selection');
      await checked(preview(mode));
      expect(textarea('request-text').value).toBe(preview(mode).suggested_text);
    });
  it('close/reopen keeps one actual form text/note and makes no new preview or send', async () => {
    await checked();
    enter('request-text', 'My edited request 🙂');
    click('Personal note · optional');
    enter('request-note', 'A personal note');
    click('Close without sending');
    expect(fixture.componentInstance.shown()).toBe(false);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(body().querySelector('#request-text')).toBeNull();
    });
    fixture.componentInstance.shown.set(true);
    await shown('Saved academic context');
    expect(textarea('request-text').value).toBe('My edited request 🙂');
    expect(textarea('request-note').value).toBe('A personal note');
    backend.expectNone('/api/v1/requests/preview');
    backend.expectNone('/api/v1/requests');
  });
  it('explicit send snapshots raw edited text/note, blocks duplicates and emits only actual sent receipt', async () => {
    await checked();
    enter('request-text', '  My raw text 🙂  ');
    click('Personal note · optional');
    enter('request-note', 'My note');
    click('Send request');
    const write = await command('/api/v1/requests');
    expect(write.request.body).toEqual({
      person_id: recipientId,
      preview_id: preview().preview_id,
      text: '  My raw text 🙂  ',
      note: 'My note',
    });
    expect(textarea('request-text').readOnly).toBe(true);
    expect(button('Close without sending').disabled).toBe(true);
    click('Send request');
    backend.expectNone('/api/v1/requests');
    write.flush(receipt);
    await vi.waitFor(() => {
      expect(fixture.componentInstance.sent).toHaveBeenCalledExactlyOnceWith(receipt);
    });
    expect(fixture.componentInstance.shown()).toBe(false);
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });
  it('empty optional note deliberately maps to null, valid240 emoji are not rejected as UTF16', async () => {
    await checked();
    enter('request-text', '🙂'.repeat(240));
    click('Send request');
    const write = await command('/api/v1/requests');
    expect(write.request.body).toEqual(
      expect.objectContaining({ text: '🙂'.repeat(240), note: null }),
    );
    write.flush(receipt);
    await vi.waitFor(() => {
      expect(fixture.componentInstance.sent).toHaveBeenCalledTimes(1);
    });
  });
  it('field blur keeps the native submit action stable while validation grows in the body', async () => {
    await checked();
    const field = textarea('request-text');
    field.focus();
    enter('request-text', '');
    const send = button('Send request');
    const before = send.getBoundingClientRect();
    expect(send.form?.id).toBe('request-composer-form');
    field.blur();
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(body().querySelector('[role="alert"]')?.textContent).toContain(
        'Write a request before sending.',
      );
    });
    const after = send.getBoundingClientRect();
    expect([after.top, after.left, after.width, after.height]).toEqual([
      before.top,
      before.left,
      before.width,
      before.height,
    ]);
    click('Send request');
    await focusedError('request-text', 'Write a request before sending');
    backend.expectNone('/api/v1/requests');
  });
  it('invalid draft stays uncut, links validation to the field and never posts a send', async () => {
    await checked();
    enter('request-text', '🙂'.repeat(241));
    click('Send request');
    await shown('Your text has not been cut');
    await focusedError('request-text', 'Your text has not been cut');
    expect(textarea('request-text').value).toBe('🙂'.repeat(241));
    expect(textarea('request-text').getAttribute('maxlength')).toBeNull();
    enter('request-text', '');
    click('Send request');
    await shown('Write a request before sending');
    await focusedError('request-text', 'Write a request before sending');
    enter('request-text', 'Valid');
    click('Personal note · optional');
    enter('request-note', 'n'.repeat(241));
    click('Personal note · optional');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(body().querySelector('#request-note')).toBeNull();
    });
    click('Send request');
    await shown('Personal note: 241');
    await focusedError('request-note', 'Your text has not been cut');
    backend.expectNone('/api/v1/requests');
  });
  it('closing before validation render does not focus a removed field or send', async () => {
    await checked();
    enter('request-text', '');
    button('Send request').click();
    fixture.componentInstance.shown.set(false);
    fixture.detectChanges();
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(body().querySelector('#request-text')).toBeNull();
    });
    backend.expectNone('/api/v1/requests');
  });
  it('replacement before validation render clears draft and ignores old focus intent', async () => {
    await checked();
    enter('request-text', '');
    button('Send request').click();
    client.setQueryData(['session'], { ...actor, account_id: 'replacement-actor' });
    fixture.detectChanges();
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(body().querySelector('#request-text')).toBeNull();
    });
    expect(client.getMutationCache().getAll()).toHaveLength(0);
    backend.expectNone('/api/v1/requests');
  });
  it('correcting a field before validation render does not send or retain an obsolete error', async () => {
    await checked();
    enter('request-text', '');
    button('Send request').click();
    enter('request-text', 'A corrected request.');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(body().textContent).not.toContain('Write a request before sending.');
    });
    expect(textarea('request-text').value).toBe('A corrected request.');
    backend.expectNone('/api/v1/requests');
  });
  it('same-owner revalidation during queued validation preserves draft and blocks stale focus', async () => {
    await checked();
    enter('request-text', '');
    button('Send request').click();
    let complete: ((value: Api['schemas']['IdentityResponse']) => void) | undefined;
    const check = client.query({
      queryKey: ['session'],
      queryFn: () =>
        new Promise<Api['schemas']['IdentityResponse']>((resolve) => {
          complete = resolve;
        }),
    });
    fixture.detectChanges();
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(button('Send request').disabled).toBe(true);
    });
    expect(textarea('request-text').value).toBe('');
    const finish = complete;
    if (finish === undefined) throw new Error('Missing session completion');
    finish(actor);
    await check;
    backend.expectNone('/api/v1/requests');
  });
  it('successful pair recovery invalidates canonical observers once, not again for unchanged session', async () => {
    await checked();
    const invalidations = vi.spyOn(client, 'invalidateQueries');
    const requests = new QueryObserver(client, {
      queryKey: ['account', actor.account_id, 'requests', 'sent', 'active'],
      queryFn: () => Promise.resolve([]),
    });
    const discovery = new QueryObserver(client, {
      queryKey: ['account', actor.account_id, 'discovery', 'find_help', 'candidates', null],
      queryFn: () => Promise.resolve([]),
    });
    const stopRequests = requests.subscribe(() => undefined);
    const stopDiscovery = discovery.subscribe(() => undefined);
    try {
      await vi.waitFor(() => {
        expect(requests.getCurrentResult().isSuccess).toBe(true);
        expect(discovery.getCurrentResult().isSuccess).toBe(true);
      });
      click('Send request');
      (await command('/api/v1/requests')).flush(connected);
      await shown('A request or connection reference already exists');
      await client.query({ queryKey: ['session'], queryFn: () => Promise.resolve(actor) });
      expect(invalidations).toHaveBeenCalledTimes(2);
      expect(fixture.componentInstance.sent).not.toHaveBeenCalled();
    } finally {
      stopRequests();
      stopDiscovery();
      requests.destroy();
      discovery.destroy();
    }
  });
  it('active session observer finalizes deferred sent receipt once with one canonical refresh', async () => {
    await checked();
    const invalidations = vi.spyOn(client, 'invalidateQueries');
    const requests = new QueryObserver(client, {
      queryKey: ['account', actor.account_id, 'requests', 'sent', 'active'],
      queryFn: () => Promise.resolve([]),
    });
    const discovery = new QueryObserver(client, {
      queryKey: ['account', actor.account_id, 'discovery', 'find_help', 'candidates', null],
      queryFn: () => Promise.resolve([]),
    });
    let finishSession: ((value: Api['schemas']['IdentityResponse']) => void) | undefined;
    const session = new QueryObserver(client, {
      queryKey: ['session'],
      staleTime: Infinity,
      queryFn: () =>
        new Promise<Api['schemas']['IdentityResponse']>((resolve) => {
          finishSession = resolve;
        }),
    });
    const stopRequests = requests.subscribe(() => undefined);
    const stopDiscovery = discovery.subscribe(() => undefined);
    const stopSession = session.subscribe(() => undefined);
    try {
      await vi.waitFor(() => {
        expect(requests.getCurrentResult().isSuccess).toBe(true);
        expect(discovery.getCurrentResult().isSuccess).toBe(true);
      });
      click('Send request');
      const write = await command('/api/v1/requests');
      const checking = session.refetch();
      write.flush(receipt);
      await vi.waitFor(() => {
        expect(
          client
            .getMutationCache()
            .getAll()
            .some(
              (mutation: Readonly<Mutation>) =>
                mutation.state.status === 'success' && mutation.state.data === receipt,
            ),
        ).toBe(true);
      });
      expect(fixture.componentInstance.sent).not.toHaveBeenCalled();
      const complete = finishSession;
      if (complete === undefined) throw new Error('Missing actual session completion');
      complete(actor);
      await checking;
      await vi.waitFor(() => {
        expect(fixture.componentInstance.sent).toHaveBeenCalledExactlyOnceWith(receipt);
      });
      expect(invalidations).toHaveBeenCalledTimes(2);
    } finally {
      stopRequests();
      stopDiscovery();
      stopSession();
      requests.destroy();
      discovery.destroy();
      session.destroy();
    }
  });
  async function holdCanonicalRead(): Promise<
    Readonly<{
      readonly observer: QueryObserver<readonly unknown[]>;
      readonly release: () => void;
      readonly close: () => void;
    }>
  > {
    let reads = 0;
    let finishRead: ((value: readonly unknown[]) => void) | undefined;
    const held = new Promise<readonly unknown[]>((resolve) => {
      finishRead = resolve;
    });
    const observer = new QueryObserver<readonly unknown[]>(client, {
      queryKey: ['account', actor.account_id, 'requests', 'sent', 'active'],
      queryFn: () => {
        reads += 1;
        return reads === 1 ? Promise.resolve([]) : held;
      },
    });
    const stop = observer.subscribe(() => undefined);
    const close = (): void => {
      stop();
      observer.destroy();
    };
    try {
      await vi.waitFor(() => {
        expect(observer.getCurrentResult().isSuccess).toBe(true);
      });
      return {
        observer,
        close,
        release: () => {
          const complete = finishRead;
          if (complete === undefined) throw new Error('Missing canonical read completion');
          complete([]);
        },
      };
    } catch (error: unknown) {
      close();
      throw error;
    }
  }
  it('a later feature draft cannot be interrupted by an earlier confirmed send canonical read', async () => {
    await checked();
    const canonical = await holdCanonicalRead();
    try {
      click('Send request');
      (await command('/api/v1/requests')).flush(receipt);
      await vi.waitFor(() => {
        expect(canonical.observer.getCurrentResult().isFetching).toBe(true);
        expect(client.getMutationCache().getAll()).toHaveLength(0);
      });
      fixture.componentInstance.shown.set(false);
      fixture.detectChanges();
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(body().querySelector('#request-text')).toBeNull();
      });
      fixture.componentInstance.shown.set(true);
      fixture.detectChanges();
      await checked();
      enter('request-text', 'A later explicitly reviewed draft.');
      canonical.release();
      await vi.waitFor(() => {
        expect(canonical.observer.getCurrentResult().isFetching).toBe(false);
      });
      expect(fixture.componentInstance.sent).not.toHaveBeenCalled();
      expect(textarea('request-text').value).toBe('A later explicitly reviewed draft.');
    } finally {
      canonical.close();
    }
  });
  for (const lifecycle of ['logout', 'replacement', 'destroy'] as const)
    it(`${lifecycle} during confirmed send canonical refresh cannot emit into a later lifetime`, async () => {
      await checked();
      const canonical = await holdCanonicalRead();
      try {
        click('Send request');
        (await command('/api/v1/requests')).flush(receipt);
        await vi.waitFor(() => {
          expect(canonical.observer.getCurrentResult().isFetching).toBe(true);
          expect(client.getMutationCache().getAll()).toHaveLength(0);
        });
        if (lifecycle === 'destroy') fixture.destroy();
        else
          client.setQueryData(
            ['session'],
            lifecycle === 'logout' ? null : { ...actor, account_id: 'replacement-actor' },
          );
        canonical.release();
        await vi.waitFor(() => {
          expect(canonical.observer.getCurrentResult().isFetching).toBe(false);
        });
        expect(fixture.componentInstance.sent).not.toHaveBeenCalled();
      } finally {
        canonical.close();
      }
    });
  it('presentation name and same-owner CSRF changes cannot start another preview during confirmed refresh', async () => {
    await checked();
    const canonical = await holdCanonicalRead();
    try {
      click('Send request');
      (await command('/api/v1/requests')).flush(receipt);
      await vi.waitFor(() => {
        expect(canonical.observer.getCurrentResult().isFetching).toBe(true);
        expect(client.getMutationCache().getAll()).toHaveLength(0);
      });
      fixture.componentInstance.name.set(null);
      const renewed = { ...actor, csrf_token: 'current-server-csrf' };
      client.setQueryData(['session'], renewed);
      fixture.componentInstance.identity.set(renewed);
      fixture.detectChanges();
      backend.expectNone('/api/v1/requests/preview');
      canonical.release();
      await vi.waitFor(() => {
        expect(fixture.componentInstance.sent).toHaveBeenCalledExactlyOnceWith(receipt);
      });
      backend.expectNone('/api/v1/requests/preview');
    } finally {
      canonical.close();
    }
  });
  it('server can_send is authoritative without inferring limits from apparently exhausted counters', async () => {
    await checked({ ...preview(), quota: { ...preview().quota, daily_sends_remaining: 0 } });
    expect(button('Send request').disabled).toBe(false);
    click('Send request');
    (await command('/api/v1/requests')).flush(receipt);
    await vi.waitFor(() => {
      expect(fixture.componentInstance.sent).toHaveBeenCalledTimes(1);
    });
  });
  it('server quota denial keeps draft and source without a fake countdown or send', async () => {
    await checked({ ...preview(), can_send: false, block_reason: 'daily_send_limit' });
    await shown('Your daily send limit has been reached');
    enter('request-text', 'Kept draft');
    expect(
      Array.from(body().querySelectorAll('button')).some(
        (item: Readonly<HTMLButtonElement>) => item.getAttribute('aria-label') === 'Send request',
      ),
    ).toBe(false);
    backend.expectNone('/api/v1/requests');
  });
  it('unknown send keeps original preview/body/key across close and recheck needs explicit retry', async () => {
    await checked();
    enter('request-text', 'Original request');
    click('Send request');
    const first = await command('/api/v1/requests');
    const key = first.request.headers.get('Idempotency-Key');
    const payload: unknown = first.request.body;
    first.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Retry same request');
    expect(textarea('request-text').readOnly).toBe(true);
    click('Close without sending');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(body().querySelector('#request-text')).toBeNull();
    });
    fixture.componentInstance.shown.set(true);
    await shown('Retry same request');
    backend.expectNone('/api/v1/requests/preview');
    client.setQueryData(['session'], { ...actor, csrf_token: 'current-csrf' });
    click('Retry same request');
    const retry = await command('/api/v1/requests');
    expect(retry.request.body).toEqual(payload);
    expect(retry.request.headers.get('Idempotency-Key')).toBe(key);
    expect(retry.request.headers.get('X-CSRF-Token')).toBe('current-csrf');
    retry.flush(receipt);
    await vi.waitFor(() => {
      expect(fixture.componentInstance.sent).toHaveBeenCalledExactlyOnceWith(receipt);
    });
  });
  it('confirmed failure reuses unchanged intent but an edited explicit send gets a new key', async () => {
    await checked();
    click('Send request');
    const first = await command('/api/v1/requests');
    const key = first.request.headers.get('Idempotency-Key');
    first.flush({}, { status: 422, statusText: 'Invalid' });
    await shown('Your draft is kept');
    click('Send request');
    const same = await command('/api/v1/requests');
    expect(same.request.headers.get('Idempotency-Key')).toBe(key);
    same.flush({}, { status: 422, statusText: 'Invalid' });
    await shown('Your draft is kept');
    enter('request-text', 'A deliberate changed request');
    click('Send request');
    const changed = await command('/api/v1/requests');
    expect(changed.request.headers.get('Idempotency-Key')).not.toBe(key);
    changed.flush(receipt);
    await vi.waitFor(() => {
      expect(fixture.componentInstance.sent).toHaveBeenCalledTimes(1);
    });
  });
  it('changing recipient never reattaches a draft; keep emits exact original selection', async () => {
    await checked();
    enter('request-text', 'Private unsent text');
    fixture.componentInstance.recipient.set('another-person');
    fixture.componentInstance.name.set('Someone new');
    await shown('Your draft belongs to another person or mode');
    expect(body().textContent).not.toContain('To Someone new');
    click('Keep original draft');
    expect(fixture.componentInstance.reconciliation).toHaveBeenCalledWith({
      actorId: actor.account_id,
      recipientId,
      mode: 'find_help',
    });
    backend.expectNone('/api/v1/requests/preview');
    backend.expectNone('/api/v1/requests');
  });
  it('changed source is reviewed explicitly without overwriting edited text or note', async () => {
    await checked();
    enter('request-text', 'Edited for review');
    click('Personal note · optional');
    enter('request-note', 'Keep my note');
    click('Recheck availability');
    const first = preview();
    const oldGoal = first.context.sender_goal;
    if (oldGoal === null) throw new Error('Missing source');
    const revised = {
      ...first,
      preview_id: 'revised-preview',
      suggested_text: 'New suggestion',
      context: {
        ...first.context,
        sender_goal: { ...oldGoal, version: 2, topic: 'Updated joins' },
      },
    };
    (await command('/api/v1/requests/preview')).flush(revised);
    await shown('The saved academic context changed');
    expect(textarea('request-text').value).toBe('Edited for review');
    expect(textarea('request-note').value).toBe('Keep my note');
    expect(button('Send request').disabled).toBe(true);
    click('Use reviewed context and keep my text');
    click('Send request');
    const write = await command('/api/v1/requests');
    expect(write.request.body).toEqual(
      expect.objectContaining({
        preview_id: revised.preview_id,
        text: 'Edited for review',
        note: 'Keep my note',
      }),
    );
    write.flush(receipt);
    await vi.waitFor(() => {
      expect(fixture.componentInstance.sent).toHaveBeenCalledTimes(1);
    });
  });
  it('same-source availability refresh and explicit Reset never silently overwrite edited text', async () => {
    await checked();
    enter('request-text', 'Keep this');
    click('Recheck availability');
    const value = {
      ...preview(),
      preview_id: 'new-same-context',
      suggested_text: 'New suggestion',
    };
    (await command('/api/v1/requests/preview')).flush(value);
    await shown('Edited request text');
    expect(textarea('request-text').value).toBe('Keep this');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(button('Reset request text to server suggestion').disabled).toBe(false);
    });
    click('Reset request text to server suggestion');
    expect(textarea('request-text').value).toBe('New suggestion');
  });
  for (const outcome of ['incoming', 'existing_outgoing', 'connected'] as const)
    it(`actual ${outcome} pair response is recovery only, never a new send or accept`, async () => {
      const result = outcome === 'connected' ? connected : { ...receipt, outcome };
      (await command('/api/v1/requests/preview')).flush(result);
      await shown('A request or connection reference already exists');
      expect(body().querySelector('a[href*="request=' + receipt.request_id + '"]')).not.toBeNull();
      backend.expectNone('/api/v1/requests');
      expect(fixture.componentInstance.sent).not.toHaveBeenCalled();
    });
  it('401 clears draft and emits expiry only for current owner without recursive callbacks', async () => {
    await checked();
    enter('request-text', 'Sensitive draft');
    click('Send request');
    (await command('/api/v1/requests')).flush({}, { status: 401, statusText: 'Unauthorized' });
    await vi.waitFor(() => {
      expect(fixture.componentInstance.expired).toHaveBeenCalledTimes(1);
    });
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });
  it('logout clears private form/cache and a late old-account success cannot emit', async () => {
    await checked();
    enter('request-text', 'Old account draft');
    click('Send request');
    const old = await command('/api/v1/requests');
    client.setQueryData(['session'], null);
    fixture.detectChanges();
    old.flush(receipt);
    await vi.waitFor(() => {
      expect(client.getMutationCache().getAll()).toHaveLength(0);
    });
    expect(fixture.componentInstance.sent).not.toHaveBeenCalled();
    expect(body().textContent).not.toContain('Old account draft');
  });
  it('same-owner session revalidation preserves the form and temporarily blocks actions', async () => {
    await checked();
    enter('request-text', 'Keep during check');
    let finishSession: ((value: Api['schemas']['IdentityResponse']) => void) | undefined;
    const check = client.query({
      queryKey: ['session'],
      queryFn: () =>
        new Promise<Api['schemas']['IdentityResponse']>((resolve) => {
          finishSession = resolve;
        }),
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(button('Send request').disabled).toBe(true);
    });
    expect(textarea('request-text').value).toBe('Keep during check');
    const resolve = finishSession;
    if (resolve === undefined) throw new Error('Missing session completion');
    resolve(actor);
    await check;
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(button('Send request').disabled).toBe(false);
    });
    expect(textarea('request-text').value).toBe('Keep during check');
  });
  it('unknown preview explicitly replays the exact check key and never sends', async () => {
    const first = await command('/api/v1/requests/preview');
    const key = first.request.headers.get('Idempotency-Key');
    first.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Retry same preview check');
    click('Retry same preview check');
    const retry = await command('/api/v1/requests/preview');
    expect(retry.request.headers.get('Idempotency-Key')).toBe(key);
    expect(retry.request.body).toEqual({ person_id: recipientId, mode: 'find_help' });
    retry.flush(preview());
    await shown('Saved academic context');
    backend.expectNone('/api/v1/requests');
  });
  it('a preview for another actor is malformed, not authority to bind that source', async () => {
    const value = preview();
    const goal = value.context.sender_goal;
    if (goal === null) throw new Error('Missing goal');
    (await command('/api/v1/requests/preview')).flush({
      ...value,
      context: { ...value.context, sender_goal: { ...goal, owner_id: 'another-actor' } },
    });
    await shown('Retry same preview check');
    expect(body().querySelector('#request-text')).toBeNull();
    backend.expectNone('/api/v1/requests');
  });
  for (const [status, text] of [
    [409, 'academic source changed'],
    [429, 'another request right now'],
    [404, 'no longer available'],
  ] as const)
    it(`confirmed ${String(status)} send error keeps the draft for explicit review`, async () => {
      await checked();
      enter('request-text', 'Kept after failure');
      click('Send request');
      (await command('/api/v1/requests')).flush({}, { status, statusText: 'Failure' });
      await shown(text);
      expect(textarea('request-text').value).toBe('Kept after failure');
      click('Review current context');
      (await command('/api/v1/requests/preview')).flush({
        ...preview(),
        preview_id: 'fresh-reviewed',
      });
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(button('Send request').disabled).toBe(false);
      });
    });
  for (const block_reason of [
    'existing_outgoing',
    'incoming',
    'connected',
    'cooldown',
    'source_changed',
    'unavailable',
    'outgoing_pending_limit',
  ] as const)
    it(`actual ${block_reason} advisory remains a server-owned denial`, async () => {
      await checked({
        ...preview(),
        can_send: false,
        block_reason,
        cooldown_until: block_reason === 'cooldown' ? '2026-11-09T00:00:00Z' : null,
      });
      expect(body().querySelector('button[aria-label="Send request"]')).toBeNull();
      expect(body().textContent).toContain('Daily allowance resets');
      backend.expectNone('/api/v1/requests');
    });
  for (const outcome of ['incoming', 'existing_outgoing', 'connected'] as const)
    it(`send resolving to ${outcome} never claims a new request or discards unsent text`, async () => {
      await checked();
      enter('request-text', 'Keep my unsent text');
      click('Send request');
      (await command('/api/v1/requests')).flush(
        outcome === 'connected' ? connected : { ...receipt, outcome },
      );
      await shown('A request or connection reference already exists');
      expect(fixture.componentInstance.sent).not.toHaveBeenCalled();
      click('Recheck current pair');
      (await command('/api/v1/requests/preview')).flush({
        ...preview(),
        preview_id: 'pair-cleared-preview',
      });
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(body().querySelector('#request-text')).not.toBeNull();
      });
      expect(textarea('request-text').value).toBe('Keep my unsent text');
    });
  it('reviewed new context uses a new server suggestion only after deliberate discard', async () => {
    await checked();
    enter('request-text', 'Old edits');
    click('Personal note · optional');
    enter('request-note', 'Old note');
    click('Recheck availability');
    const value = preview();
    const goal = value.context.sender_goal;
    if (goal === null) throw new Error('Missing goal');
    (await command('/api/v1/requests/preview')).flush({
      ...value,
      preview_id: 'changed-source',
      suggested_text: 'Reviewed new suggestion',
      context: { ...value.context, sender_goal: { ...goal, version: 2 } },
    });
    await shown('The saved academic context changed');
    click('Discard draft and use new suggestion');
    expect(textarea('request-text').value).toBe('Reviewed new suggestion');
    expect(textarea('request-note').value).toBe('');
  });
  it('current-owner send confirmation during session revalidation waits, then emits exactly once', async () => {
    await checked();
    click('Send request');
    const write = await command('/api/v1/requests');
    let finishSession: ((value: Api['schemas']['IdentityResponse']) => void) | undefined;
    const response = new Promise<Api['schemas']['IdentityResponse']>((resolve) => {
      finishSession = resolve;
    });
    const check = client.query({ queryKey: ['session'], queryFn: () => response });
    write.flush(receipt);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(body().textContent).not.toContain('Sending your request');
    });
    expect(fixture.componentInstance.sent).not.toHaveBeenCalled();
    const complete = finishSession;
    if (complete === undefined) throw new Error('Missing session finish');
    complete(actor);
    await check;
    await vi.waitFor(() => {
      expect(fixture.componentInstance.sent).toHaveBeenCalledExactlyOnceWith(receipt);
    });
  });
  it('queued send headers cancel rather than post during a new identity check', async () => {
    await checked();
    click('Send request');
    let finishSession: ((value: Api['schemas']['IdentityResponse']) => void) | undefined;
    const response = new Promise<Api['schemas']['IdentityResponse']>((resolve) => {
      finishSession = resolve;
    });
    const check = client.query({ queryKey: ['session'], queryFn: () => response });
    await shown('We couldn’t complete this action');
    backend.expectNone('/api/v1/requests');
    const complete = finishSession;
    if (complete === undefined) throw new Error('Missing session finish');
    complete(actor);
    await check;
    expect(fixture.componentInstance.sent).not.toHaveBeenCalled();
  });
  it('pending or uncertain send rejects queued controls and source discard events', async () => {
    await checked();
    const close = button('Close without sending');
    const nativeClose = button('Close');
    const refresh = button('Recheck availability');
    const reset = button('Reset request text to server suggestion');
    click('Send request');
    const write = await command('/api/v1/requests');
    for (const control of [close, nativeClose, refresh, reset])
      control.dispatchEvent(new MouseEvent('click'));
    expect(fixture.componentInstance.shown()).toBe(true);
    backend.expectNone('/api/v1/requests/preview');
    fixture.componentInstance.mode.set('offer_help');
    await shown('Your draft belongs to another person or mode');
    button('Discard draft and review this selection').dispatchEvent(new MouseEvent('click'));
    button('Keep original draft').dispatchEvent(new MouseEvent('click'));
    expect(fixture.componentInstance.reconciliation).not.toHaveBeenCalled();
    write.flush({}, { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(button('Keep original draft').disabled).toBe(false);
    });
    button('Discard draft and review this selection').dispatchEvent(new MouseEvent('click'));
    backend.expectNone('/api/v1/requests/preview');
    click('Keep original draft');
    expect(fixture.componentInstance.reconciliation).toHaveBeenCalledWith({
      actorId: actor.account_id,
      recipientId,
      mode: 'find_help',
    });
  });
  it('late replaced-owner rejection cannot expire the new actor or revive a removed draft', async () => {
    await checked();
    click('Send request');
    const old = await command('/api/v1/requests');
    client.setQueryData(['session'], { ...actor, account_id: 'replacement-actor' });
    old.flush({}, { status: 401, statusText: 'Unauthorized' });
    await vi.waitFor(() => {
      expect(client.getMutationCache().getAll()).toHaveLength(0);
    });
    expect(fixture.componentInstance.expired).not.toHaveBeenCalled();
    expect(fixture.componentInstance.sent).not.toHaveBeenCalled();
  });
  it('destroy removes sensitive cache and a late committed response cannot notify the next feature', async () => {
    await checked();
    click('Send request');
    const write = await command('/api/v1/requests');
    fixture.destroy();
    write.flush(receipt);
    await vi.waitFor(() => {
      expect(client.getMutationCache().getAll()).toHaveLength(0);
    });
    expect(fixture.componentInstance.sent).not.toHaveBeenCalled();
  });
  it('a closed mounted child creates no preview until the actual open action', async () => {
    await checked();
    fixture.destroy();
    fixture = TestBed.createComponent(ComposeHost);
    fixture.componentInstance.shown.set(false);
    fixture.detectChanges();
    await vi.waitFor(() => {
      expect(client.getMutationCache().getAll()).toHaveLength(0);
    });
    backend.expectNone('/api/v1/requests/preview');
    fixture.componentInstance.shown.set(true);
    await checked();
  });
});
