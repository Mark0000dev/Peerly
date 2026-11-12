import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { By } from '@angular/platform-browser';
import { ApiFailure } from '../../api-http';
import { StudyProgress } from './study/study-progress';
import { outcome, ownFeedback } from './study/study.fixtures';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { TuiRoot } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../app.config';
import { Chats } from './chats';
import { conversation, history, identity, message, page, peer, summary } from './chats.fixtures';

@Component({
  selector: 'chat-test-host',
  imports: [TuiRoot, Chats],
  template: '<tui-root><app-chats /></tui-root>',
})
class ChatHost {}

describe('C01/C02 canonical reads and account boundaries', () => {
  let fixture: ComponentFixture<ChatHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let visits: readonly string[];
  beforeEach(() => {
    visits = [];
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
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
    fixture = TestBed.createComponent(ChatHost);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    try {
      fixture.destroy();
      client.clear();
      backend.verify({ ignoreCancelled: true });
    } finally {
      vi.restoreAllMocks();
      TestBed.resetTestingModule();
    }
  });
  function host(): HTMLElement {
    const value: unknown = fixture.nativeElement;
    if (!(value instanceof HTMLElement)) throw new Error('Missing host');
    return value;
  }
  async function shown(text: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).toContain(text);
    });
  }
  function click(text: string): void {
    const button = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.trim() === text,
    );
    if (button === undefined) throw new Error('Missing button');
    button.click();
    fixture.detectChanges();
  }
  async function ready(): Promise<void> {
    backend.expectOne('/api/v1/me').flush(identity);
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/conversations').flush(page);
    });
    await shown(peer.display_name ?? 'Profile unavailable');
  }
  it('keeps a long actual preview, context and unread metadata in one native chat link', async () => {
    const longText = 'A long confirmed message with another paragraph.\n'.repeat(40);
    backend.expectOne('/api/v1/me').flush(identity);
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/conversations').flush({
        ...page,
        conversations: [{ ...summary, last_message: { ...message, text: longText } }],
      });
    });
    await shown(longText);
    const link = host().querySelector('a[aria-label="Maya Lim"]');
    expect(link?.getAttribute('href')).toBe(`/chats?conversation=${conversation.conversation_id}`);
    expect(link?.textContent).toContain(longText);
    expect(link?.getAttribute('aria-describedby')).toBe(
      `conversation-context-${conversation.conversation_id} conversation-meta-${conversation.conversation_id}`,
    );
    expect(link?.querySelector('.preview-line')).toBeInstanceOf(HTMLElement);
    expect(link?.querySelectorAll('button, a')).toHaveLength(0);
    expect(host().textContent).toContain('1 unread');
    backend.expectNone(`/api/v1/conversations/${conversation.conversation_id}/read-position`);
    backend.expectNone(`/api/v1/conversations/${conversation.conversation_id}/messages`);
  });
  async function admitNoOffer(): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      const request = backend.expectOne(
        `/api/v1/conversations/${conversation.conversation_id}/study-prompt-visits`,
      );
      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual({});
      expect(request.request.headers.get('X-CSRF-Token')).toBe(identity.csrf_token);
      const key = request.request.headers.get('Idempotency-Key');
      if (key === null) throw new Error('Missing foreground visit intent');
      visits = [...visits, key];
      request.flush({ outcome: 'no_offer' });
    });
  }
  async function select(admit = true): Promise<void> {
    params.next(convertToParamMap({ conversation: conversation.conversation_id }));
    await vi.waitFor(() => {
      backend
        .expectOne(`/api/v1/conversations/${conversation.conversation_id}`)
        .flush(conversation);
    });
    await vi.waitFor(() => {
      backend
        .expectOne(`/api/v1/conversations/${conversation.conversation_id}/messages`)
        .flush(history);
    });
    await shown('Original accepted context');
    (
      await vi.waitFor(() =>
        backend.expectOne(
          `/api/v1/conversations/${conversation.conversation_id}/image-preparations`,
        ),
      )
    ).flush({ preparations: [] });
    if (admit) await admitNoOffer();
  }
  it('renders actual unread/activity/context without GET acknowledgement or fabricated messages', async () => {
    await ready();
    await shown('1 unread');
    expect(host().querySelector('tui-badge-notification')?.textContent.trim()).toBe('1 unread');
    expect(host().querySelector('.row-metadata time')?.getAttribute('datetime')).toBe(
      summary.activity_at,
    );
    expect(host().textContent).toContain(message.text);
    expect(host().querySelector('a[href^="/people/"]')).toBeNull();
    expect(host().querySelector('nav a[href="/profile"]')).not.toBeNull();
    expect(
      host().querySelector('a[href="/chats?conversation=' + conversation.conversation_id + '"]'),
    ).not.toBeNull();
    backend.expectNone((request) => request.method !== 'GET');
    await select();
    await shown('Stored');
    await shown('SQL JOINs');
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('shows no chats and accepted no-message thread honestly', async () => {
    backend.expectOne('/api/v1/me').flush(identity);
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/conversations').flush({ conversations: [], next_cursor: null });
    });
    await shown('No chats yet');
    params.next(convertToParamMap({ conversation: conversation.conversation_id }));
    await vi.waitFor(() => {
      backend.expectOne(`/api/v1/conversations/${conversation.conversation_id}`).flush({
        ...conversation,
        last_confirmed_sequence: 0,
        unread_count: 0,
        can_send: false,
        peer: { ...peer, state: 'deleted', display_name: null, photo_version: null },
      });
    });
    await vi.waitFor(() => {
      backend
        .expectOne(`/api/v1/conversations/${conversation.conversation_id}/messages`)
        .flush({ messages: [], anchor_sequence: 0, next_cursor: null });
    });
    await shown('No messages yet.');
    await shown('Deleted account');
    await shown('read-only');
    await admitNoOffer();
    expect(host().textContent).not.toContain('Maya Lim');
  });
  it('keeps opaque list and history cursors in query keys and URL', async () => {
    await ready();
    params.next(
      convertToParamMap({
        cursor: 'opaque+/=',
        conversation: conversation.conversation_id,
        history_cursor: 'older+/=',
      }),
    );
    await vi.waitFor(() => {
      backend
        .expectOne('/api/v1/conversations?cursor=opaque%2B%2F%3D')
        .flush({ ...page, next_cursor: 'next-list' });
    });
    await vi.waitFor(() => {
      backend
        .expectOne(`/api/v1/conversations/${conversation.conversation_id}`)
        .flush(conversation);
    });
    await vi.waitFor(() => {
      backend
        .expectOne(
          `/api/v1/conversations/${conversation.conversation_id}/messages?cursor=older%2B%2F%3D`,
        )
        .flush({ ...history, next_cursor: 'next-history' });
    });
    await shown('Earlier messages');
    await shown('Latest messages');
    await shown('More conversations');
    await admitNoOffer();
    expect(
      client.getQueryData([
        'account',
        identity.account_id,
        'chats',
        conversation.conversation_id,
        'messages',
        'older+/=',
      ]),
    ).toEqual({ ...history, next_cursor: 'next-history' });
  });
  for (const [status, text] of [
    [404, 'This conversation is unavailable.'],
    [422, 'This page has expired.'],
    [503, 'We couldn’t load chats.'],
  ] as const)
    it(`offers genuine recovery after ${status.toString()}, without automatic retries`, async () => {
      backend.expectOne('/api/v1/me').flush(identity);
      await vi.waitFor(() => {
        backend
          .expectOne('/api/v1/conversations')
          .flush({ code: 'not_available' }, { status, statusText: 'Unavailable' });
      });
      await shown(text);
      backend.expectNone('/api/v1/conversations');
      click('Retry chats');
      await vi.waitFor(() => {
        backend.expectOne('/api/v1/conversations').flush({
          ...page,
          conversations: [
            {
              ...summary,
              last_message: null,
              peer: { ...peer, state: 'unavailable' },
              can_send: false,
            },
          ],
        });
      });
      await shown('Connected about Databases');
      await shown('Profile unavailable');
    });
  it('blocks all private reads while session is absent/ineligible', async () => {
    backend.expectOne('/api/v1/me').flush(null, { status: 401, statusText: 'Unauthorized' });
    await shown('Sign in with an eligible');
    expect(host().querySelector('a[href="/onboarding"]')?.textContent).toContain(
      'Continue account',
    );
    backend.expectNone('/api/v1/conversations');
    client.setQueryData(['session'], {
      ...identity,
      capabilities: { ...identity.capabilities, can_use_student_features: false },
    });
    await shown('Finish your profile setup to use Chats.');
    expect(host().querySelector('a[href="/onboarding"]')?.textContent).toContain('Continue setup');
    backend.expectNone('/api/v1/conversations');
  });
  it('offers account retry and revalidates current401 without trusting the old account', async () => {
    backend.expectOne('/api/v1/me').flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('We couldn’t check your account.');
    click('Retry account check');
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush(identity);
    });
    await vi.waitFor(() => {
      backend
        .expectOne('/api/v1/conversations')
        .flush({}, { status: 401, statusText: 'Unauthorized' });
    });
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush(null, { status: 401, statusText: 'Unauthorized' });
    });
    await shown('Sign in with an eligible');
    expect(
      client.getQueryData(['account', identity.account_id, 'chats', 'list', null]),
    ).toBeUndefined();
  });
  it('rechecks canonical account after403 without retaining private content or looping reads', async () => {
    backend.expectOne('/api/v1/me').flush(identity);
    await vi.waitFor(() => {
      backend
        .expectOne('/api/v1/conversations')
        .flush({ code: 'student_access_required' }, { status: 403, statusText: 'Forbidden' });
    });
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush({
        ...identity,
        capabilities: { ...identity.capabilities, can_use_student_features: false },
      });
    });
    await shown('Sign in with an eligible');
    backend.expectNone('/api/v1/conversations');
    expect(
      client.getQueryData(['account', identity.account_id, 'chats', 'list', null]),
    ).toBeUndefined();
  });
  it('admits one foreground visit while REST/SSE invalidation and history pagination remain reads only', async () => {
    await ready();
    await select();
    expect(visits).toHaveLength(1);
    await client.invalidateQueries({
      queryKey: ['account', identity.account_id, 'chats', conversation.conversation_id],
      refetchType: 'none',
    });
    void client.refetchQueries({
      queryKey: ['account', identity.account_id, 'chats', conversation.conversation_id],
    });
    await vi.waitFor(() => {
      backend
        .expectOne(`/api/v1/conversations/${conversation.conversation_id}`)
        .flush(conversation);
    });
    await vi.waitFor(() => {
      backend
        .expectOne(`/api/v1/conversations/${conversation.conversation_id}/messages`)
        .flush(history);
    });
    await shown('Original accepted context');
    params.next(
      convertToParamMap({
        conversation: conversation.conversation_id,
        history_cursor: 'older-page',
      }),
    );
    await vi.waitFor(() => {
      backend
        .expectOne(
          `/api/v1/conversations/${conversation.conversation_id}/messages?cursor=older-page`,
        )
        .flush({ ...history, next_cursor: null });
    });
    await shown('Latest messages');
    expect(visits).toHaveLength(1);
    backend.expectNone((request) => request.url.endsWith('/study-prompt-visits'));
  });
  it('defers admission while backgrounded and keeps focus when a visible foreground visit is admitted', async () => {
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    await ready();
    await select(false);
    backend.expectNone((request) => request.url.endsWith('/study-prompt-visits'));
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    const before = document.activeElement;
    document.dispatchEvent(new Event('visibilitychange'));
    await admitNoOffer();
    expect(document.activeElement).toBe(before);
    document.dispatchEvent(new Event('visibilitychange'));
    fixture.detectChanges();
    backend.expectNone((request) => request.url.endsWith('/study-prompt-visits'));
    expect(visits).toHaveLength(1);
  });
  it('keeps the feature-owned unsent feedback form through same-actor session revalidation', async () => {
    await ready();
    await select();
    click('Study progress');
    const outcomeRead = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/conversations/${conversation.conversation_id}/study-outcome`),
    );
    outcomeRead.flush({ outcome });
    await shown('Give feedback');
    click('Give feedback');
    const feedbackRead = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/conversations/${conversation.conversation_id}/feedback`),
    );
    feedbackRead.flush(ownFeedback);
    await shown('Note for the team');
    const note = host().querySelector('#study-team-note');
    if (!(note instanceof HTMLTextAreaElement)) throw new Error('Missing actual feedback draft');
    note.setRangeText('Unsent work from this tab', 0, note.value.length);
    note.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
    const child = fixture.debugElement
      .query(By.directive(StudyProgress))
      .injector.get(StudyProgress);
    const refresh = client.refetchQueries({ queryKey: ['session'], exact: true });
    const checking = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
    fixture.detectChanges();
    expect(host().querySelector('app-study-progress')).not.toBeNull();
    expect(
      fixture.debugElement.query(By.directive(StudyProgress)).injector.get(StudyProgress),
    ).toBe(child);
    checking.flush(identity);
    await refresh;
    fixture.detectChanges();
    expect(host().querySelector('app-study-progress')).not.toBeNull();
    expect(
      fixture.debugElement.query(By.directive(StudyProgress)).injector.get(StudyProgress),
    ).toBe(child);
    for (const request of backend.match((request) => request.method === 'GET')) {
      if (request.request.url.endsWith('/study-outcome')) request.flush({ outcome });
      else if (request.request.url.endsWith('/feedback')) request.flush(ownFeedback);
      else if (request.request.url.endsWith('/messages')) request.flush(history);
      else if (request.request.url.endsWith('/image-preparations'))
        request.flush({ preparations: [] });
      else if (request.request.url.endsWith('/conversations')) request.flush(page);
      else if (request.request.url === `/api/v1/conversations/${conversation.conversation_id}`)
        request.flush(conversation);
      else throw new Error('Unexpected private read during revalidation');
    }
    await shown('Would you study together again?');
    const retained = host().querySelector('#study-team-note');
    expect(retained instanceof HTMLTextAreaElement ? retained.value : null).toBe(
      'Unsent work from this tab',
    );
    expect(visits).toHaveLength(1);
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('opens manual progress after no_offer without making a second admission visit', async () => {
    await ready();
    await select();
    click('Study progress');
    await vi.waitFor(() => {
      backend
        .expectOne(`/api/v1/conversations/${conversation.conversation_id}/study-outcome`)
        .flush({ outcome: null });
    });
    await shown('Have you started working on your goal together?');
    expect(visits).toHaveLength(1);
    backend.expectNone((request) => request.url.endsWith('/study-prompt-visits'));
  });
  it('binds a deep-link foreground visit only after actual authenticated account/details arrive', async () => {
    params.next(convertToParamMap({ conversation: conversation.conversation_id }));
    backend.expectNone((request) => request.url.endsWith('/study-prompt-visits'));
    backend.expectOne('/api/v1/me').flush(identity);
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/conversations').flush(page);
    });
    await vi.waitFor(() => {
      backend
        .expectOne(`/api/v1/conversations/${conversation.conversation_id}`)
        .flush(conversation);
    });
    await vi.waitFor(() => {
      backend
        .expectOne(`/api/v1/conversations/${conversation.conversation_id}/messages`)
        .flush(history);
    });
    await shown('Original accepted context');
    await admitNoOffer();
    expect(visits).toHaveLength(1);
  });
  for (const status of [401, 403] as const)
    it(`retires actual study child on ${status.toString()} and rechecks account without automatic visit replay`, async () => {
      await ready();
      await select();
      const child: unknown = fixture.debugElement.query(
        By.directive(StudyProgress),
      ).componentInstance;
      if (!(child instanceof StudyProgress)) throw new Error('Missing actual study child');
      child.sessionFailure.emit(new ApiFailure(status, 'access_changed', null));
      await vi.waitFor(() => {
        backend.expectOne('/api/v1/me').flush(null, { status: 401, statusText: 'Unauthorized' });
      });
      await shown('Sign in with an eligible');
      expect(host().querySelector('app-study-progress')).toBeNull();
      expect(visits).toHaveLength(1);
      backend.expectNone((request) => request.url.endsWith('/study-prompt-visits'));
    });
  it('actor replacement retires study intent without transferring an automatic offer to the replacement', async () => {
    await ready();
    await select();
    client.setQueryData(['session'], { ...identity, account_id: peer.person_id });
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/conversations').flush(page);
    });
    await vi.waitFor(() => {
      backend.expectOne(`/api/v1/conversations/${conversation.conversation_id}`).flush({
        ...conversation,
        peer: { ...peer, person_id: identity.account_id, display_name: 'Original actor' },
      });
    });
    await vi.waitFor(() => {
      backend
        .expectOne(`/api/v1/conversations/${conversation.conversation_id}/messages`)
        .flush(history);
    });
    await shown('Original actor');
    expect(visits).toHaveLength(1);
    backend.expectNone((request) => request.url.endsWith('/study-prompt-visits'));
  });
  it('blocks a queued manual-open click after authority clears before the old DOM retires', async () => {
    await ready();
    await select();
    const button = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.trim() === 'Study progress',
    );
    if (button === undefined) throw new Error('Missing manual action');
    client.setQueryData(['session'], null);
    button.click();
    await shown('Sign in with an eligible');
    backend.expectNone((request) => request.url.endsWith('/study-outcome'));
    expect(host().querySelector('app-study-progress')).toBeNull();
  });
  it('leaving a conversation retires foreground intent and local study controls without writes', async () => {
    await ready();
    await select();
    params.next(convertToParamMap({}));
    await shown(peer.display_name ?? 'Profile unavailable');
    expect(host().querySelector('app-study-progress')).toBeNull();
    expect(visits).toHaveLength(1);
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('blocks a queued retry after session revocation while an old error action is still in DOM', async () => {
    backend.expectOne('/api/v1/me').flush(identity);
    await vi.waitFor(() => {
      backend
        .expectOne('/api/v1/conversations')
        .flush({}, { status: 503, statusText: 'Unavailable' });
    });
    await shown('We couldn’t load chats.');
    const button = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.trim() === 'Retry chats',
    );
    if (button === undefined) throw new Error('Missing retry action');
    client.setQueryData(['session'], null);
    button.click();
    await shown('Sign in with an eligible');
    backend.expectNone('/api/v1/conversations');
  });
  it('labels a genuine image-only last message without downloading or acknowledging it from the list', async () => {
    backend.expectOne('/api/v1/me').flush(identity);
    const read = await vi.waitFor(() => backend.expectOne('/api/v1/conversations'));
    read.flush({
      ...page,
      conversations: [
        {
          ...summary,
          last_message: {
            ...message,
            text: null,
            image_id: '00000000-0000-4000-8000-000000000080',
          },
        },
      ],
    });
    await shown('Image');
    expect(host().textContent).toContain('1 unread');
    backend.expectNone((request) => request.url.includes('/images/'));
    backend.expectNone((request) => request.method !== 'GET');
  });

  it('keeps an empty list actionable without fabricating a connection or opening a composer', async () => {
    backend.expectOne('/api/v1/me').flush(identity);
    const read = await vi.waitFor(() => backend.expectOne('/api/v1/conversations'));
    read.flush({ ...page, conversations: [] });
    await shown('No chats yet');
    expect(
      host().querySelector('[aria-label="No conversations"] a[href="/requests"]'),
    ).not.toBeNull();
    expect(host().querySelector('app-chat-message-composer')).toBeNull();
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('opens retained request details without sending or acknowledging and uses one authoritative conversation heading', async () => {
    await ready();
    await select();
    const toggle = host().querySelector('button[aria-label="Original accepted context"]');
    if (!(toggle instanceof HTMLButtonElement)) throw new Error('Missing context disclosure');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(host().querySelectorAll('h1')).toHaveLength(1);
    expect(host().querySelector('h1')?.textContent.trim()).toBe(peer.display_name);
    toggle.click();
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(toggle.getAttribute('aria-expanded')).toBe('true');
    });
    backend.expectNone((request) => request.method !== 'GET');
  });
});
