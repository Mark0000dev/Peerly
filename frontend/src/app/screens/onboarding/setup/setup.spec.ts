import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { Router } from '@angular/router';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../app.config';
import { click, control, host, shown, submit } from '../testing-host';
import { ownProfile, revision } from '../profile/profile.fixtures';
import { verifiedActor } from '../onboarding.fixtures';
import { StudySetup } from './setup';
import { complete, context, ready, receipt } from './setup.fixtures';

describe('actual study setup completion', () => {
  let fixture: ComponentFixture<StudySetup>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(StudySetup);
    fixture.componentRef.setInput('actor', verifiedActor);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify();
  });
  async function load(
    value: Readonly<Record<string, unknown>> = ready,
    profileValue: Readonly<Record<string, unknown>> = ownProfile,
  ): Promise<void> {
    const profile = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'GET' }),
    );
    profile.flush(profileValue);
    const status = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/onboarding', method: 'GET' }),
    );
    status.flush(value);
    await shown(fixture, 'What would you like to do first?');
  }
  async function prepare(): Promise<void> {
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/registration-context', method: 'POST' }),
    );
    expect(request.request.headers.get('x-csrf-token')).toBe(verifiedActor.csrf_token);
    request.flush(context);
    await shown(fixture, context.notice_text);
  }
  it('prepares actual context but never automatically completes registration', async () => {
    await load();
    await prepare();
    backend.expectNone('/api/v1/me/registration');
    expect(host(fixture).querySelector('input[type=checkbox]')).toBeNull();
    expect(host(fixture).querySelector('a[href="/terms?version=1"]')).not.toBeNull();
    expect(host(fixture).querySelector('a[href="/privacy?version=1"]')).not.toBeNull();
  });
  it('completes only explicit issued context then navigates after receipt', async () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    await load();
    await prepare();
    click(fixture, 'Continue');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/registration'));
    expect(request.request.body).toEqual({ context_id: context.id });
    expect(navigate).not.toHaveBeenCalled();
    request.flush(receipt);
    await vi.waitFor(() => {
      expect(navigate).toHaveBeenCalledWith(['/discover'], { queryParams: { mode: 'find_help' } });
    });
  });
  it('retries a lost completion response with identical immutable intent', async () => {
    vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    await load();
    await prepare();
    click(fixture, 'Continue');
    const first = await vi.waitFor(() => backend.expectOne('/api/v1/me/registration'));
    const key = first.request.headers.get('idempotency-key');
    const body: unknown = first.request.body;
    first.error(new ProgressEvent('error'));
    await shown(fixture, 'We couldn’t confirm completion');
    click(fixture, 'Retry same completion');
    const retry = await vi.waitFor(() => backend.expectOne('/api/v1/me/registration'));
    expect(retry.request.headers.get('idempotency-key')).toBe(key);
    expect(retry.request.body).toEqual(body);
    retry.flush(receipt);
  });
  it('requires actual server prerequisites and never prepares context while incomplete', async () => {
    await load({
      ...ready,
      setup_requirements: ['photo', 'study_goal'],
      capabilities: { ...ready.capabilities, can_complete_registration: false },
    });
    await shown(fixture, 'Add a photo and wait for it to be ready.');
    expect(host(fixture).textContent).toContain('Save your study goal.');
    click(fixture, 'Continue');
    backend.expectNone('/api/v1/me/registration');
    backend.expectNone('/api/v1/me/registration-context');
  });
  it('keeps a changed task as form draft and preserves all unrelated profile fields on save', async () => {
    await load(complete);
    control(fixture, 'input[value=offer_help]').setValue('offer_help');
    control(fixture, 'input[value=offer_help]').markAsDirty();
    fixture.detectChanges();
    submit(fixture);
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    expect(request.request.body).toEqual({
      expected_version: revision.version,
      display_name: revision.display_name,
      about: revision.about,
      programme: revision.programme,
      year_label: revision.year_label,
      languages: revision.languages,
      task: 'offer_help',
    });
    request.flush({ ...revision, task: 'offer_help', version: 3 });
    const reads = await vi.waitFor(() => {
      const result = backend.match((request) => request.method === 'GET');
      expect(result).toHaveLength(2);
      return result;
    });
    for (const read of reads)
      read.flush(
        read.request.url.endsWith('/profile')
          ? { ...ownProfile, profile: { ...revision, task: 'offer_help', version: 3 } }
          : complete,
      );
    await shown(fixture, 'Your setup is saved.');
  });
  it('retains registered receipt context without asking users to reaccept', async () => {
    fixture.componentRef.setInput('actor', { ...verifiedActor, registration: receipt });
    fixture.detectChanges();
    vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    await load({
      ...ready,
      registered: true,
      capabilities: {
        ...ready.capabilities,
        can_complete_registration: false,
        can_complete_setup: true,
      },
    });
    backend.expectNone('/api/v1/me/registration-context');
    click(fixture, 'Finish setup');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/registration'));
    expect(request.request.body).toEqual({ context_id: receipt.context_id });
    request.flush(receipt);
  });
  it('retries unknown context issuance with the same immutable key', async () => {
    await load();
    const first = await vi.waitFor(() => backend.expectOne('/api/v1/me/registration-context'));
    const key = first.request.headers.get('idempotency-key');
    first.error(new ProgressEvent('error'));
    await shown(fixture, 'Retry registration details');
    click(fixture, 'Retry registration details');
    const retry = await vi.waitFor(() => backend.expectOne('/api/v1/me/registration-context'));
    expect(retry.request.headers.get('idempotency-key')).toBe(key);
    retry.flush(context);
    await shown(fixture, context.notice_text);
  });
  it('refreshes an expired issued context instead of blindly retrying completion', async () => {
    await load();
    await prepare();
    click(fixture, 'Continue');
    const first = await vi.waitFor(() => backend.expectOne('/api/v1/me/registration'));
    first.flush(
      { code: 'registration_context_unavailable' },
      { status: 409, statusText: 'Conflict' },
    );
    await shown(fixture, 'These registration details are no longer available.');
    click(fixture, 'Continue');
    backend.expectNone('/api/v1/me/registration');
    click(fixture, 'Refresh registration details');
    const next = await vi.waitFor(() => backend.expectOne('/api/v1/me/registration-context'));
    next.flush({ ...context, id: 'context-2' });
    await shown(fixture, context.notice_text);
  });
  it('preserves an uncertain task body and key until explicit replay succeeds', async () => {
    await load(complete);
    control(fixture, 'input[value=offer_help]').setValue('offer_help');
    control(fixture, 'input[value=offer_help]').markAsDirty();
    fixture.detectChanges();
    submit(fixture);
    const first = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    const key = first.request.headers.get('idempotency-key');
    const body: unknown = first.request.body;
    first.error(new ProgressEvent('error'));
    await shown(fixture, 'We couldn’t confirm that save.');
    click(fixture, 'Retry same task save');
    const retry = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    expect(retry.request.headers.get('idempotency-key')).toBe(key);
    expect(retry.request.body).toEqual(body);
    retry.flush({ ...revision, task: 'offer_help', version: 3 });
    const profile = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'GET' }),
    );
    profile.flush({ ...ownProfile, profile: { ...revision, task: 'offer_help', version: 3 } });
    const status = await vi.waitFor(() => backend.expectOne('/api/v1/me/onboarding'));
    status.flush(complete);
    await shown(fixture, 'Your setup is saved.');
  });
  it('keeps a same-account first-task draft when session metadata changes', async () => {
    await load(complete);
    control(fixture, 'input[value=offer_help]').setValue('offer_help');
    control(fixture, 'input[value=offer_help]').markAsDirty();
    fixture.componentRef.setInput('actor', { ...verifiedActor, csrf_token: 'rotated-session' });
    fixture.detectChanges();
    backend.expectNone('/api/v1/me/profile');
    backend.expectNone('/api/v1/me/onboarding');
    await shown(fixture, 'What would you like to do first?');
    expect(control(fixture, 'input[value=offer_help]').value).toBe('offer_help');
  });
  it('clears private context and ignores an old-account completion callback', async () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    await load();
    await prepare();
    click(fixture, 'Continue');
    const first = await vi.waitFor(() => backend.expectOne('/api/v1/me/registration'));
    fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'second-account' });
    fixture.detectChanges();
    first.flush(receipt);
    const profile = await vi.waitFor(() => backend.expectOne('/api/v1/me/profile'));
    profile.flush(ownProfile);
    const status = await vi.waitFor(() => backend.expectOne('/api/v1/me/onboarding'));
    status.flush(complete);
    await shown(fixture, 'Your setup is saved.');
    expect(navigate).not.toHaveBeenCalled();
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });
  it('starts the first task at zero revision without manufacturing a name or optional fields', async () => {
    await load(
      { ...ready, capabilities: { ...ready.capabilities, can_complete_registration: false } },
      { profile: null, photo: null },
    );
    control(fixture, 'input[value=offer_help]').setValue('offer_help');
    control(fixture, 'input[value=offer_help]').markAsDirty();
    fixture.detectChanges();
    submit(fixture);
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    expect(request.request.body).toEqual({
      expected_version: 0,
      display_name: null,
      about: null,
      programme: null,
      year_label: null,
      languages: [],
      task: 'offer_help',
    });
    request.flush({ ...revision, version: 1, display_name: null, task: 'offer_help' });
    const profile = await vi.waitFor(() => backend.expectOne('/api/v1/me/profile'));
    profile.flush({
      profile: { ...revision, version: 1, display_name: null, task: 'offer_help' },
      photo: null,
    });
    const status = await vi.waitFor(() => backend.expectOne('/api/v1/me/onboarding'));
    status.flush({
      ...ready,
      capabilities: { ...ready.capabilities, can_complete_registration: false },
    });
    await shown(fixture, 'What would you like to do first?');
  });
  it('preserves a conflicting first-task draft until explicit canonical reload', async () => {
    await load(complete);
    control(fixture, 'input[value=offer_help]').setValue('offer_help');
    control(fixture, 'input[value=offer_help]').markAsDirty();
    fixture.detectChanges();
    submit(fixture);
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    request.flush({ code: 'profile_version_conflict' }, { status: 409, statusText: 'Conflict' });
    await shown(fixture, 'Reload saved first task');
    expect(control(fixture).value).toBe('offer_help');
    click(fixture, 'Reload saved first task');
    const profile = await vi.waitFor(() => backend.expectOne('/api/v1/me/profile'));
    profile.flush(ownProfile);
    const status = await vi.waitFor(() => backend.expectOne('/api/v1/me/onboarding'));
    status.flush(complete);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(control(fixture).value).toBe('find_help');
    });
  });
  it('recovers failed setup reads only through explicit retry', async () => {
    const profile = await vi.waitFor(() => backend.expectOne('/api/v1/me/profile'));
    profile.flush({ code: 'unavailable' }, { status: 503, statusText: 'Unavailable' });
    const status = await vi.waitFor(() => backend.expectOne('/api/v1/me/onboarding'));
    status.flush({ code: 'unavailable' }, { status: 503, statusText: 'Unavailable' });
    await shown(fixture, 'Retry setup check');
    click(fixture, 'Retry setup check');
    await load(complete);
    await shown(fixture, 'Your setup is saved.');
  });
  it('rereads server readiness after incomplete completion and preserves the original intent', async () => {
    vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    await load();
    await prepare();
    click(fixture, 'Continue');
    const first = await vi.waitFor(() => backend.expectOne('/api/v1/me/registration'));
    const key = first.request.headers.get('idempotency-key');
    first.flush({ code: 'onboarding_incomplete' }, { status: 409, statusText: 'Conflict' });
    const status = await vi.waitFor(() => backend.expectOne('/api/v1/me/onboarding'));
    status.flush(ready);
    await shown(fixture, 'Review your saved requirements');
    click(fixture, 'Continue');
    const retry = await vi.waitFor(() => backend.expectOne('/api/v1/me/registration'));
    expect(retry.request.headers.get('idempotency-key')).toBe(key);
    retry.flush(receipt);
  });
  it('keeps canonical completion visible when navigation is refused', async () => {
    vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(false);
    await load();
    await prepare();
    click(fixture, 'Continue');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/registration'));
    request.flush(receipt);
    const status = await vi.waitFor(() => backend.expectOne('/api/v1/me/onboarding'));
    status.flush(complete);
    await shown(fixture, 'Your setup is saved.');
  });
  for (const status of [401, 403]) {
    it(`propagates registration ${String(status)} without navigation or an automatic resend`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
      await load();
      await prepare();
      click(fixture, 'Continue');
      const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/registration'));
      request.flush({ code: 'unauthenticated' }, { status, statusText: 'Denied' });
      await vi.waitFor(() => {
        expect(expired).toHaveBeenCalledOnce();
      });
      expect(navigate).not.toHaveBeenCalled();
      backend.expectNone('/api/v1/me/registration');
    });
  }
  it('prepares context when changing first task makes the saved setup ready', async () => {
    await load(
      { ...ready, capabilities: { ...ready.capabilities, can_complete_registration: false } },
      { ...ownProfile, profile: { ...revision, task: 'offer_help' } },
    );
    backend.expectNone('/api/v1/me/registration-context');
    control(fixture, 'input[value=find_help]').setValue('find_help');
    control(fixture, 'input[value=find_help]').markAsDirty();
    fixture.detectChanges();
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    save.flush({ ...revision, version: 3 });
    const profile = await vi.waitFor(() => backend.expectOne('/api/v1/me/profile'));
    profile.flush({ ...ownProfile, profile: { ...revision, version: 3 } });
    const status = await vi.waitFor(() => backend.expectOne('/api/v1/me/onboarding'));
    status.flush(ready);
    await prepare();
    expect(host(fixture).querySelector('button[type=submit]')?.hasAttribute('disabled')).toBe(true);
    backend.expectNone('/api/v1/me/registration');
  });
});
