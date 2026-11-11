import { HttpErrorResponse } from '@angular/common/http';
import type { HttpClient, HttpContext } from '@angular/common/http';
import { firstValueFrom, fromEvent, takeUntil, throwIfEmpty } from 'rxjs';

export class ApiFailure extends Error {
  public constructor(
    public readonly status: number,
    public readonly code: string,
    public readonly requestId: string | null,
    public readonly retryAt: string | null = null,
  ) {
    super('Request could not be completed');
  }
}

function failure(error: Readonly<HttpErrorResponse>, body: unknown = error.error): ApiFailure {
  // Angular reports JSON decoding failures as HttpErrorResponse even for committed 2xx writes.
  // Their outcome is unknown; never classify the parsing envelope as a confirmed command error.
  if (error.status >= 200 && error.status < 300) return new ApiFailure(0, 'invalid_response', null);
  const code =
    typeof body === 'object' &&
    body !== null &&
    'code' in body &&
    typeof body.code === 'string' &&
    /^[a-z][a-z0-9_]{0,63}$/.test(body.code)
      ? body.code
      : 'request_failed';
  const requestId =
    typeof body === 'object' &&
    body !== null &&
    'request_id' in body &&
    typeof body.request_id === 'string' &&
    /^[a-zA-Z0-9_-]{1,64}$/.test(body.request_id)
      ? body.request_id
      : null;
  const recovery: unknown =
    typeof body === 'object' && body !== null && 'recovery' in body ? body.recovery : null;
  const retryAt =
    typeof recovery === 'object' &&
    recovery !== null &&
    'retry_at' in recovery &&
    typeof recovery.retry_at === 'string' &&
    Number.isFinite(Date.parse(recovery.retry_at))
      ? recovery.retry_at
      : null;
  return new ApiFailure(error.status, code, requestId, retryAt);
}

export async function readJson<T>(
  http: Readonly<HttpClient>,
  url: string,
  signal: Readonly<AbortSignal>,
  accept: (value: unknown) => value is T,
): Promise<T> {
  if (!url.startsWith('/api/v1/')) throw new ApiFailure(0, 'invalid_api_target', null);
  signal.throwIfAborted();
  try {
    const value: unknown = await firstValueFrom(
      http.get<unknown>(url).pipe(
        takeUntil(fromEvent(signal, 'abort')),
        throwIfEmpty(() => new DOMException('Request cancelled', 'AbortError')),
      ),
    );
    if (!accept(value)) throw new ApiFailure(0, 'invalid_response', null);
    return value;
  } catch (error: unknown) {
    if (error instanceof HttpErrorResponse) throw failure(error);
    throw error;
  }
}

export async function writeJson<T>(
  http: Readonly<HttpClient>,
  url: string,
  body: unknown,
  headers: Readonly<Record<string, string>>,
  accept: (value: unknown) => value is T,
  method: 'POST' | 'PUT' = 'POST',
  context?: HttpContext,
): Promise<T> {
  if (!url.startsWith('/api/v1/')) throw new ApiFailure(0, 'invalid_api_target', null);
  try {
    const value: unknown = await firstValueFrom(
      http.request<unknown>(method, url, {
        body,
        headers,
        ...(context === undefined ? {} : { context }),
      }),
    );
    if (!accept(value)) throw new ApiFailure(0, 'invalid_response', null);
    return value;
  } catch (error: unknown) {
    if (error instanceof HttpErrorResponse) throw failure(error);
    throw error;
  }
}

async function jpegFailure(
  error: Readonly<HttpErrorResponse>,
  signal: Readonly<AbortSignal>,
): Promise<ApiFailure> {
  const payload: unknown = error.error;
  if (!(payload instanceof Blob)) return failure(error);
  const type = payload.type.split(';')[0]?.trim().toLowerCase();
  if (payload.size > 8192 || (type !== 'application/json' && type !== 'application/problem+json'))
    return failure(error, null);
  try {
    const problem: unknown = JSON.parse(await payload.text());
    signal.throwIfAborted();
    return failure(error, problem);
  } catch (problem: unknown) {
    signal.throwIfAborted();
    if (problem instanceof SyntaxError || problem instanceof DOMException)
      return failure(error, null);
    throw problem;
  }
}

// Return bytes only. The actual view owns/revokes any object URL; neither URLs nor raw problem
// payloads belong in query/mutation state. Private JPEG reads share the JSON cancellation boundary.
export async function readJpeg(
  http: Readonly<HttpClient>,
  url: string,
  signal: Readonly<AbortSignal>,
): Promise<Readonly<Blob>> {
  if (!url.startsWith('/api/v1/')) throw new ApiFailure(0, 'invalid_api_target', null);
  signal.throwIfAborted();
  try {
    const response = await firstValueFrom(
      http.get(url, { responseType: 'blob', observe: 'response' }).pipe(
        takeUntil(fromEvent(signal, 'abort')),
        throwIfEmpty(() => new DOMException('Request cancelled', 'AbortError')),
      ),
    );
    signal.throwIfAborted();
    if (
      response.status !== 200 ||
      response.body === null ||
      response.body.size === 0 ||
      response.headers.get('Content-Type')?.split(';')[0]?.trim().toLowerCase() !== 'image/jpeg'
    )
      throw new ApiFailure(0, 'invalid_response', null);
    return response.body;
  } catch (error: unknown) {
    if (error instanceof HttpErrorResponse) throw await jpegFailure(error, signal);
    throw error;
  }
}
