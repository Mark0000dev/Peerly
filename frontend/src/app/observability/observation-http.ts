import { DOCUMENT } from '@angular/common';
import { HttpErrorResponse, HttpResponse } from '@angular/common/http';
import type { HttpEvent, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { defer, finalize, tap } from 'rxjs';
import { CLIENT_OBSERVATIONS } from './observation-errors';
import { CLIENT_ACTION } from './observation-context';
import { methods, uuid, traceId } from './observation-contract';
import type { HttpRoute, Method, StatusClass } from './observation-contract';
// Semantic groups derived from current enabled OpenAPI107, never resource IDs.
export function publicHttpRoute(path: string): HttpRoute {
  if (path === '/api/v1/me' || /^\/api\/v1\/auth\/(?:google|logout)(?:\/|$)/.test(path))
    return 'identity';
  if (/^\/api\/v1\/auth\/email-challenges(?:\/|$)/.test(path)) return 'verification';
  if (/^\/api\/v1\/me\/(?:registration|registration-context)(?:\/|$)/.test(path))
    return 'registration';
  if (/^\/api\/v1\/operator(?:\/|$)/.test(path)) return 'operator';
  if (
    /^\/api\/v1\/(?:support-cases|support-context)(?:\/|$)/.test(path) ||
    /^\/api\/v1\/me\/support-cases(?:\/|$)/.test(path)
  )
    return 'support';
  if (/^\/api\/v1\/me\/notification-preference$/.test(path)) return 'notifications';
  if (/^\/api\/v1\/me\/(?:goal|help-subjects)(?:\/|$)/.test(path) || path === '/api/v1/subjects')
    return 'study';
  if (
    /^\/api\/v1\/me\/(?:profile|onboarding|blocks|visibility|deletion|deletion-status|deletion-workflows|policy-status|feedback-summary)(?:\/|$)/.test(
      path,
    ) ||
    /^\/api\/v1\/(?:people|profile-reference-data)(?:\/|$)/.test(path)
  )
    return 'profile';
  if (/^\/api\/v1\/discovery(?:\/|$)/.test(path)) return 'discovery';
  if (/^\/api\/v1\/requests(?:\/|$)/.test(path)) return 'requests';
  if (/^\/api\/v1\/conversations(?:\/|$)/.test(path)) return 'conversations';
  if (/^\/api\/v1\/media(?:\/|$)/.test(path)) return 'media';
  if (/^\/api\/v1\/ai(?:\/|$)/.test(path)) return 'ai';
  return 'other';
}
export function observedApi(
  url: string,
  origin: string,
): Readonly<{ readonly route: HttpRoute }> | null {
  try {
    const target = new URL(url, origin);
    if (
      target.origin !== origin ||
      target.username !== '' ||
      target.password !== '' ||
      !target.pathname.startsWith('/api/v1/') ||
      target.pathname === '/api/v1/events' ||
      /^\/api\/v1\/telemetry(?:\/|$)/.test(target.pathname)
    )
      return null;
    return { route: publicHttpRoute(target.pathname) };
  } catch {
    return null;
  }
}
export function traceparent(value: string | null): Readonly<{ readonly traceId: string }> | null {
  if (value === null) return null;
  const match = /^00-([0-9a-f]{32})-([0-9a-f]{16})-0[01]$/.exec(value);
  const id = match?.[1];
  const span = match?.[2];
  return traceId(id) && span !== undefined && !/^0+$/.test(span) ? { traceId: id } : null;
}
export function randomTraceId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) =>
    value.toString(16).padStart(2, '0'),
  ).join('');
}
function newTraceparent(id: string): string {
  const span = randomTraceId().slice(0, 16);
  return `00-${id}-${span}-01`;
}
function statusClass(status: number): StatusClass {
  if (status >= 100 && status < 200) return '1xx';
  if (status >= 200 && status < 300) return '2xx';
  if (status >= 300 && status < 400) return '3xx';
  if (status >= 400 && status < 500) return '4xx';
  if (status >= 500 && status < 600) return '5xx';
  return 'network';
}
// Lead registers once via provideHttpClient(withInterceptors(...)); no double SDK.
export const observationInterceptor: HttpInterceptorFn = (request, next) => {
  const sink = inject(CLIENT_OBSERVATIONS);
  const document = inject(DOCUMENT);
  const target = observedApi(request.url, document.location.origin);
  const method = methods.find((value) => value === request.method);
  if (target === null || method === undefined) return next(request);
  return defer(() => {
    const captured = (() => {
      try {
        const epoch = sink.epoch();
        if (epoch === null) return null;
        const started = performance.now();
        const handle = request.context.get(CLIENT_ACTION);
        const originalAction = request.headers.get('X-Action-ID');
        const actionId = uuid(originalAction)
          ? originalAction
          : uuid(handle?.actionId)
            ? handle.actionId
            : null;
        const originalTrace = request.headers.get('traceparent');
        const existing = traceparent(originalTrace);
        const parent =
          existing !== null
            ? originalTrace
            : newTraceparent(traceId(handle?.traceId) ? handle.traceId : randomTraceId());
        const trace = traceparent(parent);
        const headers = {
          ...(actionId === null ? {} : { 'X-Action-ID': actionId }),
          ...(parent === null ? {} : { traceparent: parent }),
        };
        const correlated = request.clone({ setHeaders: headers });
        return { epoch, started, actionId, trace, correlated };
      } catch {
        return null;
      }
    })();
    if (captured === null) return next(request);
    const { epoch, started, actionId, trace, correlated } = captured;
    let settled = false;
    const observe = (status: StatusClass, requestId: string | null): void => {
      try {
        if (sink.epoch()?.id !== epoch.id) return;
        sink.observe({
          kind: 'http.observed',
          method: method satisfies Method,
          route: target.route,
          status_class: status,
          duration_ms: Math.round(Math.max(0, performance.now() - started)),
          ...(uuid(requestId) ? { request_id: requestId } : {}),
          ...(actionId === null ? {} : { action_id: actionId }),
          ...(trace === null ? {} : { trace_id: trace.traceId }),
        });
      } catch {
        /* Instrumentation must not replace an HTTP result or cancellation. */
      }
    };
    return next(correlated).pipe(
      tap({
        next: (event: Readonly<HttpEvent<unknown>>) => {
          if (event instanceof HttpResponse) {
            settled = true;
            observe(statusClass(event.status), event.headers.get('X-Request-ID'));
          }
        },
        error: (error: unknown) => {
          settled = true;
          observe(
            error instanceof HttpErrorResponse ? statusClass(error.status) : 'network',
            error instanceof HttpErrorResponse ? error.headers.get('X-Request-ID') : null,
          );
        },
      }),
      finalize(() => {
        if (!settled) observe('cancelled', null);
      }),
    );
  });
};
