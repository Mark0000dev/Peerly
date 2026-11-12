import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { By } from '@angular/platform-browser';
import { RequestComposer } from './compose/compose';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { TuiRoot } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../app.config';
import { Discovery } from './discovery';
import { identity, card, deck, pass, ownGoal } from './discovery.fixtures';

@Component({
  selector: 'discovery-test-host',
  imports: [TuiRoot, Discovery],
  template: '<tui-root><app-discovery /></tui-root>',
})
class DiscoveryHost {}

describe('Discovery actor-owned deck and private decisions', () => {
  const navigation = vi.fn<Router['navigate']>().mockResolvedValue(true);
  let fixture: ComponentFixture<DiscoveryHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: {
        queries: { retry: false, refetchOnWindowFocus: false },
        mutations: { retry: false },
      },
    });
    params = new BehaviorSubject(convertToParamMap({}));
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideHttpClientTesting(),
        provideTanStackQuery(client),
        {
          provide: ActivatedRoute,
          useValue: {
            queryParamMap: params,
            get snapshot() {
              return { queryParamMap: params.value };
            },
          },
        },
      ],
    });
    navigation.mockClear();
    vi.spyOn(TestBed.inject(Router), 'navigate').mockImplementation(navigation);
    fixture = TestBed.createComponent(DiscoveryHost);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
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
  function host(): HTMLElement {
    const value: unknown = fixture.nativeElement;
    if (!(value instanceof HTMLElement)) throw new Error('No test host');
    return value;
  }
  async function shown(text: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      for (const request of backend.match('/api/v1/me/goal')) {
        if (!request.cancelled) request.flush({ goal: null });
      }
      for (const request of backend.match('/api/v1/me/help-subjects')) {
        if (!request.cancelled) request.flush({ selection: null });
      }
      expect(host().textContent).toContain(text);
    });
  }
  function click(text: string): void {
    fixture.detectChanges();
    const button = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) =>
        (item.getAttribute('aria-label') ?? item.textContent.trim()) === text,
    );
    if (button === undefined) throw new Error(`Button missing: ${text}`);
    button.click();
    fixture.detectChanges();
  }
  async function ready(value: Readonly<Record<string, unknown>> = deck): Promise<void> {
    backend.expectOne('/api/v1/me').flush(identity);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain('Loading people');
    });
    backend.expectOne('/api/v1/discovery?mode=find_help&view=candidates').flush(value);
    await shown(value === deck ? 'Aiko Tanaka' : 'Discover');
    fixture.detectChanges();
    photos();
  }
  function photos(): void {
    for (const request of backend.match((r) => r.url.includes('/photo/'))) {
      if (!request.cancelled)
        request.flush(new Blob([new Uint8Array([255, 216, 255, 217])], { type: 'image/jpeg' }), {
          headers: { 'Content-Type': 'image/jpeg' },
        });
    }
  }
  async function write() {
    return await vi.waitFor(() => backend.expectOne(`/api/v1/discovery/passes/${card.id}`));
  }
  it('waits for trusted identity then displays only actual public card fields', async () => {
    backend.expectNone((r) => r.url.startsWith('/api/v1/discovery'));
    await ready();
    expect(host().textContent).toContain('Can help with SQL · JOINs');
    expect(host().textContent).toContain('Calculus');
    expect(host().querySelector('button[aria-label="Review request"]')).not.toBeNull();
    backend.expectNone('/api/v1/requests/preview');
    expect(host().querySelector('a[href^="/people/' + card.id + '?"]')).not.toBeNull();
  });
  it('opens through URL selection without submitting and preserves the actor-owned child on close', async () => {
    await ready();
    const child = fixture.debugElement
      .query(By.directive(RequestComposer))
      .injector.get(RequestComposer);
    click('Review request');
    expect(navigation).toHaveBeenCalledWith([], {
      relativeTo: TestBed.inject(ActivatedRoute),
      queryParams: { person: card.id, compose: 'request' },
      queryParamsHandling: 'merge',
    });
    backend.expectNone('/api/v1/requests');
    child.closed.emit();
    fixture.detectChanges();
    expect(navigation).toHaveBeenLastCalledWith([], {
      relativeTo: TestBed.inject(ActivatedRoute),
      queryParams: { compose: null },
      queryParamsHandling: 'merge',
    });
    expect(
      fixture.debugElement.query(By.directive(RequestComposer)).injector.get(RequestComposer),
    ).toBe(child);
    client.setQueryData(['session'], null);
    fixture.detectChanges();
    expect(fixture.debugElement.query(By.directive(RequestComposer))).toBeNull();
  });
  it('reconciles only the current actor and routes a canonical sent receipt to Requests', async () => {
    await ready();
    const child = fixture.debugElement
      .query(By.directive(RequestComposer))
      .injector.get(RequestComposer);
    child.reconciliation.emit({
      actorId: 'another-actor',
      recipientId: card.id,
      mode: 'offer_help',
    });
    expect(navigation).not.toHaveBeenCalled();
    child.reconciliation.emit({
      actorId: identity.account_id,
      recipientId: card.id,
      mode: 'offer_help',
    });
    expect(navigation).toHaveBeenLastCalledWith([], {
      relativeTo: TestBed.inject(ActivatedRoute),
      queryParams: { person: card.id, mode: 'offer_help', compose: 'request' },
      queryParamsHandling: 'merge',
    });
    child.sent.emit({
      outcome: 'sent',
      request_id: 'actual-request',
      version: 1,
      changed_at: '2026-11-08T00:00:00Z',
      conversation_id: null,
      undo_until: null,
    });
    expect(navigation).toHaveBeenLastCalledWith(['/requests'], {
      queryParams: { request: 'actual-request', box: 'sent' },
    });
  });
  it('does not replace a real route transition when Taiga closes its portal on activation', async () => {
    await ready();
    const router = TestBed.inject(Router);
    const target = router.parseUrl('/requests?request=actual-request&box=sent');
    const active = vi.spyOn(router, 'currentNavigation').mockReturnValue({
      id: 1,
      initialUrl: target,
      extractedUrl: target,
      trigger: 'imperative',
      extras: {},
      previousNavigation: null,
      abort: vi.fn(),
    });
    const child = fixture.debugElement
      .query(By.directive(RequestComposer))
      .injector.get(RequestComposer);
    child.closed.emit();
    expect(navigation).not.toHaveBeenCalled();
    active.mockReturnValue(null);
    child.closed.emit();
    expect(navigation).toHaveBeenCalledWith([], {
      relativeTo: TestBed.inject(ActivatedRoute),
      queryParams: { compose: null },
      queryParamsHandling: 'merge',
    });
  });
  it('guest and restricted identity never read the private deck', async () => {
    backend.expectOne('/api/v1/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    await shown('Sign in with your verified APU account');
    backend.expectNone((r) => r.url.startsWith('/api/v1/discovery'));
  });
  it('recovers a failed session check explicitly', async () => {
    backend.expectOne('/api/v1/me').flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('We couldn’t check your account');
    click('Try again');
    (await vi.waitFor(() => backend.expectOne('/api/v1/me'))).flush(null);
    await shown('We couldn’t check your account');
  });
  for (const [reason, copy] of [
    ['context_required', 'Choose your learning goal'],
    ['no_relevant_people', 'No relevant people yet'],
    ['exhausted', 'You have seen everyone for now'],
    ['no_available_passed_people', 'No available passed profiles'],
    [null, 'No people on this page'],
  ] as const)
    it(`distinguishes ${String(reason)} without changing the selected task`, async () => {
      await ready({
        ...deck,
        context: reason === 'context_required' ? null : deck.context,
        people: [],
        empty_reason: reason,
      });
      await shown(copy);
      expect(navigation).not.toHaveBeenCalled();
    });
  it('uses URL-owned mode/view/cursor and never sends person as API parameter', async () => {
    params.next(
      convertToParamMap({
        mode: 'offer_help',
        view: 'passed',
        cursor: 'opaque+/=',
        person: card.id,
      }),
    );
    backend.expectOne('/api/v1/me').flush(identity);
    await shown('Loading people');
    backend
      .expectOne('/api/v1/discovery?mode=offer_help&view=passed&cursor=opaque%2B%2F%3D')
      .flush({
        ...deck,
        context: { mode: 'offer_help', help_version: 2 },
        people: [{ ...card, own_pass: pass }],
      });
    await shown('Review again');
    photos();
    expect(host().textContent).toContain('Using your saved help areas');
  });
  it('changes mode and view by navigation and clears cursor/card', async () => {
    await ready();
    click('Offer help');
    expect(navigation).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({
        queryParams: { mode: 'offer_help', view: 'candidates', cursor: null, person: null },
      }),
    );
    click('Deck options');
    click('Review passed profiles');
    expect(navigation).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({
        queryParams: { mode: 'find_help', view: 'passed', cursor: null, person: null },
      }),
    );
  });
  it('saves a private pass with exact context, CAS, CSRF and immutable key; rereads canonical state', async () => {
    await ready();
    click('Pass');
    const request = await write();
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual({
      context: deck.context,
      passed: true,
      expected_version: 0,
    });
    expect(request.request.headers.get('X-CSRF-Token')).toBe(identity.csrf_token);
    expect(request.request.headers.get('Idempotency-Key')).toBeTruthy();
    await shown('Saving your private decision');
    request.flush(pass);
    await shown('Loading people');
    backend
      .expectOne('/api/v1/discovery?mode=find_help&view=candidates')
      .flush({ ...deck, people: [], empty_reason: 'exhausted', undo_pass: pass });
    await shown('Undo pass');
    click('Undo pass');
    expect((await write()).request.body).toEqual({
      context: deck.context,
      passed: false,
      expected_version: 1,
      undo: true,
    });
  });
  it('unknown replies preserve the exact original action even after a canonical refresh', async () => {
    await ready();
    click('Pass');
    const request = await write();
    const body: unknown = request.request.body;
    const key = request.request.headers.get('Idempotency-Key');
    request.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Decision not yet confirmed');
    click('Refresh current people');
    backend
      .expectOne('/api/v1/discovery?mode=find_help&view=candidates')
      .flush({ ...deck, context: { ...deck.context, goal_version: 2 } });
    await shown('Aiko Tanaka');
    photos();
    click('Retry same decision');
    const replay = await write();
    expect(replay.request.body).toEqual(body);
    expect(replay.request.headers.get('Idempotency-Key')).toBe(key);
    replay.flush({}, { status: 409, statusText: 'Conflict' });
    await shown('Your saved context or pass changed');
  });
  for (const [status, code, copy] of [
    [409, 'pass_undo_unavailable', 'Undo is no longer available'],
    [409, 'pass_version_conflict', 'Your saved context or pass changed'],
    [404, 'person_unavailable', 'This person is no longer available'],
  ] as const)
    it(`requires explicit ${code} recovery without automatic writes`, async () => {
      await ready();
      click('Pass');
      (await write()).flush({ code }, { status, statusText: 'Failed' });
      await shown(copy);
      click('Refresh current people');
      backend.expectOne('/api/v1/discovery?mode=find_help&view=candidates').flush(deck);
      await shown('Aiko Tanaka');
      photos();
      backend.expectNone((r) => r.method === 'PUT');
    });
  it('reauthorizes a private401 and clears the old actor', async () => {
    await ready();
    click('Pass');
    (await write()).flush({}, { status: 401, statusText: 'Unauthorized' });
    await shown('Checking your account');
    backend.expectOne('/api/v1/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    await shown('Sign in with your verified APU account');
    expect(
      client.getQueryCache().findAll({ queryKey: ['account', identity.account_id] }).length,
    ).toBe(0);
  });
  it('uses opaque next cursors, URL selected cards and real reconsideration revisions', async () => {
    const second = {
      ...card,
      id: '10000000-0000-0000-0000-000000000009',
      display_name: 'Maya Lim',
      own_pass: { ...card.own_pass, person_id: '10000000-0000-0000-0000-000000000009' },
    };
    await ready({ ...deck, people: [card, second], next_cursor: 'opaque+/=' });
    await shown('Maya Lim');
    click('Maya Lim');
    expect(navigation).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({ queryParams: { person: second.id } }),
    );
    params.next(convertToParamMap({ person: second.id }));
    await shown('Maya Lim');
    photos();
    click('Next page');
    expect(navigation).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({
        queryParams: { mode: 'find_help', view: 'candidates', cursor: 'opaque+/=', person: null },
      }),
    );
    params.next(convertToParamMap({ view: 'passed' }));
    await shown('Loading people');
    backend
      .expectOne('/api/v1/discovery?mode=find_help&view=passed')
      .flush({ ...deck, people: [{ ...card, own_pass: pass }] });
    await shown('Review again');
    photos();
    click('Review again');
    expect((await write()).request.body).toEqual({
      context: deck.context,
      passed: false,
      expected_version: 1,
    });
  });
  it('recovers an invalid cursor from the first page, never a replacement context write', async () => {
    params.next(convertToParamMap({ cursor: 'stale' }));
    backend.expectOne('/api/v1/me').flush(identity);
    await shown('Loading people');
    backend
      .expectOne('/api/v1/discovery?mode=find_help&view=candidates&cursor=stale')
      .flush({ code: 'invalid_cursor' }, { status: 422, statusText: 'Invalid' });
    await shown('This page is no longer available');
    click('Refresh current people');
    expect(navigation).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({
        queryParams: { mode: 'find_help', view: 'candidates', cursor: null, person: null },
      }),
    );
    backend.expectNone((r) => r.method === 'PUT');
  });
  for (const status of [403, 503])
    it(`read ${String(status)} has safe recovery instead of an empty deck`, async () => {
      backend.expectOne('/api/v1/me').flush(identity);
      await shown('Loading people');
      backend
        .expectOne('/api/v1/discovery?mode=find_help&view=candidates')
        .flush({ title: 'PRIVATE' }, { status, statusText: 'Unavailable' });
      await shown(
        status === 403
          ? 'Discovery is not available for your account'
          : 'We couldn’t load people right now',
      );
      expect(host().textContent).not.toContain('PRIVATE');
      click('Refresh current people');
      backend.expectOne('/api/v1/discovery?mode=find_help&view=candidates').flush(deck);
      await shown('Aiko Tanaka');
      photos();
    });
  it('restricted identity cannot start a discovery read', async () => {
    backend.expectOne('/api/v1/me').flush({
      ...identity,
      capabilities: { ...identity.capabilities, can_use_student_features: false },
    });
    await shown('Sign in with your verified APU account');
    backend.expectNone((r) => r.url.startsWith('/api/v1/discovery'));
  });
  it('an account switch before async send prevents the old intent leaving the browser', async () => {
    await ready();
    click('Pass');
    client.setQueryData(['session'], null);
    await shown('Sign in with your verified APU account');
    await Promise.resolve();
    backend.expectNone((r) => r.method === 'PUT');
  });
  for (const failure of [false, true])
    it(`late ${failure ? 'failure' : 'success'} after destruction cannot refresh or reauthorize`, async () => {
      await ready();
      click('Pass');
      const pending = await write();
      fixture.destroy();
      if (failure) pending.flush({}, { status: 401, statusText: 'Unauthorized' });
      else pending.flush(pass);
      await Promise.resolve();
      await Promise.resolve();
      backend.expectNone('/api/v1/me');
      backend.expectNone((r) => r.url.startsWith('/api/v1/discovery'));
    });
  it('same-account revalidation retains unknown intent but sends current CSRF after confirmation', async () => {
    await ready();
    click('Pass');
    const pending = await write();
    const key = pending.request.headers.get('Idempotency-Key');
    pending.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Decision not yet confirmed');
    await client.invalidateQueries({ queryKey: ['session'], refetchType: 'none' });
    client.setQueryData(['session'], { ...identity, csrf_token: 'rotated-discovery-csrf' });
    click('Retry same decision');
    const replay = await write();
    expect(replay.request.headers.get('Idempotency-Key')).toBe(key);
    expect(replay.request.headers.get('X-CSRF-Token')).toBe('rotated-discovery-csrf');
    replay.flush(pass);
    await shown('Loading people');
    backend.expectOne('/api/v1/discovery?mode=find_help&view=candidates').flush(deck);
    await shown('Aiko Tanaka');
    photos();
  });
  it('stale action and navigation controls cannot bypass a pending decision', async () => {
    await ready({ ...deck, next_cursor: 'opaque' });
    click('Deck options');
    const passButton = Array.from(host().querySelectorAll('button')).find(
      (button: Readonly<HTMLButtonElement>) => button.textContent.trim() === 'Pass',
    );
    const nextButton = Array.from(host().querySelectorAll('button')).find(
      (button: Readonly<HTMLButtonElement>) => button.textContent.trim() === 'Next page',
    );
    const viewButton = Array.from(host().querySelectorAll('button')).find(
      (button: Readonly<HTMLButtonElement>) =>
        button.textContent.trim() === 'Review passed profiles',
    );
    if (passButton === undefined || nextButton === undefined || viewButton === undefined)
      throw new Error('Missingcontrols');
    passButton.click();
    await shown('Saving your private decision');
    passButton.dispatchEvent(new Event('click'));
    nextButton.dispatchEvent(new Event('click'));
    viewButton.dispatchEvent(new Event('click'));
    const pending = await write();
    backend.expectNone((r) => r.method === 'PUT');
    expect(navigation).not.toHaveBeenCalled();
    pending.flush(pass);
    await shown('Loading people');
    backend
      .expectOne('/api/v1/discovery?mode=find_help&view=candidates')
      .flush({ ...deck, people: [], empty_reason: 'exhausted' });
    await shown('You have seen everyone');
  });
  it('photo404 refreshes canonical discovery before the new JPEG version', async () => {
    backend.expectOne('/api/v1/me').flush(identity);
    await shown('Loading people');
    backend.expectOne('/api/v1/discovery?mode=find_help&view=candidates').flush(deck);
    await shown('Aiko Tanaka');
    backend
      .expectOne(`/api/v1/people/${card.id}/photo/1`)
      .flush(new Blob(), { status: 404, statusText: 'Unavailable' });
    await shown('Retry photo');
    click('Retry photo');
    backend
      .expectOne('/api/v1/discovery?mode=find_help&view=candidates')
      .flush({ ...deck, people: [{ ...card, photo: { ...card.photo, version: 2 } }] });
    await shown('Aiko Tanaka');
    photos();
  });
  it('mismatched command receipts stay unknown and never authorize a new decision', async () => {
    await ready();
    click('Pass');
    (await write()).flush({ ...pass, person_id: 'foreign' });
    await shown('Decision not yet confirmed');
    click('Retry same decision');
    (await write()).flush({ ...pass, passed: false });
    await shown('Decision not yet confirmed');
  });
  it('a response for another mode is rejected instead of applying the wrong saved context', async () => {
    params.next(convertToParamMap({ mode: 'study_together' }));
    backend.expectOne('/api/v1/me').flush(identity);
    await shown('Loading people');
    backend.expectOne('/api/v1/discovery?mode=study_together&view=candidates').flush(deck);
    await shown('We couldn’t load people right now');
    backend.expectNone((r) => r.method === 'PUT');
  });
  it('offers the real Requests destination when this saved discovery deck is exhausted', async () => {
    await ready({ ...deck, people: [], empty_reason: 'exhausted' });
    await shown('You have seen everyone for now');
    const results = host().querySelector('[aria-label="Discovery results"]');
    expect(results?.querySelector('a[href="/requests"]')?.textContent).toContain('View requests');
    expect(results?.textContent).not.toMatch(/\d+ requests are waiting/);
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('uses canonical actor goal cache only for the matching deck version and hides it after authority ends', async () => {
    await ready();
    client.setQueryData(['account', identity.account_id, 'goal'], ownGoal);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('[aria-label="Saved discovery context"]')?.textContent).toContain(
        'SQL · JOINs',
      );
    });
    client.setQueryData(['account', identity.account_id, 'goal'], {
      goal: {
        ...ownGoal.goal,
        version: 2,
        subject: { ...ownGoal.goal.subject, label: 'Unmatched private context' },
      },
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      const text = host().querySelector('[aria-label="Saved discovery context"]')?.textContent;
      expect(text).toContain('Using your saved active goal');
      expect(text).not.toContain('Unmatched private context');
    });
    client.setQueryData(['session'], null);
    await shown('Sign in with your verified APU account');
    expect(host().querySelector('[aria-label="Saved discovery context"]')).toBeNull();
  });
  it('keeps passed profiles in their own URL context and returns without a decision', async () => {
    await ready();
    params.next(convertToParamMap({ mode: 'find_help', view: 'passed' }));
    const read = await vi.waitFor(() =>
      backend.expectOne('/api/v1/discovery?mode=find_help&view=passed'),
    );
    read.flush({ ...deck, people: [], empty_reason: 'no_available_passed_people' });
    await shown('No available passed profiles');
    expect(host().querySelector('[aria-label="Discovery mode"]')).toBeNull();
    expect(host().querySelector('[aria-label="Saved discovery context"]')).toBeNull();
    click('Back to Discover');
    expect(navigation).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({
        queryParams: { mode: 'find_help', view: 'candidates', cursor: null, person: null },
      }),
    );
    backend.expectNone((request) => request.method !== 'GET');
  });
});
