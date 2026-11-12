import { signal } from '@angular/core';
import { Capacitor } from '@capacitor/core';
import { App } from '@capacitor/app';
import type { URLOpenListenerEvent } from '@capacitor/app';
import { Browser } from '@capacitor/browser';
import type { NativeAuthPlatform } from './native-login';
import { NativeLoginFailure } from './native-login';

const activeBrowser = signal<symbol | null>(null);

export function capacitorAuthPlatform(): NativeAuthPlatform {
  if (
    !Capacitor.isNativePlatform() ||
    !Capacitor.isPluginAvailable('App') ||
    !Capacitor.isPluginAvailable('Browser')
  )
    throw new NativeLoginFailure('unavailable');
  const lease = Symbol();
  return {
    listen: async (accept) =>
      await App.addListener('appUrlOpen', (event: Readonly<URLOpenListenerEvent>) => {
        accept(event.url);
      }),
    open: async (url) => {
      activeBrowser.set(lease);
      await Browser.open({ url });
    },
    // Official Browser.close is a no-op on Android; never treat it as revocation.
    close: async () => {
      if (activeBrowser() !== lease) return;
      activeBrowser.set(null);
      await Browser.close();
    },
  };
}

export async function nativeLaunchHint(expectedWake: string): Promise<'restart-sign-in' | null> {
  if (!Capacitor.isNativePlatform() || !Capacitor.isPluginAvailable('App')) return null;
  const launched = await App.getLaunchUrl();
  // After process death the in-memory proof is intentionally gone. A launch URL
  // cannot restore authority. Parent may show a fresh-sign-in action only.
  return launched?.url === expectedWake ? 'restart-sign-in' : null;
}
