import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import {
  MutationObserver,
  provideTanStackQuery,
  QueryClient,
} from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../app.config';
import { identity, message } from '../chats.fixtures';
import { ImageReport } from './image-report';

const imageId = '00000000-0000-4000-8000-000000000040';
const contextId = '00000000-0000-4000-8000-000000000041';
const imageMessage = { ...message, image_id: imageId };
const contextUrl = `/api/v1/conversations/${message.conversation_id}/messages/${message.message_id}/report-contexts`;
const context = {
  id: contextId,
  conversation_id: message.conversation_id,
  message_id: message.message_id,
  image_id: imageId,
  issued_at: '2026-11-08T09:00:00Z',
  kind: 'message_image',
} as const;
describe('C03 peer confirmed image report', () => {
  let fixture: ComponentFixture<ImageReport>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    client = new QueryClient();
    client.setQueryData(['session'], identity);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    backend = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ImageReport);
    fixture.componentRef.setInput('actorId', identity.account_id);
    fixture.componentRef.setInput('message', imageMessage);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
  });
  function host(): HTMLElement {
    const node: unknown = fixture.nativeElement;
    if (!(node instanceof HTMLElement)) throw new Error('Missing report host');
    return node;
  }
  function click(label: string): void {
    const node = Array.from(host().querySelectorAll('button')).find(
      (button: Readonly<HTMLButtonElement>) => button.textContent.trim() === label,
    );
    if (node === undefined) throw new Error(`Missing ${label}`);
    node.click();
    fixture.detectChanges();
  }
  async function opened(): Promise<void> {
    click('Report image');
    const request = await vi.waitFor(() => backend.expectOne(contextUrl));
    expect(request.request.body).toBeNull();
    expect(request.request.headers.get('x-csrf-token')).toBe(identity.csrf_token);
    request.flush(context);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('form')).not.toBeNull();
    });
  }
  function reason(value: 'spam' | 'other'): void {
    const label = Array.from(host().querySelectorAll('label')).find(
      (item: Readonly<HTMLLabelElement>) =>
        item.textContent.trim() === (value === 'other' ? 'Other' : 'Spam'),
    );
    const control = label?.querySelector('input');
    if (!(control instanceof HTMLInputElement)) throw new Error('Missing reason');
    control.click();
    fixture.detectChanges();
  }
  function explain(value: string): void {
    const control = host().querySelector('textarea');
    if (!(control instanceof HTMLTextAreaElement)) throw new Error('Missing explanation');
    Reflect.set(control, 'value', value);
    control.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
  }
  it('does not request context until explicit action and disallows own images and text', () => {
    backend.expectNone(contextUrl);
    fixture.componentRef.setInput('message', { ...imageMessage, author_id: identity.account_id });
    fixture.detectChanges();
    expect(host().querySelector('button')).toBeNull();
    fixture.componentRef.setInput('message', message);
    fixture.detectChanges();
    expect(host().querySelector('button')).toBeNull();
    backend.expectNone(contextUrl);
  });
  it('validates category and required Other explanation before submitting the actual kind/context', async () => {
    await opened();
    click('Submit report');
    expect(host().textContent).toContain('Choose a reason');
    backend.expectNone('/api/v1/reports');
    reason('other');
    click('Submit report');
    backend.expectNone('/api/v1/reports');
    explain('Private explanation');
    click('Submit report');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/reports'));
    expect(request.request.body).toEqual({
      kind: 'message_image',
      context_id: contextId,
      category: 'other',
      comment: 'Private explanation',
    });
    expect(request.request.headers.get('Idempotency-Key')).toBeTruthy();
    request.flush({
      id: crypto.randomUUID(),
      context_id: contextId,
      kind: 'message_image',
      submitted_at: context.issued_at,
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('Report submitted');
    });
    click('Close report');
    expect(host().querySelector('form')).toBeNull();
  });
  it('retries the identical uncertain report without accepting edits or replacing its key', async () => {
    await opened();
    reason('spam');
    click('Submit report');
    const first = await vi.waitFor(() => backend.expectOne('/api/v1/reports'));
    first.flush({}, { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('result is unknown');
    });
    expect(host().querySelector('fieldset')?.disabled).toBe(true);
    click('Retry report');
    const next = await vi.waitFor(() => backend.expectOne('/api/v1/reports'));
    expect(next.request.body).toEqual(first.request.body);
    expect(next.request.headers.get('Idempotency-Key')).toBe(
      first.request.headers.get('Idempotency-Key'),
    );
    next.flush({ id: crypto.randomUUID(), context_id: contextId, submitted_at: context.issued_at });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('Report submitted');
    });
  });
  it('rejects a foreign context and allows explicit retry of context acquisition', async () => {
    click('Report image');
    (await vi.waitFor(() => backend.expectOne(contextUrl))).flush({
      ...context,
      image_id: crypto.randomUUID(),
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('couldn’t be opened');
    });
    click('Retry opening report');
    (await vi.waitFor(() => backend.expectOne(contextUrl))).flush(context);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('form')).not.toBeNull();
    });
  });
  it('preserves a report draft across an unrelated redraw of the same confirmed message', async () => {
    await opened();
    reason('other');
    explain('Keep this draft');
    fixture.componentRef.setInput('message', { ...imageMessage });
    fixture.detectChanges();
    expect(host().querySelector('textarea')?.value).toBe('Keep this draft');
    backend.expectNone(contextUrl);
  });
  it('retires late context responses on message replacement and clears private draft on session loss', async () => {
    click('Report image');
    const pending = await vi.waitFor(() => backend.expectOne(contextUrl));
    fixture.componentRef.setInput('message', { ...imageMessage, message_id: crypto.randomUUID() });
    fixture.detectChanges();
    pending.flush(context);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('form')).toBeNull();
    });
    client.setQueryData(['session'], null);
    fixture.detectChanges();
    expect(host().querySelector('button')).toBeNull();
  });
  it('emits the current canonical authentication failure without inventing a profile grant', async () => {
    const failure = vi.fn();
    fixture.componentInstance.sessionFailure.subscribe(failure);
    click('Report image');
    (await vi.waitFor(() => backend.expectOne(contextUrl))).flush(
      {},
      { status: 403, statusText: 'Forbidden' },
    );
    await vi.waitFor(() => {
      expect(failure).toHaveBeenCalledTimes(1);
    });
    backend.expectNone((request) => request.url.includes('/people/'));
  });
  it('rejects overlong private explanation and preserves unrelated mutation state during private draft retirement', async () => {
    const unrelated = new MutationObserver(client, {
      mutationKey: ['unrelated-workflow'],
      mutationFn: () => Promise.resolve('retained'),
    });
    await unrelated.mutate(undefined);
    await opened();
    reason('other');
    explain('x'.repeat(1001));
    click('Submit report');
    backend.expectNone('/api/v1/reports');
    fixture.destroy();
    expect(client.getMutationCache().findAll({ mutationKey: ['unrelated-workflow'] })).toHaveLength(
      1,
    );
    unrelated.reset();
  });
  it('distinguishes a known rejected report from an uncertain result and requests a fresh context only explicitly', async () => {
    await opened();
    reason('spam');
    click('Submit report');
    (await vi.waitFor(() => backend.expectOne('/api/v1/reports'))).flush(
      {},
      { status: 422, statusText: 'Unprocessable Content' },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('wasn’t accepted');
    });
    expect(host().textContent).not.toContain('result is unknown');
    backend.expectNone(contextUrl);
    click('Start a new report');
    (await vi.waitFor(() => backend.expectOne(contextUrl))).flush({
      ...context,
      id: crypto.randomUUID(),
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('textarea')?.value).toBe('');
    });
    click('Close report');
    expect(host().querySelector('form')).toBeNull();
  });
  it('deduplicates rapid native opening and submission events before the next render', async () => {
    const trigger = host().querySelector('button');
    if (trigger === null) throw new Error('Missing report trigger');
    trigger.click();
    trigger.click();
    (await vi.waitFor(() => backend.expectOne(contextUrl))).flush(context);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('form')).not.toBeNull();
    });
    reason('spam');
    const form = host().querySelector('form');
    if (form === null) throw new Error('Missing report form');
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    const submission = await vi.waitFor(() => backend.expectOne('/api/v1/reports'));
    submission.flush({
      id: crypto.randomUUID(),
      context_id: contextId,
      submitted_at: context.issued_at,
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('Report submitted');
    });
  });
});
