import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTanStackQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../app.config';
import { SupportRecovery } from './support-recovery';
import { supportActorFixture, supportReceiptFixture } from './support-test-data';

function host(fixture: Readonly<ComponentFixture<SupportRecovery>>): HTMLElement {
  const element: unknown = fixture.nativeElement;
  if (!(element instanceof HTMLElement)) throw new Error('Missing recovery host');
  return element;
}
describe('Support recovery reads actual owner without remembered ID or issuing new proof', () => {
  let fixture: ComponentFixture<SupportRecovery>;
  let http: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideRouter([]),
        provideHttpClientTesting(),
        provideTanStackQuery(client),
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(SupportRecovery);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    http.verify({ ignoreCancelled: true });
    TestBed.resetTestingModule();
  });
  function click(label: string): void {
    const button = Array.from(host(fixture).querySelectorAll('button')).find(
      (item: Readonly<HTMLButtonElement>) => item.textContent.trim() === label,
    );
    if (button === undefined) throw new Error('Missing recovery action');
    button.click();
    fixture.detectChanges();
  }
  it('recovers anonymous receipts after reload and explains status metadata only', async () => {
    (await vi.waitFor(() => http.expectOne('/api/v1/me'))).flush(
      { code: 'unauthenticated' },
      { status: 401, statusText: 'Unauthorized' },
    );
    (await vi.waitFor(() => http.expectOne('/api/v1/support-cases'))).flush({
      cases: [{ ...supportReceiptFixture, status: 'resolved', version: 2 }],
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain(supportReceiptFixture.case_id);
    });
    expect(host(fixture).textContent).toContain('doesn’t confirm an account change');
    http.expectNone('/api/v1/support-context');
  });
  it('uses actor receipts even for banned/unverified identity and allows separate browser proof discovery', async () => {
    (await vi.waitFor(() => http.expectOne('/api/v1/me'))).flush({
      ...supportActorFixture,
      account_status: 'banned',
      membership_status: 'unverified',
    });
    (await vi.waitFor(() => http.expectOne('/api/v1/me/support-cases'))).flush({ cases: [] });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('No recent requests');
    });
    click('Check this browser’s support proof');
    (await vi.waitFor(() => http.expectOne('/api/v1/support-cases'))).flush(
      { code: 'support_unavailable' },
      { status: 404, statusText: 'Not found' },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('original proof');
    });
    http.expectNone('/api/v1/support-context');
  });
  it('keeps browser proof recovery independent of unavailable session and supports explicit retry', async () => {
    (await vi.waitFor(() => http.expectOne('/api/v1/me'))).flush(
      { code: 'storage_unavailable' },
      { status: 503, statusText: 'Unavailable' },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('could not yet');
    });
    click('Check this browser’s support proof');
    (await vi.waitFor(() => http.expectOne('/api/v1/support-cases'))).flush(
      { code: 'storage_unavailable', request_id: 'support-reference' },
      { status: 503, statusText: 'Unavailable' },
    );
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('support-reference');
    });
    click('Check again');
    (await vi.waitFor(() => http.expectOne('/api/v1/support-cases'))).flush({ cases: [] });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('does not confirm whether');
    });
  });
  it('rechecks unavailable identity, switches proof/current actor owners and aborts an older proof read', async () => {
    (await vi.waitFor(() => http.expectOne('/api/v1/me'))).flush(
      { code: 'storage_unavailable' },
      { status: 503, statusText: 'Unavailable' },
    );
    await vi.waitFor(() => {
      // Pending and failed identity share this neutral UI. The explicit retry
      // must follow the actual failed read, not deduplicate its pending promise.
      expect(client.getQueryState(['session'])).toMatchObject({
        status: 'error',
        fetchStatus: 'idle',
      });
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('could not yet');
    });
    click('Check sign-in state');
    (await vi.waitFor(() => http.expectOne('/api/v1/me'))).flush(supportActorFixture);
    (await vi.waitFor(() => http.expectOne('/api/v1/me/support-cases'))).flush({
      cases: [supportReceiptFixture],
    });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain(supportReceiptFixture.case_id);
    });
    click('Check this browser’s support proof');
    const proof = await vi.waitFor(() => http.expectOne('/api/v1/support-cases'));
    click('Check account requests');
    expect(proof.cancelled).toBe(true);
    (await vi.waitFor(() => http.expectOne('/api/v1/me/support-cases'))).flush({ cases: [] });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).toContain('No recent requests');
    });
    expect(host(fixture).textContent).not.toContain(supportReceiptFixture.case_id);
    http.expectNone('/api/v1/support-context');
  });
});
