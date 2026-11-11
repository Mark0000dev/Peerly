// Node-side Playwright imports partially compiled Angular boundary guards.
import '@angular/compiler';
import { test as base, expect } from '@playwright/test';
import type {
  ConsoleMessage,
  Locator,
  PlaywrightTestArgs,
  PlaywrightTestOptions,
  PlaywrightWorkerOptions,
  Request,
  Response,
  TestInfo,
  WebSocket,
} from '@playwright/test';
import { closeOwnedPage } from './owned-page.mts';
import { captureWebkitPreviewFrame } from './webkit-preview-frame.mts';

type CheckpointOptions =
  | Readonly<{ readonly fullPage: boolean }>
  | Readonly<{ readonly target: Readonly<Locator> }>
  | Readonly<{ readonly webkitPreview: 'open' | 'zoom' }>;
type Checkpoint = (name: string, options?: CheckpointOptions) => Promise<void>;
interface VisualFixtures {
  readonly checkpoint: Checkpoint;
}

function forwardedError(payload: string | Buffer): string | null {
  if (typeof payload !== 'string' || !payload.includes('"vite:forward-console"')) return null;
  const event: unknown = JSON.parse(payload);
  if (
    typeof event !== 'object' ||
    event === null ||
    !('event' in event) ||
    event.event !== 'vite:forward-console' ||
    !('data' in event) ||
    typeof event.data !== 'object' ||
    event.data === null
  )
    return null;
  const data = event.data;
  if (!('type' in data) || !('data' in data) || typeof data.data !== 'object' || data.data === null)
    return null;
  const detail = data.data;
  if (
    data.type !== 'error' &&
    data.type !== 'unhandled-rejection' &&
    !(data.type === 'log' && 'level' in detail && detail.level === 'error')
  )
    return null;
  return 'message' in detail && typeof detail.message === 'string'
    ? detail.message
    : 'Forwarded browser runtime error';
}

export const test = base.extend<VisualFixtures>({
  checkpoint: [
    async (
      {
        page,
        javaScriptEnabled,
        browserName,
      }: Readonly<
        Pick<PlaywrightTestArgs, 'page'> &
          Pick<PlaywrightTestOptions, 'javaScriptEnabled'> &
          Pick<PlaywrightWorkerOptions, 'browserName'>
      >,
      use: (checkpoint: Checkpoint) => Promise<void>,
      info: Readonly<TestInfo>,
    ) => {
      let checkpoints = 0;
      let phase = 'scenario';
      let errors: readonly string[] = [];
      let failedApiUrls: readonly string[] = [];
      let consoleErrors: readonly { readonly text: string; readonly url: string }[] = [];
      let primaryFailed = true;
      try {
        // These local development/prerender fixtures have no approved production
        // release map. Configure that public build-metadata port explicitly as
        // frame-free; session, business and full-stack intake APIs stay untouched.
        // Actual emitted-map serving is verified by the separate native image proof.
        await page.route('**/assets/observation-release.json', async (route) => {
          await route.fulfill({ json: {} });
        });
        if (
          process.env['STUDYMATE_FULLSTACK'] !== '1' &&
          process.env['STUDYMATE_STATIC_BUILD'] !== '1'
        ) {
          // Controlled wire boundary only; real FastAPI streams remain unmocked.
          await page.route('**/api/v1/events', async (route) => {
            await route.fulfill({
              status: 200,
              contentType: 'text/event-stream',
              body: ': heartbeat\n\n',
            });
          });
        }
        page.on('websocket', (socket: Readonly<WebSocket>) => {
          socket.on('framesent', (frame: Readonly<{ readonly payload: string | Buffer }>) => {
            const error = forwardedError(frame.payload);
            if (error !== null) errors = [...errors, `[${phase}] ${error}`];
          });
        });
        page.on('response', (response: Readonly<Response>) => {
          if (response.status() >= 400 && new URL(response.url()).pathname.startsWith('/api/v1/'))
            failedApiUrls = [...failedApiUrls, response.url()];
        });
        page.on('requestfailed', (request: Readonly<Request>) => {
          if (new URL(request.url()).pathname.startsWith('/api/v1/'))
            failedApiUrls = [...failedApiUrls, request.url()];
        });
        page.on('console', (message: Readonly<ConsoleMessage>) => {
          if (message.type() === 'error')
            consoleErrors = [
              ...consoleErrors,
              { text: message.text(), url: message.location().url },
            ];
        });
        page.on('pageerror', (error: Readonly<Error>) => {
          errors = [...errors, error.message];
        });
        await page.exposeFunction('__peerlyReportRuntimeError', (message: unknown) => {
          errors = [...errors, typeof message === 'string' ? message : 'Unknown runtime error'];
        });
        // Observe before framework/dev-server handlers can prevent browser reporting.
        // Resource HTTP failures are not ErrorEvents; negative HTTP scenarios remain valid.
        await page.addInitScript({
          content: `
        window.addEventListener('error', event => {
          if ('message' in event && typeof event.message === 'string') {
            console.warn('[peerly owned runtime context]', ${JSON.stringify(info.project.name + ':' + info.testId)}, event.message);
            void window.__peerlyReportRuntimeError(event.message);
          }
        });
        window.addEventListener('unhandledrejection', event => {
          void window.__peerlyReportRuntimeError(event.reason instanceof Error ? event.reason.message : 'Unhandled promise rejection');
        });
      `,
        });
        await use(async (name: string, options: CheckpointOptions = { fullPage: true }) => {
          phase = 'screenshot';
          if ('webkitPreview' in options) {
            if (browserName === 'webkit') {
              const artifact = info.outputPath(`${name}-ordinary.png`);
              await page.screenshot({ path: artifact, fullPage: false });
              await info.attach(`${name}-ordinary-snapshot-artifact`, {
                path: artifact,
                contentType: 'image/png',
              });
              const frame = await captureWebkitPreviewFrame(page, {
                engine: browserName,
                state: options.webkitPreview,
                recordFrame: async (native, cycle) => {
                  await info.attach(`${name}-fresh-compositor-${String(cycle)}.jpeg`, {
                    body: native.data,
                    contentType: 'image/jpeg',
                  });
                  await info.attach(`${name}-fresh-compositor-${String(cycle)}.json`, {
                    body: JSON.stringify({
                      timestamp: native.timestamp,
                      viewportWidth: native.viewportWidth,
                      viewportHeight: native.viewportHeight,
                    }),
                    contentType: 'application/json',
                  });
                },
              });
              expect(frame).toMatchSnapshot(name.replace(/\.png$/, '.jpeg'), {
                maxDiffPixels: 0,
                threshold: 0,
              });
            } else await expect(page).toHaveScreenshot(name, { fullPage: false });
          } else if ('target' in options) await expect(options.target).toHaveScreenshot(name);
          else await expect(page).toHaveScreenshot(name, options);
          phase = 'scenario';
          checkpoints += 1;
        });
        primaryFailed = info.status !== 'passed';
        // Finish the screenshot's render/viewport restoration before checking diagnostics.
        phase = 'render-drain';
        if (!primaryFailed && javaScriptEnabled)
          await page.evaluate(
            () =>
              new Promise<void>((resolve) =>
                requestAnimationFrame(() =>
                  requestAnimationFrame(() => {
                    resolve();
                  }),
                ),
              ),
          );
      } catch (error: unknown) {
        primaryFailed = true;
        throw error;
      } finally {
        phase = 'page-close';
        const cleanup = await closeOwnedPage(page, primaryFailed);
        phase = 'closed';
        if (cleanup !== null) {
          try {
            await info.attach('owned-page-cleanup-failure', {
              body: 'Page cleanup also failed; the original test failure is preserved.',
              contentType: 'text/plain',
            });
          } catch {
            // The test already failed. A failed diagnostic attachment must not replace it.
          }
        }
      }
      if (info.status === 'passed') {
        // Browser resource diagnostics for the API failures exercised by negative scenarios
        // are distinct from JS/application console errors. Never exempt a runtime message.
        const unexpectedConsole = consoleErrors.filter(
          (entry) =>
            !(
              entry.text.startsWith('Failed to load resource:') && failedApiUrls.includes(entry.url)
            ),
        );
        expect(unexpectedConsole, 'Application console errors must be fixed').toEqual([]);
        expect(errors, 'Browser runtime errors must be fixed, not filtered').toEqual([]);
        expect(
          checkpoints,
          'Every passing integration scenario needs a screenshot assertion',
        ).toBeGreaterThan(0);
      }
    },
    { auto: true },
  ],
});

export { expect };
