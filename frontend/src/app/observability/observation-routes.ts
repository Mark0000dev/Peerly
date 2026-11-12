import { NavigationStart, NavigationEnd, NavigationCancel, NavigationError } from '@angular/router';
import type { Router, ActivatedRouteSnapshot, Event as RouterEvent } from '@angular/router';
import type { ObservationSink, Screen } from './observation-contract';
// Consume static configured route templates only, never Router URLs/query/params/data.
export function screenForRoute(route: Readonly<ActivatedRouteSnapshot>): Screen {
  const paths: readonly string[] = route.pathFromRoot.map(
    (item: Readonly<ActivatedRouteSnapshot>) => item.routeConfig?.path ?? '',
  );
  const path = paths.filter((value) => value !== '').join('/');
  if (path === '') return 'welcome';
  if (path === 'onboarding') return 'onboarding';
  if (path === 'discover') return 'discover';
  if (path === 'requests') return 'requests';
  if (path === 'chats') return 'chats';
  if (path === 'profile/notifications') return 'notifications';
  if (path === 'profile/goal' || path === 'profile/help') return 'study';
  if (path === 'profile' || path.startsWith('profile/') || path === 'people/:personId')
    return 'profile';
  if (path.startsWith('help/contact')) return 'support';
  if (path === 'help') return 'help';
  if (path === 'terms') return 'terms';
  if (path === 'privacy') return 'privacy';
  if (path === 'operator' || path.startsWith('operator/')) return 'operator';
  return 'unknown';
}
export function watchObservedRoutes(
  router: Readonly<Router>,
  sink: ObservationSink,
  now: () => number,
): () => void {
  let navigation: Readonly<{
    readonly id: number;
    readonly epoch: number;
    readonly started: number;
  }> | null = null;
  const subscription = router.events.subscribe((event: Readonly<RouterEvent>) => {
    if (event instanceof NavigationStart) {
      const epoch = sink.epoch();
      navigation = epoch === null ? null : { id: event.id, epoch: epoch.id, started: now() };
    } else if (event instanceof NavigationEnd) {
      const active = navigation;
      navigation = null;
      const epoch = sink.epoch();
      if (active?.id !== event.id || epoch?.id !== active.epoch) return;
      sink.observe({ kind: 'screen.viewed' });
      sink.observe({
        kind: 'performance.observed',
        metric: 'route_ready',
        value: Math.max(0, now() - active.started),
      });
    } else if (event instanceof NavigationCancel || event instanceof NavigationError) {
      navigation = null;
    }
  });
  return () => {
    navigation = null;
    subscription.unsubscribe();
  };
}
