import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { Router } from '@angular/router';
import { QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app';
import { ObservationRelease } from '../../observability/observation-release';
import { appConfig } from '../../app.config';
import { Policy } from './policy';

const document = {
  title: 'Privacy Policy',
  content: 'Published fixture text\nSecond paragraph.',
  reference: {
    id: '00000000-0000-0000-0000-000000000010',
    kind: 'privacy',
    version: 'test-v1',
    published_at: '2026-11-07T12:00:00Z',
  },
};

describe('published versioned policy reader', () => {
  let fixture: ComponentFixture<App>;
  let backend: HttpTestingController;
  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        {
          provide: ObservationRelease,
          useValue: { current: () => null, load: () => Promise.resolve() },
        },
        provideHttpClientTesting(),
      ],
    });
    fixture = TestBed.createComponent(App);
    backend = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    for (const node of fixture.debugElement.queryAll(By.directive(Policy)))
      node.injector.get(QueryClient).clear();
    fixture.destroy();
    backend.verify();
  });
  function text(): string {
    const value: unknown = fixture.nativeElement;
    if (!(value instanceof HTMLElement)) throw new Error('No document view');
    return value.textContent;
  }
  async function shown(expected: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(text()).toContain(expected);
    });
  }
  it('loads history only on explicit URL navigation and scopes pagination to its kind', async () => {
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/privacy?view=history');
    const first = await vi.waitFor(() =>
      backend.expectOne('/api/v1/policies/privacy/versions?limit=20'),
    );
    backend.expectNone('/api/v1/policies/privacy');
    first.flush({
      items: [{ title: document.title, reference: document.reference }],
      next_cursor: 'opaque-page',
    });
    await shown('Version history');
    await shown('test-v1');
    await router.navigateByUrl('/privacy?view=history&cursor=opaque-page');
    const next = await vi.waitFor(() =>
      backend.expectOne('/api/v1/policies/privacy/versions?limit=20&cursor=opaque-page'),
    );
    next.flush({ items: [], next_cursor: null });
    await shown('No published versions are available.');
  });
  it('rejects history references from the other document kind', async () => {
    await TestBed.inject(Router).navigateByUrl('/terms?view=history');
    const request = await vi.waitFor(() =>
      backend.expectOne('/api/v1/policies/terms/versions?limit=20'),
    );
    request.flush({
      items: [{ title: document.title, reference: document.reference }],
      next_cursor: null,
    });
    await shown('Published versions could not be loaded.');
    expect(text()).not.toContain('test-v1');
  });
  for (const kind of ['terms', 'privacy']) {
    it(`reads the actual ${kind} document as safe text`, async () => {
      await TestBed.inject(Router).navigateByUrl(`/${kind}`);
      const request = await vi.waitFor(() => backend.expectOne(`/api/v1/policies/${kind}`));
      request.flush({
        ...document,
        title: kind === 'terms' ? 'Terms of Use' : 'Privacy Policy',
        reference: { ...document.reference, kind },
        content: '<script>private()</script>',
      });
      await shown('<script>private()</script>');
      expect(fixture.debugElement.queryAll(By.css('script'))).toHaveLength(0);
      expect(fixture.debugElement.queryAll(By.css('input[type=checkbox]'))).toHaveLength(0);
    });
  }
  it('updates the query for version navigation and recovers from a publication outage', async () => {
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/privacy?version=test-v1');
    const first = await vi.waitFor(() =>
      backend.expectOne('/api/v1/policies/privacy?version=test-v1'),
    );
    first.flush({ code: 'policy_unavailable' }, { status: 503, statusText: 'Unavailable' });
    await shown('This document is not available');
    fixture.debugElement
      .query(By.css('button'))
      .triggerEventHandler('click', new MouseEvent('click'));
    const retry = await vi.waitFor(() =>
      backend.expectOne('/api/v1/policies/privacy?version=test-v1'),
    );
    retry.flush(document);
    await shown('Published fixture text');
    await router.navigateByUrl('/privacy?version=test-v2');
    const next = await vi.waitFor(() =>
      backend.expectOne('/api/v1/policies/privacy?version=test-v2'),
    );
    next.flush({ ...document, reference: { ...document.reference, version: 'test-v2' } });
    await shown('test-v2');
  });
  for (const value of [
    null,
    {},
    0,
    { ...document, title: 0 },
    { ...document, content: 0 },
    { ...document, reference: null },
    ...Object.keys(document.reference).flatMap((key) => [
      {
        ...document,
        reference: Object.fromEntries(
          Object.entries(document.reference).filter(
            ([name]: readonly [string, unknown]) => name !== key,
          ),
        ),
      },
      { ...document, reference: { ...document.reference, [key]: 0 } },
    ]),
    { ...document, reference: { ...document.reference, kind: 'invented' } },
  ]) {
    it(`rejects malformed legal content ${JSON.stringify(value)}`, async () => {
      await TestBed.inject(Router).navigateByUrl('/privacy');
      const request = await vi.waitFor(() => backend.expectOne('/api/v1/policies/privacy'));
      request.flush(value);
      await shown('This document is not available');
    });
  }
});
