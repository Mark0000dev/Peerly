import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, signal } from '@angular/core';
import { NgControl } from '@angular/forms';
import { By } from '@angular/platform-browser';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TuiRoot } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../app.config';
import type { Api } from '../../api.generated';
import { conversation, identity, message } from './chats.fixtures';
import { MessageComposer } from './message-composer';
import { jpegBase64 } from '../../../../testing/image-fixture';

@Component({
  selector: 'message-test-host',
  imports: [TuiRoot, MessageComposer],
  template:
    '<tui-root><app-chat-message-composer [actor]="actor()" [conversationId]="conversation()" [canSend]="canSend()" /></tui-root>',
})
class MessageHost {
  public readonly actor = signal(identity);
  public readonly conversation = signal(conversation.conversation_id);
  public readonly canSend = signal(true);
}
type Submitted = Api['schemas']['SendMessageBody'] & Readonly<{ readonly text: string }>;
function submitted(value: unknown): value is Submitted {
  return (
    typeof value === 'object' &&
    value !== null &&
    'client_message_id' in value &&
    typeof value.client_message_id === 'string' &&
    'text' in value &&
    typeof value.text === 'string'
  );
}
describe('C02 explicit text message intent lifecycle', () => {
  let fixture: ComponentFixture<MessageHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  const url = `/api/v1/conversations/${conversation.conversation_id}/messages`;
  beforeEach(async () => {
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
    fixture = TestBed.createComponent(MessageHost);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    (
      await vi.waitFor(() =>
        backend.expectOne(
          `/api/v1/conversations/${conversation.conversation_id}/image-preparations`,
        ),
      )
    ).flush({ preparations: [] });
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    vi.restoreAllMocks();
    TestBed.resetTestingModule();
  });
  function host(): HTMLElement {
    const element: unknown = fixture.nativeElement;
    if (!(element instanceof HTMLElement)) throw new Error('Missing host');
    return element;
  }
  function text(): HTMLTextAreaElement {
    const element = host().querySelector('textarea');
    if (element === null) throw new Error('Missing field');
    return element;
  }
  function fill(value: string): void {
    text().setRangeText(value, 0, text().value.length);
    text().dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }
  function click(name: string): void {
    const button = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) =>
        (item.getAttribute('aria-label') ?? item.textContent.trim()) === name,
    );
    if (button === undefined) throw new Error(`Missing ${name}`);
    button.click();
    fixture.detectChanges();
  }
  async function shown(value: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain(value);
    });
  }
  async function enabled(name: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      const button = Array.from(host().querySelectorAll('button')).find(
        (item: Readonly<HTMLButtonElement>) =>
          (item.getAttribute('aria-label') ?? item.textContent.trim()) === name,
      );
      expect(button?.disabled).toBe(false);
    });
  }
  async function write() {
    return vi.waitFor(() => backend.expectOne(url));
  }
  async function unknown() {
    fill(' Keep my raw text.\n ');
    click('Send message');
    const request = await write();
    const body: unknown = request.request.body;
    if (!submitted(body)) throw new Error('Invalid submitted intent');
    const key = request.request.headers.get('Idempotency-Key');
    request.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('We couldn’t confirm');
    return { body, key };
  }
  it('does not treat leaving a pristine empty draft as an attempted send', async () => {
    text().focus();
    text().blur();
    const control = fixture.debugElement.query(By.css('textarea')).injector.get(NgControl);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(control.touched).toBe(true);
    });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(host().textContent).not.toContain('Enter a message.');
    expect(control.valid).toBe(true);
    click('Send message');
    await shown('Enter a message.');
    backend.expectNone(url);
  });
  it('shows invalid edited content before blur without posting or waiting for a pointer action', async () => {
    text().focus();
    fill('x'.repeat(2001));
    await shown('Use at most 2000 characters.');
    const control = fixture.debugElement.query(By.css('textarea')).injector.get(NgControl);
    expect(control.touched).toBe(false);
    text().blur();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(host().textContent).toContain('Use at most 2000 characters.');
    backend.expectNone(url);
  });
  it('never posts on input; validates without UTF16 truncation then confirms raw intent', async () => {
    click('Send message');
    await shown('Enter a message.');
    await vi.waitFor(() => {
      expect(document.activeElement).toBe(text());
    });
    backend.expectNone(url);
    fill('😀'.repeat(2001));
    click('Send message');
    await shown('Use at most 2000');
    backend.expectNone(url);
    fill(' hello\n\tworld ');
    backend.expectNone(url);
    click('Send message');
    const request = await write();
    const body: unknown = request.request.body;
    if (!submitted(body)) throw new Error('Invalid body');
    expect(body.text).toBe(' hello\n\tworld ');
    expect(request.request.headers.get('X-CSRF-Token')).toBe(identity.csrf_token);
    expect(text().readOnly).toBe(true);
    click('Send message');
    backend.expectNone(url);
    request.flush({
      operation_id: 'op',
      conversation_id: conversation.conversation_id,
      client_message_id: body.client_message_id,
      message: {
        ...message,
        author_id: identity.account_id,
        client_message_id: body.client_message_id,
        text: body.text,
      },
    });
    await shown('Message stored.');
    expect(host().textContent).not.toContain('Enter a message.');
    expect(text().value).toBe('');
  });
  it('keeps unknown text/key/id frozen and manually replays with current CSRF', async () => {
    const initial = await unknown();
    expect(text().readOnly).toBe(true);
    expect(text().value).toBe(initial.body.text);
    client.setQueryData(['session'], { ...identity, csrf_token: 'new-csrf' });
    fixture.detectChanges();
    click('Retry same message');
    const request = await write();
    expect(request.request.body).toEqual(initial.body);
    expect(request.request.headers.get('Idempotency-Key')).toBe(initial.key);
    expect(request.request.headers.get('X-CSRF-Token')).toBe('new-csrf');
    request.flush({
      operation_id: 'op',
      conversation_id: conversation.conversation_id,
      client_message_id: initial.body.client_message_id,
      message: {
        ...message,
        client_message_id: initial.body.client_message_id,
        text: initial.body.text,
      },
    });
    await shown('Message stored.');
    expect(text().value).toBe('');
  });
  it('treats unobserved as uncertain and confirmed lookup as stored without resend', async () => {
    const initial = await unknown();
    const lookup = `/api/v1/conversations/${conversation.conversation_id}/message-operations/${initial.body.client_message_id}`;
    click('Check message status');
    const first = await vi.waitFor(() => backend.expectOne(lookup));
    first.flush({
      conversation_id: conversation.conversation_id,
      client_message_id: initial.body.client_message_id,
      outcome: 'unobserved',
    });
    await shown('Not observed yet');
    expect(text().readOnly).toBe(true);
    click('Check message status');
    const second = await vi.waitFor(() => backend.expectOne(lookup));
    second.flush({
      operation_id: 'op',
      conversation_id: conversation.conversation_id,
      client_message_id: initial.body.client_message_id,
      message: {
        ...message,
        client_message_id: initial.body.client_message_id,
        text: initial.body.text,
      },
    });
    await shown('Message stored.');
    expect(text().value).toBe('');
    backend.expectNone(url);
  });
  for (const wins of ['cancel', 'send'] as const)
    it(`resolves cancellation race when ${wins} wins, no invented deletion`, async () => {
      const initial = await unknown();
      click('Cancel message intent');
      const request = await vi.waitFor(() =>
        backend.expectOne(
          `/api/v1/conversations/${conversation.conversation_id}/message-operations/${initial.body.client_message_id}/cancel`,
        ),
      );
      expect(request.request.body).toBeNull();
      const common = {
        operation_id: 'op',
        conversation_id: conversation.conversation_id,
        client_message_id: initial.body.client_message_id,
      };
      request.flush(
        wins === 'cancel'
          ? { ...common, cancelled_at: message.sent_at }
          : {
              ...common,
              message: {
                ...message,
                client_message_id: initial.body.client_message_id,
                text: initial.body.text,
              },
            },
      );
      await shown(wins === 'cancel' ? 'Message intent cancelled.' : 'Message stored.');
      expect(text().value).toBe(wins === 'cancel' ? initial.body.text : '');
      fill('Next intent');
      click('Send message');
      const next = await write();
      const body: unknown = next.request.body;
      if (!submitted(body)) throw new Error('Invalid body');
      expect(body.client_message_id).not.toBe(initial.body.client_message_id);
      next.flush({}, { status: 422, statusText: 'Validation' });
      await shown('Review your text.');
    });
  it('clears unsent and unknown drafts on selection/account replacement and destroys sensitive mutations', async () => {
    fill('private unsent');
    fixture.componentInstance.conversation.set('new-thread');
    fixture.detectChanges();
    (
      await vi.waitFor(() =>
        backend.expectOne('/api/v1/conversations/new-thread/image-preparations'),
      )
    ).flush({ preparations: [] });
    expect(text().value).toBe('');
    fixture.componentInstance.conversation.set(conversation.conversation_id);
    fixture.detectChanges();
    await unknown();
    client.setQueryData(['session'], null);
    await shown('Message');
    expect(text().value).toBe('');
    expect(client.getMutationCache().getAll()).toHaveLength(0);
    fixture.componentInstance.actor.set({ ...identity, account_id: 'replacement' });
    fixture.detectChanges();
    expect(text().readOnly).toBe(true);
    backend.expectNone(url);
  });
  it('retains the same draft while temporarily denied and never sends on a capability change', () => {
    fill('Retained');
    fixture.componentInstance.canSend.set(false);
    fixture.detectChanges();
    click('Send message');
    backend.expectNone(url);
    expect(text().value).toBe('Retained');
    fixture.componentInstance.canSend.set(true);
    fixture.detectChanges();
    expect(text().value).toBe('Retained');
    backend.expectNone(url);
  });
  for (const status of [403, 404, 422, 429])
    it(`retains rejected text after ${status.toString()} and reuses unchanged intent explicitly`, async () => {
      fill('Rejected text');
      click('Send message');
      const first = await write();
      const body: unknown = first.request.body;
      const key = first.request.headers.get('Idempotency-Key');
      first.flush({}, { status, statusText: 'Rejected' });
      await shown(
        status === 403 || status === 404
          ? 'Sending is unavailable.'
          : status === 422
            ? 'Review your text.'
            : 'We couldn’t complete this action.',
      );
      expect(text().value).toBe('Rejected text');
      expect(text().readOnly).toBe(false);
      click('Send message');
      const retry = await write();
      expect(retry.request.body).toEqual(body);
      expect(retry.request.headers.get('Idempotency-Key')).toBe(key);
      retry.flush({}, { status: 422, statusText: 'Rejected' });
      await shown('Review your text.');
      fill('Edited intent');
      click('Send message');
      const edited = await write();
      expect(edited.request.body).not.toEqual(body);
      expect(edited.request.headers.get('Idempotency-Key')).not.toBe(key);
      edited.flush({}, { status: 422, statusText: 'Rejected' });
      await shown('Review your text.');
    });
  it('clears current401 draft/private mutations without authorizing a replacement account', async () => {
    fill('Private text');
    click('Send message');
    const first = await write();
    first.flush({}, { status: 401, statusText: 'Unauthorized' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(client.getQueryData(['session'])).toBeNull();
      expect(text().value).toBe('');
    });
    expect(client.getMutationCache().getAll()).toHaveLength(0);
    backend.expectNone(url);
  });
  it('ignores a late old-thread success after a selection change without clearing the new draft', async () => {
    fill('Old draft');
    click('Send message');
    const first = await write();
    const body: unknown = first.request.body;
    if (!submitted(body)) throw new Error('Missing intent');
    fixture.componentInstance.conversation.set('new-thread');
    fixture.detectChanges();
    (
      await vi.waitFor(() =>
        backend.expectOne('/api/v1/conversations/new-thread/image-preparations'),
      )
    ).flush({ preparations: [] });
    fill('New draft');
    first.flush({
      operation_id: 'op',
      conversation_id: conversation.conversation_id,
      client_message_id: body.client_message_id,
      message: { ...message, client_message_id: body.client_message_id, text: body.text },
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(text().value).toBe('New draft');
    });
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });
  it('manually retries an uncertain cancellation with its same key and resolves terminal cancellation', async () => {
    const initial = await unknown();
    const cancelUrl = `/api/v1/conversations/${conversation.conversation_id}/message-operations/${initial.body.client_message_id}/cancel`;
    click('Cancel message intent');
    const first = await vi.waitFor(() => backend.expectOne(cancelUrl));
    const key = first.request.headers.get('Idempotency-Key');
    first.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('We couldn’t confirm');
    await enabled('Cancel message intent');
    click('Cancel message intent');
    const retry = await vi.waitFor(() => backend.expectOne(cancelUrl));
    expect(retry.request.headers.get('Idempotency-Key')).toBe(key);
    retry.flush({
      operation_id: 'op',
      conversation_id: conversation.conversation_id,
      client_message_id: initial.body.client_message_id,
      cancelled_at: message.sent_at,
    });
    await shown('Message intent cancelled.');
    expect(text().value).toBe(initial.body.text);
  });
  it('keeps unknown intent after lookup failure and clears it only on current authentication failure', async () => {
    const initial = await unknown();
    const lookupUrl = `/api/v1/conversations/${conversation.conversation_id}/message-operations/${initial.body.client_message_id}`;
    click('Check message status');
    const first = await vi.waitFor(() => backend.expectOne(lookupUrl));
    first.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('We couldn’t confirm');
    expect(text().value).toBe(initial.body.text);
    await enabled('Check message status');
    click('Check message status');
    const second = await vi.waitFor(() => backend.expectOne(lookupUrl));
    second.flush({}, { status: 401, statusText: 'Unauthorized' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(client.getQueryData(['session'])).toBeNull();
      expect(text().value).toBe('');
    });
  });
  it('cancels a scheduled command at the current-session boundary before private transport starts', async () => {
    fill('Do not send under the next session');
    click('Send message');
    client.setQueryData(['session'], null);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(text().value).toBe('');
    });
    backend.expectNone(url);
  });
  it('clears a confirmed original draft during same-actor revalidation without sending twice', async () => {
    fill('One intent only');
    click('Send message');
    const write = await vi.waitFor(() => backend.expectOne(url));
    const body: unknown = write.request.body;
    if (!submitted(body)) throw new Error('Missing send intent');
    let resume: (() => void) | undefined;
    const waiting = new Promise<typeof identity>((resolve) => {
      resume = () => {
        resolve(identity);
      };
    });
    const release = resume;
    if (release === undefined) throw new Error('Missing session release');
    const refreshing = client.query({
      queryKey: ['session'],
      queryFn: () => waiting,
      staleTime: 0,
    });
    fixture.detectChanges();
    expect(text().readOnly).toBe(true);
    try {
      write.flush({
        operation_id: 'op',
        conversation_id: conversation.conversation_id,
        client_message_id: body.client_message_id,
        message: {
          ...message,
          author_id: identity.account_id,
          client_message_id: body.client_message_id,
          text: body.text,
        },
      });
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(text().value).toBe('');
      });
      expect(text().readOnly).toBe(true);
      backend.expectNone(url);
    } finally {
      release();
      await refreshing;
    }
    await shown('Message stored.');
    backend.expectNone(url);
  });
  it('never downgrades a selected image to text after same-actor session revalidation or an uncertain image start', async () => {
    fill('Keep this caption attached to the selected image');
    const picker = host().querySelector('input[type=file]');
    if (!(picker instanceof HTMLInputElement)) throw new Error('Missing actual attachment control');
    const source = Uint8Array.from(atob(jpegBase64), (character) => character.charCodeAt(0));
    const transfer = new DataTransfer();
    transfer.items.add(new File([source], 'controlled.jpg', { type: 'image/jpeg' }));
    Reflect.set(picker, 'files', transfer.files);
    picker.dispatchEvent(new Event('change', { bubbles: true }));
    fixture.detectChanges();
    let release: (() => void) | undefined;
    const waiting = new Promise<typeof identity>((resolve) => {
      release = () => {
        resolve(identity);
      };
    });
    const resume = release;
    if (resume === undefined) throw new Error('Missing session response release');
    const refreshing = client.query({
      queryKey: ['session'],
      queryFn: () => waiting,
      staleTime: 0,
    });
    try {
      fixture.detectChanges();
      expect(text().readOnly).toBe(true);
      click('Send message');
      backend.expectNone((request) => request.method === 'POST');
    } finally {
      resume();
      await refreshing;
    }
    const preparations = `/api/v1/conversations/${conversation.conversation_id}/image-preparations`;
    (await vi.waitFor(() => backend.expectOne({ url: preparations, method: 'GET' }))).flush({
      preparations: [],
    });
    fixture.detectChanges();
    expect(text().readOnly).toBe(false);
    click('Send message');
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: preparations, method: 'POST' }),
    );
    expect(request.request.body).toMatchObject({
      content_type: 'image/jpeg',
      size: source.byteLength,
    });
    backend.expectNone(url);
    request.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Sending stopped.');
    expect(text().value).toBe('Keep this caption attached to the selected image');
    expect(text().readOnly).toBe(true);
    click('Send message');
    backend.expectNone((pending) => pending.method === 'POST');
  });
  it('retires the caption for a confirmed image receipt during same-actor revalidation without sending it again', async () => {
    const base = `/api/v1/conversations/${conversation.conversation_id}`;
    const bytes = Uint8Array.from(atob(jpegBase64), (character) => character.charCodeAt(0));
    const preparation: Api['schemas']['ImagePreparationResponse'] = {
      image_id: '00000000-0000-4000-8000-000000000040',
      client_message_id: message.client_message_id,
      conversation_id: conversation.conversation_id,
      state: 'ready',
      source_state: 'ready',
      source_version: 1,
      expected_source: {
        content_type: 'image/jpeg',
        size: bytes.byteLength,
        sha256: 'a'.repeat(64),
      },
      display: { width: 2, height: 2, size: bytes.byteLength },
      failure: null,
      message_outcome: null,
      created_at: '2026-11-08T09:00:00Z',
      updated_at: '2026-11-08T09:00:00Z',
      upload_expires_at: '2026-11-08T10:00:00Z',
      processing_expires_at: '2026-11-08T10:00:00Z',
    };
    void client.invalidateQueries({
      queryKey: [
        'account',
        identity.account_id,
        'chats',
        conversation.conversation_id,
        'image-preparations',
      ],
    });
    (await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`))).flush({
      preparations: [preparation],
    });
    await shown('Your recent image preparations');
    host().querySelector('summary')?.click();
    click('Select preparation');
    (
      await vi.waitFor(() =>
        backend.expectOne(`${base}/image-preparations/${preparation.image_id}/display`),
      )
    ).flush(new Blob([bytes], { type: 'image/jpeg' }), {
      headers: { 'Content-Type': 'image/jpeg' },
    });
    fill('An image with its original caption');
    click('Send message');
    (
      await vi.waitFor(() =>
        backend.expectOne(`${base}/image-preparations/${preparation.image_id}`),
      )
    ).flush(preparation);
    // The pipeline independently rechecks canonical readiness after resolving
    // the recovered source; both real reads need a boundary response.
    (
      await vi.waitFor(() =>
        backend.expectOne(`${base}/image-preparations/${preparation.image_id}`),
      )
    ).flush(preparation);
    (
      await vi.waitFor(() =>
        backend.expectOne(`${base}/message-operations/${preparation.client_message_id}`),
      )
    ).flush({
      outcome: 'unobserved',
      conversation_id: conversation.conversation_id,
      client_message_id: preparation.client_message_id,
    });
    const request = await write();
    expect(request.request.body).toMatchObject({
      image_id: preparation.image_id,
      text: 'An image with its original caption',
    });
    let release: (() => void) | undefined;
    const waiting = new Promise<typeof identity>((resolve) => {
      release = () => {
        resolve(identity);
      };
    });
    const resume = release;
    if (resume === undefined) throw new Error('Missing session response release');
    const refreshing = client.query({
      queryKey: ['session'],
      queryFn: () => waiting,
      staleTime: 0,
    });
    try {
      request.flush({
        operation_id: 'confirmed-image',
        conversation_id: conversation.conversation_id,
        client_message_id: preparation.client_message_id,
        message: {
          ...message,
          author_id: identity.account_id,
          client_message_id: preparation.client_message_id,
          image_id: preparation.image_id,
          text: 'An image with its original caption',
        },
      });
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(text().value).toBe('');
      });
      expect(text().readOnly).toBe(true);
      backend.expectNone(url);
    } finally {
      resume();
      await refreshing;
    }
    (await vi.waitFor(() => backend.expectOne(`${base}/image-preparations`))).flush({
      preparations: [],
    });
    fixture.detectChanges();
    click('Send message');
    backend.expectNone((pending) => pending.method === 'POST');
  });
  it('does not silently send text when an attempted attachment is invalid; only explicit removal restores text-only Send', async () => {
    fill('Keep this caption with my intended attachment');
    const picker = host().querySelector('input[type=file]');
    if (!(picker instanceof HTMLInputElement)) throw new Error('Missing actual attachment control');
    const transfer = new DataTransfer();
    transfer.items.add(new File(['not an image'], 'invalid.pdf', { type: 'application/pdf' }));
    Reflect.set(picker, 'files', transfer.files);
    picker.dispatchEvent(new Event('change', { bubbles: true }));
    fixture.detectChanges();
    click('Send message');
    await shown('Choose a JPEG or PNG image.');
    expect(text().value).toBe('Keep this caption with my intended attachment');
    expect(text().readOnly).toBe(false);
    backend.expectNone((request) => request.method === 'POST');
    const remove = Array.from(host().querySelectorAll('button')).find(
      (button: Readonly<HTMLButtonElement>) => button.textContent.trim() === 'Remove image',
    );
    if (remove === undefined)
      throw new Error('Invalid attempted attachment must be explicitly removable');
    remove.click();
    fixture.detectChanges();
    click('Send message');
    const request = await write();
    const body: unknown = request.request.body;
    if (!submitted(body)) throw new Error('Missing explicit text-only intent');
    expect(body.text).toBe('Keep this caption with my intended attachment');
    expect(body.image_id).toBeUndefined();
    request.flush({
      operation_id: 'op',
      conversation_id: conversation.conversation_id,
      client_message_id: body.client_message_id,
      message: { ...message, client_message_id: body.client_message_id, text: body.text },
    });
    await shown('Message stored.');
  });
  it('shows the committed text receipt while an unrelated image-preparations refresh is pending or fails', async () => {
    fill('Confirmed independently of image recovery');
    click('Send message');
    const request = await write();
    const body: unknown = request.request.body;
    if (!submitted(body)) throw new Error('Missing text intent');
    request.flush({
      operation_id: 'op',
      conversation_id: conversation.conversation_id,
      client_message_id: body.client_message_id,
      message: { ...message, client_message_id: body.client_message_id, text: body.text },
    });
    const refresh = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/conversations/${conversation.conversation_id}/image-preparations`),
    );
    await shown('Message stored.');
    expect(text().value).toBe('');
    expect(text().readOnly).toBe(false);
    refresh.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Message stored.');
    backend.expectNone((request) => request.method === 'POST');
  });
  it('keeps new sends blocked after an idle failed session check with old cached identity', async () => {
    fill('Retained while account check fails');
    await expect(
      client.query({
        queryKey: ['session'],
        queryFn: () => Promise.reject(new Error('Controlled identity failure')),
        staleTime: 0,
      }),
    ).rejects.toThrow('Controlled identity failure');
    fixture.detectChanges();
    expect(client.getQueryData(['session'])).toEqual(identity);
    expect(text().readOnly).toBe(true);
    click('Send message');
    backend.expectNone(url);
  });
});
