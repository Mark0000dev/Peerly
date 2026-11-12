import { jpegBase64 } from '../../../../testing/image-fixture';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { NgControl } from '@angular/forms';
import { By } from '@angular/platform-browser';
import { Component, signal } from '@angular/core';
import type { WritableSignal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { TuiRoot, TUI_BREAKPOINT } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../app.config';
import { Person } from './person';
import { PersonFeedbackSummary } from './feedback-summary';
import { ApiFailure } from '../../api-http';
import { actor, person, blocked, receipt } from './person.fixtures';

@Component({
  selector: 'person-test-host',
  imports: [TuiRoot, Person],
  template: '<tui-root><app-person /></tui-root>',
})
class PersonHost {}

describe('person screen and actor-bound safety commands', () => {
  let fixture: ComponentFixture<PersonHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  let breakpoint: WritableSignal<'mobile' | 'desktopLarge' | 'desktopSmall'>;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let query = convertToParamMap({});
  const personUrl = `/api/v1/people/${person.id}`;
  beforeEach(() => {
    breakpoint = signal<'mobile' | 'desktopLarge' | 'desktopSmall'>('desktopLarge');
    client = new QueryClient({
      defaultOptions: {
        queries: { retry: false, refetchOnWindowFocus: false },
        mutations: { retry: false },
      },
    });
    query = convertToParamMap({});
    params = new BehaviorSubject(convertToParamMap({ personId: person.id }));
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideHttpClientTesting(),
        provideTanStackQuery(client),
        { provide: TUI_BREAKPOINT, useValue: breakpoint },
        {
          provide: ActivatedRoute,
          useValue: {
            paramMap: params,
            get snapshot() {
              return { paramMap: params.value, queryParamMap: query };
            },
          },
        },
      ],
    });
    fixture = TestBed.createComponent(PersonHost);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    try {
      publishedPhotos();
      fixture.destroy();
      client.clear();
      backend.verify();
    } finally {
      TestBed.resetTestingModule();
    }
  });
  function host(): HTMLElement {
    const element: unknown = fixture.nativeElement;
    if (!(element instanceof HTMLElement)) throw new Error('Missing host');
    return element;
  }
  function publishedPhotos(): void {
    for (const request of backend.match(
      (candidate) =>
        candidate.url.startsWith('/api/v1/people/') && candidate.url.endsWith('/feedback-summary'),
    )) {
      if (!request.cancelled)
        request.flush({ state: 'building', responses: 0, publicly_visible: true });
    }
    for (const request of backend.match(
      (candidate) =>
        candidate.url.startsWith('/api/v1/people/') && candidate.url.endsWith('/photo/1'),
    )) {
      if (!request.cancelled)
        request.flush(
          new Blob([Uint8Array.from(atob(jpegBase64), (character) => character.charCodeAt(0))], {
            type: 'image/jpeg',
          }),
          { headers: { 'Content-Type': 'image/jpeg' } },
        );
    }
  }
  async function shown(text: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      publishedPhotos();
      expect(
        host().textContent.includes(text) ||
          Array.from(host().querySelectorAll('button')).some(
            (button: Readonly<HTMLButtonElement>) => button.getAttribute('aria-label') === text,
          ),
      ).toBe(true);
    });
  }
  function click(label: string): void {
    fixture.detectChanges();
    const button = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) =>
        (item.getAttribute('aria-label') ?? item.textContent.trim()) === label,
    );
    if (button === undefined) throw new Error(`Missing button ${label}`);
    button.click();
    fixture.detectChanges();
  }
  async function respond(url: string, body: Readonly<Record<string, unknown>>, status = 200) {
    const request = await vi.waitFor(() => backend.expectOne(url));
    request.flush(body, {
      status,
      statusText: status === 200 || status === 201 ? 'OK' : 'Failure',
    });
    fixture.detectChanges();

    return request;
  }
  async function load(): Promise<void> {
    await respond('/api/v1/me', actor);
    await respond('/api/v1/me/blocks', { people: [], next_cursor: null });
    await respond(personUrl, person);
    await shown(person.display_name);
  }
  async function report(): Promise<void> {
    click('More options');
    click('Report profile');
    await shown('Submit report');
  }
  function comment(value: string): void {
    const field = host().querySelector('#report-comment');
    if (!(field instanceof HTMLTextAreaElement)) throw new Error('Missing comment');
    const control = fixture.debugElement
      .query(By.css('#report-comment'))
      .injector.get(NgControl).control;
    if (control === null) throw new Error('Missing comment control');
    control.setValue(value);
    fixture.detectChanges();
  }
  it('does not start private reads before a verified session and renders actual profile fields', async () => {
    await shown('Checking your session');
    backend.expectNone(personUrl);
    await load();
    expect(host().textContent).toContain('JOINs and subqueries');
    expect(host().textContent).toContain('Integration by parts');
    expect(host().textContent).toContain('Provided by this student');
    const academic = host().querySelector('article[aria-label="Academic profile"]');
    if (academic === null) throw new Error('Missing academic profile group');
    expect(academic.querySelectorAll('section[tuiCell]')).toHaveLength(5);
    expect(academic.querySelector('app-person-feedback-summary')).toBeNull();
    expect(host().querySelector('.feedback-surface app-person-feedback-summary')).not.toBeNull();
    expect(host().querySelector('.verification tui-icon')?.getAttribute('aria-hidden')).toBe(
      'true',
    );
    expect(actor.capabilities.can_use_student_features).toBe(true);
    const review = host().querySelector('.profile-actions a');
    if (!(review instanceof HTMLAnchorElement)) throw new Error('Missing permitted preview link');
    expect(review.textContent.trim()).toBe('Review request');
    const preview = new URL(review.href);
    expect(preview.pathname).toBe('/discover');
    expect(preview.searchParams.get('person')).toBe(person.id);
    expect(preview.searchParams.get('compose')).toBe('request');
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('renders sign-in for an unauthenticated actor', async () => {
    await respond('/api/v1/me', { code: 'unauthenticated' }, 401);
    await shown('Sign in and complete');
    backend.expectNone(personUrl);
  });
  it('renders session failure and explicit retry', async () => {
    await respond('/api/v1/me', {}, 503);
    await shown('couldn’t check your session');
    click('Check session');
    await respond('/api/v1/me', {
      ...actor,
      capabilities: { ...actor.capabilities, can_use_student_features: false },
    });
    await shown('Sign in and complete');
  });
  it('renders neutral unavailable and retries a failed read', async () => {
    await respond('/api/v1/me', actor);
    await respond('/api/v1/me/blocks', { people: [], next_cursor: null });
    await respond(personUrl, { code: 'person_unavailable' }, 404);
    await shown('This profile is unavailable');
    expect(host().textContent).not.toContain('Report profile');
    click('Refresh current status');
    await respond('/api/v1/me/blocks', { people: [], next_cursor: null });
    await respond(personUrl, {
      ...person,
      about: null,
      programme: null,
      year_label: null,
      languages: [],
      goal: null,
      help_subjects: null,
    });
    await shown(person.display_name);
    expect(host().textContent).not.toContain('Learning goal');
  });
  it('blocks, rereads canonical state, then unblocks using current own version', async () => {
    await load();
    click('More options');
    click('Block person');
    click('Confirm');
    const request = await respond(`/api/v1/me/blocks/${person.id}`, blocked);
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual({
      blocked: true,
      expected_version: 0,
      context_id: person.access_context_id,
    });
    expect(request.request.headers.get('x-csrf-token')).toBe(actor.csrf_token);
    expect(request.request.headers.get('idempotency-key')).toMatch(/^[a-f0-9-]{36}$/);
    await respond('/api/v1/me/blocks', {
      people: [{ block: blocked, display_name: person.display_name, deleted: false }],
      next_cursor: null,
    });
    await respond(personUrl, { code: 'person_unavailable' }, 404);
    await shown('This profile is unavailable');
    click('More options');
    click('Unblock person');
    click('Confirm');
    const unblock = await respond(`/api/v1/me/blocks/${person.id}`, {
      ...blocked,
      blocked: false,
      version: 2,
    });
    expect(unblock.request.body).toEqual({
      blocked: false,
      expected_version: 1,
      context_id: person.access_context_id,
    });
    await respond('/api/v1/me/blocks', { people: [], next_cursor: null });
    await respond(personUrl, { ...person, own_block: { ...blocked, blocked: false, version: 2 } });
    await shown(person.display_name);
  });
  it('keeps unknown block payload/key unchanged for explicit retry', async () => {
    await load();
    click('More options');
    click('Block person');
    click('Confirm');
    const original = await respond(`/api/v1/me/blocks/${person.id}`, {}, 503);
    await shown('couldn’t confirm the result');
    click('Retry same block action');
    const retried = await respond(`/api/v1/me/blocks/${person.id}`, {}, 503);
    expect(retried.request.body).toEqual(original.request.body);
    expect(retried.request.headers.get('idempotency-key')).toBe(
      original.request.headers.get('idempotency-key'),
    );
    await shown('couldn’t confirm the result');
    click('Close');
  });
  it('reports actual kind/context and displays only a stored receipt', async () => {
    await load();
    await report();
    comment('Private explanation');
    click('Submit report');
    const request = await respond('/api/v1/reports', receipt, 201);
    expect(request.request.body).toEqual({
      kind: 'profile',
      context_id: person.access_context_id,
      category: 'harassment',
      comment: 'Private explanation',
    });
    await shown('Report stored');
    expect(host().textContent).toContain('does not confirm human review');
    backend.expectNone(`/api/v1/me/blocks/${person.id}`);
  });
  it('validates Other and Unicode length before writing', async () => {
    await load();
    await report();
    const other = host().querySelector('input[value="other"]');
    if (!(other instanceof HTMLInputElement)) throw new Error('Missing Other');
    other.click();
    click('Submit report');
    await shown('Explain the reason');
    comment('😀'.repeat(1001));
    click('Submit report');
    await shown('Use no more than 1000');
    backend.expectNone('/api/v1/reports');
    comment('😀'.repeat(1000));
    click('Submit report');
    await respond('/api/v1/reports', receipt, 201);
    await shown('Report stored');
  });
  it('retries an uncertain report with its exact original private draft and key', async () => {
    await load();
    await report();
    comment('Original');
    click('Submit report');
    const original = await respond('/api/v1/reports', {}, 503);
    await shown('couldn’t confirm');
    comment('Changed draft');
    click('Retry same report');
    const retry = await respond('/api/v1/reports', receipt, 201);
    expect(retry.request.body).toEqual(original.request.body);
    expect(retry.request.headers.get('idempotency-key')).toBe(
      original.request.headers.get('idempotency-key'),
    );
    await shown('Report stored');
  });
  it.each([409, 429, 403, 404])(
    'renders safe report failure %s without provider text',
    async (status) => {
      await load();
      await report();
      click('Submit report');
      await respond(
        '/api/v1/reports',
        {
          code: 'safe_error',
          message: 'secret provider text',
          recovery: { retry_at: '2026-11-08T00:00:00Z' },
        },
        status,
      );
      await shown(
        status === 409
          ? 'The state changed'
          : status === 429
            ? 'Too many attempts'
            : status === 404
              ? 'This report reference is unavailable'
              : 'couldn’t complete',
      );
      expect(host().textContent).not.toContain('secret provider text');
      expect(host().textContent).toContain('Try again after');
    },
  );
  it('clears report drafts and private cache on session expiry', async () => {
    await load();
    await report();
    comment('Never keep this');
    click('Submit report');
    await respond('/api/v1/reports', { code: 'unauthenticated' }, 401);
    await respond('/api/v1/me', {}, 401);
    await shown('Sign in and complete');
    expect(client.getQueryData(['account', actor.account_id, 'person', person.id])).toBeUndefined();
    expect(host().textContent).not.toContain('Never keep this');
  });
  it('pages own blocks without assuming target absence on the first page', async () => {
    await respond('/api/v1/me', actor);
    await respond('/api/v1/me/blocks', { people: [], next_cursor: 'opaque + cursor' });
    await respond(personUrl, person);
    await shown(person.display_name);
    click('Check next blocked people');
    await respond('/api/v1/me/blocks?cursor=opaque%20%2B%20cursor', {
      people: [{ block: blocked, deleted: false, display_name: person.display_name }],
      next_cursor: null,
    });
    click('More options');
    await shown('Unblock person');
  });
  it('revalidates the session after a private read returns 401', async () => {
    await respond('/api/v1/me', actor);
    await respond('/api/v1/me/blocks', { people: [], next_cursor: null });
    await respond(personUrl, {}, 401);
    await respond('/api/v1/me', {}, 401);
    await shown('Sign in and complete');
  });
  it('changes URL-owned identity without showing the previous student', async () => {
    await load();
    params.next(convertToParamMap({ personId: 'another-person' }));
    fixture.detectChanges();
    await respond('/api/v1/people/another-person', {
      ...person,
      id: 'another-person',
      display_name: 'New student',
      own_block: { ...person.own_block, person_id: 'another-person' },
    });
    await shown('New student');
    expect(host().textContent).not.toContain(person.display_name);
  });
  it.each([201, 503])(
    'ignores late report %s after URL changes and drops old mutation cache',
    async (status) => {
      await load();
      await report();
      comment('Old private draft');
      click('Submit report');
      const pending = await vi.waitFor(() => backend.expectOne('/api/v1/reports'));
      params.next(convertToParamMap({ personId: 'new-person' }));
      fixture.detectChanges();
      await respond('/api/v1/people/new-person', {
        ...person,
        id: 'new-person',
        display_name: 'New person',
        own_block: { ...person.own_block, person_id: 'new-person' },
      });
      await shown('New person');
      await report();
      comment('New private draft');
      pending.flush(status === 201 ? receipt : {}, { status, statusText: 'Late result' });
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(host().textContent).toContain('Submit report');
      });
      const field = host().querySelector('#report-comment');
      expect(field instanceof HTMLTextAreaElement && field.value).toBe('New private draft');
      expect(client.getMutationCache().findAll({ mutationKey: ['person-safety'] })).toHaveLength(0);
    },
  );
  it.each([200, 503])('ignores late block %s after navigation', async (status) => {
    await load();
    click('More options');
    click('Block person');
    click('Confirm');
    const pending = await vi.waitFor(() => backend.expectOne(`/api/v1/me/blocks/${person.id}`));
    params.next(convertToParamMap({ personId: 'new-person' }));
    fixture.detectChanges();
    await respond('/api/v1/people/new-person', {
      ...person,
      id: 'new-person',
      display_name: 'New person',
      own_block: { ...person.own_block, person_id: 'new-person' },
    });
    await shown('New person');
    await report();
    pending.flush(status === 200 ? blocked : {}, { status, statusText: 'Late result' });
    await shown('Submit report');
    backend.expectNone('/api/v1/me/blocks');
  });
  it('does not leak previous account report drafts when the session changes', async () => {
    await load();
    await report();
    comment('Old account draft');
    client.setQueryData(['session'], {
      ...actor,
      account_id: 'new-actor',
      csrf_token: 'new-token',
    });
    fixture.detectChanges();
    await respond('/api/v1/me/blocks', { people: [], next_cursor: null });
    await respond(personUrl, person);
    await shown(person.display_name);
    await report();
    const field = host().querySelector('#report-comment');
    expect(field instanceof HTMLTextAreaElement && field.value).toBe('');
  });
  it('preserves uncertainty across status refresh and blocks a replacement intent', async () => {
    await load();
    click('More options');
    click('Block person');
    click('Confirm');
    await respond(`/api/v1/me/blocks/${person.id}`, {}, 503);
    await shown('couldn’t confirm');
    click('Confirm');
    backend.expectNone(`/api/v1/me/blocks/${person.id}`);
    click('Close');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('[role=dialog]')).toBeNull();
    });
    click('Refresh current status');
    await respond('/api/v1/me/blocks', { people: [], next_cursor: null });
    await respond(personUrl, person);
    await shown('couldn’t confirm');
  });
  it('requires explicit refresh after a block version conflict', async () => {
    await load();
    click('More options');
    click('Block person');
    click('Confirm');
    await respond(`/api/v1/me/blocks/${person.id}`, { code: 'block_version_conflict' }, 409);
    await shown('The state changed');
    click('Confirm');
    backend.expectNone(`/api/v1/me/blocks/${person.id}`);
    click('Close');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('[role=dialog]')).toBeNull();
    });
    click('Refresh current status');
    await respond('/api/v1/me/blocks', { people: [], next_cursor: null });
    await respond(personUrl, person);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).not.toContain('The state changed');
    });
    click('More options');
    click('Block person');
    click('Confirm');
    await respond(`/api/v1/me/blocks/${person.id}`, {}, 403);
    await shown('couldn’t complete');
  });
  it('keeps disclosed context reportable when the target disappears without revealing their profile', async () => {
    await load();
    await client.invalidateQueries({
      queryKey: ['account', actor.account_id, 'person', person.id],
      refetchType: 'none',
    });
    const refresh = client.refetchQueries({
      queryKey: ['account', actor.account_id, 'person', person.id],
    });
    await respond(personUrl, {}, 404);
    await refresh;
    await shown('This profile is unavailable');
    expect(host().textContent).not.toContain(person.display_name);
    await report();
    click('Submit report');
    const request = await respond('/api/v1/reports', receipt, 201);
    expect(request.request.body).toMatchObject({ context_id: person.access_context_id });
    await shown('Report stored');
  });
  it('loads only the current authorized JPEG and revokes its object URL on logout', async () => {
    const revoked = vi.spyOn(URL, 'revokeObjectURL');
    await load();
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('img')?.getAttribute('src')).toMatch(/^blob:/);
    });
    const url = host().querySelector('img')?.getAttribute('src');
    client.setQueryData(['session'], null);
    await shown('Sign in and complete');
    expect(revoked).toHaveBeenCalledWith(url);
    expect(host().querySelector('img')).toBeNull();
    revoked.mockRestore();
  });
  it('treats photo storage failure separately from unavailable profile and retries the same current version', async () => {
    await respond('/api/v1/me', actor);
    await respond('/api/v1/me/blocks', { people: [], next_cursor: null });
    const profileRequest = await vi.waitFor(() => backend.expectOne(personUrl));
    profileRequest.flush(person);
    const photoRequest = await vi.waitFor(() => {
      fixture.detectChanges();
      return backend.expectOne(`${personUrl}/photo/1`);
    });
    photoRequest.flush(
      new Blob([JSON.stringify({ code: 'storage_unavailable' })], { type: 'application/json' }),
      { status: 503, statusText: 'Unavailable' },
    );
    await shown('Photo didn’t load');
    expect(host().textContent).toContain(person.display_name);
    click('Retry photo');
    const retry = await vi.waitFor(() => backend.expectOne(`${personUrl}/photo/1`));
    retry.flush(
      new Blob([Uint8Array.from(atob(jpegBase64), (character) => character.charCodeAt(0))], {
        type: 'image/jpeg',
      }),
      { headers: { 'Content-Type': 'image/jpeg' } },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('img')).not.toBeNull();
    });
  });
  it('keeps an uncertain immutable report across same-account session revalidation', async () => {
    await load();
    await report();
    comment('Original intent');
    click('Submit report');
    const original = await respond('/api/v1/reports', {}, 503);
    await shown('couldn’t confirm');
    const revalidation = client.refetchQueries({ queryKey: ['session'] });
    await respond('/api/v1/me', { ...actor, csrf_token: 'revalidated-csrf' });
    await revalidation;
    await respond('/api/v1/me/blocks', { people: [], next_cursor: null });
    await respond(personUrl, { code: 'person_unavailable' }, 404);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('[role=dialog]')).toBeNull();
    });
    await report();
    await shown('Retry same report');
    click('Retry same report');
    const retry = await respond('/api/v1/reports', receipt, 201);
    expect(retry.request.body).toEqual(original.request.body);
    expect(retry.request.headers.get('idempotency-key')).toBe(
      original.request.headers.get('idempotency-key'),
    );
    expect(retry.request.headers.get('x-csrf-token')).toBe('revalidated-csrf');
    await shown('Report stored');
  });
  it('prevents duplicate form submission while a report is pending', async () => {
    await load();
    await report();
    click('Submit report');
    const pending = await vi.waitFor(() => backend.expectOne('/api/v1/reports'));
    await shown('Submitting report');
    const form = host().querySelector('form');
    if (!(form instanceof HTMLFormElement)) throw new Error('Missing report form');
    form.requestSubmit();
    backend.expectNone('/api/v1/reports');
    pending.flush(receipt, { status: 201, statusText: 'Created' });
    await shown('Report stored');
  });
  it('requires refreshing a conflicting report reference before a fresh command', async () => {
    await load();
    await report();
    click('Submit report');
    await respond('/api/v1/reports', {}, 409);
    await shown('The state changed');
    click('Submit report');
    backend.expectNone('/api/v1/reports');
    click('Refresh current status');
    await respond('/api/v1/me/blocks', { people: [], next_cursor: null });
    await respond(personUrl, person);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).not.toContain('The state changed');
    });
    click('Submit report');
    await respond('/api/v1/reports', receipt, 201);
    await shown('Report stored');
  });
  it('does not let an in-flight result update a destroyed screen', async () => {
    await load();
    await report();
    click('Submit report');
    const pending = await vi.waitFor(() => backend.expectOne('/api/v1/reports'));
    fixture.destroy();
    pending.flush(receipt, { status: 201, statusText: 'Created' });
    await vi.waitFor(() => {
      expect(client.getMutationCache().findAll({ mutationKey: ['person-safety'] })).toHaveLength(0);
    });
  });
  it('unblocks an own block after a direct reload without fabricating a fresh disclosure context', async () => {
    await respond('/api/v1/me', actor);
    await respond('/api/v1/me/blocks', {
      people: [{ block: blocked, deleted: false, display_name: person.display_name }],
      next_cursor: null,
    });
    await respond(personUrl, {}, 404);
    await shown('This profile is unavailable');
    click('More options');
    expect(host().textContent).not.toContain('Report profile');
    click('Unblock person');
    click('Confirm');
    const request = await respond(`/api/v1/me/blocks/${person.id}`, {
      ...blocked,
      blocked: false,
      version: 2,
    });
    expect(request.request.body).toEqual({ blocked: false, expected_version: 1 });
    await respond('/api/v1/me/blocks', { people: [], next_cursor: null });
    await respond(personUrl, { ...person, own_block: { ...blocked, blocked: false, version: 2 } });
    await shown(person.display_name);
  });
  it('continues pagination for a directly unavailable profile until its own active block is found', async () => {
    await respond('/api/v1/me', actor);
    await respond('/api/v1/me/blocks', { people: [], next_cursor: 'next' });
    await respond(personUrl, {}, 404);
    await shown('Check next blocked people');
    expect(host().textContent).not.toContain('More options');
    click('Check next blocked people');
    await respond('/api/v1/me/blocks?cursor=next', {
      people: [{ block: blocked, deleted: true, display_name: null }],
      next_cursor: null,
    });
    await shown('More options');
    click('More options');
    await shown('Unblock person');
    expect(host().textContent).not.toContain('Report profile');
  });
  for (const status of [401, 403] as const)
    it(`rechecks canonical authority after summary ${String(status)} without keeping private content`, async () => {
      await load();
      const refresh = client.refetchQueries({
        queryKey: ['account', actor.account_id, 'person', person.id, 'feedback-summary'],
        exact: true,
      });
      await respond(`${personUrl}/feedback-summary`, { code: 'access_changed' }, status);
      await refresh;
      const session = await vi.waitFor(() => backend.expectOne('/api/v1/me'));
      expect(client.getQueryData(['session'])).toBeNull();
      expect(
        client.getQueryData(['account', actor.account_id, 'person', person.id]),
      ).toBeUndefined();
      session.flush({ code: 'unauthenticated' }, { status: 401, statusText: 'Unauthorized' });
      await shown('Sign in and complete student verification');
      expect(host().textContent).not.toContain(person.display_name);
    });
  it('ignores a queued summary event from a retired actor and a non-authority read failure', async () => {
    await load();
    const summary = fixture.debugElement
      .query(By.directive(PersonFeedbackSummary))
      .injector.get(PersonFeedbackSummary);
    summary.sessionFailure.emit({
      actorId: 'former-actor',
      error: new ApiFailure(401, 'unauthenticated', null),
    });
    summary.sessionFailure.emit({
      actorId: actor.account_id,
      error: new ApiFailure(503, 'storage_unavailable', null),
    });
    fixture.detectChanges();
    expect(client.getQueryData(['session'])).toEqual(actor);
    backend.expectNone('/api/v1/me');
    expect(host().textContent).toContain(person.display_name);
  });
  it('replaces a current photo version and revokes the previous private object URL', async () => {
    const revoked = vi.spyOn(URL, 'revokeObjectURL');
    await load();
    await vi.waitFor(() => {
      fixture.detectChanges();
      publishedPhotos();
      expect(host().querySelector('img')?.getAttribute('src')).toMatch(/^blob:/);
    });
    const previous = host().querySelector('img')?.getAttribute('src');
    const refreshing = client.refetchQueries({
      queryKey: ['account', actor.account_id, 'person', person.id],
      exact: true,
    });
    const request = await vi.waitFor(() => backend.expectOne(personUrl));
    request.flush({ ...person, photo: { display_url: `${personUrl}/photo/2`, version: 2 } });
    await refreshing;
    const photo = await vi.waitFor(() => {
      fixture.detectChanges();
      return backend.expectOne(`${personUrl}/photo/2`);
    });
    photo.flush(
      new Blob([Uint8Array.from(atob(jpegBase64), (character) => character.charCodeAt(0))], {
        type: 'image/jpeg',
      }),
      { headers: { 'Content-Type': 'image/jpeg' } },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('img')?.getAttribute('src')).toMatch(/^blob:/);
    });
    expect(host().querySelector('img')?.getAttribute('src')).not.toBe(previous);
    expect(revoked).toHaveBeenCalledWith(previous);
    revoked.mockRestore();
  });
  it('does not resume private reads from cached identity after session revalidation fails', async () => {
    await load();
    const refresh = client.refetchQueries({ queryKey: ['session'] });
    await respond('/api/v1/me', {}, 503);
    await refresh;
    await shown('couldn’t check your session');
    backend.expectNone(personUrl);
    backend.expectNone('/api/v1/me/blocks');
    click('Check session');
    await respond('/api/v1/me', actor);
    await respond('/api/v1/me/blocks', { people: [], next_cursor: null });
    await respond(personUrl, person);
    await shown(person.display_name);
  });
  it('revalidates a photo 401 even when another private query already has a server error', async () => {
    await load();
    const blockRead = client.refetchQueries({ queryKey: ['account', actor.account_id, 'blocks'] });
    await respond('/api/v1/me/blocks', {}, 503);
    await blockRead;
    const photoRead = client.refetchQueries({
      queryKey: ['account', actor.account_id, 'person-photo', person.id],
    });
    const request = await vi.waitFor(() => backend.expectOne(`${personUrl}/photo/1`));
    request.flush(
      new Blob([JSON.stringify({ code: 'unauthenticated' })], { type: 'application/json' }),
      { status: 401, statusText: 'Unauthenticated' },
    );
    await respond('/api/v1/me', {}, 401);
    await photoRead;
    await shown('Sign in and complete');
    expect(client.getQueryData(['account', actor.account_id, 'person', person.id])).toBeUndefined();
  });
  it('uses the supported fullscreen dialog on narrow media without reducing text scale', async () => {
    await load();
    breakpoint.set('mobile');
    await report();
    expect(host().querySelector('tui-dialog')?.getAttribute('data-appearance')).toBe('fullscreen');
  });
  it('rechecks the public profile after a stale photo 404 and reads only the new current version', async () => {
    await respond('/api/v1/me', actor);
    await respond('/api/v1/me/blocks', { people: [], next_cursor: null });
    const profileRequest = await vi.waitFor(() => backend.expectOne(personUrl));
    profileRequest.flush(person);
    const stale = await vi.waitFor(() => {
      fixture.detectChanges();
      return backend.expectOne(`${personUrl}/photo/1`);
    });
    stale.flush(
      new Blob([JSON.stringify({ code: 'person_unavailable' })], { type: 'application/json' }),
      { status: 404, statusText: 'Unavailable' },
    );
    await shown('Photo didn’t load');
    click('Retry photo');
    click('Retry photo');
    await respond(personUrl, {
      ...person,
      photo: { display_url: `${personUrl}/photo/2`, version: 2 },
    });
    const current = await vi.waitFor(() => {
      fixture.detectChanges();
      return backend.expectOne(`${personUrl}/photo/2`);
    });
    current.flush(
      new Blob([Uint8Array.from(atob(jpegBase64), (character) => character.charCodeAt(0))], {
        type: 'image/jpeg',
      }),
      { headers: { 'Content-Type': 'image/jpeg' } },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('img')).not.toBeNull();
    });
    backend.expectNone(`${personUrl}/photo/1`);
  });
  it('retries a browser-decoder failure without requesting an original or historical photo', async () => {
    await load();
    await vi.waitFor(() => {
      fixture.detectChanges();
      publishedPhotos();
      expect(host().querySelector('img')).not.toBeNull();
    });
    host().querySelector('img')?.dispatchEvent(new Event('error'));
    await shown('Photo didn’t load');
    click('Retry photo');
    const request = await vi.waitFor(() => backend.expectOne(`${personUrl}/photo/1`));
    request.flush(
      new Blob([Uint8Array.from(atob(jpegBase64), (character) => character.charCodeAt(0))], {
        type: 'image/jpeg',
      }),
      { headers: { 'Content-Type': 'image/jpeg' } },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().querySelector('img')).not.toBeNull();
    });
  });
  it('does not let a stale photo retry control fetch private bytes after logout', async () => {
    await load();
    await vi.waitFor(() => {
      fixture.detectChanges();
      publishedPhotos();
      expect(host().querySelector('img')).not.toBeNull();
    });
    host().querySelector('img')?.dispatchEvent(new Event('error'));
    await shown('Photo didn’t load');
    const retry = Array.from(host().querySelectorAll('button')).find(
      (button: Readonly<HTMLButtonElement>) => button.textContent.trim() === 'Retry photo',
    );
    if (retry === undefined) throw new Error('Missing photo retry control');
    client.setQueryData(['session'], null);
    retry.click();
    backend.expectNone(`${personUrl}/photo/1`);
    await shown('Sign in and complete');
  });
  it('does not let a stale retry fetch an unknown photo version while another URL target is loading', async () => {
    await load();
    await vi.waitFor(() => {
      fixture.detectChanges();
      publishedPhotos();
      expect(host().querySelector('img')).not.toBeNull();
    });
    host().querySelector('img')?.dispatchEvent(new Event('error'));
    await shown('Photo didn’t load');
    const retry = Array.from(host().querySelectorAll('button')).find(
      (button: Readonly<HTMLButtonElement>) => button.textContent.trim() === 'Retry photo',
    );
    if (retry === undefined) throw new Error('Missing photo retry control');
    params.next(convertToParamMap({ personId: 'new-person' }));
    retry.click();
    backend.expectNone('/api/v1/people/new-person/photo/null');
    await respond('/api/v1/people/new-person', {
      ...person,
      id: 'new-person',
      display_name: 'New person',
      own_block: { ...person.own_block, person_id: 'new-person' },
    });
    await shown('New person');
  });
  it('preserves only Discovery navigation parameters and opens the authoritative preview without sending', async () => {
    query = convertToParamMap({
      mode: 'offer_help',
      view: 'passed',
      cursor: 'opaque+/=',
      redirect: 'https://other.example',
    });
    await load();
    const back = host().querySelector('a[aria-label="Back to Discover"]');
    const review = Array.from(host().querySelectorAll('a')).find(
      (link: Readonly<HTMLAnchorElement>) => link.textContent.trim() === 'Review request',
    );
    if (!(back instanceof HTMLAnchorElement) || review === undefined)
      throw new Error('Missing profile navigation');
    const backUrl = new URL(back.href);
    expect(backUrl.pathname).toBe('/discover');
    expect(backUrl.searchParams.get('mode')).toBe('offer_help');
    expect(backUrl.searchParams.get('view')).toBe('passed');
    expect(backUrl.searchParams.get('cursor')).toBe('opaque+/=');
    expect(backUrl.searchParams.get('person')).toBe(person.id);
    expect(backUrl.searchParams.has('redirect')).toBe(false);
    const preview = new URL(review.href);
    expect(preview.pathname).toBe('/discover');
    expect(preview.searchParams.get('mode')).toBe('offer_help');
    expect(preview.searchParams.get('person')).toBe(person.id);
    expect(preview.searchParams.get('compose')).toBe('request');
    backend.expectNone((request) => request.method !== 'GET');
  });

  it('defaults a direct profile preview to Find help without forwarding untrusted mode or return URLs', async () => {
    query = convertToParamMap({ mode: 'unknown', view: 'unknown', next: '//other.example' });
    await load();
    const back = host().querySelector('a[aria-label="Back to Discover"]');
    const review = Array.from(host().querySelectorAll('a')).find(
      (link: Readonly<HTMLAnchorElement>) => link.textContent.trim() === 'Review request',
    );
    if (!(back instanceof HTMLAnchorElement) || review === undefined)
      throw new Error('Missing profile navigation');
    expect(new URL(back.href).search).toBe('');
    expect(new URL(review.href).searchParams.get('mode')).toBe('find_help');
    backend.expectNone((request) => request.method !== 'GET');
  });
});
