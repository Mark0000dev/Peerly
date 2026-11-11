import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTanStackQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TuiDialogService } from '@taiga-ui/core';
import { TUI_CONFIRM } from '@taiga-ui/kit';
import { of } from 'rxjs';
import { appConfig } from '../../app.config';
import { NotificationPreferences } from './notification-preferences';
import {
  defaultPreference,
  notificationActorFixture,
  savedPreference,
} from './notification-test-data';

function host(fixture: Readonly<ComponentFixture<NotificationPreferences>>): HTMLElement {
  const element: unknown = fixture.nativeElement;
  if (!(element instanceof HTMLElement)) throw new Error('Missing notifications host');
  return element;
}
describe('P02 actual preference CAS and same-key recovery without device permission claims', () => {
  let fixture: ComponentFixture<NotificationPreferences>;
  let http: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideRouter([]),
        provideHttpClientTesting(),
        provideTanStackQuery(client),
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(NotificationPreferences);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    http.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
    vi.restoreAllMocks();
  });
  function click(label: string): void {
    const button = Array.from(host(fixture).querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.trim() === label,
    );
    if (button === undefined) throw new Error('Missing preference action');
    button.click();
    fixture.detectChanges();
  }
  async function load(): Promise<void> {
    (await vi.waitFor(() => http.expectOne('/api/v1/me'))).flush(notificationActorFixture);
    (await vi.waitFor(() => http.expectOne('/api/v1/me/notification-preference'))).flush(
      defaultPreference,
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('haven’t saved');
    });
  }
  function chooseAll(): void {
    const radio = host(fixture).querySelector<HTMLInputElement>('input[value="all_updates"]');
    if (radio === null) throw new Error('Missing mode');
    radio.click();
    fixture.detectChanges();
  }
  it('reads real default without requiring activation or sending an implicit write', async () => {
    await load();
    http.expectNone((request) => request.method === 'PUT');
    expect(host(fixture).textContent).toContain('Device delivery is unavailable');
    expect(
      host(fixture).querySelector('input[value="messages_and_requests"]:checked'),
    ).not.toBeNull();
  });
  it('writes one enum with actual CAS/CSRF, then uses canonical read rather than overwriting newer state with replay receipt', async () => {
    await load();
    chooseAll();
    click('Save preference');
    const request = await vi.waitFor(() => http.expectOne((pending) => pending.method === 'PUT'));
    expect(request.request.body).toEqual({ mode: 'all_updates', expected_version: 0 });
    expect(request.request.headers.get('x-csrf-token')).toBe('notification-csrf');
    request.flush(savedPreference);
    const canonical = await vi.waitFor(() =>
      http.expectOne(
        (pending) => pending.method === 'GET' && pending.url.endsWith('notification-preference'),
      ),
    );
    canonical.flush({ ...savedPreference, mode: 'messages_and_requests', version: 2 });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('Your choice was saved');
      const adopt = Array.from(host(fixture).querySelectorAll('button')).find(
        (item: Readonly<HTMLButtonElement>) =>
          item.textContent.trim() === 'Use current saved preference',
      );
      // Mutation success renders before the canonical read's observer settles.
      // Wait for the actual enabled action; a disabled native click sends nothing.
      expect(adopt?.disabled).toBe(false);
    });
    expect(host(fixture).querySelector('input[value="all_updates"]:checked')).not.toBeNull();
    expect(host(fixture).querySelector('fieldset')?.disabled).toBe(true);
    click('Use current saved preference');
    (
      await vi.waitFor(() =>
        http.expectOne(
          (pending) => pending.method === 'GET' && pending.url.endsWith('notification-preference'),
        ),
      )
    ).flush({ ...savedPreference, mode: 'messages_and_requests', version: 2 });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(
        host(fixture).querySelector('input[value="messages_and_requests"]:checked'),
      ).not.toBeNull();
    });
  });
  it('keeps exact intent/key on unknown PUT and blocks a new selection', async () => {
    await load();
    chooseAll();
    click('Save preference');
    const request = await vi.waitFor(() => http.expectOne((pending) => pending.method === 'PUT'));
    const key = request.request.headers.get('idempotency-key');
    const body: unknown = request.request.body;
    request.flush({ code: 'storage_unavailable' }, { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('save outcome is unknown');
    });
    expect(host(fixture).querySelector('fieldset')?.disabled).toBe(true);
    click('Retry identical save');
    const replay = await vi.waitFor(() => http.expectOne((pending) => pending.method === 'PUT'));
    expect(replay.request.body).toEqual(body);
    expect(replay.request.headers.get('idempotency-key')).toBe(key);
    replay.flush(savedPreference);
    (
      await vi.waitFor(() =>
        http.expectOne(
          (pending) => pending.method === 'GET' && pending.url.endsWith('notification-preference'),
        ),
      )
    ).flush(savedPreference);
  });
  it('requires fresh read to clear a version conflict and never automatically resends', async () => {
    await load();
    chooseAll();
    click('Save preference');
    (await vi.waitFor(() => http.expectOne((pending) => pending.method === 'PUT'))).flush(
      { code: 'notification_preference_version_conflict' },
      { status: 409, statusText: 'Conflict' },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('changed elsewhere');
    });
    http.expectNone((pending) => pending.method === 'PUT');
    click('Use current saved preference');
    (
      await vi.waitFor(() =>
        http.expectOne(
          (pending) => pending.method === 'GET' && pending.url.endsWith('notification-preference'),
        ),
      )
    ).flush({ ...savedPreference, version: 2 });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).querySelector('fieldset')?.disabled).toBe(false);
    });
  });
  it('blocks while session is checking, preserves the selected draft, and retires on actual replacement', async () => {
    await load();
    chooseAll();
    void client.invalidateQueries({ queryKey: ['session'] });
    const session = await vi.waitFor(() => http.expectOne('/api/v1/me'));
    fixture.detectChanges();
    expect(host(fixture).textContent).toContain('choice has not been changed');
    session.flush({
      ...notificationActorFixture,
      account_id: '00000000-0000-4000-8000-000000000121',
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('choice has not been changed');
    });
    http.expectNone((pending) => pending.method === 'PUT');
  });
  it('requires different dirty/pending/unknown leave confirmations and no prompt after confirmed save', async () => {
    await load();
    const dialogs = vi.spyOn(TestBed.inject(TuiDialogService), 'open').mockReturnValue(of(false));
    expect(await fixture.componentInstance.canLeave()).toBe(true);
    expect(dialogs).not.toHaveBeenCalled();
    chooseAll();
    expect(await fixture.componentInstance.canLeave()).toBe(false);
    expect(dialogs).toHaveBeenLastCalledWith(
      TUI_CONFIRM,
      expect.objectContaining({ label: 'Discard unsaved changes?' }),
    );
    click('Save preference');
    const pending = await vi.waitFor(() => http.expectOne((request) => request.method === 'PUT'));
    expect(await fixture.componentInstance.canLeave()).toBe(false);
    expect(dialogs).toHaveBeenLastCalledWith(
      TUI_CONFIRM,
      expect.objectContaining({ label: 'Leave before the save is confirmed?' }),
    );
    pending.flush({ code: 'storage_unavailable' }, { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('save outcome is unknown');
    });
    dialogs.mockReturnValue(of(true));
    expect(await fixture.componentInstance.canLeave()).toBe(true);
    expect(dialogs).toHaveBeenLastCalledWith(
      TUI_CONFIRM,
      expect.objectContaining({ label: 'Leave before the save is confirmed?' }),
    );
    click('Retry identical save');
    (await vi.waitFor(() => http.expectOne((request) => request.method === 'PUT'))).flush(
      savedPreference,
    );
    (
      await vi.waitFor(() =>
        http.expectOne(
          (request) => request.method === 'GET' && request.url.endsWith('notification-preference'),
        ),
      )
    ).flush(savedPreference);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('Your choice was saved');
    });
    dialogs.mockClear();
    expect(await fixture.componentInstance.canLeave()).toBe(true);
    expect(dialogs).not.toHaveBeenCalled();
  });
  it('rechecks a missing session before loading the real canonical default', async () => {
    (await vi.waitFor(() => http.expectOne('/api/v1/me'))).flush(
      { code: 'unauthenticated' },
      { status: 401, statusText: 'Unauthorized' },
    );
    await vi.waitFor(() => {
      // This copy is also visible during the initial pending read. A retry
      // before it settles joins that same request instead of starting another.
      expect(client.getQueryState(['session'])).toMatchObject({
        status: 'success',
        fetchStatus: 'idle',
        data: null,
      });
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('active, verified');
    });
    http.expectNone('/api/v1/me/notification-preference');
    click('Check sign-in state');
    (await vi.waitFor(() => http.expectOne('/api/v1/me'))).flush(notificationActorFixture);
    (await vi.waitFor(() => http.expectOne('/api/v1/me/notification-preference'))).flush(
      defaultPreference,
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).querySelector('fieldset')?.disabled).toBe(false);
    });
  });
  it('keeps same-actor selected draft after403, refreshes current read explicitly and does not auto-retry PUT', async () => {
    await load();
    chooseAll();
    click('Save preference');
    (await vi.waitFor(() => http.expectOne((request) => request.method === 'PUT'))).flush(
      { code: 'student_action_denied', request_id: 'preference-denial' },
      { status: 403, statusText: 'Denied' },
    );
    const identity = await vi.waitFor(() => http.expectOne('/api/v1/me'));
    fixture.detectChanges();
    expect(host(fixture).textContent).toContain('choice has not been changed');
    identity.flush(notificationActorFixture);
    (await vi.waitFor(() => http.expectOne('/api/v1/me/notification-preference'))).flush(
      defaultPreference,
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('preference-denial');
      expect(host(fixture).querySelector('input[value="all_updates"]:checked')).not.toBeNull();
    });
    http.expectNone((request) => request.method === 'PUT');
    click('Read current preference');
    (await vi.waitFor(() => http.expectOne('/api/v1/me/notification-preference'))).flush(
      defaultPreference,
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      const action = Array.from(host(fixture).querySelectorAll('button')).find(
        (item: Readonly<HTMLButtonElement>) =>
          item.textContent.trim() === 'Use current saved preference',
      );
      expect(action?.disabled).toBe(false);
    });
    expect(host(fixture).querySelector('fieldset')?.disabled).toBe(true);
    click('Use current saved preference');
    (await vi.waitFor(() => http.expectOne('/api/v1/me/notification-preference'))).flush(
      defaultPreference,
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).querySelector('fieldset')?.disabled).toBe(false);
      expect(
        host(fixture).querySelector('input[value="messages_and_requests"]:checked'),
      ).not.toBeNull();
    });
  });
  it('retires selected and private mutation state after401 is confirmed as logout', async () => {
    await load();
    chooseAll();
    click('Save preference');
    (await vi.waitFor(() => http.expectOne((request) => request.method === 'PUT'))).flush(
      { code: 'unauthenticated' },
      { status: 401, statusText: 'Unauthorized' },
    );
    (await vi.waitFor(() => http.expectOne('/api/v1/me'))).flush(
      { code: 'unauthenticated' },
      { status: 401, statusText: 'Unauthorized' },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('active, verified');
      expect(
        client.getMutationCache().findAll({ mutationKey: ['notification-preference-save'] }),
      ).toHaveLength(0);
    });
    expect(await fixture.componentInstance.canLeave()).toBe(true);
    http.expectNone('/api/v1/me/notification-preference');
  });
  it('does not abandon a known failed intent when a fresh canonical rebase read fails', async () => {
    await load();
    chooseAll();
    click('Save preference');
    (await vi.waitFor(() => http.expectOne((request) => request.method === 'PUT'))).flush(
      { code: 'invalid_request' },
      { status: 422, statusText: 'Invalid' },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('selection is still here');
    });
    click('Use current saved preference');
    (await vi.waitFor(() => http.expectOne('/api/v1/me/notification-preference'))).flush(
      { code: 'storage_unavailable' },
      { status: 503, statusText: 'Unavailable' },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('could not be loaded');
    });
    click('Try again');
    (await vi.waitFor(() => http.expectOne('/api/v1/me/notification-preference'))).flush(
      defaultPreference,
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).querySelector('input[value="all_updates"]:checked')).not.toBeNull();
      expect(host(fixture).querySelector('fieldset')?.disabled).toBe(true);
    });
    http.expectNone((request) => request.method === 'PUT');
    click('Use current saved preference');
    (await vi.waitFor(() => http.expectOne('/api/v1/me/notification-preference'))).flush(
      defaultPreference,
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).querySelector('fieldset')?.disabled).toBe(false);
    });
  });
  it('aborts a pending canonical adoption on actual replacement and ignores the old owner', async () => {
    await load();
    chooseAll();
    click('Save preference');
    (await vi.waitFor(() => http.expectOne((request) => request.method === 'PUT'))).flush(
      { code: 'notification_preference_version_conflict' },
      { status: 409, statusText: 'Conflict' },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('changed elsewhere');
    });
    click('Use current saved preference');
    const canonical = await vi.waitFor(() => http.expectOne('/api/v1/me/notification-preference'));
    client.setQueryData(['session'], {
      ...notificationActorFixture,
      account_id: '00000000-0000-4000-8000-000000000122',
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(canonical.cancelled).toBe(true);
      expect(host(fixture).textContent).toContain('active, verified');
    });
    expect(await fixture.componentInstance.canLeave()).toBe(true);
    http.expectNone((request) => request.method === 'PUT');
  });
  it('ignores a late committed write after destroy without starting another canonical read', async () => {
    await load();
    chooseAll();
    click('Save preference');
    const pending = await vi.waitFor(() => http.expectOne((request) => request.method === 'PUT'));
    fixture.destroy();
    pending.flush(savedPreference);
    await Promise.resolve();
    await Promise.resolve();
    expect(
      client.getMutationCache().findAll({ mutationKey: ['notification-preference-save'] }),
    ).toHaveLength(0);
    expect(
      client
        .getQueryCache()
        .findAll({ queryKey: ['account', notificationActorFixture.account_id] }),
    ).toHaveLength(0);
    http.expectNone('/api/v1/me/notification-preference');
  });
});
