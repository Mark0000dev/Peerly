import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TuiDialogService } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../app.config';
import { verifiedActor } from '../onboarding.fixtures';
import { click, shown } from '../testing-host';
import { goal } from '../study/goal.fixtures';
import { CompleteGoal } from './complete-goal';

describe('explicit goal completion command', () => {
  let fixture: ComponentFixture<CompleteGoal>;
  let backend: HttpTestingController;
  let client: QueryClient;
  let confirmation: Subject<boolean>;
  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    client.setQueryData(['session'], verifiedActor);
    confirmation = new Subject<boolean>();
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideHttpClientTesting(),
        provideTanStackQuery(client),
        { provide: TuiDialogService, useValue: { open: () => confirmation } },
      ],
    });
    fixture = TestBed.createComponent(CompleteGoal);
    fixture.componentRef.setInput('actorId', verifiedActor.account_id);
    fixture.componentRef.setInput('goal', goal);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    confirmation.complete();
    client.clear();
    backend.verify({ ignoreCancelled: true });
  });
  it('sends no command before confirmation and retains CAS/key after a lost response', async () => {
    click(fixture, 'Mark goal done');
    backend.expectNone('/api/v1/me/goal/complete');
    confirmation.next(true);
    const first = await vi.waitFor(() => backend.expectOne('/api/v1/me/goal/complete'));
    expect(first.request.body).toEqual({ goal_id: goal.id, expected_version: goal.version });
    expect(first.request.headers.get('x-csrf-token')).toBe(verifiedActor.csrf_token);
    const key = first.request.headers.get('idempotency-key');
    first.error(new ProgressEvent('error'));
    await shown(fixture, 'Retry same completion');
    click(fixture, 'Retry same completion');
    const retry = await vi.waitFor(() => backend.expectOne('/api/v1/me/goal/complete'));
    expect(retry.request.body).toEqual(first.request.body);
    expect(retry.request.headers.get('idempotency-key')).toBe(key);
    retry.flush({ ...goal, version: 3, completed_at: '2026-11-09T08:00:00Z' });
    await shown(fixture, 'Goal completed.');
  });
  it('does not complete a changed goal after a delayed confirmation', async () => {
    click(fixture, 'Mark goal done');
    fixture.componentRef.setInput('goal', { ...goal, version: 3 });
    fixture.detectChanges();
    confirmation.next(true);
    await Promise.resolve();
    backend.expectNone('/api/v1/me/goal/complete');
  });
  it('does not complete a former owner goal after account replacement', async () => {
    click(fixture, 'Mark goal done');
    client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement' });
    confirmation.next(true);
    await Promise.resolve();
    backend.expectNone('/api/v1/me/goal/complete');
  });
  it('lets cancellation finish without any server mutation', async () => {
    click(fixture, 'Mark goal done');
    confirmation.next(false);
    await Promise.resolve();
    backend.expectNone('/api/v1/me/goal/complete');
  });
  it('exposes a version conflict and invalidates canonical state only after explicit reload', async () => {
    client.setQueryData(['account', verifiedActor.account_id, 'goal'], { goal });
    click(fixture, 'Mark goal done');
    confirmation.next(true);
    const write = await vi.waitFor(() => backend.expectOne('/api/v1/me/goal/complete'));
    write.flush({ code: 'goal_version_conflict' }, { status: 409, statusText: 'Conflict' });
    await shown(fixture, 'Reload saved goal');
    expect(client.getQueryState(['account', verifiedActor.account_id, 'goal'])?.isInvalidated).toBe(
      false,
    );
    click(fixture, 'Reload saved goal');
    await vi.waitFor(() => {
      expect(
        client.getQueryState(['account', verifiedActor.account_id, 'goal'])?.isInvalidated,
      ).toBe(true);
    });
    backend.expectNone('/api/v1/me/goal/complete');
  });
  it('propagates denied current-owner completion to the real session boundary without claiming success', async () => {
    const expired = vi.fn();
    fixture.componentInstance.expired.subscribe(expired);
    click(fixture, 'Mark goal done');
    confirmation.next(true);
    const write = await vi.waitFor(() => backend.expectOne('/api/v1/me/goal/complete'));
    write.flush({ code: 'membership_required' }, { status: 403, statusText: 'Forbidden' });
    await shown(fixture, 'Your goal could not be completed.');
    expect(expired).toHaveBeenCalledOnce();
    backend.expectNone('/api/v1/me/goal/complete');
  });

  it('emits current-owner authentication loss once without completing the goal', async () => {
    const expired = vi.fn();
    fixture.componentInstance.expired.subscribe(expired);
    click(fixture, 'Mark goal done');
    confirmation.next(true);
    (await vi.waitFor(() => backend.expectOne('/api/v1/me/goal/complete'))).flush(
      { code: 'unauthenticated' },
      { status: 401, statusText: 'Unauthorized' },
    );
    await shown(fixture, 'Your goal could not be completed.');
    expect(expired).toHaveBeenCalledOnce();
    backend.expectNone('/api/v1/me/goal/complete');
  });
  for (const status of [200, 401, 403]) {
    it(`ignores a retired owner's late completion ${String(status)} without invalidating replacement state`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      click(fixture, 'Mark goal done');
      confirmation.next(true);
      const write = await vi.waitFor(() => backend.expectOne('/api/v1/me/goal/complete'));
      const replacement = { ...verifiedActor, account_id: 'replacement-owner' };
      client.setQueryData(['session'], replacement);
      fixture.componentRef.setInput('actorId', replacement.account_id);
      fixture.detectChanges();
      const replacementKey = ['account', replacement.account_id, 'goal'];
      client.setQueryData(replacementKey, { goal });
      if (status === 200)
        write.flush({ ...goal, version: 3, completed_at: '2026-11-09T08:00:00Z' });
      else write.flush({ code: 'denied' }, { status, statusText: 'Denied' });
      await fixture.whenStable();
      expect(client.getQueryState(replacementKey)?.isInvalidated).toBe(false);
      expect(client.getMutationCache().getAll()).toHaveLength(0);
      expect(expired).not.toHaveBeenCalled();
      backend.expectNone('/api/v1/me/goal/complete');
    });
  }
  it('rejects a confirmation for a different goal even when its version is the same', async () => {
    click(fixture, 'Mark goal done');
    fixture.componentRef.setInput('goal', { ...goal, id: '00000000-0000-4000-8000-000000000099' });
    fixture.detectChanges();
    confirmation.next(true);
    await fixture.whenStable();
    backend.expectNone('/api/v1/me/goal/complete');
  });
  it('does not complete a goal when sign-in checking begins while confirmation is open', async () => {
    click(fixture, 'Mark goal done');
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    confirmation.next(true);
    await fixture.whenStable();
    backend.expectNone('/api/v1/me/goal/complete');
  });
  it('keeps a successful owned completion invalidation deferred while membership is unavailable', async () => {
    const key = ['account', verifiedActor.account_id, 'goal'];
    client.setQueryData(key, { goal });
    click(fixture, 'Mark goal done');
    confirmation.next(true);
    const write = await vi.waitFor(() => backend.expectOne('/api/v1/me/goal/complete'));
    client.setQueryData(['session'], { ...verifiedActor, membership_status: 'unverified' });
    write.flush({ ...goal, version: 3, completed_at: '2026-11-09T08:00:00Z' });
    await shown(fixture, 'Goal completed.');
    expect(client.getQueryState(key)?.isInvalidated).toBe(true);
    backend.expectNone('/api/v1/me/goal');
  });

  it('offers no completion action for an already completed canonical goal', async () => {
    fixture.componentRef.setInput('goal', {
      ...goal,
      version: 3,
      completed_at: '2026-11-09T08:00:00Z',
    });
    fixture.detectChanges();
    await fixture.whenStable();
    const element: unknown = fixture.nativeElement;
    if (!(element instanceof HTMLElement)) throw new Error('Missing goal-completion host');
    expect(element.querySelector('button')).toBeNull();
    backend.expectNone('/api/v1/me/goal/complete');
  });
});
