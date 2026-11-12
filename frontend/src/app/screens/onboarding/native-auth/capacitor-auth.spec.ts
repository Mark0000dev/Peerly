import { describe, expect, it, vi } from 'vitest';

const native = vi.hoisted(() => ({
  enabled: vi.fn(() => false),
  available: vi.fn<(name: string) => boolean>().mockReturnValue(true),

  listen: vi.fn(
    (_event: 'appUrlOpen', accept: (event: Readonly<{ readonly url: string }>) => void) => {
      accept({ url: 'dev.alekseiorlov.peerly://auth/complete' });
      return Promise.resolve({ remove: () => Promise.resolve() });
    },
  ),
  launch: vi
    .fn<() => Promise<Readonly<{ readonly url: string }> | undefined>>()
    .mockResolvedValue(undefined),
  open: vi
    .fn<(input: Readonly<{ readonly url: string }>) => Promise<void>>()
    .mockResolvedValue(undefined),
  close: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
}));
vi.mock('@capacitor/core', () => ({
  Capacitor: { isNativePlatform: native.enabled, isPluginAvailable: native.available },
}));
vi.mock('@capacitor/app', () => ({
  App: { addListener: native.listen, getLaunchUrl: native.launch },
}));
vi.mock('@capacitor/browser', () => ({ Browser: { open: native.open, close: native.close } }));

import { capacitorAuthPlatform, nativeLaunchHint } from './capacitor-auth';
import { NativeLoginFailure } from './native-login';

// Public API invocation checks only; actual platform/browser cookie interoperability
// requires the signed-device matrix, not these controlled boundary doubles.
describe('Capacitor external browser wiring', () => {
  it('rejects web and missing plugin configurations', async () => {
    native.enabled.mockReturnValue(false);
    expect(() => capacitorAuthPlatform()).toThrow(NativeLoginFailure);
    await expect(nativeLaunchHint('dev.alekseiorlov.peerly://auth/complete')).resolves.toBeNull();
    native.enabled.mockReturnValue(true);
    native.available.mockImplementation((name) => name !== 'App');
    expect(() => capacitorAuthPlatform()).toThrow(NativeLoginFailure);
    await expect(nativeLaunchHint('dev.alekseiorlov.peerly://auth/complete')).resolves.toBeNull();
    native.available.mockImplementation((name) => name !== 'Browser');
    expect(() => capacitorAuthPlatform()).toThrow(NativeLoginFailure);
  });

  it('uses external Browser and removes the App listener', async () => {
    native.enabled.mockReturnValue(true);
    native.available.mockReturnValue(true);
    const platform = capacitorAuthPlatform();
    const accept = vi.fn();
    const listener = await platform.listen(accept);
    await platform.open('https://peerly.example.test/api/v1/auth/native/start');
    await listener.remove();
    await platform.close();
    expect(accept).toHaveBeenCalledWith('dev.alekseiorlov.peerly://auth/complete');
    expect(native.open).toHaveBeenCalledWith({
      url: 'https://peerly.example.test/api/v1/auth/native/start',
    });
    expect(native.close).toHaveBeenCalled();
  });

  it('cold launch may offer restart but cannot reconstruct a proof', async () => {
    native.enabled.mockReturnValue(true);
    native.available.mockReturnValue(true);
    native.launch.mockResolvedValue(undefined);
    await expect(nativeLaunchHint('dev.alekseiorlov.peerly://auth/complete')).resolves.toBeNull();
    native.launch.mockResolvedValue({
      url: 'dev.alekseiorlov.peerly://auth/complete?token=forbidden',
    });
    await expect(nativeLaunchHint('dev.alekseiorlov.peerly://auth/complete')).resolves.toBeNull();
    native.launch.mockResolvedValue({ url: 'dev.alekseiorlov.peerly://auth/complete' });
    await expect(nativeLaunchHint('dev.alekseiorlov.peerly://auth/complete')).resolves.toBe(
      'restart-sign-in',
    );
  });
});

it('does not close a newer external browser when an older attempt cleans up', async () => {
  native.enabled.mockReturnValue(true);
  native.available.mockReturnValue(true);
  const older = capacitorAuthPlatform();
  const newer = capacitorAuthPlatform();
  await older.open('https://peerly.example.test/api/v1/auth/native/start');
  await newer.open('https://peerly.example.test/api/v1/auth/native/start');
  native.close.mockClear();
  await older.close();
  expect(native.close).not.toHaveBeenCalled();
  await newer.close();
  expect(native.close).toHaveBeenCalledTimes(1);
});
