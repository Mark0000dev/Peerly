import { chromium, webkit, request } from '@playwright/test';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const { values } = parseArgs({
  options: {
    origin: { type: 'string' },
    output: { type: 'string' },
    'webkit-endpoint': { type: 'string' },
    project: { type: 'string', multiple: true },
    motion: { type: 'string', multiple: true },
    'update-snapshots': { type: 'boolean', default: false },
    'controlled-auth': { type: 'boolean', default: false },
  },
});
if (values.origin === undefined || values.output === undefined)
  throw new Error(
    'Required: --origin <actual production image origin> --output <artifact directory>',
  );
const url = new URL(values.origin);
if (
  !['http:', 'https:'].includes(url.protocol) ||
  url.username !== '' ||
  url.password !== '' ||
  url.pathname !== '/' ||
  url.search !== '' ||
  url.hash !== ''
)
  throw new Error('Expected credential-free canonical origin');
const origin = url.origin;
if (values['controlled-auth'] && !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname))
  throw new Error('Controlled auth fixtures require an owned loopback build origin');
// Node24's native erasable TypeScript support reads the existing typed fixture;
// no duplicate DTO, production mock, credential or live identity provider.
const authFixtures = values['controlled-auth']
  ? await import('../src/app/screens/onboarding/onboarding.fixtures.ts')
  : null;
const output = resolve(values.output);
const directory = dirname(fileURLToPath(import.meta.url));
const endpoint = values['webkit-endpoint'] ?? process.env['STUDYMATE_WEBKIT_WS_ENDPOINT'];
if (endpoint === undefined) throw new Error('A supported owned WebKit server endpoint is required');
const names = ['chat', 'hello', 'letter', 'oops', 'read', 'rest'];
const projects = [
  {
    name: 'chromium-mobile',
    engine: chromium,
    viewport: { width: 360, height: 800 },
    isMobile: true,
    hasTouch: true,
  },
  {
    name: 'webkit-mobile',
    engine: webkit,
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  },
  {
    name: 'chromium-desktop',
    engine: chromium,
    viewport: { width: 1440, height: 900 },
    isMobile: false,
    hasTouch: false,
  },
];
const selected =
  values.project === undefined
    ? projects
    : projects.filter((project) => values.project.includes(project.name));
if (
  selected.length === 0 ||
  values.project?.some((name) => !projects.some((project) => project.name === name))
)
  throw new Error('Unknown native proof project');
const motions = values.motion ?? ['no-preference', 'reduce'];
if (motions.some((mode) => !['no-preference', 'reduce'].includes(mode)))
  throw new Error('Unknown motion mode');
const hash = (value) => createHash('sha256').update(value).digest('hex');
await mkdir(output, { recursive: true });

async function differences(page, left, right, regions) {
  return await page.evaluate(
    async ({ first, second, boxes }) => {
      const decode = async (encoded) => {
        const bytes = Uint8Array.from(atob(encoded), (letter) => letter.charCodeAt(0));
        const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
        const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
        const context = canvas.getContext('2d');
        if (context === null) throw new Error('PNG analysis context unavailable');
        context.drawImage(bitmap, 0, 0);
        bitmap.close();
        return context.getImageData(0, 0, canvas.width, canvas.height);
      };
      const a = await decode(first);
      const b = await decode(second);
      if (a.width !== b.width || a.height !== b.height)
        throw new Error('Screenshot dimensions changed');
      const counters = boxes.map((box) => ({ name: box.name, changed: 0 }));
      let total = 0;
      for (let index = 0; index < a.data.length; index += 4) {
        if (
          a.data[index] === b.data[index] &&
          a.data[index + 1] === b.data[index + 1] &&
          a.data[index + 2] === b.data[index + 2] &&
          a.data[index + 3] === b.data[index + 3]
        )
          continue;
        total += 1;
        const x = (index / 4) % a.width;
        const y = Math.floor(index / 4 / a.width);
        boxes.forEach((box, position) => {
          if (
            x >= Math.floor(box.x) &&
            x < Math.ceil(box.x + box.width) &&
            y >= Math.floor(box.y) &&
            y < Math.ceil(box.y + box.height)
          )
            counters[position].changed += 1;
        });
      }
      return { width: a.width, height: a.height, changed: total, regions: counters };
    },
    { first: left.toString('base64'), second: right.toString('base64'), boxes: regions },
  );
}

async function ready(page, selector) {
  await page.waitForFunction(
    () =>
      document.fonts.status === 'loaded' &&
      document.getAnimations().every((animation) => {
        const timing = animation.effect?.getComputedTiming();
        // Scroll-driven timelines expose CSSNumberish durations and intentionally
        // remain running; they are not unfinished finite page-enter transitions.
        const finite =
          timing !== undefined &&
          typeof timing.activeDuration === 'number' &&
          Number.isFinite(timing.activeDuration);
        return !finite || ['finished', 'idle'].includes(animation.playState);
      }),
  );
  // Route headings and fonts can be ready while a newly selected SVG is still
  // downloading/decoding. Await the actual picture image, not an arbitrary delay.
  await page.locator(selector).evaluateAll(async (images) => {
    if (images.length === 0) throw new Error('No actual mascot image');
    const decoding = Promise.all(
      images.map((image) => {
        if (!(image instanceof HTMLImageElement)) throw new Error('Expected a mascot image');
        return image.decode();
      }),
    );
    let deadline;
    try {
      await Promise.race([
        decoding,
        new Promise((_, reject) => {
          deadline = setTimeout(() => reject(new Error('Mascot SVG decode timed out')), 10_000);
        }),
      ]);
    } finally {
      clearTimeout(deadline);
    }
  });
  await page.evaluate(() => new Promise(requestAnimationFrame));
}
async function geometry(page, selector) {
  return await page.locator(selector).evaluateAll((images) =>
    images.map((image) => {
      if (!(image instanceof HTMLImageElement) || !image.complete || image.naturalWidth === 0)
        throw new Error('Production SVG image is not loaded');
      const box = image.getBoundingClientRect();
      return {
        name: new URL(image.src).pathname.split('/').at(-1),
        selectedSource: new URL(image.currentSrc).pathname,
        x: box.x,
        y: box.y,
        width: box.width,
        height: box.height,
      };
    }),
  );
}
async function centerVisibleMascot(image) {
  // Native nearest-edge scrolling can round fractional image bounds beyond the
  // viewport. Center the real consumer with the public API; keep strict bounds.
  await image.evaluate((element) =>
    element.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' }),
  );
}

async function capture(page, project, mode, kind, selector) {
  await ready(page, selector);
  const boxes = await geometry(page, selector);
  if (boxes.length === 0) throw new Error('No actual mascot image');
  if (boxes.some((box) => box.selectedSource.endsWith('-still.svg') !== (mode === 'reduce')))
    throw new Error('Native picture selected the wrong motion variant');
  const viewport = page.viewportSize();
  if (
    viewport === null ||
    boxes.some(
      (box) =>
        box.x < 0 ||
        box.y < 0 ||
        box.x + box.width > viewport.width ||
        box.y + box.height > viewport.height,
    )
  )
    throw new Error('Required mascot is clipped by the viewport');
  const frames = [];
  for (let index = 0; index < 3; index += 1) {
    // Observe distinct animation phases, rather than assuming consecutive PNG
    // requests imply a new rendered SVG frame. The shortest continuous artwork
    // cycle is 2.4s (twinkle); sample its quarter-period using the public frame
    // clock. Apply the identical observation window to reduced motion too.
    await page.evaluate(
      () =>
        new Promise((resolve) => {
          const start = performance.now();
          const observe = (now) => {
            if (now - start >= 600) resolve();
            else requestAnimationFrame(observe);
          };
          requestAnimationFrame(observe);
        }),
    );
    const frame = await page.screenshot({ animations: 'allow', fullPage: false });
    await writeFile(join(output, `${project}-${mode}-${kind}-${String(index)}.png`), frame);
    const current = await geometry(page, selector);
    if (JSON.stringify(current) !== JSON.stringify(boxes))
      throw new Error('Mascot outer geometry moved');
    frames.push(frame);
  }
  const pairs = [];
  for (let index = 1; index < frames.length; index += 1)
    pairs.push(await differences(page, frames[index - 1], frames[index], boxes));
  await writeFile(
    join(output, `${project}-${mode}-${kind}-measurements.json`),
    JSON.stringify({ boxes, pairs }, null, 2) + '\n',
  );
  if (mode === 'reduce') {
    if (pairs.some((pair) => pair.changed !== 0))
      throw new Error('Reduced-motion screenshots are not stable');
    const baseline = join(
      directory,
      '__screenshots__',
      'mascot-motion',
      project,
      `${kind}-reduce.png`,
    );
    if (values['update-snapshots']) {
      await mkdir(dirname(baseline), { recursive: true });
      await writeFile(baseline, frames[0]);
    } else {
      const reference = await readFile(baseline);
      const compared = await differences(page, reference, frames[0], boxes);
      if (compared.changed !== 0) throw new Error('Reduced-motion golden differs');
    }
  } else {
    for (const box of boxes)
      if (
        !pairs.some((pair) =>
          pair.regions.some((region) => region.name === box.name && region.changed > 0),
        )
      )
        throw new Error(`No normal-motion pixels changed for ${box.name}`);
  }
  return { kind, boxes, pairs, capture: 'full-viewport PNG, animations allow, all pixels decoded' };
}

const network = await request.newContext();
let reports = [];
let diagnostics = [];
let startupFailure = null;
const message = (error) =>
  error instanceof Error ? error.message : 'Unknown native proof failure';
async function closeSafely(close, project, mode, resource) {
  try {
    await close();
  } catch (error) {
    diagnostics = [
      ...diagnostics,
      { project, mode, kind: 'cleanup', resource, text: message(error) },
    ];
  }
}
try {
  for (const name of names) {
    for (const suffix of ['', '-still']) {
      const filename = `mascot-${name}${suffix}.svg`;
      const response = await network.get(origin + `/assets/brand/${filename}`, {
        headers: { 'Accept-Encoding': 'identity' },
      });
      if (
        response.status() !== 200 ||
        !response.headers()['content-type']?.includes('image/svg+xml')
      )
        throw new Error(`Actual production asset unavailable: ${filename}`);
      const source = await readFile(join(directory, '..', 'src', 'assets', 'brand', filename));
      if (hash(await response.body()) !== hash(source))
        throw new Error(`Production asset hash differs: ${filename}`);
    }
  }
  for (const project of selected) {
    let browser = null;
    try {
      browser =
        project.engine === webkit
          ? await webkit.connect(endpoint, { exposeNetwork: '<loopback>', timeout: 30_000 })
          : await chromium.launch({ timeout: 30_000 });
    } catch (error) {
      reports = [...reports, { project: project.name, status: 'failed', error: message(error) }];
      continue;
    }
    try {
      for (const mode of motions) {
        let context = null;
        let pages = [];
        let failure = null;
        let captures = null;
        const observe = (page) => {
          page.on('response', (response) => {
            if (response.status() >= 400) {
              const url = new URL(response.url());
              diagnostics = [
                ...diagnostics,
                {
                  project: project.name,
                  mode,
                  kind: 'http-status',
                  origin: url.origin,
                  path: url.pathname,
                  status: response.status(),
                },
              ];
            }
          });
          page.on('pageerror', (error) => {
            diagnostics = [
              ...diagnostics,
              { project: project.name, mode, kind: 'pageerror', text: error.message },
            ];
          });
          page.on('console', (entry) => {
            if (entry.type() === 'error')
              diagnostics = [
                ...diagnostics,
                {
                  project: project.name,
                  mode,
                  kind: 'console.error',
                  text: entry.text(),
                  path: entry.location().url ? new URL(entry.location().url).pathname : null,
                },
              ];
          });
        };
        try {
          context = await browser.newContext({
            viewport: project.viewport,
            isMobile: project.isMobile,
            hasTouch: project.hasTouch,
            deviceScaleFactor: 1,
            reducedMotion: mode,
            locale: 'en-GB',
            timezoneId: 'Asia/Kuala_Lumpur',
          });
          // Native message-only ErrorEvents (including ResizeObserver) need an
          // explicit passive observer: pageerror alone can miss browser events.
          // Do not cancel, rewrite or filter the original browser diagnostics.
          await context.addInitScript(() => {
            addEventListener(
              'error',
              (event) => {
                console.error(
                  '[peerly native motion window.error]',
                  event instanceof ErrorEvent ? event.message : 'Resource load error',
                );
              },
              true,
            );
            addEventListener('unhandledrejection', (event) => {
              console.error(
                '[peerly native motion unhandledrejection]',
                event.reason instanceof Error ? event.reason.message : String(event.reason),
              );
            });
          });
          context.setDefaultTimeout(10_000);
          context.setDefaultNavigationTimeout(30_000);
          const landing = await context.newPage();
          pages = [...pages, landing];
          observe(landing);
          await landing.goto(origin);
          await landing.getByRole('heading', { level: 1 }).waitFor();
          const hero = landing.locator('img[src*="mascot-"]').first();
          await centerVisibleMascot(hero);
          const actualPreference = await landing.evaluate(
            () => matchMedia('(prefers-reduced-motion: reduce)').matches,
          );
          if (actualPreference !== (mode === 'reduce'))
            throw new Error('Actual motion preference differs');
          const heroSource = await hero.getAttribute('src');
          if (heroSource === null) throw new Error('Missing landing mascot source');
          const landingCapture = await capture(
            landing,
            project.name,
            mode,
            'landing',
            `img[src="${heroSource}"]`,
          );
          const safetySelector = 'peerly-mascot.safety-art img';
          await centerVisibleMascot(landing.locator(safetySelector));
          const safetyCapture = await capture(
            landing,
            project.name,
            mode,
            'landing-safety',
            safetySelector,
          );
          const missing = await context.newPage();
          pages = [...pages, missing];
          observe(missing);
          await missing.goto(origin + '/mascot-proof-missing-page');
          await missing.getByRole('heading', { name: 'Page not found', exact: true }).waitFor();
          const missingSelector = 'peerly-mascot img';
          await centerVisibleMascot(missing.locator(missingSelector));
          const missingCapture = await capture(
            missing,
            project.name,
            mode,
            'not-found',
            missingSelector,
          );
          const authCaptures = [];
          if (authFixtures !== null) {
            for (const scenario of [
              {
                name: 'confirmed-membership',
                identity: authFixtures.verifiedActor,
                heading: 'Your APU email is confirmed',
              },
              {
                name: 'email-code',
                identity: authFixtures.pending,
                heading: 'Check your APU email',
              },
            ]) {
              const auth = await context.newPage();
              pages = [...pages, auth];
              observe(auth);
              // Controlled read-only schema boundary for the ACTUAL built Angular
              // consumer. This is not Google/email/provider integration evidence.
              await auth.clock.setFixedTime(new Date('2026-11-07T12:00:00Z'));
              await auth.route(origin + '/api/v1/**', async (route) => {
                const request = route.request();
                const path = new URL(request.url()).pathname;
                try {
                  if (path === '/api/v1/telemetry/events' && request.method() === 'POST') {
                    const batch = request.postDataJSON();
                    if (
                      batch?.schema_version !== 1 ||
                      batch.expected_actor_id !== scenario.identity.account_id ||
                      !Array.isArray(batch.events) ||
                      batch.events.length < 1 ||
                      batch.events.length > 20 ||
                      !batch.events.every(
                        (event) =>
                          typeof event?.event_id === 'string' &&
                          /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/iu.test(event.event_id),
                      )
                    )
                      throw new Error('Invalid controlled observation batch');
                    // Explicit actual-contract fixture only: no live analytics
                    // write, payload logging or claim that staging503 is fixed.
                    await route.fulfill({
                      json: {
                        schema_version: 1,
                        accepted: batch.events.map((event) => event.event_id),
                        duplicates: [],
                        received_at: '2026-11-07T12:00:00Z',
                      },
                    });
                    return;
                  }
                  if (request.method() !== 'GET')
                    throw new Error('Unexpected business mutation in read-only mascot proof');
                  if (path === '/api/v1/me') {
                    await route.fulfill({ json: scenario.identity });
                    return;
                  }
                  if (path === '/api/v1/auth/email-challenges/' + authFixtures.challenge.id) {
                    await route.fulfill({ json: authFixtures.challenge });
                    return;
                  }
                  throw new Error('Unexpected API read in controlled mascot proof');
                } catch (error) {
                  diagnostics = [
                    ...diagnostics,
                    {
                      project: project.name,
                      mode,
                      kind: 'controlled-boundary',
                      method: request.method(),
                      path,
                      text: message(error),
                    },
                  ];
                  try {
                    await route.abort('failed');
                  } catch (abortError) {
                    diagnostics = [
                      ...diagnostics,
                      {
                        project: project.name,
                        mode,
                        kind: 'controlled-route-cleanup',
                        path,
                        text: message(abortError),
                      },
                    ];
                  }
                }
              });
              await auth.goto(origin + '/onboarding');
              await auth.getByRole('heading', { name: scenario.heading, exact: true }).waitFor();
              await auth.waitForFunction(() =>
                [...document.images].every((image) => image.complete && image.naturalWidth > 0),
              );
              const selector = 'peerly-mascot img';
              await centerVisibleMascot(auth.locator(selector));
              authCaptures.push(
                await capture(auth, project.name, mode, 'auth-' + scenario.name, selector),
              );
            }
          }
          const sheet = await context.newPage();
          pages = [...pages, sheet];
          observe(sheet);
          // Synthetic asset worksheet only, never a new product screen or a design-fidelity proof.
          await sheet.setContent(
            `<meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;padding:16px;font:14px sans-serif}main{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;max-width:660px;margin:auto}figure{margin:0;text-align:center}img{width:100%;max-width:200px;height:180px;object-fit:contain}@media(min-width:700px){main{grid-template-columns:repeat(3,minmax(0,1fr))}}</style><main>${names.map((name) => `<figure><picture><source media="(prefers-reduced-motion: reduce)" srcset="${origin}/assets/brand/mascot-${name}-still.svg"><img src="${origin}/assets/brand/mascot-${name}.svg"></picture><figcaption>${name}</figcaption></figure>`).join('')}</main>`,
          );
          await sheet.locator('img').last().waitFor();
          await sheet.waitForFunction(() =>
            [...document.images].every((image) => image.complete && image.naturalWidth > 0),
          );
          const worksheet = await capture(sheet, project.name, mode, 'asset-sheet', 'img');
          captures = {
            landing: landingCapture,
            safety: safetyCapture,
            notFound: missingCapture,
            worksheet,
            controlledAuth: authCaptures,
          };
        } catch (error) {
          failure = message(error);
        } finally {
          // Preserve the primary capture/behavior failure and collect cleanup failures separately.
          for (const page of pages)
            await closeSafely(() => page.close(), project.name, mode, 'page');
          if (context !== null)
            await closeSafely(() => context.close(), project.name, mode, 'context');
        }
        reports = [
          ...reports,
          {
            project: project.name,
            mode,
            status: failure === null ? 'passed' : 'failed',
            error: failure,
            captures,
          },
        ];
      }
    } finally {
      await closeSafely(() => browser.close(), project.name, 'all', 'browser');
    }
  }
} catch (error) {
  startupFailure = message(error);
} finally {
  await closeSafely(() => network.dispose(), 'all', 'all', 'request context');
}
const passed =
  startupFailure === null &&
  diagnostics.length === 0 &&
  reports.length === selected.length * motions.length &&
  reports.every((report) => report.status === 'passed');
await writeFile(
  join(output, 'report.json'),
  JSON.stringify(
    {
      origin,
      status: passed ? 'passed' : 'failed',
      projects: reports,
      selected_projects: selected.map((project) => project.name),
      selected_motions: motions,
      controlled_auth:
        authFixtures === null
          ? null
          : {
              boundary:
                'Existing typed read fixtures at actual compiled Angular consumers; no providers',
              fixed_browser_time: '2026-11-07T12:00:00Z',
              excludes:
                'Live Google/email/analytics, real membership persistence, auth error mascot',
              observation_delivery: 'Explicit actual-contract controlled acknowledgement only',
            },
      startupFailure,
      diagnostics,
    },
    null,
    2,
  ) + '\n',
);
if (!passed)
  throw new Error(
    'Native motion proof failed; full captures/measurements/diagnostics preserved in report.json',
  );
console.log(
  `Mascot actual-build proof PASS: ${selected.map((project) => project.name).join(', ')}; motions=${motions.join(', ')}`,
);
