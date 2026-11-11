import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TuiRoot } from '@taiga-ui/core';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../../../api.generated';
import type { ApiFailure } from '../../../api-http';
import { appConfig } from '../../../app.config';
import { verifiedActor } from '../onboarding.fixtures';
const actor = {
  ...verifiedActor,
  capabilities: { ...verifiedActor.capabilities, can_use_student_features: true },
} as const;
import { OwnFeedbackSummary } from './feedback-summary';
import { isFeedbackSummary } from './feedback-summary-contract';

const building = {
  state: 'building',
  responses: 2,
  publicly_visible: true,
} as const satisfies Api['schemas']['BuildingFeedbackSummaryResponse'];
const available = {
  state: 'available',
  responses: 5,
  yes: 3,
  maybe: 1,
  no: 1,
  publicly_visible: true,
} as const satisfies Api['schemas']['AvailableFeedbackSummaryResponse'];
@Component({
  selector: 'summary-test-host',
  imports: [TuiRoot, OwnFeedbackSummary],
  template: `<tui-root
    ><app-own-feedback-summary [actorId]="owner()" (sessionFailure)="failed($event)"
  /></tui-root>`,
})
class SummaryHost {
  public readonly owner = signal<string>(actor.account_id);
  public readonly failures = signal<
    readonly Readonly<{ readonly actorId: string; readonly error: ApiFailure }>[]
  >([]);
  public failed(value: Readonly<{ readonly actorId: string; readonly error: ApiFailure }>): void {
    this.failures.update((values) => [...values, value]);
  }
}

describe('F03 actual aggregate guard', () => {
  it('accepts thresholded counts and explicit zero/building without deriving proficiency', () => {
    expect(isFeedbackSummary(building)).toBe(true);
    expect(isFeedbackSummary({ responses: 2, publicly_visible: true })).toBe(true);
    expect(
      isFeedbackSummary({ responses: 3, yes: 1, maybe: 1, no: 1, publicly_visible: true }),
    ).toBe(true);
    expect(isFeedbackSummary({ ...building, responses: 0 })).toBe(true);
    expect(isFeedbackSummary(available)).toBe(true);
    expect(isFeedbackSummary({ ...available, publicly_visible: false })).toBe(true);
  });
  for (const value of [
    null,
    [],
    {},
    { ...building, state: 'other' },
    { ...building, responses: 3 },
    { ...building, responses: -1 },
    { ...building, responses: 0.5 },
    { ...building, yes: 1 },
    { ...building, maybe: 1 },
    { ...building, no: 1 },
    { ...building, publicly_visible: 'true' },
    { ...available, responses: 2 },
    { ...available, yes: 9 },
    { ...available, maybe: -1 },
    { ...available, no: 0.5 },
    { ...available, yes: Number.MAX_SAFE_INTEGER + 1 },
    { ...available, responses: NaN },
    { ...available, maybe: undefined },
  ])
    it(`rejects corrupt or premature aggregate ${JSON.stringify(value)}`, () => {
      expect(isFeedbackSummary(value)).toBe(false);
    });
});

describe('F03 own profile feedback, private actor scope', () => {
  let fixture: ComponentFixture<SummaryHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  const url = '/api/v1/me/feedback-summary';
  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    client.setQueryData(['session'], actor);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    backend = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(SummaryHost);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
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
  function click(label: string): void {
    const button = Array.from(host().querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.trim() === label,
    );
    if (button === undefined) throw new Error('Missing action');
    button.click();
    fixture.detectChanges();
  }
  async function respond(body: Readonly<Record<string, unknown>>, status = 200): Promise<void> {
    const request = await vi.waitFor(() => backend.expectOne(url));
    expect(request.request.method).toBe('GET');
    request.flush(body, { status, statusText: status === 200 ? 'OK' : 'Unavailable' });
  }
  it('renders building count without rating cells and explains privacy on explicit action', async () => {
    await respond(building);
    await shown('2 partners have responded.');
    expect(host().querySelector('dl')).toBeNull();
    click('About');
    await shown('Names and notes are never shown');
    click('About');
    expect(host().textContent).not.toContain('Names and notes are never shown');
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('renders exact Yes Maybe No and no invented descriptors or proficiency score', async () => {
    await respond(available);
    await shown('3 of 5 partners would study together again.');
    expect(
      Array.from(host().querySelectorAll('dt')).map(
        (item: Readonly<HTMLElement>) => item.textContent,
      ),
    ).toEqual(['Yes', 'Maybe', 'No']);
    expect(
      Array.from(host().querySelectorAll('dd')).map(
        (item: Readonly<HTMLElement>) => item.textContent,
      ),
    ).toEqual(['3', '1', '1']);
    expect(host().textContent).not.toContain('Mentioned most');
    expect(client.getQueryData(['account', actor.account_id, 'feedback-summary'])).toEqual(
      available,
    );
  });
  it('does not disclose counts when returned public visibility is false', async () => {
    await respond({ ...available, publicly_visible: false });
    await shown('Your feedback summary isn’t public');
    expect(host().querySelector('dl')).toBeNull();
    expect(host().textContent).not.toContain('3 of 5');
  });
  it('treats404 as unavailable without guessing a private lifecycle reason', async () => {
    await respond({ code: 'profile_unavailable' }, 404);
    await shown('Your feedback summary is unavailable');
    expect(host().textContent).not.toContain('hidden');
    expect(host().textContent).not.toContain('deleted');
    expect(host().textContent).not.toContain('Retry feedback');
  });
  it('keeps503 local and retries only after explicit user action', async () => {
    await respond({ code: 'storage_unavailable' }, 503);
    await shown('We couldn’t load peer feedback.');
    backend.expectNone(url);
    click('Retry feedback');
    await respond(available);
    await shown('3 of 5');
  });
  it('rejects a malformed successful response without exposing corrupt counts', async () => {
    await respond({ ...available, yes: 9 });
    await shown('We couldn’t load peer feedback.');
    expect(host().textContent).not.toContain('9 of 5');
  });
  for (const status of [401, 403] as const)
    it(`reports${status.toString()} to the actual parent owner`, async () => {
      await respond({ code: 'access_changed' }, status);
      await vi.waitFor(() => {
        expect(fixture.componentInstance.failures()).toHaveLength(1);
      });
      expect(fixture.componentInstance.failures()[0]?.actorId).toBe(actor.account_id);
      expect(fixture.componentInstance.failures()[0]?.error.status).toBe(status);
    });
  it('aborts a former actor read and never reveals it after replacement', async () => {
    const old = await vi.waitFor(() => backend.expectOne(url));
    const next = '00000000-0000-4000-8000-000000000099';
    client.setQueryData(['session'], { ...actor, account_id: next });
    fixture.componentInstance.owner.set(next);
    fixture.detectChanges();
    expect(old.cancelled).toBe(true);
    await respond(building);
    await shown('2 partners');
    expect(host().textContent).not.toContain('3 of 5');
    expect(client.getQueryData(['account', next, 'feedback-summary'])).toEqual(building);
  });
  it('cancels the native request when the actual component is destroyed', async () => {
    const request = await vi.waitFor(() => backend.expectOne(url));
    fixture.destroy();
    expect(request.cancelled).toBe(true);
  });
  it('reads canonical counts again when returning to a recently visited profile', async () => {
    await respond(available);
    await shown('3 of 5');
    fixture.destroy();
    fixture = TestBed.createComponent(SummaryHost);
    fixture.detectChanges();
    await respond(building);
    await shown('2 partners');
    expect(host().textContent).not.toContain('3 of 5');
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('does not retry a private read after its canonical session was cleared', async () => {
    await respond({ code: 'storage_unavailable' }, 503);
    await shown('We couldn’t load peer feedback.');
    client.setQueryData(['session'], null);
    click('Retry feedback');
    await vi.waitFor(() => {
      expect(
        client.getQueryState(['account', actor.account_id, 'feedback-summary'])?.fetchStatus,
      ).toBe('idle');
    });
    backend.expectNone(url);
  });
});
