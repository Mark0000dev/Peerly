import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { defineConfig } from '@playwright/test';

const testPort = process.env['STUDYMATE_TEST_PORT'] ?? '4317';
if (!/^[0-9]{4,5}$/.test(testPort) || Number(testPort) < 1024 || Number(testPort) > 65535)
  throw new Error('Invalid loopback test port');
const webkitEndpoint = process.env['STUDYMATE_WEBKIT_WS_ENDPOINT'];
const staticBuild = process.env['STUDYMATE_STATIC_BUILD'] === '1';
const fullStack = process.env['STUDYMATE_FULLSTACK'] === '1';
const origin = `${fullStack ? 'https' : 'http'}://127.0.0.1:${testPort}`;
const tlsDirectory = fullStack ? mkdtempSync(join(tmpdir(), 'studymate-frontend-tls-')) : '';
const tlsArgument = (name: string): string =>
  `'${join(tlsDirectory, name).replaceAll("'", "'\\''")}'`;

export default defineConfig({
  testDir: './src/app/screens',
  testMatch: staticBuild
    ? '**/*.prerender.visual.spec.ts'
    : fullStack
      ? '**/*.fullstack.visual.spec.ts'
      : '**/*.visual.spec.ts',
  testIgnore:
    staticBuild || fullStack
      ? []
      : ['**/*.fullstack.visual.spec.ts', '**/*.prerender.visual.spec.ts'],
  snapshotPathTemplate:
    '{testDir}/{testFileDir}/__screenshots__/{testFileName}/{projectName}/{arg}{ext}',
  updateSnapshots: 'none',
  forbidOnly: true,
  retries: 0,
  workers: 2,
  reporter: [['list'], ['html', { open: 'never' }]],
  expect: {
    toHaveScreenshot: { animations: 'disabled', caret: 'hide', maxDiffPixels: 0 },
  },
  use: {
    baseURL: origin,
    ignoreHTTPSErrors: fullStack,
    locale: 'en-GB',
    timezoneId: 'Asia/Kuala_Lumpur',
    colorScheme: 'light',
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium-mobile',
      use: {
        browserName: 'chromium',
        viewport: { width: 360, height: 800 },
        isMobile: true,
        hasTouch: true,
      },
    },
    {
      name: 'webkit-mobile',
      use: {
        browserName: 'webkit',
        ...(webkitEndpoint === undefined
          ? {}
          : { connectOptions: { wsEndpoint: webkitEndpoint, exposeNetwork: '<loopback>' } }),
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
    {
      name: 'chromium-desktop',
      use: { browserName: 'chromium', viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: [
    ...(fullStack
      ? [
          {
            command: 'cd ../backend && .venv/bin/python ../frontend/testing/backend_fixture.py',
            env: {
              STUDYMATE_TEST_TLS_DIRECTORY: tlsDirectory,
              STUDYMATE_TEST_PUBLIC_ORIGIN: origin,
            },
            url: 'http://127.0.0.1:8768/api/health',
            gracefulShutdown: { signal: 'SIGTERM' as const, timeout: 10_000 },
            reuseExistingServer: false,
            timeout: 120_000,
          },
        ]
      : []),
    {
      command: staticBuild
        ? 'node testing/static_server.mjs'
        : fullStack
          ? `npm start -- --host 127.0.0.1 --port ${testPort} --proxy-config testing/proxy.json --ssl --ssl-cert ${tlsArgument('cert.pem')} --ssl-key ${tlsArgument('key.pem')}`
          : `npm start -- --host 127.0.0.1 --port ${testPort}`,
      url: origin,
      ignoreHTTPSErrors: fullStack,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
