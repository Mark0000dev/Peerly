import { provideNoPhotoReview } from './profile/photo-review-unit.fixtures';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { Router } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { TuiDialogService } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { of } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../../api.generated';
import { appConfig } from '../../app.config';
import { ProfilePage } from './profile-page';
import { verifiedActor } from './onboarding.fixtures';
import { ownProfile, profileReference } from './profile/profile.fixtures';
import { ownGoal, catalogue } from './study/goal.fixtures';
import { ownHelp } from './study/help.fixtures';
import { ready, complete, receipt } from './setup/setup.fixtures';
import { click, shown, host, control } from './testing-host';

const active = {
  ...verifiedActor,
  registration: receipt,
  capabilities: { ...verifiedActor.capabilities, can_use_student_features: true },
} as const;
describe('P01 actual profile shell session, canonical reads and editor lifetimes', () => {
  let fixture: ComponentFixture<unknown>;
  let component: ProfilePage;
  let backend: HttpTestingController;
  let client: QueryClient;
  const confirm = vi.fn(() => of(false));
  let destroy: (() => void) | undefined;
  beforeEach(() => {
    TestBed.resetTestingModule();
    confirm.mockReset();
    confirm.mockReturnValue(of(false));
    destroy = undefined;
  });
  afterEach(() => {
    try {
      destroy?.();
    } finally {
      TestBed.resetTestingModule();
    }
  });
  async function mount(
    mode?: string,
    actor: Api['schemas']['IdentityResponse'] | null = verifiedActor,
    profileStatus = 200,
  ): Promise<void> {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    client.setQueryData(['session'], actor);
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideNoPhotoReview(),
        provideHttpClientTesting(),
        provideTanStackQuery(client),
        { provide: TuiDialogService, useValue: { open: confirm } },
      ],
    });
    TestBed.inject(Router).resetConfig([
      { path: 'profile', component: ProfilePage, data: { editor: mode } },
    ]);
    const harness = await RouterTestingHarness.create();
    fixture = harness.fixture;
    backend = TestBed.inject(HttpTestingController);
    destroy = () => {
      fixture.destroy();
      client.clear();
      backend.verify({ ignoreCancelled: true });
    };
    const navigation = harness.navigateByUrl('/profile', ProfilePage);
    const me = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    if (actor === null)
      me.flush({ code: 'session_required' }, { status: 401, statusText: 'Unauthorized' });
    else me.flush(actor);
    if (actor?.account_status === 'active' && actor.membership_status === 'verified') {
      if (mode === undefined) {
        if (profileStatus === 401) {
          await read('/api/v1/me/profile', { code: 'session_required' }, 401);
          await read('/api/v1/me', { code: 'session_required' }, 401);
        } else {
          await overview(profileStatus);
          if (actor.capabilities.can_use_student_features)
            await read('/api/v1/me/feedback-summary', {
              state: 'building',
              responses: 0,
              publicly_visible: true,
            });
        }
      } else if (mode === 'profile') {
        await read('/api/v1/me/profile', ownProfile);
        await read('/api/v1/profile-reference-data', profileReference);
      } else if (mode === 'goal') {
        await read('/api/v1/me/goal', ownGoal);
        await read('/api/v1/subjects?query=&limit=20', catalogue);
      } else if (mode === 'help') await read('/api/v1/me/help-subjects', ownHelp);
      else if (mode === 'blocks')
        await read('/api/v1/me/blocks', { people: [], next_cursor: null });
      else if (mode === 'visibility')
        await read(
          '/api/v1/me/onboarding',
          profileStatus === 200 ? complete : { code: 'temporarily_unavailable' },
          profileStatus,
        );
    }
    component = await navigation;
    fixture.detectChanges();
  }
  async function read(
    url: string,
    body: Readonly<Record<string, unknown>>,
    status = 200,
  ): Promise<void> {
    const request = await vi.waitFor(() => backend.expectOne({ url, method: 'GET' }));
    request.flush(body, { status, statusText: status === 200 ? 'OK' : 'Failure' });
  }
  async function overview(profileStatus = 200): Promise<void> {
    await read(
      '/api/v1/me/profile',
      profileStatus === 200 ? ownProfile : { code: 'temporarily_unavailable' },
      profileStatus,
    );
    await read('/api/v1/me/goal', ownGoal);
    await read('/api/v1/me/help-subjects', ownHelp);
    await read('/api/v1/me/onboarding', ready);
    await shown(
      fixture,
      profileStatus === 200
        ? ownProfile.profile.display_name
        : 'Some profile information could not be loaded.',
    );
  }
  it('projects actual owned profile, goal and help without edits, guessed counts or a synthetic activation', async () => {
    await mount();
    expect(host(fixture).textContent).toContain(ownGoal.goal.subject.label);
    expect(host(fixture).textContent).toContain(ownHelp.selection.subjects[0].label);
    expect(host(fixture).querySelector('a[href="/profile/edit"]')).not.toBeNull();
    expect(await component.canLeave()).toBe(true);
    expect(confirm).not.toHaveBeenCalled();
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('retries failed overview reads explicitly with the same actual query namespace', async () => {
    await mount(undefined, verifiedActor, 503);
    click(fixture, 'Retry profile information');
    await overview();
    expect(client.getQueryData(['account', verifiedActor.account_id, 'profile'])).toEqual(
      ownProfile,
    );
  });
  it('renders own feedback only for the actual activated capability and does not mirror its DTO', async () => {
    await mount(undefined, active);
    await shown(fixture, 'feedback');
    expect(client.getQueryData(['account', active.account_id, 'feedback-summary'])).toMatchObject({
      state: 'building',
      responses: 0,
    });
  });
  it('shows actual sign-out, clears private query/mutation state, and does not navigate to a fake callback', async () => {
    await mount();
    click(fixture, 'Sign out');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/auth/logout'));
    expect(request.request.headers.get('x-csrf-token')).toBe(verifiedActor.csrf_token);
    request.flush(null);
    await shown(fixture, 'Sign in');
    expect(client.getQueryData(['session'])).toBeNull();
    expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });
  it('treats a lost sign-out response as unknown and checks the real session before allowing any further private command', async () => {
    await mount();
    click(fixture, 'Sign out');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/auth/logout'));
    request.error(new ProgressEvent('error'));
    await read('/api/v1/me', { code: 'session_required' }, 401);
    await shown(fixture, 'Sign in');
    expect(client.getQueryData(['session'])).toBeNull();
    backend.expectNone((pending) => pending.method === 'PUT');
  });
  it('revalidates denied private reads and retires the account instead of rendering stale owned data', async () => {
    await mount(undefined, verifiedActor, 401);
    await shown(fixture, 'Sign in');
    expect(client.getQueryCache().findAll({ queryKey: ['account'] })).toHaveLength(0);
  });
  it('does not issue private reads for a signed-out actor', async () => {
    await mount(undefined, null);
    await shown(fixture, 'Sign in');
    expect(await component.canLeave()).toBe(true);
    backend.expectNone((request) => request.url !== '/api/v1/me');
  });
  it('keeps banned/revoked accounts in the existing recovery flow', async () => {
    await mount(undefined, { ...verifiedActor, account_status: 'banned' });
    await shown(fixture, 'Your student account needs attention');
    backend.expectNone((request) => request.url !== '/api/v1/me');
  });
  it('loads the actual visibility state and makes read failure retryable without extra profile/goal reads', async () => {
    await mount('visibility', verifiedActor, 503);
    await shown(fixture, 'Profile visibility could not be loaded.');
    click(fixture, 'Retry visibility');
    await read('/api/v1/me/onboarding', complete);
    await shown(fixture, 'Your profile can appear in Discover.');
    backend.expectNone('/api/v1/me/profile');
    backend.expectNone('/api/v1/me/goal');
  });
  it('delegates dirty profile exit to the shared public confirmation and retains the actual form when cancelled', async () => {
    await mount('profile');
    await shown(fixture, 'About · optional');
    control(fixture, '#profile-about').setValue('Unsent private draft');
    control(fixture, '#profile-about').markAsDirty();
    expect(await component.canLeave()).toBe(false);
    expect(control(fixture, '#profile-about').value).toBe('Unsent private draft');
    confirm.mockReturnValueOnce(of(true));
    expect(await component.canLeave()).toBe(true);
    backend.expectNone((request) => request.method === 'PUT');
  });
  it('delegates the clean Goal editor lifetime without a second QueryClient or a copied draft', async () => {
    await mount('goal');
    await shown(fixture, 'Save goal');
    expect(await component.canLeave()).toBe(true);
    expect(confirm).not.toHaveBeenCalled();
  });
  it('delegates the clean Help editor lifetime and reads its catalogue only when requested', async () => {
    await mount('help');
    await shown(fixture, 'Changes apply after you save.');
    expect(await component.canLeave()).toBe(true);
    backend.expectNone('/api/v1/subjects?query=&limit=20');
  });
  it('mounts the actual owner blocked-list consumer without speculative peer reads', async () => {
    await mount('blocks');
    await shown(fixture, 'No blocked people on this page.');
    backend.expectNone('/api/v1/me/profile');
    backend.expectNone('/api/v1/me/goal');
  });
});
