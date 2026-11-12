import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { Router } from '@angular/router';
import { QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './app';
import { ObservationRelease } from './observability/observation-release';
import { appConfig } from './app.config';
import { Onboarding } from './screens/onboarding/onboarding';
import { verifiedActor } from './screens/onboarding/onboarding.fixtures';
import { ownHelp } from './screens/onboarding/study/help.fixtures';

describe('application routing and query ownership', () => {
  let fixture: ComponentFixture<App> | null = null;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        ...appConfig.providers,
        provideHttpClientTesting(),
        {
          provide: ObservationRelease,
          useValue: { current: () => null, load: () => Promise.resolve() },
        },
      ],
    });
  });
  afterEach(() => {
    try {
      if (fixture !== null) {
        for (const element of fixture.debugElement.queryAll(By.directive(Onboarding)))
          element.injector.get(QueryClient).clear();
        fixture.destroy();
      }
      TestBed.inject(HttpTestingController).verify();
    } finally {
      fixture = null;
      TestBed.resetTestingModule();
    }
  });
  it('renders public landing without private requests', async () => {
    fixture = TestBed.createComponent(App);
    await TestBed.inject(Router).navigateByUrl('/');
    await fixture.whenStable();
    expect(TestBed.inject(Router).url).toBe('/');
    expect(fixture.debugElement.queryAll(By.css('h1'))).toHaveLength(1);
    TestBed.inject(HttpTestingController).expectNone('/api/v1/me');
  });
  it('keeps an unknown route on the actual public not-found screen', async () => {
    fixture = TestBed.createComponent(App);
    await TestBed.inject(Router).navigateByUrl('/unknown-route');
    await fixture.whenStable();
    expect(TestBed.inject(Router).url).toBe('/unknown-route');
    const headings = fixture.debugElement.queryAll(By.css('h1'));
    expect(headings).toHaveLength(1);
    const heading: unknown = headings[0]?.nativeElement;
    if (!(heading instanceof HTMLHeadingElement)) throw new Error('Missing not-found heading');
    expect(heading.textContent.trim()).toBe('Page not found');
    TestBed.inject(HttpTestingController).expectNone('/api/v1/me');
  });
  it('renders real public support after checking identity without preparing or submitting a case', async () => {
    fixture = TestBed.createComponent(App);
    await TestBed.inject(Router).navigateByUrl('/help');
    const http = TestBed.inject(HttpTestingController);
    const session = await vi.waitFor(() => http.expectOne('/api/v1/me'));
    session.flush({ code: 'unauthenticated' }, { status: 401, statusText: 'Unauthorized' });
    await fixture.whenStable();
    expect(fixture.debugElement.queryAll(By.css('h1'))).toHaveLength(1);
    expect(fixture.debugElement.queryAll(By.css('form'))).toHaveLength(1);
    expect(fixture.debugElement.queryAll(By.css('#support-reply'))).toHaveLength(1);
    http.expectNone('/api/v1/support-context');
    http.expectNone('/api/v1/support-cases');
    http.expectNone('/api/v1/me/support-cases');
  });
  for (const code of ['login_cancelled', 'login_provider_unavailable', 'untrusted-provider-text']) {
    it(`strips callback metadata without trusting it as identity: ${code}`, async () => {
      fixture = TestBed.createComponent(App);
      const router = TestBed.inject(Router);
      await router.navigateByUrl(
        `/onboarding?auth_error=${code}&auth_ref=00000000-0000-0000-0000-000000000001`,
      );
      const request = await vi.waitFor(() =>
        TestBed.inject(HttpTestingController).expectOne('/api/v1/me'),
      );
      request.flush({ code: 'unauthenticated' }, { status: 401, statusText: 'Unauthorized' });
      const rendered = fixture;
      await vi.waitFor(() => {
        rendered.detectChanges();
        expect(router.url).toBe('/onboarding');
        expect(
          rendered.debugElement.queryAll(By.css('a[href^="/api/v1/auth/google/start"]')),
        ).toHaveLength(1);
      });
    });
  }
  it('loads private bootstrap and query defaults only on the actual app route', async () => {
    fixture = TestBed.createComponent(App);
    await TestBed.inject(Router).navigateByUrl('/onboarding');
    const request = await vi.waitFor(() =>
      TestBed.inject(HttpTestingController).expectOne('/api/v1/me'),
    );
    request.flush({ code: 'unauthenticated' }, { status: 401, statusText: 'Unauthorized' });
    await fixture.whenStable();
    const screen = fixture.debugElement.query(By.directive(Onboarding));
    expect(screen.injector.get(QueryClient).getDefaultOptions().mutations?.retry).toBe(false);
    expect(screen.injector.get(QueryClient).getDefaultOptions().queries?.retry).toBe(false);
    const rendered = fixture;
    await vi.waitFor(() => {
      rendered.detectChanges();
      expect(
        rendered.debugElement.queryAll(By.css('a[href^="/api/v1/auth/google/start"]')),
      ).toHaveLength(1);
    });
  });
  it('disconnects screen observers on navigation and the font watcher before iframe removal', async () => {
    const observing = vi.spyOn(ResizeObserver.prototype, 'observe');
    const disconnecting = vi.spyOn(ResizeObserver.prototype, 'disconnect');
    try {
      fixture = TestBed.createComponent(App);
      await TestBed.inject(Router).navigateByUrl('/onboarding');
      const request = await vi.waitFor(() =>
        TestBed.inject(HttpTestingController).expectOne('/api/v1/me'),
      );
      request.flush(verifiedActor);
      await fixture.whenStable();
      const root: unknown = fixture.nativeElement;
      if (!(root instanceof HTMLElement)) throw new Error('Missing application root');
      const button = await vi.waitFor(() => {
        const found = Array.from(root.querySelectorAll('button')).find(
          (element: Readonly<HTMLButtonElement>) =>
            element.textContent.trim() === 'Your help areas',
        );
        if (found === undefined) throw new Error('Missing help-subject entry');
        return found;
      });
      button.click();
      const help = await vi.waitFor(() =>
        TestBed.inject(HttpTestingController).expectOne('/api/v1/me/help-subjects'),
      );
      help.flush(ownHelp);
      await fixture.whenStable();
      const rendered = fixture;
      await vi.waitFor(() => {
        rendered.detectChanges();
        expect(root.querySelector('input')).toBeInstanceOf(HTMLInputElement);
      });
      const observations = observing.mock.calls.map(
        ([target]: Readonly<Parameters<ResizeObserver['observe']>>, index) => ({
          target,
          observer: observing.mock.contexts[index],
        }),
      );
      const font = observations.find(
        (entry: Readonly<(typeof observations)[number]>) => entry.target.ownerDocument !== document,
      );
      if (font === undefined) throw new Error('Missing enabled native font watcher');
      const iframe = Array.from(document.querySelectorAll('iframe')).find(
        (element: Readonly<HTMLIFrameElement>) =>
          element.contentDocument === font.target.ownerDocument,
      );
      if (iframe === undefined) throw new Error('Missing owned font detector frame');
      const fields = observations.filter(
        (entry: Readonly<(typeof observations)[number]>) => entry.target.ownerDocument === document,
      );
      expect(fields.length).toBeGreaterThan(0);
      const client = fixture.debugElement.query(By.directive(Onboarding)).injector.get(QueryClient);
      await TestBed.inject(Router).navigateByUrl('/');
      await fixture.whenStable();
      for (const field of fields) expect(disconnecting.mock.contexts).toContain(field.observer);
      expect(disconnecting.mock.contexts).not.toContain(font.observer);
      expect(iframe.isConnected).toBe(true);
      client.clear();
      const removing = vi.spyOn(iframe, 'remove');
      fixture.destroy();
      fixture = null;
      expect(iframe.isConnected).toBe(false);
      const index = disconnecting.mock.contexts.findIndex((observer) => observer === font.observer);
      const disconnectedAt = disconnecting.mock.invocationCallOrder[index];
      const removedAt = removing.mock.invocationCallOrder[0];
      if (disconnectedAt === undefined || removedAt === undefined)
        throw new Error('Missing detector cleanup');
      expect(disconnectedAt).toBeLessThan(removedAt);
    } finally {
      vi.restoreAllMocks();
    }
  });
});
