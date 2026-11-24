import { provideNoPhotoReview } from './photo-review-unit.fixtures';
import { host, shown, control, submit, click } from '../testing-host';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { By } from '@angular/platform-browser';
import { PhotoWorkflow } from './photo/photo';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import type { Mutation } from '@tanstack/angular-query-experimental';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../app.config';
import { ProfileBasics } from './profile';
import { PhotoAssistance } from '../study/ai/photo-assistance';
import { OwnFeedbackSummary } from './feedback-summary';
import { ApiFailure } from '../../../api-http';
import { ownProfile, revision } from './profile.fixtures';
import { verifiedActor } from '../onboarding.fixtures';

describe('owned profile name draft', () => {
  let fixture: ComponentFixture<ProfileBasics>;
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
      providers: [
        ...appConfig.providers,
        provideNoPhotoReview(),
        provideHttpClientTesting(),
        provideTanStackQuery(client),
      ],
    });
    fixture = TestBed.createComponent(ProfileBasics);
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
    value: Readonly<Record<string, unknown>> = ownProfile,
    status = 200,
  ): Promise<void> {
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'GET' }),
    );
    request.flush(value, { status, statusText: status === 200 ? 'OK' : 'Failure' });
    await shown(fixture, status === 200 ? 'Display name' : 'We couldn’t load your profile');
  }

  it('retains the same native form through same-actor auth checks and exposes a remote CAS change instead of overwriting edits', async () => {
    await load();
    edit('My unsaved name');
    const input = host(fixture).querySelector('#profile-name');
    fixture.componentRef.setInput('checking', true);
    client.removeQueries({ queryKey: ['account', verifiedActor.account_id, 'profile'] });
    fixture.componentRef.setInput('actor', { ...verifiedActor, csrf_token: 'rotated-same-actor' });
    fixture.detectChanges();
    expect(host(fixture).querySelector('#profile-name')).toBe(input);
    expect(control(fixture, '#profile-name').value).toBe('My unsaved name');
    backend.expectNone((request) => request.method === 'PUT');
    client.setQueryData(['session'], { ...verifiedActor, csrf_token: 'rotated-same-actor' });
    fixture.componentRef.setInput('checking', false);
    fixture.detectChanges();
    const read = await vi.waitFor(() => backend.expectOne('/api/v1/me/profile'));
    read.flush({
      profile: { ...revision, version: 3, display_name: 'Remote saved name' },
      photo: null,
    });
    await shown(fixture, 'Reload saved profile');
    expect(control(fixture, '#profile-name').value).toBe('My unsaved name');
    expect(host(fixture).querySelector('#profile-name')).toBe(input);
    expect(fixture.componentInstance.hasUnsavedChanges).toBe(true);
    backend.expectNone((request) => request.method === 'PUT');
  });

  it('retires the previous actor form on replacement instead of carrying its values into another account', async () => {
    await load();
    edit('Private owner draft');
    const replacement = { ...verifiedActor, account_id: 'replacement-owner' };
    client.setQueryData(['session'], replacement);
    fixture.componentRef.setInput('actor', replacement);
    fixture.detectChanges();
    const read = await vi.waitFor(() => backend.expectOne('/api/v1/me/profile'));
    read.flush({ profile: null, photo: null });
    await shown(fixture, 'Display name');
    expect(control(fixture, '#profile-name').value).toBe('');
    expect(fixture.componentInstance.hasUnsavedChanges).toBe(false);
    backend.expectNone((request) => request.method === 'PUT');
  });

  function edit(value: string): void {
    control(fixture, '#profile-name').setValue(value);
    control(fixture, '#profile-name').markAsDirty();
  }

  async function activeSummary(): Promise<void> {
    await load();
    const active = {
      ...verifiedActor,
      capabilities: { ...verifiedActor.capabilities, can_use_student_features: true },
    } as const;
    client.setQueryData(['session'], active);
    fixture.componentRef.setInput('actor', active);
    fixture.detectChanges();
  }
  for (const status of [401, 403] as const)
    it(`retires own private state after feedback summary ${String(status)}`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      await activeSummary();
      const summary = await vi.waitFor(() => backend.expectOne('/api/v1/me/feedback-summary'));
      summary.flush({ code: 'access_changed' }, { status, statusText: 'Unavailable' });
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(expired).toHaveBeenCalledOnce();
      });
      expect(client.getQueryData(['session'])).toBeNull();
      expect(client.getQueryData(['account', verifiedActor.account_id, 'profile'])).toBeUndefined();
      expect(control(fixture, '#profile-name').value).toBe('');
    });
  it('mounts own summary only after activation and ignores retired actor/non-auth outputs', async () => {
    backend.expectNone('/api/v1/me/feedback-summary');
    await activeSummary();
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/feedback-summary'));
    request.flush({ state: 'building', responses: 1, publicly_visible: true });
    await shown(fixture, '1 partner has responded');
    const expired = vi.fn();
    fixture.componentInstance.expired.subscribe(expired);
    const summary = fixture.debugElement
      .query(By.directive(OwnFeedbackSummary))
      .injector.get(OwnFeedbackSummary);
    summary.sessionFailure.emit({
      actorId: 'former-actor',
      error: new ApiFailure(401, 'unauthenticated', null),
    });
    summary.sessionFailure.emit({
      actorId: verifiedActor.account_id,
      error: new ApiFailure(503, 'storage_unavailable', null),
    });
    expect(expired).not.toHaveBeenCalled();
    expect(client.getQueryData(['session'])).not.toBeNull();
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('loads a saved draft without exposing a fake activation action', async () => {
    await shown(fixture, 'Loading your profile');
    await load();
    expect(control(fixture, '#profile-name').value).toBe(revision.display_name);
    expect(host(fixture).textContent).not.toContain('Discover');
  });
  it('starts a new draft at the documented zero revision and rejects invalid names locally', async () => {
    await load({ profile: null, photo: null });
    submit(fixture);
    await shown(fixture, 'Enter a display name');
    backend.expectNone({ url: '/api/v1/me/profile', method: 'PUT' });
    edit('Maya');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    expect(save.request.body).toEqual({
      about: null,
      programme: null,
      year_label: null,
      languages: [],
      task: 'find_help',
      display_name: 'Maya',
      expected_version: 0,
    });
    expect(save.request.headers.get('x-csrf-token')).toBe(verifiedActor.csrf_token);
    expect(save.request.headers.get('idempotency-key')).toMatch(/^[a-f0-9-]{36}$/);
    save.flush({ ...revision, display_name: 'Maya', version: 1 });
    await load({ profile: { ...revision, display_name: 'Maya', version: 1 }, photo: null });
    await shown(fixture, 'Profile saved.');
    expect(control(fixture, '#profile-name').value).toBe('Maya');
  });
  it('preserves optional fields, original version and one in-flight save', async () => {
    await load();
    edit(' New Name ');
    submit(fixture);
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    expect(save.request.body).toEqual({
      about: revision.about,
      programme: revision.programme,
      year_label: revision.year_label,
      languages: revision.languages,
      task: revision.task,
      display_name: 'New Name',
      expected_version: 2,
    });
    await shown(fixture, 'Saving…');
    save.flush({ ...revision, version: 3, display_name: 'New Name' });
    await load({ profile: { ...revision, version: 3, display_name: 'New Name' }, photo: null });
    await shown(fixture, 'Profile saved.');
  });
  for (const status of [0, 408, 503]) {
    it(`retries uncertain ${String(status)} with the same exact intent and freezes editing`, async () => {
      await load();
      edit('New Name');
      submit(fixture);
      const save = await vi.waitFor(() =>
        backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
      );
      const key = save.request.headers.get('idempotency-key');
      const body: unknown = save.request.body;
      if (status === 0) save.error(new ProgressEvent('error'));
      else save.flush({ code: 'unavailable' }, { status, statusText: 'Unknown' });
      await shown(fixture, 'We couldn’t confirm your save');
      expect(host(fixture).querySelector('input')?.readOnly).toBe(true);
      submit(fixture);
      const retry = await vi.waitFor(() =>
        backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
      );
      expect(retry.request.headers.get('idempotency-key')).toBe(key);
      expect(retry.request.body).toEqual(body);
      const saved = { ...revision, version: 3, display_name: 'New Name' };
      retry.flush(saved);
      await load({ profile: saved, photo: null });
      await shown(fixture, 'Profile saved.');
    });
  }
  it('preserves a conflicting draft until explicit reload, then adopts the current revision', async () => {
    await load();
    edit('My draft');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    save.flush({ code: 'profile_version_conflict' }, { status: 409, statusText: 'Conflict' });
    await shown(fixture, 'Your profile changed elsewhere');
    expect(control(fixture, '#profile-name').value).toBe('My draft');
    submit(fixture);
    backend.expectNone({ url: '/api/v1/me/profile', method: 'PUT' });
    click(fixture, 'Reload saved profile');
    await load({ profile: { ...revision, display_name: 'Other device', version: 4 }, photo: null });
    expect(control(fixture, '#profile-name').value).toBe('Other device');
  });
  it('shows a safe validation failure without leaking raw server text', async () => {
    await load();
    edit('Name');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    save.flush({ code: 'invalid', title: 'PRIVATE' }, { status: 422, statusText: 'Invalid' });
    await shown(fixture, 'We couldn’t save your profile');
    expect(host(fixture).textContent).not.toContain('PRIVATE');
    expect(control(fixture, '#profile-name').value).toBe('Name');
  });
  it('recovers a failed profile read only by explicit retry', async () => {
    await load({ code: 'unavailable' }, 503);
    click(fixture, 'Try again');
    await load();
    expect(control(fixture, '#profile-name').value).toBe(revision.display_name);
  });
  for (const status of [401, 403]) {
    it(`clears the name and asks the identity boundary to revalidate after write ${String(status)}`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      await load();
      edit('Private draft');
      submit(fixture);
      const save = await vi.waitFor(() =>
        backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
      );
      save.flush({ code: 'unavailable' }, { status, statusText: 'Denied' });
      await vi.waitFor(() => {
        expect(expired).toHaveBeenCalledOnce();
      });
      expect(control(fixture, '#profile-name').value).toBe('');
      expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
    });
    it(`asks the identity boundary to revalidate after read ${String(status)}`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      await load({ code: 'unavailable' }, status);
      expect(expired).toHaveBeenCalledOnce();
    });
  }
  it('does not let an old actor save completion reset a replacement actor draft', async () => {
    await load();
    edit('Old draft');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement' });
    fixture.componentRef.setInput('actor', { ...verifiedActor, account_id: 'replacement' });
    fixture.detectChanges();
    await load({ profile: { ...revision, display_name: 'Replacement' }, photo: null });
    edit('New private draft');
    save.flush({ ...revision, display_name: 'Old draft' });
    await shown(fixture, 'Display name');
    expect(control(fixture, '#profile-name').value).toBe('New private draft');
    backend.expectNone({ url: '/api/v1/me/profile', method: 'GET' });
  });
  it('keeps the photo editor and dirty name draft alive during a background photo refresh', async () => {
    await load();
    edit('Unsaved name');
    click(fixture, 'Add photo');
    const history = await vi.waitFor(() => backend.expectOne('/api/v1/media/uploads'));
    history.flush({ photo: null, uploads: [] });
    await shown(fixture, 'Choose photo');
    const child = fixture.debugElement
      .query(By.directive(PhotoWorkflow))
      .injector.get(PhotoWorkflow);
    child.refreshProfile.emit();
    const refresh = await vi.waitFor(() => backend.expectOne('/api/v1/me/profile'));
    await shown(fixture, 'Refreshing your profile…');
    expect(
      fixture.debugElement.query(By.directive(PhotoWorkflow)).injector.get(PhotoWorkflow),
    ).toBe(child);
    expect(control(fixture, '#profile-name').value).toBe('Unsaved name');
    refresh.flush(ownProfile);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).not.toContain('Refreshing your profile…');
    });
    expect(
      fixture.debugElement.query(By.directive(PhotoWorkflow)).injector.get(PhotoWorkflow),
    ).toBe(child);
    expect(control(fixture, '#profile-name').value).toBe('Unsaved name');
    backend.expectNone('/api/v1/media/uploads');
  });
  for (const status of [503, 403]) {
    it(`preserves cached drafts only for a transient profile refresh failure ${String(status)}`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      await load();
      edit('Unsaved name');
      click(fixture, 'Add photo');
      const history = await vi.waitFor(() => backend.expectOne('/api/v1/media/uploads'));
      history.flush({ photo: null, uploads: [] });
      await shown(fixture, 'Choose photo');
      const child = fixture.debugElement
        .query(By.directive(PhotoWorkflow))
        .injector.get(PhotoWorkflow);
      child.refreshProfile.emit();
      const refresh = await vi.waitFor(() => backend.expectOne('/api/v1/me/profile'));
      refresh.flush({ code: 'unavailable' }, { status, statusText: 'Failure' });
      if (status === 403) {
        await shown(fixture, 'We couldn’t load your profile.');
        expect(expired).toHaveBeenCalled();
        expect(fixture.debugElement.query(By.directive(PhotoWorkflow))).toBeNull();
        expect(host(fixture).textContent).not.toContain('Unsaved name');
        return;
      }
      await shown(fixture, 'We couldn’t refresh your profile. Your draft is still here.');
      expect(expired).not.toHaveBeenCalled();
      expect(control(fixture, '#profile-name').value).toBe('Unsaved name');
      expect(
        fixture.debugElement.query(By.directive(PhotoWorkflow)).injector.get(PhotoWorkflow),
      ).toBe(child);
      click(fixture, 'Retry profile refresh');
      const retry = await vi.waitFor(() => backend.expectOne('/api/v1/me/profile'));
      retry.flush(ownProfile);
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(host(fixture).textContent).not.toContain('We couldn’t refresh your profile.');
      });
      expect(control(fixture, '#profile-name').value).toBe('Unsaved name');
      expect(
        fixture.debugElement.query(By.directive(PhotoWorkflow)).injector.get(PhotoWorkflow),
      ).toBe(child);
      backend.expectNone('/api/v1/media/uploads');
    });
  }

  it('pauses a queued profile save during identity checking and explicitly retries its original intent', async () => {
    await load();
    edit('Queued profile draft');
    submit(fixture);
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    await shown(fixture, 'Your save paused during a sign-in check.');
    backend.expectNone((request) => request.method === 'PUT');
    expect(control(fixture, '#profile-name').value).toBe('Queued profile draft');
    const rotated = { ...verifiedActor, csrf_token: 'rotated-after-check' };
    client.setQueryData(['session'], rotated);
    fixture.componentRef.setInput('actor', rotated);
    fixture.componentRef.setInput('checking', false);
    fixture.detectChanges();
    // The same-owner projection is still fresh; checking must not refetch it.
    backend.expectNone('/api/v1/me/profile');
    submit(fixture);
    const retry = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    expect(retry.request.headers.get('x-csrf-token')).toBe(rotated.csrf_token);
    expect(retry.request.body).toMatchObject({
      display_name: 'Queued profile draft',
      expected_version: 2,
    });
    retry.flush({ ...revision, version: 3, display_name: 'Queued profile draft' });
    await load({
      profile: { ...revision, version: 3, display_name: 'Queued profile draft' },
      photo: null,
    });
    await shown(fixture, 'Profile saved.');
  });
  it('accepts its owned save receipt during identity checking without launching a private read', async () => {
    await load();
    edit('Committed owner draft');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    save.flush({ ...revision, version: 3, display_name: 'Committed owner draft' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(control(fixture, '#profile-name').value).toBe('Committed owner draft');
      expect(
        client.getQueryState(['account', verifiedActor.account_id, 'profile'])?.isInvalidated,
      ).toBe(true);
    });
    expect(control(fixture, '#profile-name').value).toBe('Committed owner draft');
    expect(
      client.getQueryState(['account', verifiedActor.account_id, 'profile'])?.isInvalidated,
    ).toBe(true);
    backend.expectNone('/api/v1/me/profile');
  });
  it('keeps a committed name when the subsequent canonical projection is older', async () => {
    await load();
    edit('Committed name');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    save.flush({ ...revision, version: 3, display_name: 'Committed name' });
    await load();
    expect(control(fixture, '#profile-name').value).toBe('Committed name');
    await shown(fixture, 'Your profile changed elsewhere');
    submit(fixture);
    backend.expectNone((request) => request.method === 'PUT');
  });

  it('ignores stale-owner and non-authority photo-assistance failures without erasing the name draft', async () => {
    await load();
    edit('Current private name');
    const advice = fixture.debugElement
      .query(By.directive(PhotoAssistance))
      .injector.get(PhotoAssistance);
    const expired = vi.fn();
    fixture.componentInstance.expired.subscribe(expired);
    advice.expired.emit({
      actorId: '00000000-0000-4000-8000-000000000099',
      failure: new ApiFailure(401, 'denied', null),
    });
    advice.expired.emit({
      actorId: verifiedActor.account_id,
      failure: new ApiFailure(503, 'unavailable', null),
    });
    expect(control(fixture, '#profile-name').value).toBe('Current private name');
    expect(expired).not.toHaveBeenCalled();
    backend.expectNone((request) => request.method !== 'GET');
  });
  for (const status of [401, 403]) {
    it(`retires the current owner name draft after photo-assistance authority failure ${String(status)}`, async () => {
      await load();
      edit('Private name to retire');
      const advice = fixture.debugElement
        .query(By.directive(PhotoAssistance))
        .injector.get(PhotoAssistance);
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      advice.expired.emit({
        actorId: verifiedActor.account_id,
        failure: new ApiFailure(status, 'denied', null),
      });
      expect(control(fixture, '#profile-name').value).toBe('');
      expect(client.getQueryData(['account', verifiedActor.account_id, 'profile'])).toBeUndefined();
      expect(expired).toHaveBeenCalledOnce();
      backend.expectNone((request) => request.method !== 'GET');
    });
  }
  it('preserves a committed profile receipt when the immediate canonical read has no projection yet', async () => {
    await load();
    edit('Committed without projection');
    submit(fixture);
    const write = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    write.flush({ ...revision, version: 3, display_name: 'Committed without projection' });
    await load({ profile: null, photo: null });
    expect(control(fixture, '#profile-name').value).toBe('Committed without projection');
    await shown(fixture, 'Your profile changed elsewhere');
    submit(fixture);
    backend.expectNone((request) => request.method === 'PUT');
  });
  it('retains a committed name and exposes canonical refresh failure without silently replaying', async () => {
    await load();
    edit('Committed before read failure');
    submit(fixture);
    const write = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    write.flush({ ...revision, version: 3, display_name: 'Committed before read failure' });
    const read = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'GET' }),
    );
    read.flush({ code: 'unavailable' }, { status: 503, statusText: 'Unavailable' });
    await shown(fixture, 'We couldn’t refresh your profile. Your draft is still here.');
    expect(control(fixture, '#profile-name').value).toBe('Committed before read failure');
    backend.expectNone((request) => request.method === 'PUT');
  });
  it('recovers a definitive validation rejection only through a corrected draft and a fresh save intent', async () => {
    await load();
    edit('Rejected profile draft');
    submit(fixture);
    const rejected = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    const rejectedKey = rejected.request.headers.get('idempotency-key');
    expect(rejectedKey).toMatch(/^[a-f0-9-]{36}$/);
    rejected.flush(
      { code: 'profile_validation_failed', title: 'PRIVATE VALIDATION DETAIL' },
      { status: 422, statusText: 'Invalid' },
    );
    await shown(fixture, 'We couldn’t save your profile');
    expect(host(fixture).textContent).not.toContain('PRIVATE VALIDATION DETAIL');
    expect(control(fixture, '#profile-name').value).toBe('Rejected profile draft');
    const input = host(fixture).querySelector('#profile-name');
    if (!(input instanceof HTMLInputElement)) throw new Error('Missing profile name input');
    expect(input.readOnly).toBe(false);
    backend.expectNone((request) => request.method === 'PUT');
    edit('Corrected profile draft');
    submit(fixture);
    const corrected = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    expect(corrected.request.headers.get('idempotency-key')).toMatch(/^[a-f0-9-]{36}$/);
    expect(corrected.request.headers.get('idempotency-key')).not.toBe(rejectedKey);
    expect(corrected.request.body).toMatchObject({
      display_name: 'Corrected profile draft',
      expected_version: 2,
    });
    const saved = { ...revision, display_name: 'Corrected profile draft', version: 3 };
    corrected.flush(saved);
    await load({ profile: saved, photo: null });
    await shown(fixture, 'Profile saved.');
    backend.expectNone((request) => request.method === 'PUT');
  });
  it('ignores a retired owner’s late forbidden save without clearing the replacement draft or authority', async () => {
    const expired = vi.fn();
    fixture.componentInstance.expired.subscribe(expired);
    await load();
    edit('Retired owner private draft');
    submit(fixture);
    const retired = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    const replacement = { ...verifiedActor, account_id: '00000000-0000-4000-8000-000000000098' };
    client.setQueryData(['session'], replacement);
    fixture.componentRef.setInput('actor', replacement);
    fixture.detectChanges();
    const saved = { ...revision, display_name: 'Replacement saved name', version: 4 };
    await load({ profile: saved, photo: null });
    edit('Replacement private draft');
    retired.flush({ code: 'access_denied' }, { status: 403, statusText: 'Denied' });
    await vi.waitFor(() => {
      expect(
        client
          .getMutationCache()
          .getAll()
          .some(
            (mutation: Readonly<Mutation>) =>
              mutation.state.status === 'error' &&
              mutation.state.error instanceof ApiFailure &&
              mutation.state.error.status === 403,
          ),
      ).toBe(true);
    });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(control(fixture, '#profile-name').value).toBe('Replacement private draft');
    expect(expired).not.toHaveBeenCalled();
    expect(client.getQueryData(['session'])).toEqual(replacement);
    expect(client.getQueryData(['account', replacement.account_id, 'profile'])).toEqual({
      profile: saved,
      photo: null,
    });
    backend.expectNone((request) => request.method === 'PUT');
    backend.expectNone('/api/v1/me/profile');
  });
});
