import type { CapacitorConfig } from '@capacitor/cli';
import { nativeBuilds } from './src/app/native-transport/config';

const variant = process.env['PEERLY_NATIVE_VARIANT'] ?? 'production';
if (variant !== 'production' && variant !== 'staging') throw new Error('Invalid native variant');
const build = nativeBuilds[variant];
const config: CapacitorConfig = {
  appId: build.appId,
  appName: build.appName,
  webDir: 'dist/studymate/browser',
  loggingBehavior: 'none',
  android: { allowMixedContent: false, webContentsDebuggingEnabled: false },
  plugins: {
    PeerlyTransport: { apiOrigin: build.apiOrigin, wakeUrl: build.wakeUrl },
    CapacitorHttp: { enabled: false },
    CapacitorCookies: { enabled: false },
  },
};
export default config;
