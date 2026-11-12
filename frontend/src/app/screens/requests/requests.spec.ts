import { jpegBase64 } from '../../../../testing/image-fixture';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { TuiRoot } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../../api.generated';
import { appConfig } from '../../app.config';
import { Requests } from './requests';
import { identity, page, request, detail, receipt, viewed, declined } from './requests.fixtures';

@Component({
  selector: 'requests-test-host',
  imports: [TuiRoot, Requests],
  template: '<tui-root><app-requests /></tui-root>',
})
class RequestsHost {}

describe('Requests lifecycle and owned explicit acknowledgements', () => {
  let fixture: ComponentFixture<RequestsHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  const navigate = vi.fn<Router['navigate']>().mockResolvedValue(true);
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
    navigate.mockClear();
    vi.spyOn(TestBed.inject(Router), 'navigate').mockImplementation(navigate);
    fixture = TestBed.createComponent(RequestsHost);
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
    const element: unknown = fixture.nativeElement;
    if (!(element instanceof HTMLElement)) throw new Error('Missing host');
    return element;
  }
  async function shown(text: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      for (const photo of backend.match(
        (request) => request.method === 'GET' && request.url.includes('/photo/'),
      )) {
        if (!photo.cancelled)
          photo.flush(
            new Blob([Uint8Array.from(atob(jpegBase64), (value) => value.charCodeAt(0))], {
              type: 'image/jpeg',
            }),
            { headers: { 'Content-Type': 'image/jpeg' } },
          );
      }
      expect(host().textContent).toContain(text);
    });
  }
  function button(text: string): HTMLButtonElement {
    const result = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) =>
        (item.getAttribute('aria-label') ?? item.textContent.trim()) === text,
    );
    if (result === undefined) throw new Error(`Missing ${text}`);
    return result;
  }
  function click(text: string): void {
    fixture.detectChanges();
    button(text).click();
    fixture.detectChanges();
  }
  async function ready(data: Api['schemas']['RequestPageResponse'] = page): Promise<void> {
    backend.expectOne('/api/v1/me').flush(identity);
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/requests?box=received&view=active').flush(data);
    });
    await shown('Received');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).not.toContain('Loading requests');
    });
  }
  async function selected(data: Api['schemas']['RequestDetailResponse'] = detail): Promise<void> {
    params.next(convertToParamMap({ request: request.request_id }));
    await vi.waitFor(() => {
      backend.expectOne(`/api/v1/requests/${request.request_id}`).flush(data);
    });
    await shown('Academic context when sent');
  }
  async function command(action: string) {
    return vi.waitFor(() => backend.expectOne(`/api/v1/requests/${request.request_id}/${action}`));
  }
  async function canonical(
    data: Api['schemas']['RequestSummaryResponse'] = request,
  ): Promise<void> {
    await vi.waitFor(() => {
      backend
        .expectOne('/api/v1/requests?box=received&view=active')
        .flush({ ...page, requests: [data] });
    });
    if (params.value.has('request'))
      await vi.waitFor(() => {
        backend
          .expectOne(`/api/v1/requests/${request.request_id}`)
          .flush({ ...detail, request: data, disclosed_version: data.version });
      });
    await shown(data.peer.display_name ?? 'Profile unavailable');
  }
  it('reads actual quota/unread without ACK on list, uses genuine profile and omits compose/chat', async () => {
    await ready();
    await shown('Maya Lim');
    expect(host().textContent).toContain('1 unread received requests');
    const card = host().querySelector('article');
    if (card === null) throw new Error('Missing request card');
    expect(card.getAttribute('data-appearance')).toBe('floating');
    expect(card.querySelector('header')?.textContent).toContain('Would like help with SQL');
    expect(card.querySelector('header time')?.getAttribute('datetime')).toBe(request.sent_at);
    expect(card.querySelector('blockquote')?.textContent).toBe(request.text);
    expect(host().querySelector('a[href="/people/' + request.peer.person_id + '"]')).not.toBeNull();
    expect(host().textContent).not.toContain('Send request');
    backend.expectNone((item) => item.method !== 'GET');
  });
  it('empty received active view offers the genuine Discover route', async () => {
    await ready({ ...page, requests: [], unread_received: 0 });
    await shown('No requests for you yet');
    expect(host().querySelector('a[href="/discover"]')?.textContent).toContain('Discover');
    backend.expectNone((item) => item.method !== 'GET');
  });
  for (const state of [
    { box: 'sent', view: 'active', title: 'No sent requests yet', discover: true },
    { box: 'received', view: 'history', title: 'No closed requests yet', discover: false },
    {
      box: 'received',
      view: 'recently_declined',
      title: 'No recently declined requests',
      discover: false,
    },
  ] as const)
    it(`empty ${state.box}/${state.view} keeps its actual view meaning`, async () => {
      await ready({ ...page, requests: [], unread_received: 0 });
      params.next(convertToParamMap({ box: state.box, view: state.view }));
      await vi.waitFor(() => {
        backend.expectOne(`/api/v1/requests?box=${state.box}&view=${state.view}`).flush({
          ...page,
          requests: [],
          unread_received: 0,
        });
      });
      await shown(state.title);
      const discover = Array.from(host().querySelectorAll('a')).filter(
        (link: Readonly<HTMLAnchorElement>) => link.textContent.trim() === 'Discover people',
      );
      expect(discover).toHaveLength(state.discover ? 1 : 0);
      backend.expectNone((item) => item.method !== 'GET');
    });
  it('foreground ACK sends disclosed revision only after explicit click and rereads canonically', async () => {
    await ready();
    await selected();
    backend.expectNone((item) => item.method === 'POST');
    click('Mark as viewed');
    const write = await command('viewed');
    expect(write.request.body).toEqual({ disclosure_id: detail.disclosure_id });
    expect(write.request.headers.get('X-CSRF-Token')).toBe(identity.csrf_token);
    expect(write.request.headers.get('Idempotency-Key')).toMatch(/^[\da-f-]{36}$/);
    write.flush(viewed);
    await canonical({ ...request, unread: false });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).not.toContain('Mark as viewed');
    });
  });
  it('hidden document never ACKs merely from a stale user control', async () => {
    await ready();
    await selected();
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    click('Mark as viewed');
    backend.expectNone((item) => item.method === 'POST');
  });
  it('ACK deduplication accepts the first receipt for the same owned stored revision', async () => {
    await ready();
    await selected({ ...detail, disclosure_id: 'later-owned-disclosure' });
    click('Mark as viewed');
    const write = await command('viewed');
    expect(write.request.body).toEqual({ disclosure_id: 'later-owned-disclosure' });
    // The backend's unique viewer/request/version receipt retains its first disclosure.
    write.flush(viewed);
    await canonical({ ...request, unread: false });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).not.toContain('Mark as viewed');
    });
    expect(host().textContent).not.toContain('Retry same acknowledgement');
  });
  it('accept uses actual pair/version and real receipt only triggers current canonical state', async () => {
    await ready();
    await shown('Maya Lim');
    click('Accept request');
    const write = await command('accept');
    expect(write.request.body).toEqual({ person_id: request.peer.person_id, expected_version: 1 });
    expect(button('Decline').disabled).toBe(true);
    write.flush(receipt);
    await canonical({
      ...request,
      version: 2,
      state: 'accepted',
      conversation_id: receipt.conversation_id,
      capabilities: {
        ...request.capabilities,
        accept: false,
        decline: false,
        open_conversation: true,
      },
    });
    await shown('Connected. No message was sent by accepting.');
    if (receipt.conversation_id === null) throw new Error('Missing accepted conversation fixture');
    expect(host().querySelector('a[href^="/chats?"]')?.getAttribute('href')).toBe(
      '/chats?conversation=' + receipt.conversation_id,
    );
    backend.expectNone((item) => item.method === 'POST' && item.url.includes('/messages'));
  });
  it('decline and Undo use server versions, not inferred local removal', async () => {
    await ready();
    await shown('Maya Lim');
    click('Decline');
    (await command('decline')).flush({
      ...receipt,
      outcome: 'declined',
      undo_until: declined.undo_until,
      conversation_id: null,
    });
    await canonical(declined);
    await shown('Undo available');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(button('Undo decline').disabled).toBe(false);
    });
    click('Undo decline');
    const undo = await command('undo-decline');
    expect(undo.request.body).toEqual({ person_id: request.peer.person_id, expected_version: 2 });
    undo.flush({ ...receipt, version: 3, outcome: 'undo_decline', conversation_id: null });
    await canonical({ ...request, version: 3 });
    await shown('Pending');
  });
  it('expired observed Undo cannot send and does not claim the server finalized it', async () => {
    await ready({ ...page, requests: [{ ...declined, undo_until: declined.observed_at }] });
    await shown('Checking current Undo availability');
    expect(button('Undo decline').disabled).toBe(true);
    click('Undo decline');
    backend.expectNone((item) => item.method === 'POST');
  });
  it('withdraw requires explicit consequence confirmation and preserves actual daily counters', async () => {
    const outgoing = {
      ...request,
      capabilities: { ...request.capabilities, accept: false, decline: false, withdraw: true },
    };
    await ready({ ...page, requests: [outgoing] });
    await shown('Maya Lim');
    click('Withdraw');
    await shown('Withdraw this request?');
    backend.expectNone((item) => item.method === 'POST');
    click('Keep request');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('section[aria-label="Withdraw confirmation"]')).toBeNull();
    });
    backend.expectNone((item) => item.method === 'POST');
    click('Withdraw');
    await shown('Withdraw this request?');
    click('Withdraw request');
    (await command('withdraw')).flush({ ...receipt, outcome: 'withdrawn', conversation_id: null });
    await canonical({
      ...outgoing,
      version: 2,
      state: 'withdrawn',
      capabilities: { ...outgoing.capabilities, withdraw: false },
    });
    await shown('Withdrawn');
  });
  it('unknown decision replays exact original key/body with current CSRF even after refreshed version', async () => {
    await ready();
    await shown('Maya Lim');
    click('Decline');
    const first = await command('decline');
    const key = first.request.headers.get('Idempotency-Key');
    const body: unknown = first.request.body;
    first.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Retry same decision');
    client.setQueryData(['session'], { ...identity, csrf_token: 'rotated-csrf' });
    click('Refresh requests');
    await canonical({ ...request, version: 7 });
    click('Retry same decision');
    const replay = await command('decline');
    expect(replay.request.body).toEqual(body);
    expect(replay.request.headers.get('Idempotency-Key')).toBe(key);
    expect(replay.request.headers.get('X-CSRF-Token')).toBe('rotated-csrf');
    replay.flush({ ...receipt, outcome: 'declined', conversation_id: null });
    await canonical(request);
    await shown('Pending');
  });
  it('unknown ACK preserves exact disclosure while canonical detail changes', async () => {
    await ready();
    await selected();
    click('Mark as viewed');
    const first = await command('viewed');
    const key = first.request.headers.get('Idempotency-Key');
    first.flush({}, { status: 408, statusText: 'Timeout' });
    await shown('Retry same acknowledgement');
    click('Retry same acknowledgement');
    const replay = await command('viewed');
    expect(replay.request.body).toEqual({ disclosure_id: detail.disclosure_id });
    expect(replay.request.headers.get('Idempotency-Key')).toBe(key);
    replay.flush(viewed);
    await canonical({ ...request, unread: false });
  });
  for (const status of [403, 404, 409, 422, 500])
    it(`confirmed or uncertain action ${String(status)} requires explicit recovery`, async () => {
      await ready();
      await shown('Maya Lim');
      click('Accept request');
      (await command('accept')).flush(
        { code: 'request_version_conflict' },
        { status, statusText: 'Failure' },
      );
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(host().querySelector('[role="alert"]')).not.toBeNull();
        expect(button('Refresh requests').disabled).toBe(false);
      });
      click('Refresh requests');
      await canonical();
      expect(host().textContent).toContain('Maya Lim');
    });
  it('wrong successful receipt stays unknown rather than accepting another request', async () => {
    await ready();
    await shown('Maya Lim');
    click('Accept request');
    (await command('accept')).flush({ ...receipt, request_id: 'another-request' });
    await shown('Retry same decision');
  });
  it('wrong successful ACK stays unknown rather than claiming a newer revision viewed', async () => {
    await ready();
    await selected();
    click('Mark as viewed');
    (await command('viewed')).flush({ ...viewed, stored_version: 2 });
    await shown('Retry same acknowledgement');
  });
  it('URL owns box/view/cursor/selection and changing box clears incompatible filters', async () => {
    await ready({ ...page, next_cursor: 'opaque/cursor' });
    await shown('Maya Lim');
    click('Next page');
    expect(navigate).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({
        queryParams: {
          box: 'received',
          view: 'active',
          cursor: 'opaque/cursor',
          request: null,
        },
      }),
    );
    click('Sent');
    expect(navigate).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({
        queryParams: {
          box: 'sent',
          view: 'active',
          cursor: null,
          request: null,
        },
      }),
    );
    click('History');
    click('Recently declined');
    click('Review request');
    expect(navigate).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({
        queryParams: {
          box: 'received',
          view: 'active',
          cursor: null,
          request: request.request_id,
        },
      }),
    );
    params.next(convertToParamMap({ box: 'sent', view: 'recently_declined', cursor: 'opaque' }));
    await vi.waitFor(() => {
      backend
        .expectOne('/api/v1/requests?box=sent&view=active&cursor=opaque')
        .flush({ ...page, requests: [] });
    });
    await shown('0 of 5 pending');
    click('Refresh requests');
    expect(navigate).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({
        queryParams: { box: 'sent', view: 'active', cursor: null, request: null },
      }),
    );
  });
  it('detail404 is neutral and explicit retry does not acknowledge', async () => {
    await ready();
    params.next(convertToParamMap({ request: request.request_id }));
    await vi.waitFor(() => {
      backend
        .expectOne(`/api/v1/requests/${request.request_id}`)
        .flush({}, { status: 404, statusText: 'Unavailable' });
    });
    await shown('This request is no longer available.');
    click('Refresh requests');
    await canonical();
    await shown('Academic context when sent');
    click('Back to requests');
    backend.expectNone((item) => item.method === 'POST');
  });
  it('masked lifecycle peers keep retained text without private profile links', async () => {
    await ready({
      ...page,
      requests: [
        {
          ...request,
          peer: { ...request.peer, state: 'deleted', display_name: null, photo_version: null },
        },
      ],
    });
    await shown('Deleted account');
    expect(host().textContent).toContain(request.text);
    expect(host().querySelector('a[href^="/people"]')).toBeNull();
  });
  it('list failure retries explicitly, empty state makes no write', async () => {
    backend.expectOne('/api/v1/me').flush(identity);
    await vi.waitFor(() => {
      backend
        .expectOne('/api/v1/requests?box=received&view=active')
        .flush({}, { status: 503, statusText: 'Unavailable' });
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('[role="alert"]')).not.toBeNull();
      expect(button('Refresh requests').disabled).toBe(false);
    });
    click('Refresh requests');
    await vi.waitFor(() => {
      backend
        .expectOne('/api/v1/requests?box=received&view=active')
        .flush({ ...page, requests: [] });
    });
    await shown('No requests for you yet');
    backend.expectNone((item) => item.method === 'POST');
  });
  it('guest has no private reads', async () => {
    backend.expectOne('/api/v1/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    await shown('Complete your profile');
    backend.expectNone((item) => item.url.startsWith('/api/v1/requests'));
  });
  it('restricted actor has no private reads', async () => {
    backend.expectOne('/api/v1/me').flush({
      ...identity,
      capabilities: { ...identity.capabilities, can_use_student_features: false },
    });
    await shown('Complete your profile');
    backend.expectNone((item) => item.url.startsWith('/api/v1/requests'));
  });
  it('session failure retries only after explicit action', async () => {
    backend.expectOne('/api/v1/me').flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Retry account check');
    click('Retry account check');
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush(identity);
    });
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/requests?box=received&view=active').flush(page);
    });
    await shown('Maya Lim');
  });
  it('current401 clears private state and rechecks session', async () => {
    await ready();
    await shown('Maya Lim');
    click('Accept request');
    (await command('accept')).flush({}, { status: 401, statusText: 'Unauthorized' });
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    });
    await shown('Complete your profile');
    expect(host().textContent).not.toContain('Maya Lim');
  });
  for (const status of [200, 401])
    it(`old actor ${String(status)} cannot alter replacement session or list`, async () => {
      await ready();
      await shown('Maya Lim');
      click('Accept request');
      const old = await command('accept');
      client.setQueryData(['session'], { ...identity, account_id: 'replacement-actor' });
      await vi.waitFor(() => {
        backend
          .expectOne('/api/v1/requests?box=received&view=active')
          .flush({ ...page, requests: [] });
      });
      await shown('No requests for you yet');
      if (status === 200) old.flush(receipt);
      else old.flush({}, { status, statusText: 'Unauthorized' });
      await vi.waitFor(() => {
        expect(client.getQueryData(['session'])).toEqual(
          expect.objectContaining({ account_id: 'replacement-actor' }),
        );
      });
      backend.expectNone('/api/v1/me');
    });
  it('destroyed decision callback cannot invalidate private reads', async () => {
    await ready();
    await shown('Maya Lim');
    click('Accept request');
    const write = await command('accept');
    fixture.destroy();
    write.flush(receipt);
    await vi.waitFor(() => {
      expect(
        client.getMutationCache().findAll({ mutationKey: ['requests-decision'] }),
      ).toHaveLength(0);
    });
    backend.expectNone('/api/v1/requests?box=received&view=active');
  });
  it('server Undo deadline expiration rereads actual capabilities for selected detail', async () => {
    await ready({ ...page, requests: [declined] });
    await selected({ ...detail, request: declined, disclosed_version: 2 });
    await shown('Undo available');
    vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 11000);
    await canonical({
      ...request,
      state: 'declined',
      version: 3,
      capabilities: { ...request.capabilities, accept: false, decline: false },
    });
    await shown('Declined');
    expect(host().textContent).not.toContain('Undo decline');
  });
  it('sent projection remains neutral for pending and final recipient declines', async () => {
    await ready();
    params.next(convertToParamMap({ box: 'sent', view: 'history' }));
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/requests?box=sent&view=history').flush({
        ...page,
        requests: [
          { ...request, state: 'pending_decline' },
          { ...request, request_id: 'other-request', state: 'declined' },
        ],
      });
    });
    await shown('Closed');
    expect(host().textContent).toContain('Pending');
    expect(host().textContent).not.toContain('Declined');
  });
  it('a queued decision cannot be sent after logout changes canonical ownership', async () => {
    await ready();
    await shown('Maya Lim');
    click('Accept request');
    client.setQueryData(['session'], null);
    await shown('Complete your profile');
    backend.expectNone((item) => item.method === 'POST');
  });
  for (const status of [200, 401])
    it(`late old-account ACK ${String(status)} cannot alter replacement identity`, async () => {
      await ready();
      await selected();
      click('Mark as viewed');
      const old = await command('viewed');
      client.setQueryData(['session'], { ...identity, account_id: 'replacement-actor' });
      await vi.waitFor(() => {
        backend
          .expectOne('/api/v1/requests?box=received&view=active')
          .flush({ ...page, requests: [] });
      });
      await vi.waitFor(() => {
        backend
          .expectOne(`/api/v1/requests/${request.request_id}`)
          .flush({}, { status: 404, statusText: 'Unavailable' });
      });
      if (status === 200) old.flush(viewed);
      else old.flush({}, { status, statusText: 'Unauthorized' });
      await shown('This request is no longer available.');
      expect(client.getQueryData(['session'])).toEqual(
        expect.objectContaining({ account_id: 'replacement-actor' }),
      );
      backend.expectNone('/api/v1/me');
    });
  it('pending decision rejects queued navigation, refresh and duplicate decision events', async () => {
    await ready({ ...page, next_cursor: 'next' });
    await shown('Maya Lim');
    const controls = [
      'Sent',
      'History',
      'Review request',
      'Next page',
      'Refresh requests',
      'Accept request',
    ].map((name) => button(name));
    click('Decline');
    const first = await command('decline');
    for (const control of controls) control.dispatchEvent(new MouseEvent('click'));
    expect(navigate).not.toHaveBeenCalled();
    backend.expectNone((item) => item.method === 'POST');
    first.flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Retry same decision');
    click('Retry same decision');
    (await command('decline')).flush({}, { status: 409, statusText: 'Conflict' });
    await shown('This request changed');
  });
  it('ACK retry failure preserves receipt intent then confirmed error refresh permits a new explicit ACK', async () => {
    await ready();
    await selected();
    click('Mark as viewed');
    (await command('viewed')).flush({}, { status: 503, statusText: 'Unavailable' });
    await shown('Retry same acknowledgement');
    click('Retry same acknowledgement');
    (await command('viewed')).flush({}, { status: 409, statusText: 'Conflict' });
    await shown('This request changed');
    click('Refresh requests');
    await canonical();
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(button('Mark as viewed').disabled).toBe(false);
    });
  });
  it('read cancellation on logout exposes no stale request or spontaneous ACK', async () => {
    backend.expectOne('/api/v1/me').flush(identity);
    const read = await vi.waitFor(() =>
      backend.expectOne('/api/v1/requests?box=received&view=active'),
    );
    client.setQueryData(['session'], null);
    await shown('Complete your profile');
    expect(read.cancelled).toBe(true);
    backend.expectNone((item) => item.method === 'POST');
  });
});
