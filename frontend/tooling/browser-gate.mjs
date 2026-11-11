import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { constants } from 'node:os';
import { createInterface } from 'node:readline';
import { pathToFileURL } from 'node:url';
import { setTimeout, clearTimeout } from 'node:timers';
import { stripVTControlCharacters } from 'node:util';

// Observe the complete CLI lifetime, including diagnostics after a browser target detaches.
export function clientRuntimeFailure(line) {
  const text = stripVTControlCharacters(line);
  return (
    text.includes('(client)') &&
    (text.includes('[Unhandled') ||
      text.includes('[console.error]') ||
      text.includes('[peerly owned runtime context]'))
  );
}

export function runBrowserGate(
  command,
  args,
  {
    timeoutMs = 600_000,
    killGraceMs = 15_000,
    signal,
    stdout = process.stdout,
    stderr = process.stderr,
    env = process.env,
  } = {},
) {
  const cancellation = () => (signal?.reason?.exitCode === 143 ? 143 : 130);
  if (signal?.aborted) return Promise.resolve(cancellation());
  return new Promise((resolve) => {
    const grouped = process.platform !== 'win32';
    const child = spawn(command, args, {
      stdio: ['inherit', 'pipe', 'pipe'],
      detached: grouped,
      env,
    });
    let diagnostic = false;
    let stopped = null;
    let finished = false;
    let escalation;
    const readers = [child.stdout, child.stderr].map((stream, index) => {
      stream.pipe(index === 0 ? stdout : stderr, { end: false });
      const reader = createInterface({ input: stream, crlfDelay: Infinity });
      reader.on('line', (line) => {
        diagnostic ||= clientRuntimeFailure(line);
      });
      return reader;
    });
    const terminate = (kind) => {
      try {
        if (grouped && child.pid !== undefined) process.kill(-child.pid, kind);
        else child.kill(kind);
      } catch (error) {
        if (!(error instanceof Error && 'code' in error && error.code === 'ESRCH')) throw error;
      }
    };
    const stop = (code, kind) => {
      if (finished || stopped !== null) return;
      stopped = code;
      terminate(kind);
      escalation = setTimeout(() => terminate('SIGKILL'), killGraceMs);
    };
    const abort = () =>
      stop(cancellation(), signal?.reason?.signal === 'SIGINT' ? 'SIGINT' : 'SIGTERM');
    const timer = setTimeout(() => stop(124, 'SIGTERM'), timeoutMs);
    const complete = (code) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      clearTimeout(escalation);
      signal?.removeEventListener('abort', abort);
      for (const reader of readers) reader.close();
      if (diagnostic)
        stderr.write('Browser runtime diagnostic detected; see the unchanged runner output.\n');
      resolve(stopped ?? (code === 0 && diagnostic ? 1 : code));
    };
    signal?.addEventListener('abort', abort, { once: true });
    // Cancellation can arrive between the initial check and listener registration.
    if (signal?.aborted) abort();
    child.once('error', () => {
      stderr.write('Browser test runner could not start.\n');
      complete(1);
    });
    child.once('close', (code, exitSignal) => {
      complete(code ?? 128 + (constants.signals[exitSignal] ?? 0));
    });
  });
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const controller = new globalThis.AbortController();
  const interrupt = () => controller.abort({ signal: 'SIGINT', exitCode: 130 });
  const terminate = () => controller.abort({ signal: 'SIGTERM', exitCode: 143 });
  process.on('SIGINT', interrupt);
  process.on('SIGTERM', terminate);
  try {
    process.exitCode = await runBrowserGate(
      process.execPath,
      [createRequire(import.meta.url).resolve('@playwright/test/cli'), ...process.argv.slice(2)],
      { signal: controller.signal },
    );
  } finally {
    process.off('SIGINT', interrupt);
    process.off('SIGTERM', terminate);
  }
}
