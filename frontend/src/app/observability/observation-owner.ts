import { HttpClient } from '@angular/common/http';
import { DestroyRef, inject } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import type { Event as RouterEvent } from '@angular/router';
import { QueryClient } from '@tanstack/angular-query-experimental';
import type { Api } from '../api.generated';
import { sessionOptions } from '../screens/session';
import { createObservationBuffer } from './observation-buffer';
import { createObservationDelivery } from './observation-delivery';
import { CLIENT_OBSERVATIONS, CLIENT_RELEASE_ASSETS } from './observation-errors';
import { randomTraceId } from './observation-http';
import { observeNativePerformance } from './observation-performance';
import { screenForRoute, watchObservedRoutes } from './observation-routes';

// This lazy routed owner borrows the one canonical query cache. No identity copy
// survives a pending /me read, logout, actor replacement or route destruction.
export function attachClientObservations(): void {
  const http = inject(HttpClient);
  const client = inject(QueryClient);
  const router = inject(Router);
  const destroy = inject(DestroyRef);
  const bridge = inject(CLIENT_OBSERVATIONS);
  const release = inject(CLIENT_RELEASE_ASSETS);
  const key = sessionOptions(http, client).queryKey;
  const identity = () => {
    const state = client.getQueryState<Api['schemas']['IdentityResponse'] | null>(key);
    return state?.status === 'success' && state.fetchStatus === 'idle'
      ? (state.data ?? null)
      : null;
  };
  const buffer = createObservationBuffer({
    actor: () => identity()?.account_id ?? null,
    screen: () => {
      let route = router.routerState.snapshot.root;
      while (route.firstChild !== null) route = route.firstChild;
      return screenForRoute(route);
    },
    uuid: () => crypto.randomUUID(),
    traceId: randomTraceId,
    release,
    delivery: createObservationDelivery(http, identity, Date.now),
    clock: {
      monotonic: () => performance.now(),
      wall: Date.now,
      schedule: (callback, delay) => {
        const timer = setTimeout(callback, delay);
        return () => {
          clearTimeout(timer);
        };
      },
    },
  });
  const detach = bridge.attach(buffer);
  let observedEpoch: number | undefined;
  const synchronize = (committed = false) => {
    buffer.synchronize();
    const after = buffer.epoch()?.id;
    // Route providers may initialize after NavigationStart but before the target
    // snapshot is committed. Never label the first authenticated view as the
    // previous screen merely because identity was already cached.
    if (after !== undefined && !committed && router.currentNavigation() !== null) return;
    if (after !== undefined && observedEpoch !== after) buffer.observe({ kind: 'screen.viewed' });
    observedEpoch = after;
  };
  // Cache notifications include fetching and removal, not only successful data.
  const unsubscribe = client.getQueryCache().subscribe(() => {
    synchronize();
  });
  const navigation = router.events.subscribe((event: Readonly<RouterEvent>) => {
    if (event instanceof NavigationEnd) synchronize(true);
  });
  synchronize();
  const stopRoutes = watchObservedRoutes(router, buffer, () => performance.now());
  const stopPerformance = observeNativePerformance(buffer, () => performance.now());
  destroy.onDestroy(() => {
    unsubscribe();
    navigation.unsubscribe();
    stopRoutes();
    stopPerformance();
    detach();
  });
}
