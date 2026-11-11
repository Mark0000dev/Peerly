import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { TuiRoot } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../app.config';
import { conversation, currentGoal, identity, shareReceipt, shares } from './chats.fixtures';
import { GoalSharing } from './goal-sharing';
@Component({
  selector: 'share-test-host',
  imports: [TuiRoot, GoalSharing],
  template:
    '<tui-root><app-chat-goal-sharing [actor]="actor()" [conversationId]="conversation()" [canShare]="canShare()" /></tui-root>',
})
class ShareHost {
  public readonly actor = signal(identity);
  public readonly conversation = signal(conversation.conversation_id);
  public readonly canShare = signal(true);
}
describe('C04 explicitly reviewed goal version/source intent', () => {
  let fixture: ComponentFixture<ShareHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  const url = `/api/v1/conversations/${conversation.conversation_id}/goal-shares`;
  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: {
        queries: { retry: false, refetchOnWindowFocus: false },
        mutations: { retry: false },
      },
    });
    client.setQueryData(['session'], identity);
    params = new BehaviorSubject(convertToParamMap({ conversation: conversation.conversation_id }));
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
    fixture = TestBed.createComponent(ShareHost);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    vi.restoreAllMocks();
    TestBed.resetTestingModule();
  });
  function host(): HTMLElement {
    const element: unknown = fixture.nativeElement;
    if (!(element instanceof HTMLElement)) throw new Error('Missing host');
    return element;
  }
  function button(name: string): HTMLButtonElement {
    const value = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) =>
        (item.getAttribute('aria-label') ?? item.textContent.trim()) === name,
    );
    if (value === undefined) throw new Error(`Missing ${name}`);
    return value;
  }
  function click(name: string): void {
    button(name).click();
    fixture.detectChanges();
  }
  async function shown(text: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain(text);
    });
  }
  async function open(): Promise<void> {
    click('View shared goals');
    await vi.waitFor(() => {
      backend.expectOne(url).flush(shares);
    });
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me/goal').flush({ goal: currentGoal });
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(button('Review current goal for sharing').isConnected).toBe(true);
    });
  }
  async function canonical(): Promise<void> {
    await vi.waitFor(() => {
      backend.expectOne(url).flush({
        ...shares,
        current_context_version: 1,
        anchor_version: 1,
        latest: { ...shareReceipt, can_complete: true },
      });
    });
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me/goal').flush({ goal: currentGoal });
    });
  }
  async function post() {
    return vi.waitFor(() =>
      backend.expectOne((request) => request.url === url && request.method === 'POST'),
    );
  }
  it('performs no request on construction and only shares after explicit source review and Share', async () => {
    backend.expectNone(url);
    backend.expectNone('/api/v1/me/goal');
    await open();
    backend.expectNone((request) => request.method !== 'GET');
    click('Review current goal for sharing');
    await shown('Share this goal version');
    backend.expectNone((request) => request.method !== 'GET');
    click('Share reviewed goal');
    const request = await post();
    expect(request.request.body).toEqual({
      goal_id: currentGoal.id,
      expected_goal_version: currentGoal.version,
      expected_context_version: 0,
    });
    expect(request.request.headers.get('X-CSRF-Token')).toBe(identity.csrf_token);
    request.flush(shareReceipt);
    await canonical();
    await shown('Goal share stored.');
    await shown('Your shared goal');
  });
  it('requires fresh review after goal/context changes and never overwrites original context', async () => {
    await open();
    click('Review current goal for sharing');
    client.setQueryData(['account', identity.account_id, 'chats', 'current-goal'], {
      goal: { ...currentGoal, version: 3, topic: 'New source' },
    });
    await shown('The reviewed source changed.');
    expect(host().textContent).not.toContain('Share this goal version');
    backend.expectNone((request) => request.method === 'POST');
    click('Review current goal for sharing');
    click('Share reviewed goal');
    const request = await post();
    expect(request.request.body).toEqual({
      goal_id: currentGoal.id,
      expected_goal_version: 3,
      expected_context_version: 0,
    });
    request.flush({}, { status: 409, statusText: 'Conflict' });
    await shown('The goal or shared context changed.');
    expect(host().textContent).toContain('New source');
  });
  it('replays uncertain shares with exact immutable body/key despite source and CSRF refresh', async () => {
    await open();
    click('Review current goal for sharing');
    click('Share reviewed goal');
    const first = await post();
    const body: unknown = first.request.body;
    const key = first.request.headers.get('Idempotency-Key');
    first.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('We couldn’t confirm whether this goal was shared.');
    client.setQueryData(['session'], { ...identity, csrf_token: 'new-csrf' });
    client.setQueryData(['account', identity.account_id, 'chats', 'current-goal'], {
      goal: { ...currentGoal, version: 3 },
    });
    fixture.detectChanges();
    click('Retry same goal share');
    const replay = await post();
    expect(replay.request.body).toEqual(body);
    expect(replay.request.headers.get('Idempotency-Key')).toBe(key);
    expect(replay.request.headers.get('X-CSRF-Token')).toBe('new-csrf');
    replay.flush(shareReceipt);
    await canonical();
    await shown('Goal share stored.');
  });
  it('does not offer sharing for no current goal/completed goal/current capability denial', async () => {
    click('View shared goals');
    await vi.waitFor(() => {
      backend.expectOne(url).flush(shares);
    });
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me/goal').flush({ goal: null });
    });
    await shown('You have no current goal');
    client.setQueryData(['account', identity.account_id, 'chats', 'current-goal'], {
      goal: { ...currentGoal, completed_at: currentGoal.updated_at },
    });
    await shown('This goal is completed.');
    client.setQueryData(['account', identity.account_id, 'chats', 'current-goal'], {
      goal: currentGoal,
    });
    fixture.componentInstance.canShare.set(false);
    fixture.detectChanges();
    expect(button('Review current goal for sharing').disabled).toBe(true);
    backend.expectNone((request) => request.method === 'POST');
  });
  it('uses actual opaque share paging, retains baseline and renders historical sources read-only', async () => {
    await open();
    params.next(
      convertToParamMap({ conversation: conversation.conversation_id, share_cursor: 'opaque+/=' }),
    );
    await vi.waitFor(() => {
      backend.expectOne(url + '?cursor=opaque%2B%2F%3D').flush({
        ...shares,
        latest: { ...shareReceipt, can_complete: false },
        history: [{ ...shareReceipt, can_complete: false }],
        next_cursor: 'older',
      });
    });
    await shown('Earlier shared goals');
    await shown('Latest shared goals');
    await shown('Retained context version 1');
    await shown('Read-only goal context');
    backend.expectNone((request) => request.method === 'POST');
  });
  for (const status of [401, 422, 503])
    it(`recovers actual shared read ${status.toString()} without an automatic write`, async () => {
      click('View shared goals');
      await vi.waitFor(() => {
        backend.expectOne('/api/v1/me/goal').flush({ goal: currentGoal });
      });
      await vi.waitFor(() => {
        backend.expectOne(url).flush({}, { status, statusText: 'Unavailable' });
      });
      if (status === 401) {
        await vi.waitFor(() => {
          expect(client.getQueryData(['session'])).toBeNull();
        });
      } else {
        await shown(status === 422 ? 'This shared-goal page' : 'Shared goals are unavailable');
        click('Refresh shared goals');
        await vi.waitFor(() => {
          backend.expectOne(url).flush(shares);
        });
        await vi.waitFor(() => {
          backend.expectOne('/api/v1/me/goal').flush({ goal: currentGoal });
        });
      }
      backend.expectNone((request) => request.method === 'POST');
    });
  it('reuses an unchanged confirmed-failure share key, but gives each changed goal/context a new intent', async () => {
    await open();
    click('Review current goal for sharing');
    click('Share reviewed goal');
    const first = await post();
    const firstKey = first.request.headers.get('Idempotency-Key');
    first.flush({}, { status: 422, statusText: 'Rejected' });
    await shown('This shared-goal page');
    click('Share reviewed goal');
    const same = await post();
    expect(same.request.headers.get('Idempotency-Key')).toBe(firstKey);
    same.flush({}, { status: 422, statusText: 'Rejected' });
    await shown('This shared-goal page');
    client.setQueryData(['account', identity.account_id, 'chats', 'current-goal'], {
      goal: { ...currentGoal, id: 'new-goal' },
    });
    await shown('The reviewed source changed.');
    click('Review current goal for sharing');
    click('Share reviewed goal');
    const newGoal = await post();
    const newKey = newGoal.request.headers.get('Idempotency-Key');
    expect(newKey).not.toBe(firstKey);
    newGoal.flush({}, { status: 422, statusText: 'Rejected' });
    await shown('This shared-goal page');
    client.setQueryData(['account', identity.account_id, 'chats', 'current-goal'], {
      goal: { ...currentGoal, id: 'new-goal', version: 3 },
    });
    await shown('The reviewed source changed.');
    click('Review current goal for sharing');
    click('Share reviewed goal');
    const version = await post();
    expect(version.request.headers.get('Idempotency-Key')).not.toBe(newKey);
    version.flush({}, { status: 422, statusText: 'Rejected' });
    await shown('This shared-goal page');
    client.setQueryData(
      ['account', identity.account_id, 'chats', conversation.conversation_id, 'goal-shares', null],
      { ...shares, current_context_version: 2 },
    );
    await shown('The reviewed source changed.');
    click('Review current goal for sharing');
    click('Share reviewed goal');
    const context = await post();
    expect(context.request.body).toEqual({
      goal_id: 'new-goal',
      expected_goal_version: 3,
      expected_context_version: 2,
    });
    context.flush({}, { status: 409, statusText: 'Conflict' });
    await shown('The goal or shared context changed.');
  });
  it('ignores late old-thread share receipts and clears reviewed source on a genuine selection change', async () => {
    await open();
    click('Review current goal for sharing');
    click('Share reviewed goal');
    const old = await post();
    fixture.componentInstance.conversation.set('new-thread');
    fixture.detectChanges();
    old.flush(shareReceipt);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(button('View shared goals').isConnected).toBe(true);
    });
    expect(host().textContent).not.toContain('Goal share stored.');
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });
  it('clears a current401 share intent and cannot replay it as another actor', async () => {
    await open();
    click('Review current goal for sharing');
    click('Share reviewed goal');
    const write = await post();
    write.flush({}, { status: 401, statusText: 'Unauthorized' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(client.getQueryData(['session'])).toBeNull();
    });
    expect(client.getMutationCache().getAll()).toHaveLength(0);
    expect(host().textContent).not.toContain('Share reviewed goal');
    fixture.componentInstance.actor.set({ ...identity, account_id: 'other' });
    fixture.detectChanges();
    backend.expectNone((request) => request.method === 'POST');
  });
});
