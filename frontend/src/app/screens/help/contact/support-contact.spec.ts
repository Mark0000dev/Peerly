import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTanStackQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TuiDialogService } from '@taiga-ui/core';
import { TUI_CONFIRM } from '@taiga-ui/kit';
import { of } from 'rxjs';
import { appConfig } from '../../../app.config';
import type { Api } from '../../../api.generated';
import { SupportContact } from './support-contact';
import {
  supportActorFixture,
  supportProofFixture,
  supportReceiptFixture,
} from './support-test-data';

function host(fixture: Readonly<ComponentFixture<SupportContact>>): HTMLElement {
  const element: unknown = fixture.nativeElement;
  if (!(element instanceof HTMLElement)) throw new Error('Missing support host');
  return element;
}
describe('A04/W04 actual form and proof/session ownership', () => {
  let fixture: ComponentFixture<SupportContact>;
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
    fixture = TestBed.createComponent(SupportContact);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    http.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
    vi.restoreAllMocks();
  });
  async function session(actor: Api['schemas']['IdentityResponse'] | null): Promise<void> {
    const request = await vi.waitFor(() => http.expectOne('/api/v1/me'));
    if (actor === null)
      request.flush({ code: 'unauthenticated' }, { status: 401, statusText: 'Unauthorized' });
    else request.flush(actor);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).not.toContain('Sending is paused');
    });
  }
  function click(label: string): void {
    const button = Array.from(host(fixture).querySelectorAll('button')).find(
      (element: Readonly<HTMLButtonElement>) => element.textContent.trim() === label,
    );
    if (button === undefined) throw new Error('Missing support action');
    button.click();
    fixture.detectChanges();
  }
  function fill(): void {
    for (const [selector, value] of [
      ['#support-reply', 'student@example.org'],
      ['#support-message', 'I cannot access the university inbox.'],
      ['#support-details', 'A bounded explanation.'],
    ]) {
      if (selector === undefined || value === undefined) throw new Error('Missing input');
      const element = host(fixture).querySelector(selector);
      if (!(element instanceof HTMLInputElement) && !(element instanceof HTMLTextAreaElement))
        throw new Error('Missing support field');
      Reflect.set(element, 'value', value);
      element.dispatchEvent(new Event('input', { bubbles: true }));
    }
    fixture.detectChanges();
  }
  async function begin(actor: Api['schemas']['IdentityResponse'] | null): Promise<void> {
    await session(actor);
    fill();
    click('Send to the team');
    const proof = await vi.waitFor(() => http.expectOne('/api/v1/support-context'));
    expect(proof.request.body).toEqual({});
    expect(proof.request.headers.has('idempotency-key')).toBe(false);
    proof.flush(supportProofFixture());
  }
  it('validates without requesting a support context or exposing private content', async () => {
    await session(null);
    click('Send to the team');
    expect(host(fixture).textContent).toContain('valid reply address');
    http.expectNone('/api/v1/support-context');
  });
  it.each([
    null,
    supportActorFixture,
    { ...supportActorFixture, account_status: 'banned', membership_status: 'unverified' },
  ] as const)(
    'uses actual anonymous or account-bound CSRF without activation guard',
    async (actor) => {
      await begin(actor);
      const request = await vi.waitFor(() =>
        http.expectOne(actor === null ? '/api/v1/support-cases' : '/api/v1/me/support-cases'),
      );
      expect(request.request.headers.get('x-csrf-token')).toBe(
        actor === null ? 'proof-csrf' : 'session-csrf',
      );
      expect(request.request.body).toEqual({
        topic: 'other',
        reply_address: 'student@example.org',
        message: 'I cannot access the university inbox.',
        details: 'A bounded explanation.',
      });
      request.flush(supportReceiptFixture);
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(host(fixture).textContent).toContain('Request received');
      });
      expect(host(fixture).textContent).not.toContain('Message delivered');
      expect(host(fixture).querySelector('form')).toBeNull();
    },
  );
  it('replays identical unknown creation with original key/body and no fresh proof', async () => {
    await begin(null);
    const first = await vi.waitFor(() => http.expectOne('/api/v1/support-cases'));
    const key = first.request.headers.get('idempotency-key');
    const body: unknown = first.request.body;
    first.flush({ code: 'storage_unavailable' }, { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('whether your request was received');
    });
    expect(host(fixture).querySelector('fieldset')?.disabled).toBe(true);
    click('Retry identical request');
    const replay = await vi.waitFor(() => http.expectOne('/api/v1/support-cases'));
    expect(replay.request.body).toEqual(body);
    expect(replay.request.headers.get('idempotency-key')).toBe(key);
    http.expectNone('/api/v1/support-context');
    replay.flush(supportReceiptFixture);
  });
  it('keeps a known validation failure editable without losing text', async () => {
    await begin(null);
    const request = await vi.waitFor(() => http.expectOne('/api/v1/support-cases'));
    request.flush({ code: 'invalid_request' }, { status: 422, statusText: 'Invalid' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('Edit request');
    });
    click('Edit request');
    expect(host(fixture).querySelector('fieldset')?.disabled).toBe(false);
    expect(host(fixture).querySelector<HTMLTextAreaElement>('#support-message')?.value).toContain(
      'university inbox',
    );
  });
  it('retires a bound draft and ignores a pending result after a real actor change', async () => {
    await begin(supportActorFixture);
    const pending = await vi.waitFor(() => http.expectOne('/api/v1/me/support-cases'));
    client.setQueryData(['session'], {
      ...supportActorFixture,
      account_id: '00000000-0000-4000-8000-000000000111',
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('Sending is paused');
    });
    pending.flush(supportReceiptFixture);
    await Promise.resolve();
    fixture.detectChanges();
    expect(host(fixture).textContent).not.toContain(supportReceiptFixture.case_id);
  });
  it('confirms dirty and unknown leave separately, and permits clean or received departure', async () => {
    await session(null);
    const dialogs = vi.spyOn(TestBed.inject(TuiDialogService), 'open').mockReturnValue(of(false));
    expect(await fixture.componentInstance.canLeave()).toBe(true);
    expect(dialogs).not.toHaveBeenCalled();
    fill();
    expect(await fixture.componentInstance.canLeave()).toBe(false);
    expect(dialogs).toHaveBeenLastCalledWith(
      TUI_CONFIRM,
      expect.objectContaining({ label: 'Discard unsaved changes?' }),
    );
    click('Send to the team');
    (await vi.waitFor(() => http.expectOne('/api/v1/support-context'))).flush(
      supportProofFixture(),
    );
    const pending = await vi.waitFor(() => http.expectOne('/api/v1/support-cases'));
    expect(await fixture.componentInstance.canLeave()).toBe(false);
    expect(dialogs).toHaveBeenLastCalledWith(
      TUI_CONFIRM,
      expect.objectContaining({ label: 'Leave before the save is confirmed?' }),
    );
    pending.flush({ code: 'storage_unavailable' }, { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('whether your request was received');
    });
    expect(await fixture.componentInstance.canLeave()).toBe(false);
    dialogs.mockReturnValue(of(true));
    expect(await fixture.componentInstance.canLeave()).toBe(true);
    click('Retry identical request');
    (await vi.waitFor(() => http.expectOne('/api/v1/support-cases'))).flush(supportReceiptFixture);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('Request received');
    });
    dialogs.mockClear();
    expect(await fixture.componentInstance.canLeave()).toBe(true);
    expect(dialogs).not.toHaveBeenCalled();
  });
  it('keeps current actor draft across an unavailable session, resumes explicit retry, and never sends during context/session race', async () => {
    await session(supportActorFixture);
    fill();
    click('Send to the team');
    const preparation = await vi.waitFor(() => http.expectOne('/api/v1/support-context'));
    void client.invalidateQueries({ queryKey: ['session'] });
    const recheck = await vi.waitFor(() => http.expectOne('/api/v1/me'));
    preparation.flush(supportProofFixture());
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('Sending is paused');
    });
    http.expectNone('/api/v1/me/support-cases');
    recheck.flush({ code: 'storage_unavailable' }, { status: 503, statusText: 'Unavailable' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).querySelector<HTMLTextAreaElement>('#support-message')?.value).toContain(
        'university inbox',
      );
    });
    click('Check sign-in state');
    (await vi.waitFor(() => http.expectOne('/api/v1/me'))).flush(supportActorFixture);
    await vi.waitFor(() => {
      fixture.detectChanges();
      const retry = Array.from(host(fixture).querySelectorAll('button')).find(
        (item: Readonly<HTMLButtonElement>) =>
          item.textContent.trim() === 'Retry identical request',
      );
      expect(retry?.disabled).toBe(false);
    });
    click('Retry identical request');
    const admitted = await vi.waitFor(() => http.expectOne('/api/v1/me/support-cases'));
    expect(admitted.request.headers.get('x-csrf-token')).toBe(supportActorFixture.csrf_token);
    http.expectNone('/api/v1/support-context');
    admitted.flush(supportReceiptFixture);
  });
  it.each([401, 403])(
    'revalidates actual session after actor command %s without exposing a later receipt',
    async (status) => {
      await begin(supportActorFixture);
      (await vi.waitFor(() => http.expectOne('/api/v1/me/support-cases'))).flush(
        { code: 'unauthenticated' },
        { status, statusText: 'Denied' },
      );
      const recheck = await vi.waitFor(() => http.expectOne('/api/v1/me'));
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('Sending is paused');
      expect(host(fixture).querySelector<HTMLTextAreaElement>('#support-message')?.value).toContain(
        'university inbox',
      );
      recheck.flush({ code: 'unauthenticated' }, { status: 401, statusText: 'Unauthorized' });
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(host(fixture).querySelector<HTMLTextAreaElement>('#support-message')?.value).toBe(
          '',
        );
      });
      expect(await fixture.componentInstance.canLeave()).toBe(true);
      http.expectNone('/api/v1/me/support-cases');
    },
  );
  it('does not send a case or renew expired proof and preserves conservative unavailable recovery', async () => {
    await session(null);
    fill();
    click('Send to the team');
    (await vi.waitFor(() => http.expectOne('/api/v1/support-context'))).flush({
      ...supportProofFixture(),
      expires_at: new Date(Date.now() - 1000).toISOString(),
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('proof is unavailable or expired');
    });
    http.expectNone('/api/v1/support-cases');
    click('Retry identical request');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('proof is unavailable or expired');
    });
    http.expectNone('/api/v1/support-context');
    http.expectNone('/api/v1/support-cases');
  });
  it('keeps quota-rejected input editable and sends absent details as actual null', async () => {
    await session(null);
    fill();
    const details = host(fixture).querySelector<HTMLTextAreaElement>('#support-details');
    if (details === null) throw new Error('Missing details');
    Reflect.set(details, 'value', '');
    details.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
    click('Send to the team');
    (await vi.waitFor(() => http.expectOne('/api/v1/support-context'))).flush(
      supportProofFixture(),
    );
    const request = await vi.waitFor(() => http.expectOne('/api/v1/support-cases'));
    expect(request.request.body).toEqual(expect.objectContaining({ details: null }));
    request.flush(
      { code: 'support_quota_exceeded', request_id: 'quota-reference' },
      { status: 429, statusText: 'Quota' },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('Too many requests');
      expect(host(fixture).textContent).toContain('quota-reference');
    });
    click('Edit request');
    expect(host(fixture).querySelector('fieldset')?.disabled).toBe(false);
  });
});
