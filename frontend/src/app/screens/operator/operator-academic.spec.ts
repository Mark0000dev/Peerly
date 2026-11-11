import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import type { Api } from '../../api.generated';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { TuiRoot } from '@taiga-ui/core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../app.config';
import { Operator } from './operator';
import { userEvent } from 'vitest/browser';
import type { Query } from '@tanstack/angular-query-experimental';
import {
  academicGoal,
  academicGoals,
  academicHistory,
  academicHelp,
  academicRevision,
} from './operator-academic.fixtures';
import { account, accounts, detail, operatorIdentity } from './operator.fixtures';

@Component({
  selector: 'operator-host',
  imports: [TuiRoot, Operator],
  template: '<tui-root><app-operator /></tui-root>',
})
class Host {}
@Component({ template: '' })
class Empty {}

describe('M04 academic actual tabs, history and shared authority', () => {
  let fixture: ComponentFixture<Host>;
  let backend: HttpTestingController;
  let client: QueryClient;
  let router: Router;
  const target = `/api/v1/operator/accounts/${account.account_id}`;
  beforeEach(async () => {
    client = new QueryClient({
      defaultOptions: {
        queries: { retry: false, refetchOnWindowFocus: false },
        mutations: { retry: false },
      },
    });
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideRouter([{ path: 'operator/accounts', component: Empty }]),
        provideHttpClientTesting(),
        provideTanStackQuery(client),
      ],
    });
    router = TestBed.inject(Router);
    await router.navigateByUrl('/operator/accounts');
    fixture = TestBed.createComponent(Host);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
    vi.restoreAllMocks();
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
  function button(text: string): void {
    const value = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) =>
        item.textContent.trim() === text || item.getAttribute('aria-label') === text,
    );
    if (value === undefined) throw new Error('Missing button');
    value.click();
    fixture.detectChanges();
  }
  function fill(id: string, value: string): void {
    const input = host().querySelector(`#operator-${id}`);
    if (!(input instanceof HTMLInputElement)) throw new Error('Missing input');
    input.setRangeText(value, 0, input.value.length);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
  }
  async function navigate(query: Readonly<Record<string, string>>): Promise<void> {
    await router.navigateByUrl(`/operator/accounts?${new URLSearchParams(query).toString()}`);
    fixture.detectChanges();
  }
  async function login(query: Readonly<Record<string, string>> = {}): Promise<void> {
    await navigate(query);
    backend.expectOne('/api/v1/me').flush(operatorIdentity);
    await shown('Find accounts');
  }
  async function flushList(
    body: Api['schemas']['OperatorAccountsResponse'] = accounts,
  ): Promise<void> {
    await vi.waitFor(() => {
      backend
        .expectOne((request) => request.url.startsWith('/api/v1/operator/accounts?'))
        .flush(body);
    });
  }
  async function flushDetail(
    body: Api['schemas']['OperatorAccountDetailResponse'] = detail,
  ): Promise<void> {
    await vi.waitFor(() => {
      backend.expectOne(target).flush(body);
    });
  }
  const roots = `${target}/goals`;
  const history = `${roots}/${academicGoal.id}/history`;
  const help = `${target}/help-history`;
  async function flushRoots(
    body: Api['schemas']['OperatorGoalsResponse'] = academicGoals,
  ): Promise<void> {
    await vi.waitFor(() => {
      backend.expectOne((request) => request.url.startsWith(`${roots}?`)).flush(body);
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).not.toContain('Loading goals…');
    });
  }
  async function flushHistory(
    body: Api['schemas']['OperatorGoalHistoryResponse'] = academicHistory,
  ): Promise<void> {
    await vi.waitFor(() => {
      backend.expectOne((request) => request.url.startsWith(`${history}?`)).flush(body);
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).not.toContain('Loading goal history…');
    });
  }
  async function flushHelp(
    body: Api['schemas']['OperatorHelpHistoryResponse'] = academicHelp,
  ): Promise<void> {
    await vi.waitFor(() => {
      backend.expectOne((request) => request.url.startsWith(`${help}?`)).flush(body);
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host().textContent).not.toContain('Loading help history…');
    });
  }
  async function fail(path: string, status: number): Promise<void> {
    await vi.waitFor(() => {
      backend
        .expectOne((request) => request.url.startsWith(`${path}?`))
        .flush(
          { code: status === 403 ? 'operator_access_denied' : 'controlled_failure' },
          { status, statusText: 'Controlled failure' },
        );
    });
  }
  it('fetches only the actual active tab and explicit selected goal; renders historical literal text safely', async () => {
    await login({ account: account.account_id });
    await flushDetail();
    await shown('Comparing LEFT JOIN examples.');
    backend.expectNone(
      (request) => request.url.includes('/goals') || request.url.includes('/help-history'),
    );
    button('Goals');
    await flushRoots();
    await shown(academicGoal.id);
    backend.expectNone((request) => request.url.startsWith(`${history}?`));
    expect(host().textContent).not.toContain(academicRevision.subject_label);
    button(`Inspect goal ${academicGoal.id}`);
    await flushHistory();
    await shown(academicRevision.subject_label);
    expect(host().textContent).toContain(academicRevision.context);
    expect(host().textContent).toContain('ARCHIVE:key/unchanged');
    expect(host().querySelector('b')).toBeNull();
    expect(router.url).toContain(`goal=${academicGoal.id}`);
    button('Close goal history');
    await vi.waitFor(() => {
      expect(router.url).not.toContain('goal=');
    });
    button('Help');
    await flushHelp();
    await shown('Stored clear');
    await shown('Historical SQL <literal>');
    expect(host().querySelector('[role=tab][aria-selected=true]')?.textContent.trim()).toBe('Help');
    expect(host().querySelector('[role=tabpanel]')?.getAttribute('aria-labelledby')).toBe(
      'operator-tab-help',
    );
    button('Overview');
    await flushDetail();
    await shown('Comparing LEFT JOIN examples.');
  });
  it('submits URL filters explicitly, resets selected history/cursor and keeps opaque root pages separate', async () => {
    await login({
      account: account.account_id,
      tab: 'goals',
      goal_state: 'completed',
      goals_cursor: 'opaque-old',
    });
    await flushRoots({
      ...academicGoals,
      goals: [{ ...academicGoal, completed_at: academicRevision.saved_at }],
      next_cursor: 'opaque +/=',
    });
    await shown('Completed at');
    button('Next goals');
    await flushRoots();
    await vi.waitFor(() => {
      expect(new URL(router.url, 'http://fixture.invalid').searchParams.get('goals_cursor')).toBe(
        'opaque +/=',
      );
    });
    button('First goals page');
    await flushRoots();
    button('Refresh goals');
    await flushRoots();
    const select = host().querySelector('#operator-goal-state');
    if (!(select instanceof HTMLSelectElement)) throw new Error('Missing state select');
    await userEvent.selectOptions(select, 'active');
    fill('goal-from', '2025-01-01T00:00:00Z');
    fill('goal-before', '2026-01-01T00:00:00+08:00');
    backend.expectNone((request) => request.url.startsWith(`${roots}?`));
    button('Apply filters');
    await flushRoots({ ...academicGoals, goals: [] });
    await shown('No stored goals match');
    expect(router.url).toContain('goal_state=active');
    expect(router.url).not.toContain('goals_cursor=');
    expect(router.url).not.toContain('goal=');
    fill('goal-before', 'invalid');
    button('Apply filters');
    await shown('timezone');
    backend.expectNone((request) => request.url.startsWith(`${roots}?`));
  });
  it('keeps help stored order/clear distinct from absent history and resets opaque help pagination on refresh', async () => {
    await login({ account: account.account_id, tab: 'help' });
    await flushHelp({ ...academicHelp, next_cursor: 'older/help+=' });
    await shown('Stored clear');
    backend.expectNone((request) => request.url.includes('/goals'));
    button('Older help revisions');
    await flushHelp({ ...academicHelp, revisions: [], anchor_version: 0 });
    await shown('No stored help revisions.');
    expect(new URL(router.url, 'http://fixture.invalid').searchParams.get('help_cursor')).toBe(
      'older/help+=',
    );
    button('Refresh help history');
    await flushHelp();
    await shown('Historical SQL <literal>');
    expect(router.url).not.toContain('help_cursor=');
    button('Refresh help history');
    await flushHelp();
  });
  it('blocks malformed selected goal before inspection and resets only academic filters', async () => {
    await login({ account: account.account_id, tab: 'goals', goal: 'bad', goal_state: 'active' });
    await shown('selected goal ID must be a UUID');
    backend.expectNone((request) => request.url.includes('/operator/accounts/'));
    button('Reset academic filters');
    await flushRoots();
    expect(router.url).toContain(`account=${account.account_id}`);
    expect(router.url).not.toContain('goal_state=');
    await navigate({ account: account.account_id, tab: 'unknown' });
    await shown('Choose Overview, Goals or Help.');
  });
  it('keeps503/404 local to goal panels and explicitly retries/reset invalid root and history cursors', async () => {
    await login({ account: account.account_id, tab: 'goals', goals_cursor: 'invalid' });
    await fail(roots, 422);
    await shown('These filters or this cursor could not be used');
    button('First goals page');
    await fail(roots, 503);
    await shown('records could not be loaded');
    button('Retry goals');
    await flushRoots();
    button(`Inspect goal ${academicGoal.id}`);
    await fail(history, 404);
    await shown('academic record is unavailable');
    expect(host().textContent).toContain('Stored goal roots.');
    button('Retry goal history');
    await flushHistory({ ...academicHistory, next_cursor: 'older-goal' });
    await shown(academicRevision.subject_label);
    button('Older goal revisions');
    await fail(history, 422);
    await shown('These filters or this cursor could not be used');
    button('First goal history page');
    await flushHistory({ ...academicHistory, revisions: [] });
    await shown('No stored goal revisions');
    button('Refresh goal history');
    await flushHistory({ ...academicHistory, next_cursor: 'older-again' });
    button('Older goal revisions');
    await flushHistory();
    button('Refresh goal history');
    await flushHistory();
  });
  it('retries missing/failed help reads and resets invalid help cursor without losing selected account', async () => {
    await login({ account: account.account_id, tab: 'help', help_cursor: 'invalid' });
    await fail(help, 422);
    await shown('These filters or this cursor could not be used');
    button('First help history page');
    await fail(help, 404);
    await shown('academic record is unavailable');
    button('Retry help history');
    await fail(help, 503);
    await shown('records could not be loaded');
    button('Retry help history');
    await flushHelp();
    expect(router.url).toContain(`account=${account.account_id}`);
    expect(host().textContent).not.toContain('Operator access denied');
  });
  it('retires all siblings on child403 including in-flight overview/list and allows explicit authority recheck', async () => {
    await login({ account: account.account_id, lifecycle: 'all' });
    const list = backend.expectOne((request) =>
      request.url.startsWith('/api/v1/operator/accounts?'),
    );
    const overview = backend.expectOne(target);
    await navigate({
      account: account.account_id,
      lifecycle: 'all',
      tab: 'goals',
      goal: academicGoal.id,
    });
    const pending = backend.expectOne((request) => request.url.startsWith(`${roots}?`));
    await fail(history, 403);
    await shown('Operator access denied');
    expect(list.cancelled).toBe(true);
    expect(overview.cancelled).toBe(true);
    expect(pending.cancelled).toBe(true);
    expect(host().textContent).not.toContain('Stored goal roots.');
    expect(
      client
        .getQueryCache()
        .findAll({ queryKey: ['account', operatorIdentity.account_id, 'operator'] }),
    ).toHaveLength(1);
    button('Check access again');
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush(operatorIdentity);
    });
    await flushList();
    await flushRoots();
    await flushHistory();
    await shown(academicRevision.subject_label);
  });
  it('replacement actor retires prior help content and starts its own page without old actor cursor', async () => {
    await login({ account: account.account_id, tab: 'help', help_cursor: 'old-actor-page' });
    await flushHelp();
    await shown('Historical SQL <literal>');
    const replacement = { ...operatorIdentity, account_id: '00000000-0000-4000-8000-000000000099' };
    void client.invalidateQueries({ queryKey: ['session'] });
    await vi.waitFor(() => {
      backend.expectOne('/api/v1/me').flush(replacement);
    });
    const request = await vi.waitFor(() =>
      backend.expectOne((item) => item.url.startsWith(`${help}?`)),
    );
    expect(
      new URL(request.request.url, 'http://fixture.invalid').searchParams.get('cursor'),
    ).toBeNull();
    request.flush({ code: 'operator_access_denied' }, { status: 403, statusText: 'Forbidden' });
    await shown('Operator access denied');
    expect(host().textContent).not.toContain('Historical SQL <literal>');
    expect(router.url).not.toContain('help_cursor=');
  });
  it('clears real native state/date controls into unfiltered URL without sending all or null strings', async () => {
    await login({
      account: account.account_id,
      tab: 'goals',
      goal_state: 'completed',
      goal_created_from: '2025-01-01T00:00:00Z',
    });
    await flushRoots({
      ...academicGoals,
      goals: [{ ...academicGoal, completed_at: academicRevision.saved_at }],
    });
    for (const id of ['operator-goal-state', 'operator-goal-from']) {
      const field = host().querySelector(`#${id}`);
      const cleaner = field?.closest('tui-textfield')?.querySelector('button');
      if (!(cleaner instanceof HTMLButtonElement)) throw new Error('Missing academic cleaner');
      cleaner.click();
      fixture.detectChanges();
    }
    button('Apply filters');
    await flushRoots();
    expect(router.url).not.toContain('goal_state=');
    expect(router.url).not.toContain('goal_created_from=');
  });
  it('rejects valid-shaped responses belonging to a different requested account or goal at the HTTP boundary', async () => {
    await login({ account: account.account_id, tab: 'goals' });
    await flushRoots({ ...academicGoals, account_id: academicGoal.id, goals: [] });
    await shown('records could not be loaded');
    await navigate({ account: account.account_id, tab: 'goals', goal: academicGoal.id });
    await flushHistory({
      ...academicHistory,
      goal: { ...academicGoal, id: account.account_id },
      revisions: [],
    });
    await shown('records could not be loaded');
    expect(host().textContent).not.toContain(academicRevision.subject_label);
    await navigate({ account: account.account_id, tab: 'help' });
    await flushHelp({ ...academicHelp, account_id: academicGoal.id, revisions: [] });
    await shown('records could not be loaded');
    expect(host().textContent).not.toContain('Historical SQL <literal>');
  });
  it('changing history page does not cancel an independently pending roots read in the same tab', async () => {
    await login({ account: account.account_id, tab: 'goals', goal: academicGoal.id });
    const pendingRoots = await vi.waitFor(() =>
      backend.expectOne((request) => request.url.startsWith(`${roots}?`)),
    );
    await flushHistory({ ...academicHistory, next_cursor: 'older' });
    await shown(academicRevision.subject_label);
    button('Older goal revisions');
    const nextHistory = await vi.waitFor(() =>
      backend.expectOne((request) => request.url.startsWith(`${history}?`)),
    );
    expect(pendingRoots.cancelled).toBe(false);
    nextHistory.flush(academicHistory);
    pendingRoots.flush(academicGoals);
    await shown('Current version');
  });
  it('child401 retires cached parent identity and rechecks the canonical session before further reads', async () => {
    await login({ account: account.account_id, tab: 'help' });
    await fail(help, 401);
    await vi.waitFor(() => {
      backend
        .expectOne('/api/v1/me')
        .flush({ code: 'unauthenticated' }, { status: 401, statusText: 'Unauthenticated' });
    });
    await shown('Sign in with your operator Google account');
    expect(
      client.getQueryCache().findAll({ queryKey: ['account', operatorIdentity.account_id] }),
    ).toHaveLength(0);
    expect(
      client
        .getQueryCache()
        .findAll({ queryKey: ['account'] })
        .every((query: Readonly<Query>) => query.state.data === undefined),
    ).toBe(true);
    backend.expectNone((request) => request.url.includes('/help-history'));
  });
});
