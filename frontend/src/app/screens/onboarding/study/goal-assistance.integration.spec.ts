import { Component, input, output } from '@angular/core';
import { TuiRoot } from '@taiga-ui/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../../../api.generated';
import { ApiFailure } from '../../../api-http';
import { appConfig } from '../../../app.config';
import { verifiedActor } from '../onboarding.fixtures';
import { host, shown, control, submit, click } from '../testing-host';
import { StudyGoal } from './goal';
import { catalogue, goal, ownGoal } from './goal.fixtures';
import { GoalAssistance } from './ai/goal-assistance';

@Component({
  imports: [TuiRoot, StudyGoal],
  template: `<tui-root
    ><peerly-study-goal [actor]="actor()" (expired)="expired.emit()"
  /></tui-root>`,
})
class AssistedGoalHost {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
  public readonly expired = output();
}

describe('actual Goal form and optional AI integration', () => {
  let fixture: ComponentFixture<AssistedGoalHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(async () => {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    client.setQueryData(['session'], verifiedActor);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(AssistedGoalHost);
    fixture.componentRef.setInput('actor', verifiedActor);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    const subjects = await vi.waitFor(() => backend.expectOne('/api/v1/subjects?query=&limit=20'));
    subjects.flush(catalogue);
    const read = await vi.waitFor(() => backend.expectOne('/api/v1/me/goal'));
    read.flush(ownGoal);
    await shown(fixture, 'Suggest clearer wording');
  });
  afterEach(() => {
    try {
      fixture.destroy();
      client.clear();
      backend.verify({ ignoreCancelled: true });
    } finally {
      TestBed.resetTestingModule();
    }
  });
  function assistance(): GoalAssistance {
    return fixture.debugElement.query(By.directive(GoalAssistance)).injector.get(GoalAssistance);
  }
  function editContext(value: string): void {
    control(fixture, '#goal-context').setValue(value);
    control(fixture, '#goal-context').markAsDirty();
    fixture.detectChanges();
  }
  async function suggestion(value = 'A clearer context'): Promise<void> {
    const source = assistance().draft().source;
    click(fixture, 'Suggest clearer wording');
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/ai/jobs', method: 'POST' }),
    );
    expect(request.request.body).toEqual({
      kind: 'clarify_goal',
      source,
      target: 'context',
      text: control(fixture, '#goal-context').value,
    });
    const response: Api['schemas']['JobResponse'] = {
      id: '00000000-0000-4000-8000-000000000099',
      kind: 'clarify_goal',
      source: { ...source, content_hash: '1'.repeat(64) },
      target: 'context',
      state: 'succeeded',
      created_at: new Date().toISOString(),
      deadline: new Date(Date.now() + 60000).toISOString(),
      result: { suggestion: value },
      failure: null,
      poll_after_ms: null,
    };
    request.flush(response);
    await shown(fixture, 'Review before using');
  }
  it('real503-shaped unavailability never blocks the separate explicit manual goal save', async () => {
    click(fixture, 'Suggest clearer wording');
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/ai/jobs', method: 'POST' }),
    );
    request.flush({ code: 'ai_unavailable' }, { status: 503, statusText: 'Unavailable' });
    await shown(fixture, 'AI assistance isn’t available right now');
    expect(control(fixture, '#goal-context').value).toBe(goal.context);
    backend.expectNone((request) => request.method === 'PUT');
    editContext('My manually edited context');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
    );
    expect(save.request.body).toEqual(
      expect.objectContaining({
        context: 'My manually edited context',
        expected_version: 2,
        expected_goal_id: goal.id,
      }),
    );
    save.flush({ ...goal, version: 3, context: 'My manually edited context' });
    const read = await vi.waitFor(() => backend.expectOne('/api/v1/me/goal'));
    read.flush({ goal: { ...goal, version: 3, context: 'My manually edited context' } });
    await shown(fixture, 'Goal saved.');
    backend.expectNone('/api/v1/ai/jobs');
  });
  it('explicit Apply edits only the form, and Back to my text restores the owned original', async () => {
    const original = control(fixture, '#goal-context').value;
    await suggestion();
    click(fixture, 'Use suggestion');
    await shown(fixture, 'Suggestion applied · not saved');
    expect(control(fixture, '#goal-context').value).toBe('A clearer context');
    expect(control(fixture, '#goal-context').dirty).toBe(true);
    backend.expectNone((request) => request.method === 'PUT');
    click(fixture, 'Back to my text');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(control(fixture, '#goal-context').value).toBe(original);
    });
    expect(host(fixture).textContent).not.toContain('Suggestion applied · not saved');
    backend.expectNone((request) => request.method === 'PUT');
  });
  it('an applied suggestion is persisted only by the normal explicit CAS Save', async () => {
    await suggestion();
    click(fixture, 'Use suggestion');
    await shown(fixture, 'Suggestion applied · not saved');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
    );
    expect(save.request.body).toEqual(
      expect.objectContaining({
        context: 'A clearer context',
        topic: goal.topic,
        expected_version: 2,
        expected_goal_id: goal.id,
      }),
    );
    save.flush({ ...goal, version: 3, context: 'A clearer context' });
    const read = await vi.waitFor(() => backend.expectOne('/api/v1/me/goal'));
    read.flush({ goal: { ...goal, version: 3, context: 'A clearer context' } });
    await shown(fixture, 'Goal saved.');
  });
  it('a catalogue result selects only a current known canonical area without changing the task', async () => {
    const source = assistance().draft().source;
    click(fixture, 'Suggest a knowledge area');
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/ai/jobs', method: 'POST' }),
    );
    expect(request.request.body).toEqual({
      kind: 'suggest_subject',
      source,
      label: goal.subject.label,
      candidate_ids: catalogue.items.map((item) => item.id),
    });
    request.flush({
      id: '00000000-0000-4000-8000-000000000098',
      kind: 'suggest_subject',
      source: { ...source, content_hash: '2'.repeat(64) },
      target: null,
      state: 'succeeded',
      created_at: new Date().toISOString(),
      deadline: new Date(Date.now() + 60000).toISOString(),
      result: { ids: [catalogue.items[1].id] },
      failure: null,
      poll_after_ms: null,
    } satisfies Api['schemas']['JobResponse']);
    await shown(fixture, 'Review before using');
    click(fixture, `Use ${catalogue.items[1].name}`);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(control(fixture, '#goal-subject').value).toEqual(
        expect.objectContaining({
          kind: 'canonical',
          id: catalogue.items[1].id,
          label: catalogue.items[1].name,
        }),
      );
    });
    expect(control(fixture, '#goal-topic').value).toBe(goal.topic);
    backend.expectNone((request) => request.method === 'PUT');
  });
  it('ignores stale text/area outputs, unknown IDs and any result during a parent conflict', async () => {
    const child = assistance();
    const oldSource = child.draft().source;
    editContext('Keep this newer draft');
    child.applyText.emit({ source: oldSource, target: 'context', value: 'Old suggestion' });
    child.applyArea.emit({ source: oldSource, id: catalogue.items[1].id });
    expect(control(fixture, '#goal-context').value).toBe('Keep this newer draft');
    const source = child.draft().source;
    child.applyArea.emit({ source, id: '00000000-0000-4000-8000-000000000097' });
    expect(control(fixture, '#goal-subject').value).toEqual(
      expect.objectContaining({ id: catalogue.items[0].id }),
    );
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/goal', method: 'PUT' }),
    );
    save.flush({ code: 'goal_version_conflict' }, { status: 409, statusText: 'Conflict' });
    await shown(fixture, 'Your goal changed elsewhere');
    child.applyText.emit({
      source: child.draft().source,
      target: 'context',
      value: 'Blocked during conflict',
    });
    expect(control(fixture, '#goal-context').value).toBe('Keep this newer draft');
  });
  it('does not apply or undo against pending, failed, missing or different session authority', async () => {
    const child = assistance();
    const source = child.draft().source;
    let release: () => void = () => {
      throw new Error('Missing response gate');
    };
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const pending = client.query({
      queryKey: ['session'],
      queryFn: async () => {
        await gate;
        return verifiedActor;
      },
    });
    try {
      child.applyText.emit({ source, target: 'context', value: 'Pending suggestion' });
      expect(control(fixture, '#goal-context').value).toBe(goal.context);
    } finally {
      release();
      await pending;
    }
    await expect(
      client.query({
        queryKey: ['session'],
        queryFn: () => Promise.reject(new Error('Check failed')),
      }),
    ).rejects.toThrow('Check failed');
    child.applyText.emit({ source, target: 'context', value: 'Failed authority suggestion' });
    expect(control(fixture, '#goal-context').value).toBe(goal.context);
    client.removeQueries({ queryKey: ['session'] });
    child.applyArea.emit({ source, id: catalogue.items[1].id });
    expect(control(fixture, '#goal-subject').value).toEqual(
      expect.objectContaining({ id: catalogue.items[0].id }),
    );
    client.setQueryData(['session'], { ...verifiedActor, account_id: 'replacement-actor' });
    child.applyText.emit({ source, target: 'context', value: 'Other actor suggestion' });
    expect(control(fixture, '#goal-context').value).toBe(goal.context);
  });
  it('same-actor metadata refresh preserves draft identity; edits retire the Undo history', async () => {
    editContext('Private unsaved text');
    const before = assistance().draft();
    fixture.componentRef.setInput('actor', { ...verifiedActor, csrf_token: 'fresh-csrf' });
    fixture.detectChanges();
    expect(assistance().draft().source).toEqual(before.source);
    expect(control(fixture, '#goal-context').value).toBe('Private unsaved text');
    const child = assistance();
    child.applyText.emit({
      source: child.draft().source,
      target: 'topic',
      value: 'A revised task',
    });
    await shown(fixture, 'Suggestion applied · not saved');
    expect(control(fixture, '#goal-topic').value).toBe('A revised task');
    click(fixture, 'Back to my text');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(control(fixture, '#goal-topic').value).toBe(goal.topic);
    });
    child.applyText.emit({ source: child.draft().source, target: 'context', value: 'New context' });
    await shown(fixture, 'Suggestion applied · not saved');
    editContext('Further manual edit');
    expect(host(fixture).textContent).not.toContain('Back to my text');
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('ignores retired/non-auth expiry outputs and never erases a replacement actor cache', () => {
    const child = assistance();
    const expired = vi.fn();
    fixture.componentInstance.expired.subscribe(expired);
    child.expired.emit({
      actorId: 'old-actor',
      failure: new ApiFailure(401, 'unauthenticated', null),
    });
    child.expired.emit({
      actorId: verifiedActor.account_id,
      failure: new ApiFailure(503, 'ai_unavailable', null),
    });
    expect(expired).not.toHaveBeenCalled();
    const replacement = { ...verifiedActor, account_id: 'replacement-actor' };
    client.setQueryData(['session'], replacement);
    client.setQueryData(['account', replacement.account_id, 'goal'], ownGoal);
    child.expired.emit({
      actorId: verifiedActor.account_id,
      failure: new ApiFailure(403, 'account_unavailable', null),
    });
    expect(client.getQueryData(['account', replacement.account_id, 'goal'])).toEqual(ownGoal);
    expect(expired).not.toHaveBeenCalled();
    client.setQueryData(['session'], verifiedActor);
    child.expired.emit({
      actorId: verifiedActor.account_id,
      failure: new ApiFailure(401, 'unauthenticated', null),
    });
    expect(expired).toHaveBeenCalledOnce();
    expect(client.getQueryData(['account', verifiedActor.account_id, 'goal'])).toBeUndefined();
  });
});
