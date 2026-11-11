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
});
