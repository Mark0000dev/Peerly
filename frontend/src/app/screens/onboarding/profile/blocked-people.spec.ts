import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../app.config';
import { verifiedActor } from '../onboarding.fixtures';
import { click, shown } from '../testing-host';
import { BlockedPeople } from './blocked-people';

const person = {
  block: {
    person_id: '00000000-0000-4000-8000-000000000055',
    blocked: true,
    version: 2,
    changed_at: '2026-11-07T12:00:00Z',
  },
  display_name: 'Maya Tan',
  deleted: false,
} as const;
describe('owner block list command boundary', () => {
  let fixture: ComponentFixture<BlockedPeople>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    TestBed.resetTestingModule();
    client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    client.setQueryData(['session'], verifiedActor);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(BlockedPeople);
    fixture.componentRef.setInput('actor', verifiedActor);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify({ ignoreCancelled: true });
  });
  async function load(): Promise<void> {
    const read = await vi.waitFor(() => backend.expectOne('/api/v1/me/blocks'));
    read.flush({ people: [person], next_cursor: null });
    await shown(fixture, person.display_name);
  }
  it('uses server CAS and replays only the identical uncertain unblock', async () => {
    await load();
    click(fixture, 'Unblock');
    const first = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/me/blocks/${person.block.person_id}`),
    );
    expect(first.request.body).toEqual({ blocked: false, expected_version: 2 });
    expect(first.request.headers.get('x-csrf-token')).toBe(verifiedActor.csrf_token);
    const key = first.request.headers.get('idempotency-key');
    first.error(new ProgressEvent('error'));
    await shown(fixture, 'Retry same unblock');
    click(fixture, 'Retry same unblock');
    const retry = await vi.waitFor(() => backend.expectOne(first.request.url));
    expect(retry.request.body).toEqual(first.request.body);
    expect(retry.request.headers.get('idempotency-key')).toBe(key);
    retry.flush({ ...person.block, blocked: false, version: 3 });
    const read = await vi.waitFor(() => backend.expectOne('/api/v1/me/blocks'));
    read.flush({ people: [], next_cursor: null });
    await shown(fixture, 'No blocked people on this page.');
  });
  it('does not issue private commands while the same actor authority is unknown', async () => {
    await load();
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    click(fixture, 'Unblock');
    click(fixture, 'Reload blocked people');
    backend.expectNone((request) => request.method === 'PUT');
    backend.expectNone('/api/v1/me/blocks');
    fixture.componentRef.setInput('checking', false);
    fixture.detectChanges();
  });
  it('treats an incorrect person receipt as uncertain, not a successful unblock', async () => {
    await load();
    click(fixture, 'Unblock');
    const request = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/me/blocks/${person.block.person_id}`),
    );
    request.flush({ ...person.block, person_id: 'other-person', blocked: false });
    await shown(fixture, 'Retry same unblock');
    backend.expectNone('/api/v1/me/blocks');
  });
  it('notifies the actual auth boundary for denied reads without fabricating an empty list', async () => {
    const expired = vi.fn();
    fixture.componentInstance.expired.subscribe(expired);
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/me/blocks'));
    request.flush({ code: 'membership_required' }, { status: 403, statusText: 'Forbidden' });
    await shown(fixture, 'Blocked people could not be loaded.');
    expect(expired).toHaveBeenCalled();
  });
  it('paginates the actual opaque owner cursor and returns to the first canonical page without merging copied people', async () => {
    const initial = await vi.waitFor(() => backend.expectOne('/api/v1/me/blocks'));
    initial.flush({ people: [person], next_cursor: 'page 2' });
    await shown(fixture, person.display_name);
    click(fixture, 'Next page');
    const next = await vi.waitFor(() => backend.expectOne('/api/v1/me/blocks?cursor=page%202'));
    next.flush({ people: [{ ...person, deleted: true, display_name: null }], next_cursor: null });
    await shown(fixture, 'Deleted account');
    click(fixture, 'First page');
    const first = await vi.waitFor(() => backend.expectOne('/api/v1/me/blocks'));
    first.flush({ people: [person], next_cursor: null });
    await shown(fixture, person.display_name);
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('does not convert a version conflict into an automatic unblock, and explicitly reloads the current block version', async () => {
    await load();
    click(fixture, 'Unblock');
    const write = await vi.waitFor(() =>
      backend.expectOne(`/api/v1/me/blocks/${person.block.person_id}`),
    );
    write.flush({ code: 'block_version_conflict' }, { status: 409, statusText: 'Conflict' });
    await shown(fixture, 'Unblocking could not be completed.');
    click(fixture, 'Unblock');
    backend.expectNone((request) => request.method === 'PUT');
    click(fixture, 'Reload blocked people');
    const read = await vi.waitFor(() => backend.expectOne('/api/v1/me/blocks'));
    read.flush({
      people: [{ ...person, block: { ...person.block, version: 3 } }],
      next_cursor: null,
    });
    await shown(fixture, person.display_name);
    backend.expectNone((request) => request.method === 'PUT');
  });
});
