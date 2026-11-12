import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { setTimeout, clearTimeout } from 'node:timers';
import { join } from 'node:path';
import { URL, fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

// Developer-only native isolation fixture. No application route/provider/dependency patch.
const variant =
  process.argv.find((argument) => argument.startsWith('--variant='))?.slice(10) ?? 'baseline';
assert.ok(['baseline', 'idempotent', 'owner-cleanup'].includes(variant));
const capture =
  process.argv.find((argument) => argument.startsWith('--capture='))?.slice(10) ?? 'direct';
assert.ok(['direct', 'matcher', 'viewport-cycle'].includes(capture));
const output = join(tmpdir(), 'peerly-font-watcher-minimal-' + variant + '-' + Date.now());
await mkdir(output);
const packageRoot = new URL('../node_modules/@taiga-ui/font-watcher/', import.meta.url);
const metadata = JSON.parse(await readFile(new URL('package.json', packageRoot), 'utf8'));
assert.equal(metadata.version, '0.6.0');
const entry = metadata.exports['.'].module;
assert.equal(entry, './index.esm.js');
const source = await readFile(new URL(entry, packageRoot));
const fingerprint = createHash('sha256').update(source).digest('hex');
const provenance = {
  version: metadata.version,
  entry,
  sha256: fingerprint,
  provider: createHash('sha256')
    .update(
      await readFile(
        new URL(
          '../node_modules/@taiga-ui/core/fesm2022/taiga-ui-core-utils-miscellaneous.mjs',
          import.meta.url,
        ),
      ),
    )
    .digest('hex'),
  resizePlugin: createHash('sha256')
    .update(
      await readFile(
        new URL(
          '../node_modules/@taiga-ui/event-plugins/fesm2022/taiga-ui-event-plugins.mjs',
          import.meta.url,
        ),
      ),
    )
    .digest('hex'),
};

function client(watcher, platform, mode) {
  const { document, window, ResizeObserver, MutationObserver } = platform;
  const root = document.documentElement;
  const detector = document.createElement('iframe');
  let events = [];
  let lastMetric = null;
  let fontCallbacks = 0;
  let spanSize = null;
  let companion = null;
  let mirror = null;
  let mutationCount = 0;
  let mutations = null;
  let stopped = false;
  const record = (event, fields = {}) => {
    events = [
      ...events.slice(-127),
      { event, at: platform.performance.timeOrigin + platform.performance.now(), ...fields },
    ];
  };
  const disposeFont = watcher((size) => {
    lastMetric = size;
    fontCallbacks += 1;
    const value = String(Math.min(28, Math.max(17, size)) - 17);
    const previous = root.style.getPropertyValue('--t-font-offset');
    record('font.callback', {
      size,
      previous,
      value,
      width: detector.contentDocument?.body.clientWidth ?? null,
    });
    if (mode === 'idempotent' && previous === value) {
      record('font.same-value-skipped');
      return;
    }
    root.style.setProperty('--t-font-offset', value);
    record('font.write', { value, same: previous === value });
  }, detector);
  function recover() {
    const field = document.createElement('section');
    field.innerHTML =
      '<label>Message<textarea rows="2"></textarea></label><span id="mirror" aria-hidden="true">.\n.</span>';
    mirror = field.querySelector('#mirror');
    const input = field.querySelector('textarea');
    companion = new ResizeObserver((entries) => {
      const entry = entries[0];
      spanSize = { width: entry.contentRect.width, height: entry.contentRect.height };
      record('textfield.callback', spanSize);
      input.style.height = String(mirror.offsetHeight) + 'px';
      record('textfield.write', { height: input.style.height });
    });
    // Same native observer/observe/disconnect pattern as the installed ResizePlugin.
    // The span is observed before insertion, matching the actual owner trace.
    companion.observe(mirror);
    document.querySelector('#error').remove();
    document.querySelector('#slot').append(field);
    record('textfield.attached');
  }
  function dispose() {
    if (stopped) return;
    stopped = true;
    record('owner.dispose');
    companion?.disconnect();
    disposeFont();
    mutations?.disconnect();
  }
  for (const event of ['resize', 'pagehide'])
    window.addEventListener(event, () => {
      record(event, { width: window.innerWidth, height: window.innerHeight });
    });
  window.addEventListener('error', (event) => {
    record('error', { message: event.message });
    // Error-only late transport; no console/network I/O in metric callbacks/pagehide.
    // This does not preventDefault, disconnect, reschedule or filter the native event.
    platform.navigator.sendBeacon('/error', JSON.stringify({ mode, events }));
  });
  Object.defineProperty(window, 'fontRepro', {
    value: Object.freeze({
      recover,
      dispose,
      metric(size) {
        detector.contentDocument.documentElement.style.fontSize = String(size) + 'px';
      },
      startMutations() {
        mutations = new MutationObserver((records) => {
          mutationCount += records.length;
        });
        mutations.observe(root, { attributes: true, attributeFilter: ['style'] });
      },
      snapshot() {
        return { events, fontCallbacks, lastMetric, spanSize, mutationCount, stopped };
      },
    }),
  });
}

// Public Playwright runner/matcher, isolated from Angular's application harness.
// A native page.screenshot is used only to create the expected PNG; the subsequent
// matcher performs an ordinary comparison (no update mode, masking or tolerance).
async function matcherCapture(origin) {
  const testModule = import.meta.resolve('@playwright/test');
  const spec = `import {test,expect} from ${JSON.stringify(testModule)};
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';
test('native watcher capture and close', async ({page},testInfo) => {
 const errors=[];
 page.on('pageerror', error=>errors.push(error.message));
 const states=[];
 try {
  await page.goto(${JSON.stringify(origin)});
  await page.waitForFunction(()=>globalThis.fontRepro?.snapshot().lastMetric!==null);
  for (const name of ['unavailable','recovered']) {
   if(name==='recovered') {
    await page.evaluate(()=>globalThis.fontRepro.recover());
    await page.waitForFunction(()=>globalThis.fontRepro.snapshot().spanSize!==null);
    if (${JSON.stringify(capture === 'viewport-cycle')}) {
     // Explicitly reproduce the observed top-level viewport input, not an app fix.
     await page.evaluate(()=>globalThis.fontRepro.startMutations());
     const before=await page.evaluate(()=>globalThis.fontRepro.snapshot());
     await page.setViewportSize({width:1,height:1});
     await page.waitForFunction(count=>globalThis.fontRepro.snapshot().fontCallbacks>count,before.fontCallbacks);
     const compact=await page.evaluate(()=>globalThis.fontRepro.snapshot());
     states.push({name:'explicit-1x1',snapshot:compact});
     await page.setViewportSize({width:1440,height:900});
     await page.waitForFunction(count=>globalThis.fontRepro.snapshot().fontCallbacks>count,compact.fontCallbacks);
     const restored=await page.evaluate(()=>globalThis.fontRepro.snapshot());
     states.push({name:'explicit-restore',snapshot:restored});
     expect(compact.lastMetric).toBe(before.lastMetric);
     expect(restored.lastMetric).toBe(before.lastMetric);
     expect(restored.spanSize).toEqual(before.spanSize);
     expect(restored.mutationCount).toBe(0);
    }
   }
   const options={fullPage:true,animations:'disabled',caret:'hide'};
   await page.screenshot({...options,path:testInfo.snapshotPath(name+'.png')});
   await expect(page).toHaveScreenshot(name+'.png',{...options,maxDiffPixels:0});
   states.push({name,snapshot:await page.evaluate(()=>globalThis.fontRepro.snapshot())});
  }
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 } finally {
  await writeFile(${JSON.stringify(join(output, 'matcher-lifecycle.json'))},JSON.stringify({states,errors},null,2));
  await page.close();
 }
 expect(errors).toEqual([]);
});`;
  await writeFile(join(output, 'native.spec.mjs'), spec);
  await writeFile(
    join(output, 'playwright.config.mjs'),
    `export default {testDir:${JSON.stringify(output)},testMatch:'native.spec.mjs',workers:1,retries:0,timeout:30000,globalTimeout:60000,updateSnapshots:'none',reporter:'list',snapshotPathTemplate:'{testDir}/expected/{arg}{ext}',outputDir:${JSON.stringify(join(output, 'test-results'))},use:{browserName:'chromium',viewport:{width:1440,height:900},reducedMotion:'reduce'}};`,
  );
  await new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        fileURLToPath(import.meta.resolve('@playwright/test/cli')),
        'test',
        '--config',
        join(output, 'playwright.config.mjs'),
      ],
      { stdio: 'inherit' },
    );
    const interrupt = () => child.kill('SIGINT');
    const terminate = () => child.kill('SIGTERM');
    process.once('SIGINT', interrupt);
    process.once('SIGTERM', terminate);
    const timeout = setTimeout(() => child.kill('SIGKILL'), 75000);
    const cleanup = () => {
      clearTimeout(timeout);
      process.removeListener('SIGINT', interrupt);
      process.removeListener('SIGTERM', terminate);
    };
    child.once('error', (error) => {
      cleanup();
      reject(error);
    });
    child.once('exit', (code, signal) => {
      cleanup();
      if (code === 0) resolve();
      else reject(new Error('Native matcher runner failed: ' + String(code ?? signal)));
    });
  });
  return JSON.parse(await readFile(join(output, 'matcher-lifecycle.json'), 'utf8'));
}

const html =
  '<!doctype html><html><head><meta charset="utf-8"><title>Native font watcher isolation</title>' +
  '<style>html{font-size:calc(17px + var(--t-font-offset,0)*1px)}body{margin:1rem;font-family:system-ui}main{min-block-size:120vh}label{display:grid}textarea{font:inherit;line-height:calc(28/17)}#mirror{display:inline-block;inline-size:1px;white-space:pre;line-height:calc(28/17)}</style>' +
  '</head><body><main><h1>Native font watcher isolation</h1><p id="error">Conversation unavailable</p><div id="slot"></div></main>' +
  '<script type="module">import { tuiFontSizeWatcher } from "/watcher.mjs";(' +
  client.toString() +
  ')(tuiFontSizeWatcher,globalThis,' +
  JSON.stringify(variant) +
  ');</script></body></html>';
const errors = [];
const server = createServer((request, response) => {
  if (request.method === 'POST' && request.url === '/error') {
    let body = '';
    request.on('data', (chunk) => {
      body += chunk;
    });
    request.on('end', () => {
      try {
        errors.push(JSON.parse(body));
      } catch {
        errors.push({ error: 'invalid diagnostic beacon' });
      }
      response.writeHead(204).end();
    });
    return;
  }
  if (request.url === '/watcher.mjs') {
    response
      .writeHead(200, { 'Content-Type': 'application/javascript', 'Cache-Control': 'no-store' })
      .end(source);
    return;
  }
  if (request.url === '/favicon.ico') {
    response.writeHead(204).end();
    return;
  }
  response.writeHead(200, { 'Content-Type': 'text/html', 'Cache-Control': 'no-store' }).end(html);
});
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const address = server.address();
assert.ok(address !== null && typeof address !== 'string');
const origin = 'http://127.0.0.1:' + address.port;
let browser;
const result = { variant, capture, provenance, output, semantics: null, lifecycle: null };
let failure = null;
try {
  browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: 'reduce',
  });
  const metricPage = await context.newPage();
  metricPage.on('pageerror', (error) =>
    errors.push({ phase: 'semantics', message: error.message }),
  );
  await metricPage.goto(origin);
  await metricPage.waitForFunction(() => globalThis.fontRepro?.snapshot().lastMetric !== null);
  await metricPage.evaluate(() => {
    globalThis.fontRepro.recover();
    globalThis.fontRepro.startMutations();
  });
  await metricPage.waitForFunction(() => globalThis.fontRepro.snapshot().spanSize !== null);
  const before = await metricPage.evaluate(() => globalThis.fontRepro.snapshot());
  await metricPage.setViewportSize({ width: 1280, height: 900 });
  await metricPage.waitForFunction(
    (count) =>
      globalThis.fontRepro.snapshot().events.filter((event) => event.event === 'font.callback')
        .length > count,
    before.fontCallbacks,
  );
  const same = await metricPage.evaluate(() => globalThis.fontRepro.snapshot());
  assert.equal(same.lastMetric, before.lastMetric);
  assert.deepEqual(same.spanSize, before.spanSize);
  await metricPage.evaluate(() => globalThis.fontRepro.metric(28));
  await metricPage.waitForFunction(
    () =>
      globalThis.fontRepro.snapshot().lastMetric === 28 &&
      globalThis.getComputedStyle(globalThis.document.documentElement).fontSize === '28px',
  );
  await metricPage.screenshot({
    path: join(output, 'metric-28.png'),
    fullPage: true,
    animations: 'disabled',
  });
  await metricPage.evaluate(() => globalThis.fontRepro.metric(17));
  await metricPage.waitForFunction(
    () =>
      globalThis.fontRepro.snapshot().lastMetric === 17 &&
      globalThis.getComputedStyle(globalThis.document.documentElement).fontSize === '17px',
  );
  await metricPage.screenshot({
    path: join(output, 'metric-17.png'),
    fullPage: true,
    animations: 'disabled',
  });
  result.semantics = {
    before,
    same,
    restored: await metricPage.evaluate(() => globalThis.fontRepro.snapshot()),
  };
  await metricPage.evaluate(() => globalThis.fontRepro.dispose());
  await metricPage.close();

  if (capture !== 'direct') {
    await context.close();
    await browser.close();
    result.lifecycle = await matcherCapture(origin);
  } else {
    const page = await context.newPage();
    page.on('pageerror', (error) =>
      errors.push({ phase: 'capture-close', message: error.message }),
    );
    await page.goto(origin);
    await page.waitForFunction(() => globalThis.fontRepro?.snapshot().lastMetric !== null);
    await page.screenshot({
      path: join(output, 'error-state.png'),
      fullPage: true,
      animations: 'disabled',
      caret: 'hide',
    });
    await page.evaluate(() => globalThis.fontRepro.recover());
    await page.waitForFunction(() => globalThis.fontRepro.snapshot().spanSize !== null);
    await page.screenshot({
      path: join(output, 'recovered-state.png'),
      fullPage: true,
      animations: 'disabled',
      caret: 'hide',
    });
    result.lifecycle = await page.evaluate(() => globalThis.fontRepro.snapshot());
    if (variant === 'owner-cleanup') await page.evaluate(() => globalThis.fontRepro.dispose());
    // Match the existing owned-test render drain; never an application scheduling fix.
    await page.evaluate(
      () =>
        new Promise((resolve) =>
          globalThis.requestAnimationFrame(() => globalThis.requestAnimationFrame(resolve)),
        ),
    );
    await page.close();
    await context.close();
  }
} catch (error) {
  failure = error;
} finally {
  if (browser?.isConnected()) await browser.close();
  await new Promise((resolve, reject) =>
    server.close((error) => (error === undefined ? resolve() : reject(error))),
  );
  await writeFile(
    join(output, 'result.json'),
    JSON.stringify({ ...result, errors, failure: failure?.message ?? null }, null, 2),
  );
}
process.stdout.write(
  JSON.stringify({
    output,
    variant,
    sourceHash: fingerprint,
    observedErrors: errors.length,
    failure: failure?.message ?? null,
  }) + '\n',
);
if (failure !== null) throw failure;
if (errors.length > 0) process.exitCode = 1;
