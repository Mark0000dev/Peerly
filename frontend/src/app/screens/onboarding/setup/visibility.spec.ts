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
  beforeEach(() => {
    client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    client.setQueryData(['session'], verifiedActor);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
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
