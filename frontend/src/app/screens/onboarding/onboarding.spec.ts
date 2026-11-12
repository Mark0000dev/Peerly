import { host, shown, control, submit, click } from './testing-host';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { Capacitor } from '@capacitor/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../app.config';
import { Onboarding } from './onboarding';
import { HelpSubjects } from './study/help';
import { By } from '@angular/platform-browser';
import { firstValueFrom, Subject } from 'rxjs';
import { actor, pending, challenge, verifiedActor } from './onboarding.fixtures';

describe('Google identity and institutional verification screen', () => {
  let fixture: ComponentFixture<Onboarding>;
  let client: QueryClient;
  let backend: HttpTestingController;
  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: {
        queries: { retry: false, refetchOnWindowFocus: false },
        mutations: { retry: false },
      },
    });
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(Onboarding);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify();
    vi.restoreAllMocks();
  });
  async function me(value: Readonly<Record<string, unknown>> = actor, status = 200): Promise<void> {
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    request.flush(value, { status, statusText: status === 200 ? 'OK' : 'Failure' });
  }
  async function status(value: Readonly<Record<string, unknown>> = challenge): Promise<void> {
    const request = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/auth/email-challenges/${challenge.id}`),
    );
    request.flush(value);
  }

  it('returns from a real setup editor without a fake route or retained private draft', async () => {
    await me(verifiedActor);
    await shown(fixture, 'Your help areas');
    click(fixture, 'Your help areas');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/help-subjects'));
    request.flush({ selection: null });
    await shown(fixture, 'Add something you can help with.');
    click(fixture, 'Back to setup');
    await shown(fixture, 'Your profile');
    expect(host(fixture).textContent).not.toContain('Add something you can help with.');
  });
  it('does not apply an old editor leave decision to a replacement account', async () => {
    await me(verifiedActor);
    await shown(fixture, 'Your help areas');
    click(fixture, 'Your help areas');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/help-subjects'));
    request.flush({ selection: null });
    await shown(fixture, 'Add something you can help with.');
    const node = fixture.debugElement.query(By.directive(HelpSubjects));
    const editor = node.injector.get(HelpSubjects);
    const decision = new Subject<boolean>();
    vi.spyOn(editor, 'confirmLeave').mockReturnValue(firstValueFrom(decision));
    click(fixture, 'Review saved setup');
    client.setQueryData(['session'], {
      ...verifiedActor,
      account_id: '00000000-0000-0000-0000-000000000003',
    });
    fixture.detectChanges();
    decision.next(true);
    decision.complete();
    await fixture.whenStable();
    await shown(fixture, 'Your APU email is confirmed');
    expect(host(fixture).textContent).not.toContain('Review your setup');
    backend.expectNone('/api/v1/me/onboarding');
  });
  it('renders Google navigation without manufacturing legal receipts or identity data', async () => {
    await me({ code: 'unauthenticated' }, 401);
    await shown(fixture, 'Continue with Google');
    const link = host(fixture).querySelector('a[href^="/api/v1/auth/google/start"]');
    expect(link?.getAttribute('href')).toBe('/api/v1/auth/google/start?return_to=/onboarding');
    expect(host(fixture).querySelectorAll('input[type=checkbox]')).toHaveLength(0);
    expect(host(fixture).textContent).not.toContain('fixture-csrf');
  });
  it('does not send native users into an embedded Google web view', async () => {
    await me({ code: 'unauthenticated' }, 401);
    await shown(fixture, 'Continue with Google');
    fixture.destroy();
    vi.spyOn(Capacitor, 'isNativePlatform').mockReturnValue(true);
    fixture = TestBed.createComponent(Onboarding);
    fixture.detectChanges();
    await me({ code: 'unauthenticated' }, 401);
    await shown(fixture, 'Use Peerly in a web browser');
    expect(host(fixture).querySelector('a[href^="/api/v1/auth/google/start"]')).toBeNull();
  });
  it('keeps server bootstrap failure recoverable', async () => {
    await me({ code: 'unavailable' }, 503);
    await shown(fixture, 'We couldn’t check your sign-in');
    click(fixture, 'Try again');
    await me({ code: 'unauthenticated' }, 401);
    await shown(fixture, 'Continue with Google');
  });
  for (const value of [
    { ...actor, account_status: 'banned' },
    {
      ...actor,
      membership_status: 'revoked',
      capabilities: { ...actor.capabilities, can_verify_student_email: false },
    },
    { ...actor, membership_status: 'verified', verified_at: '2026-11-07T12:00:00Z' },
  ]) {
    it(`honours actual account capabilities ${JSON.stringify(value)}`, async () => {
      await me(value);
      await shown(fixture, 'Signed in with Google');
      expect(host(fixture).querySelector('input')).toBeNull();
    });
  }
  it('clears another account’s verification draft and private mutation cache on identity replacement', async () => {
    await me();
    await shown(fixture, 'Confirm your APU email');
    control(fixture, '#student-email').setValue('private@mail.apu.edu.my');
    const mutation = client.getMutationCache().build(client, {
      mutationFn: (value: Readonly<{ readonly draft: string }>) => Promise.resolve(value.draft),
    });
    await mutation.execute({ draft: 'old account private draft' });
    click(fixture, 'Check status');
    await me({ ...actor, account_id: '00000000-0000-0000-0000-000000000088' });
    await shown(fixture, 'Confirm your APU email');
    expect(control(fixture, '#student-email').value).toBe('');
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });
  for (const outcome of [200, 401, 503]) {
    it(`ignores an old account's late send ${String(outcome)} after identity replacement`, async () => {
      await me();
      await shown(fixture, 'Confirm your APU email');
      control(fixture, '#student-email').setValue(challenge.email);
      submit(fixture);
      const send = await vi.waitFor(() => backend.expectOne('/api/v1/auth/email-challenges'));
      click(fixture, 'Check status');
      await me({ ...actor, account_id: '00000000-0000-0000-0000-000000000088' });
      await shown(fixture, 'Confirm your APU email');
      control(fixture, '#student-email').setValue('new-draft@mail.apu.edu.my');
      send.flush(
        outcome === 200
          ? { id: challenge.id, expires_at: challenge.expires_at, resend_at: challenge.resend_at }
          : { code: 'unavailable' },
        { status: outcome, statusText: outcome === 200 ? 'OK' : 'Failure' },
      );
      await shown(fixture, 'Confirm your APU email');
      expect(control(fixture, '#student-email').value).toBe('new-draft@mail.apu.edu.my');
      backend.expectNone('/api/v1/me');
    });
  }
  it('validates the actual exact-domain field and preserves invalid input', async () => {
    await me();
    await shown(fixture, 'Confirm your APU email');
    submit(fixture);
    await shown(fixture, 'Enter a student address');
    control(fixture, '#student-email').setValue('student@gmail.com');
    submit(fixture);
    expect(control(fixture, '#student-email').value).toBe('student@gmail.com');
    backend.expectNone((request) => request.method === 'POST');
  });
  it('creates an actor-bound challenge with CSRF and stable intent metadata', async () => {
    await me();
    await shown(fixture, 'Confirm your APU email');
    control(fixture, '#student-email').setValue(challenge.email);
    submit(fixture);
    submit(fixture);
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/auth/email-challenges'));
    expect(request.request.headers.get('x-csrf-token')).toBe(actor.csrf_token);
    expect(request.request.headers.get('idempotency-key')).toMatch(/^[a-zA-Z0-9_-]{8,128}$/);
    expect(request.request.body).toEqual({ email: challenge.email });
    request.flush(
      { id: challenge.id, expires_at: challenge.expires_at, resend_at: challenge.resend_at },
      { status: 202, statusText: 'Accepted' },
    );
    await me(pending);
    await status();
    await shown(fixture, 'Check your APU email');
  });
  it('retries an uncertain send with the same key and never says nothing was sent', async () => {
    await me();
    await shown(fixture, 'Confirm your APU email');
    control(fixture, '#student-email').setValue(challenge.email);
    submit(fixture);
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/auth/email-challenges'));
    const key = request.request.headers.get('idempotency-key');
    request.error(new ProgressEvent('error'));
    await me();
    await shown(fixture, 'We couldn’t confirm the result');
    expect(control(fixture, '#student-email').value).toBe(challenge.email);
    expect(host(fixture).textContent).not.toContain('Nothing was sent');
    submit(fixture);
    const retried = await vi.waitFor(() => backend.expectOne('/api/v1/auth/email-challenges'));
    expect(retried.request.headers.get('idempotency-key')).toBe(key);
    retried.flush({
      id: challenge.id,
      expires_at: challenge.expires_at,
      resend_at: challenge.resend_at,
    });
    await me(pending);
    await status();
    await shown(fixture, 'Check your APU email');
  });
  it('confirms six digits once and refreshes authoritative membership', async () => {
    await me(pending);
    await status();
    await shown(fixture, 'Check your APU email');
    control(fixture, '#verification-code').setValue('123456');
    const request = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/auth/email-challenges/${challenge.id}/verify`),
    );
    expect(request.request.body).toEqual({ code: '123456' });
    request.flush({ verified_at: '2026-11-07T12:00:00Z' });
    await me({ ...actor, membership_status: 'verified', verified_at: '2026-11-07T12:00:00Z' });
    await shown(fixture, 'Your APU email is confirmed');
  });
  it('retains incorrect digits and uses remaining attempts from the status response', async () => {
    await me(pending);
    await status();
    await shown(fixture, 'Check your APU email');
    control(fixture, '#verification-code').setValue('123456');
    const request = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/auth/email-challenges/${challenge.id}/verify`),
    );
    request.flush({ code: 'verification_wrong' }, { status: 422, statusText: 'Wrong' });
    await me(pending);
    await status({ ...challenge, verification_outcome: 'wrong', attempts_remaining: 4 });
    await shown(fixture, 'Attempts remaining: 4');
    expect(control(fixture, '#verification-code').value).toBe('123456');
  });
  it('service acceptance never confirms inbox delivery and quarantine help cannot bypass server resend permission', async () => {
    await me(pending);
    await status();
    await shown(fixture, 'The mail service accepted');
    const text = host(fixture).textContent.replace(/\s+/g, ' ');
    expect(text).toContain('This does not confirm delivery to your inbox');
    expect(text).toContain('quarantine');
    expect(host(fixture).querySelector('a[href="/help/contact"]')).not.toBeNull();
    const resend = Array.from(host(fixture).querySelectorAll('button')).find(
      (button: Readonly<HTMLButtonElement>) => button.textContent.trim() === 'Resend code',
    );
    expect(resend?.disabled).toBe(true);
    expect(text).toContain('Resend available after');
    backend.expectNone((request) => request.method !== 'GET');
    click(fixture, 'Check status');
    await me(pending);
    await status({ ...challenge, delivery: 'queued', can_verify: false });
    await shown(fixture, 'not confirmed acceptance yet');
    expect(host(fixture).textContent).not.toContain('The mail service accepted');
    expect(host(fixture).querySelector<HTMLInputElement>('#verification-code')?.readOnly).toBe(
      true,
    );
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('resends only after explicit server permission and supersedes using the current reference', async () => {
    await me(pending);
    await status({ ...challenge, can_resend: true });
    await shown(fixture, 'Check your APU email');
    click(fixture, 'Resend code');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/auth/email-challenges'));
    expect(request.request.body).toEqual({ email: challenge.email, resend_of: challenge.id });
    request.flush({
      id: challenge.id,
      expires_at: challenge.expires_at,
      resend_at: challenge.resend_at,
    });
    await me(pending);
    await status();
    await shown(fixture, 'Check your APU email');
  });
  it('changing email is local until an explicit replacement send', async () => {
    await me(pending);
    await status();
    await shown(fixture, 'Check your APU email');
    click(fixture, 'Change email');
    await shown(fixture, 'Confirm your APU email');
    expect(control(fixture, '#student-email').value).toBe(challenge.email);
    backend.expectNone((request) => request.method !== 'GET');
  });
  for (const value of [
    { ...challenge, state: 'locked', can_verify: false },
    { ...challenge, state: 'expired', can_verify: false, can_resend: true },
    { ...challenge, delivery: 'failed' },
    {
      ...challenge,
      state: 'consumed',
      verification_outcome: 'support_required',
      can_verify: false,
    },
  ]) {
    it(`restores actual challenge state after reload ${JSON.stringify(value)}`, async () => {
      await me(pending);
      await status(value);
      await shown(fixture, 'Signed in with Google');
      expect(host(fixture).textContent).not.toContain('Nothing was sent');
    });
  }
  it('clears drafts and private cache on logout without persisting credentials', async () => {
    await me();
    await shown(fixture, 'Confirm your APU email');
    control(fixture, '#student-email').setValue(challenge.email);
    client.setQueryData(['account', actor.account_id, 'fixture'], { private: 'data' });
    click(fixture, 'Sign out');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/auth/logout'));
    expect(request.request.headers.get('x-csrf-token')).toBe(actor.csrf_token);
    request.flush(null, { status: 204, statusText: 'No Content' });
    await me({ code: 'unauthenticated' }, 401);
    await shown(fixture, 'Continue with Google');
    expect(client.getQueryData(['account', actor.account_id, 'fixture'])).toBeUndefined();
  });
});
