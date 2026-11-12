import { TuiDialogService } from '@taiga-ui/core';
import { of, Subject } from 'rxjs';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../app.config';
import { click, host, shown } from '../testing-host';
import { verifiedActor } from '../onboarding.fixtures';
import { complete, visibility } from './setup.fixtures';
import { ProfileVisibility } from './visibility';

describe('canonical visibility and freshness confirmation', () => {
  let fixture: ComponentFixture<ProfileVisibility>;
  let backend: HttpTestingController;
  let client: QueryClient;
  const confirm = vi.fn(() => of(true));
  beforeEach(() => {
    confirm.mockReset();
    confirm.mockReturnValue(of(true));
    client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    client.setQueryData(['session'], verifiedActor);
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideHttpClientTesting(),
        provideTanStackQuery(client),
        { provide: TuiDialogService, useValue: { open: confirm } },
      ],
    });
    fixture = TestBed.createComponent(ProfileVisibility);
    fixture.componentRef.setInput('actor', verifiedActor);
    fixture.componentRef.setInput('status', complete);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify();
  });
  it('explains pending-request closure before confirmation and cancellation sends no command', async () => {
    const decision = new Subject<boolean>();
    confirm.mockReturnValue(decision);
    expect(host(fixture).textContent).toContain('Pending requests close and won’t reopen');
    expect(host(fixture).textContent).toContain('Your existing chats keep working');
    click(fixture, 'Hide my profile');
    click(fixture, 'Hide my profile');
    expect(confirm).toHaveBeenCalledOnce();
    backend.expectNone('/api/v1/me/visibility');
    decision.next(false);
    decision.complete();
    await fixture.whenStable();
    backend.expectNone('/api/v1/me/visibility');
    expect(host(fixture).textContent).not.toContain('Updating your profile visibility');
  });
  it.each(['actor', 'revision', 'session'] as const)(
    'does not apply a confirmation after its %s context retires',
    async (changed) => {
      const decision = new Subject<boolean>();
      confirm.mockReturnValue(decision);
      click(fixture, 'Hide my profile');
      backend.expectNone('/api/v1/me/visibility');
      if (changed === 'actor')
        fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'replacement' });
      else if (changed === 'revision')
        fixture.componentRef.setInput('status', {
          ...complete,
          visibility: { ...visibility, version: 2 },
        });
      else client.setQueryData(['session'], null);
      fixture.detectChanges();
      decision.next(true);
      decision.complete();
      await fixture.whenStable();
      backend.expectNone('/api/v1/me/visibility');
    },
  );
  it('uses actual discovery capability and preserves an unmet human-review requirement', () => {
    const restricted = {
      ...complete,
      capabilities: { ...complete.capabilities, can_discover: false, can_make_new_contacts: false },
    };
    fixture.componentRef.setInput('status', restricted);
    fixture.detectChanges();
    expect(host(fixture).textContent).toContain('Your profile can’t appear in Discover right now.');
    expect(host(fixture).textContent).not.toContain('Your profile can appear in Discover.');
    fixture.componentRef.setInput('status', {
      ...restricted,
      visibility: { ...visibility, version: 2, hidden: true, hidden_at: '2026-11-07T12:00:00Z' },
      restore_requirements: ['photo_review'],
      capabilities: {
        ...restricted.capabilities,
        can_hide_profile: false,
        can_restore_profile: false,
      },
    });
    fixture.detectChanges();
    expect(host(fixture).textContent).toContain('A replacement photo reviewed by the team');
    expect(
      Array.from(host(fixture).querySelectorAll('button')).some(
        (button: Readonly<HTMLButtonElement>) => button.textContent.trim() === 'Show my profile',
      ),
    ).toBe(false);
    backend.expectNone((request) => request.method === 'PUT');
  });
  it('never confirms freshness from a read and requires explicit server-permitted action', async () => {
    fixture.componentRef.setInput('status', {
      ...complete,
      discovery_exposure: { paused: true, can_confirm: true, requirements: [] },
    });
    await shown(fixture, 'Show my profile again');
    backend.expectNone('/api/v1/me/visibility');
    click(fixture, 'Show my profile again');
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/visibility', method: 'PUT' }),
    );
    expect(request.request.body).toEqual({ hidden: false, expected_version: visibility.version });
    expect(request.request.headers.get('x-csrf-token')).toBe(verifiedActor.csrf_token);
    request.flush({ ...visibility, version: 2 });
  });
  it('does not offer confirmation while server requires photo or study context', async () => {
    fixture.componentRef.setInput('status', {
      ...complete,
      discovery_exposure: {
        paused: true,
        can_confirm: false,
        requirements: ['photo', 'study_context'],
      },
    });
    await shown(fixture, 'Review your photo and study setup');
    expect(host(fixture).textContent).not.toContain('Show my profile again');
    backend.expectNone('/api/v1/me/visibility');
  });
  it('hidden profiles retain existing chats and show only actual restore capability', async () => {
    fixture.componentRef.setInput('status', {
      ...complete,
      visibility: { ...visibility, hidden: true },
      capabilities: { ...complete.capabilities, can_restore_profile: true },
    });
    await shown(fixture, 'Existing chats continue to work.');
    click(fixture, 'Show my profile');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/visibility'));
    expect(request.request.body).toEqual({ hidden: false, expected_version: 1 });
    request.flush({ ...visibility, version: 2 });
  });
  it('retains exact hide intent after lost response rather than converting retry into unhide', async () => {
    click(fixture, 'Hide my profile');
    const first = await vi.waitFor(() => backend.expectOne('/api/v1/me/visibility'));
    const key = first.request.headers.get('idempotency-key');
    first.error(new ProgressEvent('error'));
    await shown(fixture, 'We couldn’t confirm the visibility change');
    click(fixture, 'Retry same change');
    const retry = await vi.waitFor(() => backend.expectOne('/api/v1/me/visibility'));
    expect(retry.request.headers.get('idempotency-key')).toBe(key);
    expect(retry.request.body).toEqual({ hidden: true, expected_version: 1 });
    expect(confirm).toHaveBeenCalledOnce();
    retry.flush({ ...visibility, hidden: true, version: 2 });
  });
  it('requires explicit canonical reload after CAS conflict', async () => {
    click(fixture, 'Hide my profile');
    const first = await vi.waitFor(() => backend.expectOne('/api/v1/me/visibility'));
    first.flush({ code: 'profile_visibility_conflict' }, { status: 409, statusText: 'Conflict' });
    await shown(fixture, 'Reload your saved setup');
    click(fixture, 'Hide my profile');
    backend.expectNone('/api/v1/me/visibility');
    click(fixture, 'Reload saved setup');
    await shown(fixture, 'Hide my profile');
  });
  it('clears owned private mutation payloads on account change', async () => {
    click(fixture, 'Hide my profile');
    const first = await vi.waitFor(() => backend.expectOne('/api/v1/me/visibility'));
    first.error(new ProgressEvent('error'));
    await shown(fixture, 'Retry same change');
    fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'second-account' });
    fixture.detectChanges();
    expect(client.getMutationCache().getAll()).toHaveLength(0);
    expect(host(fixture).textContent).not.toContain('Retry same change');
  });
  it('propagates denied membership without inventing a successful visibility state', async () => {
    const expired = vi.fn();
    fixture.componentInstance.expired.subscribe(expired);
    click(fixture, 'Hide my profile');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/visibility'));
    request.flush({ code: 'membership_required' }, { status: 403, statusText: 'Forbidden' });
    await vi.waitFor(() => {
      expect(expired).toHaveBeenCalledOnce();
    });
    expect(host(fixture).textContent).not.toContain('Your profile is hidden');
  });
});
