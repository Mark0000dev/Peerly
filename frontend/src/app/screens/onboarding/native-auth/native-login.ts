import { nativeBuilds, readNativeBuild } from '../../../native-transport/config';
import type { NativeBuild } from '../../../native-transport/config';
export interface NativeAuthListener {
  readonly remove: () => Promise<void>;
}

export interface NativeAuthPlatform {
  readonly listen: (accept: (url: string) => void) => Promise<NativeAuthListener>;
  readonly open: (url: string) => Promise<void>;
  readonly close: () => Promise<void>;
}

export interface NativeCookieSession {
  readonly begin: (signal: Readonly<AbortSignal>) => Promise<void>;
  // Implementations must reject cancelled epochs BEFORE applying Set-Cookie.
  // Never implement with JS Cookies.setCookie, token return values or Browser jar copying.
  readonly exchange: (
    attemptId: string,
    verifier: string,
    signal: Readonly<AbortSignal>,
  ) => Promise<void>;
}

export interface NativeAuthBoundary {
  // Parent composes existing Query cancellation/removal, not an alternate session store.
  readonly retirePrivateQueries: (signal: Readonly<AbortSignal>) => Promise<void>;
  readonly revalidateSession: (signal: Readonly<AbortSignal>) => Promise<void>;
}

export const nativeWakeUrl = nativeBuilds.production.wakeUrl;
const timeoutMilliseconds = 300_000;

export class NativeLoginFailure extends Error {
  public constructor(public readonly reason: 'configuration' | 'unavailable' | 'expired') {
    super('Native sign-in could not be completed');
  }
}

export function acceptsNativeWake(url: string, expected: string = nativeWakeUrl): boolean {
  // Strict raw equality rejects tokens, fragments, userinfo, alternate hosts and routes.
  return url === expected;
}

async function createProof(): Promise<
  Readonly<{ readonly verifier: string; readonly challenge: string }>
> {
  const entropy = crypto.getRandomValues(new Uint8Array(32));
  const verifier = btoa(String.fromCharCode(...entropy))
    .replaceAll('+', '-')
    .replaceAll('/', '_')
    .replaceAll('=', '');
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  const challenge = btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replaceAll('+', '-')
    .replaceAll('/', '_')
    .replaceAll('=', '');
  return { verifier, challenge };
}

// Ephemeral proof stays only on this stack. Caller owns one TanStack mutation and
// an actor/view AbortSignal; concurrent starts must be disabled by that mutation.
export async function runNativeLogin(
  config: Readonly<NativeBuild>,
  platform: Readonly<NativeAuthPlatform>,
  cookies: Readonly<NativeCookieSession>,
  boundary: Readonly<NativeAuthBoundary>,
  signal: Readonly<AbortSignal>,
): Promise<void> {
  const trusted = readNativeBuild(config);
  signal.throwIfAborted();
  const lifetime = new AbortController();
  const cancel = (): void => {
    lifetime.abort();
  };
  signal.addEventListener('abort', cancel, { once: true });
  const expire = setTimeout(() => {
    lifetime.abort(new NativeLoginFailure('expired'));
  }, timeoutMilliseconds);
  try {
    await boundary.retirePrivateQueries(lifetime.signal);
    lifetime.signal.throwIfAborted();
    await cookies.begin(lifetime.signal);
    lifetime.signal.throwIfAborted();
    const proof = await createProof();
    lifetime.signal.throwIfAborted();
    const attempt = crypto.randomUUID();
    let resolveWake: (() => void) | undefined;
    const wake = new Promise<void>((resolve) => {
      resolveWake = resolve;
    });
    const abortWake = (): void => resolveWake?.();
    lifetime.signal.addEventListener('abort', abortWake, { once: true });
    const listener = await platform.listen((url) => {
      if (acceptsNativeWake(url, trusted.wakeUrl)) resolveWake?.();
    });
    try {
      lifetime.signal.throwIfAborted();
      const target = new URL('/api/v1/auth/native/start', trusted.apiOrigin);
      target.searchParams.set('attempt_id', attempt);
      target.searchParams.set('challenge', proof.challenge);
      await platform.open(target.href);
      lifetime.signal.throwIfAborted();
      await wake;
      lifetime.signal.throwIfAborted();
      await boundary.retirePrivateQueries(lifetime.signal);
      lifetime.signal.throwIfAborted();
      await cookies.exchange(attempt, proof.verifier, lifetime.signal);
      lifetime.signal.throwIfAborted();
      await boundary.revalidateSession(lifetime.signal);
      lifetime.signal.throwIfAborted();
    } finally {
      lifetime.signal.removeEventListener('abort', abortWake);
      try {
        await listener.remove();
      } finally {
        await platform.close();
      }
    }
  } finally {
    clearTimeout(expire);
    signal.removeEventListener('abort', cancel);
    // Ports must tear down outstanding native work on this signal, too.
    lifetime.abort();
  }
}
