import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { TestRequest } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { TuiRoot } from '@taiga-ui/core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../app.config';
import { OperatorConversation } from './operator-conversation';
import { operatorIdentity } from './operator.fixtures';
import { conversationId, otherConversationId, messagePage } from './operator-conversation.fixtures';

@Component({
  selector: 'operator-conversation-host',
  imports: [TuiRoot, OperatorConversation],
  template: '<tui-root><app-operator-conversation /></tui-root>',
})
class Host {}
@Component({ template: '' })
class Empty {}

describe('M05 retained conversation ownership', () => {
  let fixture: ComponentFixture<Host>;
  let backend: HttpTestingController;
  let client: QueryClient;
  let router: Router;
  beforeEach(async () => {
    TestBed.resetTestingModule();
    client = new QueryClient({
      defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
    });
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideRouter([{ path: 'operator/conversations', component: Empty }]),
        provideHttpClientTesting(),
        provideTanStackQuery(client),
      ],
    });
    router = TestBed.inject(Router);
    await router.navigateByUrl('/operator/conversations');
    fixture = TestBed.createComponent(Host);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
    vi.restoreAllMocks();
  });
  function host(): HTMLElement {
    const value: unknown = fixture.nativeElement;
    if (!(value instanceof HTMLElement)) throw new Error('Missing report host');
    return value;
  }
  async function shown(text: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain(text);
    });
  }
  function click(label: string): void {
    const button = Array.from(host().querySelectorAll('button')).find(
      (value: Readonly<HTMLButtonElement>) =>
        value.getAttribute('aria-label') === label || value.textContent.trim() === label,
    );
    if (button === undefined) throw new Error(`Missing ${label}`);
    button.click();
    fixture.detectChanges();
  }
  function fill(id: string, value: string): void {
    const input = host().querySelector(`#${id}`);
    if (!(input instanceof HTMLInputElement)) throw new Error(`Missing ${id}`);
    input.setRangeText(value, 0, input.value.length);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
  }
  async function navigate(params: Readonly<Record<string, string>>): Promise<void> {
    await router.navigateByUrl(`/operator/conversations?${new URLSearchParams(params).toString()}`);
    fixture.detectChanges();
  }
  async function request(path: string): Promise<TestRequest> {
    let found: TestRequest | undefined;
    await vi.waitFor(() => {
      fixture.detectChanges();
      found = backend.expectOne((value) => value.url.startsWith(`/api/v1/operator/${path}`));
    });
    if (found === undefined) throw new Error(`Missing request ${path}`);
    return found;
  }
  async function login(params: Readonly<Record<string, string>> = {}): Promise<void> {
    await navigate(params);
    backend.expectOne('/api/v1/me').flush(operatorIdentity);
    await shown('Open retained conversation');
  }
  const path = `conversations/${conversationId}/messages`;
  it('does not query without explicit valid selection; form commits URL and literal data safely', async () => {
    await login();
    backend.expectNone((r) => r.url.includes('/operator/conversations/'));
    fill('conversation-id', 'bad');
    click('Open retained conversation');
    await shown('Conversation ID must be a UUID.');
    fill('conversation-id', conversationId);
    click('Open retained conversation');
    (await request(path)).flush(messagePage);
    await shown('Stored literal');
    expect(router.url).toContain(`conversation=${conversationId}`);
    expect(host().querySelector('article script')).toBeNull();
    expect(host().textContent).toContain(messagePage.request_id);
    expect(host().querySelector('textarea')).toBeNull();
  });
  it('rejects invalid route before reads and resets invalid cursor', async () => {
    await login({ conversation: 'bad' });
    await shown('Conversation ID must be a UUID.');
    backend.expectNone((r) => r.url.includes('/operator/conversations/'));
    await navigate({ conversation: conversationId });
    (await request(path)).flush(messagePage);
    await shown('Stored literal');
    await navigate({ conversation: conversationId, cursor: '' });
    await shown('The page cursor is invalid');
    click('First page');
    (await request(path)).flush({ ...messagePage, messages: [], next_cursor: null });
    await shown('No retained messages');
  });
  it('keeps one source page, older cursor and first page refresh in URL', async () => {
    await login({ conversation: conversationId });
    (await request(path)).flush(messagePage);
    await shown('Stored literal');
    click('Older message page');
    const older = await request(path);
    expect(older.request.urlWithParams).toContain('cursor=signed-older-page');
    older.flush({ ...messagePage, messages: [], next_cursor: null });
    await shown('No retained messages');
    expect(host().textContent).not.toContain('Stored literal');
    click('First page');
    (await request(path)).flush({ ...messagePage, next_cursor: null });
    await shown('Stored literal');
    click('Refresh');
    (await request(path)).flush(messagePage);
    await shown('Stored literal');
  });
  it('keeps local503 and404 retryable and offers422 first-page recovery', async () => {
    await login({ conversation: conversationId, cursor: 'old' });
    (await request(path)).flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Messages could not be loaded');
    click('Retry');
    (await request(path)).flush({}, { status: 404, statusText: 'Missing' });
    await shown('This retained conversation is unavailable');
    click('Retry');
    (await request(path)).flush({}, { status: 422, statusText: 'Invalid' });
    await shown('This page cursor could not be used');
    click('First page');
    (await request(path)).flush(messagePage);
    await shown('Stored literal');
    expect(router.url).not.toContain('cursor=');
  });
  it('retires old messages on selection switch and removes incompatible cursor before new read', async () => {
    await login({ conversation: conversationId, cursor: 'old' });
    const late = await request(path);
    await navigate({ conversation: otherConversationId, cursor: 'old' });
    const fresh = await request(`conversations/${otherConversationId}/messages`);
    expect(fresh.request.urlWithParams).not.toContain('cursor=');
    expect(late.cancelled).toBe(true);
    fresh.flush({
      ...messagePage,
      conversation_id: otherConversationId,
      messages: [],
      next_cursor: null,
    });
    await shown('No retained messages');
    expect(router.url).not.toContain('cursor=');
  });
  it('denies on403 and restores only after actual session recheck', async () => {
    await login({ conversation: conversationId });
    (await request(path)).flush({}, { status: 403, statusText: 'Forbidden' });
    await shown('Operator access denied');
    expect(host().textContent).not.toContain('Conversation record');
    click('Check operator access again');
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush(operatorIdentity);
    });
    (await request(path)).flush(messagePage);
    await shown('Stored literal');
  });
  it('rechecks401 canonical session and never reveals old private records', async () => {
    await login({ conversation: conversationId });
    (await request(path)).flush({}, { status: 401, statusText: 'Unauthorized' });
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    });
    await shown('Sign in with your operator');
    expect(host().textContent).not.toContain('Stored literal');
  });
  it('keeps failed session retry and guest flow separate from private reads', async () => {
    backend.expectOne('/api/v1/me').flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Your session could not be checked');
    click('Retry');
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    });
    await shown('Sign in with your operator');
    backend.expectNone((r) => r.url.includes('/operator/conversations/'));
  });
  it('rejects cross-conversation response rather than silently adopting foreign messages', async () => {
    await login({ conversation: conversationId });
    (await request(path)).flush({
      ...messagePage,
      conversation_id: otherConversationId,
      messages: [],
    });
    await shown('Messages could not be loaded');
    expect(host().textContent).not.toContain('Conversation record');
  });
  it('resets actor-bound cursor before replacement request and retires previous private cache', async () => {
    await login({ conversation: conversationId, cursor: 'old-actor' });
    (await request(path)).flush(messagePage);
    await shown('Stored literal');
    await client.invalidateQueries({ queryKey: ['session'], refetchType: 'none' });
    const pending = client.refetchQueries({ queryKey: ['session'] });
    await vi.waitFor(() => {
      backend
        .expectOne('/api/v1/me')
        .flush({ ...operatorIdentity, account_id: otherConversationId });
    });
    await pending;
    const next = await request(path);
    expect(next.request.urlWithParams).not.toContain('cursor=');
    next.flush({ ...messagePage, messages: [], next_cursor: null });
    await shown('No retained messages');
    expect(host().textContent).not.toContain('Stored literal');
    expect(router.url).not.toContain('cursor=');
  });
});
