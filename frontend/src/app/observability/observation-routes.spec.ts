import { TestBed } from '@angular/core/testing';
import { Component } from '@angular/core';
import { Router, provideRouter } from '@angular/router';
import { afterEach, describe, expect, it } from 'vitest';
import { watchObservedRoutes, screenForRoute } from './observation-routes';
import { createObservationBridge } from './observation-bridge';
import type { ObservationBuffer } from './observation-buffer';
import type { Epoch, ObservationInput } from './observation-contract';
@Component({ template: '' })
class Empty {}
afterEach(() => {
  TestBed.resetTestingModule();
});
describe('semantic route lifecycle and owned root bridge', () => {
  it('reads static route templates only and marks only completed same-epoch navigations', async () => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'chats', component: Empty },
          { path: 'people/:personId', component: Empty },
          { path: 'profile/goal', component: Empty },
          { path: 'blocked', component: Empty, canActivate: [() => false] },
        ]),
      ],
    });
    const router = TestBed.inject(Router);
    let events: readonly ObservationInput[] = [];
    let now = 100;
    let epoch: Epoch | null = { id: 1, startedAt: 0 };
    const dispose = watchObservedRoutes(
      router,
      {
        observe: (input) => {
          events = [...events, input];
          return true;
        },
        beginAction: () => null,
        epoch: () => epoch,
      },
      () => now++,
    );
    await router.navigateByUrl('/chats?draft=PRIVATE');
    expect(events).toEqual([
      { kind: 'screen.viewed' },
      { kind: 'performance.observed', metric: 'route_ready', value: 1 },
    ]);
    const chats = router.routerState.snapshot.root.firstChild;
    if (chats === null) throw new Error('Missing actual route');
    expect(screenForRoute(chats)).toBe('chats');
    events = [];
    await router.navigateByUrl('/people/private-account-id?email=secret');
    const person = router.routerState.snapshot.root.firstChild;
    if (person === null) throw new Error('Missing actual route');
    expect(screenForRoute(person)).toBe('profile');
    expect(JSON.stringify(events)).not.toMatch(/private|secret|email|account/);
    events = [];
    await router.navigateByUrl('/blocked');
    expect(events).toEqual([]);
    epoch = null;
    await router.navigateByUrl('/profile/goal');
    expect(events).toEqual([]);
    dispose();
  });
  for (const [path, screen] of [
    ['profile/notifications', 'notifications'],
    ['profile/help', 'study'],
    ['help/contact', 'support'],
    ['help', 'help'],
    ['terms', 'terms'],
    ['privacy', 'privacy'],
    ['operator/support', 'operator'],
    ['unclassified', 'unknown'],
    ['profile/visibility', 'profile'],
  ] as const) {
    it(`classifies the real static ${path} route without query or resource data`, async () => {
      TestBed.configureTestingModule({ providers: [provideRouter([{ path, component: Empty }])] });
      const router = TestBed.inject(Router);
      await router.navigateByUrl(`/${path}?private=NEVER_CAPTURE`);
      const route = router.routerState.snapshot.root.firstChild;
      if (route === null) throw new Error('Missing committed route');
      expect(screenForRoute(route)).toBe(screen);
    });
  }
  it('attaches a child adapter resource without copying session state; stale detach cannot remove replacement', () => {
    const bridge = createObservationBridge();
    let firstDisposed = 0;
    let secondDisposed = 0;
    let seen: readonly ObservationInput[] = [];
    const resource = (dispose: () => void): ObservationBuffer => ({
      observe: (input) => {
        seen = [...seen, input];
        return true;
      },
      beginAction: () => null,
      epoch: () => ({ id: 1, startedAt: 0 }),
      synchronize: () => undefined,
      flush: () => undefined,
      dispose,
      drops: () => ({
        overflow: 0,
        invalid: 0,
        expired: 0,
        actor_changed: 0,
        rejected: 0,
        exhausted: 0,
        unavailable: 0,
      }),
    });
    expect(bridge.observe({ kind: 'screen.viewed' })).toBe(false);
    expect(bridge.epoch()).toBeNull();
    const detachFirst = bridge.attach(
      resource(() => {
        firstDisposed += 1;
      }),
    );
    const detachSecond = bridge.attach(
      resource(() => {
        secondDisposed += 1;
      }),
    );
    expect(firstDisposed).toBe(1);
    detachFirst();
    expect(bridge.observe({ kind: 'screen.viewed' })).toBe(true);
    expect(seen).toHaveLength(1);
    detachSecond();
    expect(secondDisposed).toBe(1);
    expect(bridge.epoch()).toBeNull();
    expect(bridge.beginAction('submit')).toBeNull();
  });
});
