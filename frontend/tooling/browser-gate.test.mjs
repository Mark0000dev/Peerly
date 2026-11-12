import assert from 'node:assert/strict';
import { Writable } from 'node:stream';
import { test } from 'node:test';
import { clientRuntimeFailure, runBrowserGate } from './browser-gate.mjs';

function output(onWrite = () => {}) {
  let text = '';
  const stream = new Writable({
    write(chunk, _encoding, done) {
      text += chunk.toString();
      onWrite(text);
      done();
    },
  });
  return { stream, text: () => text };
}

for (const marker of [
  '[Unhandled error] Error: ResizeObserver loop completed with undelivered notifications.',
  '[console.error] Unexpected application failure',
  '[Unhandled rejection] Uncaught promise',
  '[console.warn] [peerly owned runtime context] chromium-desktop:fixture ResizeObserver loop completed with undelivered notifications.',
]) {
  test(`late forwarded ${marker} fails a successful runner without hiding output`, async () => {
    const stdout = output();
    const stderr = output();
    const text = `[WebServer] (client) ${marker}`;
    const child = `process.stdout.write(${JSON.stringify(text.slice(0, 20))});setImmediate(()=>process.stdout.write(${JSON.stringify(text.slice(20))}));`;
    const code = await runBrowserGate(process.execPath, ['-e', child], {
      stdout: stdout.stream,
      stderr: stderr.stream,
    });
    assert.equal(code, 1);
    assert.equal(stdout.text(), text);
    assert.match(stderr.text(), /Browser runtime diagnostic detected/);
  });
}

test('ordinary output and browser HTTP resource diagnostics are preserved', async () => {
  const stdout = output();
  const stderr = output();
  const text =
    'Failed to load resource: 401\n[WebServer] (client) [console.warn] An ordinary warning\n18 passed\n';
  const code = await runBrowserGate(
    process.execPath,
    ['-e', `process.stdout.write(${JSON.stringify(text)})`],
    { stdout: stdout.stream, stderr: stderr.stream },
  );
  assert.equal(code, 0);
  assert.equal(stdout.text(), text);
  assert.equal(stderr.text(), '');
  assert.equal(
    clientRuntimeFailure('ordinary message about [console.error] without a client event'),
    false,
  );
});

test('runner failure exit code is retained', async () => {
  assert.equal(
    await runBrowserGate(process.execPath, ['-e', 'process.exit(7)'], {
      stdout: output().stream,
      stderr: output().stream,
    }),
    7,
  );
});

test('cancellation terminates the owned process and keeps cancellation status', async () => {
  const controller = new globalThis.AbortController();
  const stdout = output((text) => {
    if (text.includes('READY')) controller.abort();
  });
  const child = `process.on('SIGTERM',()=>{process.stdout.write('STOPPED');process.exit(0)});process.stdout.write('READY');setInterval(()=>{},1000);`;
  assert.equal(
    await runBrowserGate(process.execPath, ['-e', child], {
      signal: controller.signal,
      stdout: stdout.stream,
      stderr: output().stream,
    }),
    130,
  );
  assert.match(stdout.text(), /STOPPED/);
});

test('timeout escalates when an owned child ignores graceful termination', async () => {
  const stdout = output();
  const child = `process.on('SIGTERM',()=>{});process.stdout.write('READY');setInterval(()=>{},1000);`;
  assert.equal(
    await runBrowserGate(process.execPath, ['-e', child], {
      timeoutMs: 1000,
      killGraceMs: 50,
      stdout: stdout.stream,
      stderr: output().stream,
    }),
    124,
  );
  assert.match(stdout.text(), /READY/);
});

test('already cancelled and failed spawn do not report success', async () => {
  const controller = new globalThis.AbortController();
  controller.abort({ signal: 'SIGTERM', exitCode: 143 });
  assert.equal(
    await runBrowserGate('missing-peerly-test-runner', [], { signal: controller.signal }),
    143,
  );
  assert.equal(
    await runBrowserGate('missing-peerly-test-runner', [], {
      stdout: output().stream,
      stderr: output().stream,
    }),
    1,
  );
});
