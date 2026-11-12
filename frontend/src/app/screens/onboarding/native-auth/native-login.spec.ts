import { nativeBuilds, NativeConfigurationFailure } from '../../../native-transport/config';
import { signal } from '@angular/core';
import { describe, expect, it, vi } from 'vitest';
import { acceptsNativeWake, nativeWakeUrl, runNativeLogin } from './native-login';
import type { NativeAuthPlatform, NativeCookieSession, NativeAuthBoundary } from './native-login';

function fixture() {
  const callback = signal<((url: string) => void) | null>(null);
  const remove = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
  const close = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
  const open = vi.fn<(url: string) => Promise<void>>().mockResolvedValue(undefined);
  const platform: NativeAuthPlatform = {
    listen: (accept) => {
      callback.set(accept);
      return Promise.resolve({ remove });
    },
    open,
    close,
  };
  const begin = vi.fn<NativeCookieSession['begin']>().mockResolvedValue(undefined);
  const exchange = vi.fn<NativeCookieSession['exchange']>().mockResolvedValue(undefined);
  const retirePrivateQueries = vi
    .fn<NativeAuthBoundary['retirePrivateQueries']>()
    .mockResolvedValue(undefined);
  const revalidateSession = vi
    .fn<NativeAuthBoundary['revalidateSession']>()
    .mockResolvedValue(undefined);
  const controller = new AbortController();
  const run = (): Promise<void> =>
    runNativeLogin(
      nativeBuilds.production,
      platform,
      { begin, exchange },
      { retirePrivateQueries, revalidateSession },
      controller.signal,
    );
  return {
    run,
    controller,
    callback,
    remove,
    close,
    open,
    exchange,
    begin,
    retirePrivateQueries,
    revalidateSession,
    platform,
  };
}

describe('native sign-in lifecycle', () => {
  it.each([
    nativeWakeUrl + '?token=forbidden',
    nativeWakeUrl + '#code=forbidden',
    'dev.alekseiorlov.peerly://attacker/complete',
    'https://peerly.example.test/onboarding',
    'dev.alekseiorlov.peerly://auth/complete/',
  ])('ignores foreign or data-bearing links: %s', (url) => {
    expect(acceptsNativeWake(url)).toBe(false);
  });

  it('binds S256 proof without sending verifier or any token in the browser URL', async () => {
    const context = fixture();
    const result = context.run();
    await vi.waitFor(() => {
      expect(context.open).toHaveBeenCalledOnce();
    });
    context.callback()?.(nativeWakeUrl + '?token=forbidden');
    expect(context.exchange).not.toHaveBeenCalled();
    context.callback()?.(nativeWakeUrl);
    context.callback()?.(nativeWakeUrl);
    await result;
    const url = new URL(context.open.mock.calls[0]?.[0] ?? 'https://invalid.example.test');
    const proof = context.exchange.mock.calls[0];
    if (proof === undefined) throw new Error('Expected proof-bound exchange');
    const [attempt, verifier] = proof;
    expect(url.origin).toBe(nativeBuilds.production.apiOrigin);
    expect(url.pathname).toBe('/api/v1/auth/native/start');
    expect(Array.from(url.searchParams.keys())).toEqual(['attempt_id', 'challenge']);
    expect(url.searchParams.get('attempt_id')).toBe(attempt);
    expect(url.href).not.toContain(verifier);
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
    expect(url.searchParams.get('challenge')).toBe(
      btoa(String.fromCharCode(...new Uint8Array(digest)))
        .replaceAll('+', '-')
        .replaceAll('/', '_')
        .replaceAll('=', ''),
    );
    expect(context.exchange).toHaveBeenCalledOnce();
    expect(context.retirePrivateQueries).toHaveBeenCalledTimes(2);
    expect(context.revalidateSession).toHaveBeenCalledOnce();
    expect(context.remove).toHaveBeenCalledOnce();
    expect(context.close).toHaveBeenCalledOnce();
  });

  it('cancels while browser is open and ignores late links', async () => {
    const context = fixture();
    const result = context.run();
    const rejected = expect(result).rejects.toMatchObject({ name: 'AbortError' });
    await vi.waitFor(() => {
      expect(context.open).toHaveBeenCalledOnce();
    });
    context.controller.abort();
    context.callback()?.(nativeWakeUrl);
    await rejected;
    expect(context.exchange).not.toHaveBeenCalled();
    expect(context.revalidateSession).not.toHaveBeenCalled();
    expect(context.remove).toHaveBeenCalledOnce();
    expect(context.close).toHaveBeenCalledOnce();
  });

  it('does not revalidate an actor retired during exchange', async () => {
    const context = fixture();
    context.exchange.mockImplementation(() => {
      context.controller.abort();
      return Promise.resolve();
    });
    const result = context.run();
    const rejected = expect(result).rejects.toMatchObject({ name: 'AbortError' });
    await vi.waitFor(() => {
      expect(context.open).toHaveBeenCalledOnce();
    });
    context.callback()?.(nativeWakeUrl);
    await rejected;
    expect(context.revalidateSession).not.toHaveBeenCalled();
  });

  it.each([
    'http://peerly.example.test',
    'https://user:pass@peerly.example.test',
    'https://peerly.example.test/path',
  ])('rejects unsafe API origin %s', async (origin) => {
    const context = fixture();
    await expect(
      runNativeLogin(
        { ...nativeBuilds.production, apiOrigin: origin },
        context.platform,
        { begin: context.begin, exchange: context.exchange },
        {
          retirePrivateQueries: context.retirePrivateQueries,
          revalidateSession: context.revalidateSession,
        },
        context.controller.signal,
      ),
    ).rejects.toBeInstanceOf(NativeConfigurationFailure);
    expect(context.open).not.toHaveBeenCalled();
  });

  it('expires instead of persisting the proof for a later launch', async () => {
    vi.useFakeTimers();
    try {
      const context = fixture();
      const result = context.run();
      const rejected = expect(result).rejects.toMatchObject({ reason: 'expired' });
      await vi.waitFor(() => {
        expect(context.open).toHaveBeenCalledOnce();
      });
      await vi.advanceTimersByTimeAsync(300_000);
      await rejected;
      expect(context.exchange).not.toHaveBeenCalled();
      expect(context.remove).toHaveBeenCalledOnce();
    } finally {
      vi.useRealTimers();
    }
  });
});
