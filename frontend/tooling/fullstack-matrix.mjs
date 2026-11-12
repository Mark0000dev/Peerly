import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { runBrowserGate } from './browser-gate.mjs';

// Each Playwright invocation starts and tears down its own real migrated fixture.
// The two genuine support cohorts must not share the five/source/day budget.
export async function runFullstackMatrix(args, { signal, run = runBrowserGate } = {}) {
  if (args.some((arg) => /^--grep(?:-invert)?(?:=|$)|^-g(?:=|$)|^--project(?:=|$)/.test(arg)))
    throw new Error(
      'Full matrix owns cohort filters/projects; use browser-gate for a scoped diagnostic.',
    );
  const cli = createRequire(import.meta.url).resolve('@playwright/test/cli');
  let result = 0;
  // Each real browser project needs its own source-admission budget. Production
  // login/source and support quotas stay unchanged; only isolated fixture schemas
  // separate independent cases. No source-IP spoof, clocks or retained-data reset.
  const projects = ['chromium-mobile', 'webkit-mobile', 'chromium-desktop'];
  const cohorts = projects.flatMap((project) => [
    { name: `core-and-anonymous-${project}`, project, filter: '--grep-invert' },
    { name: `authenticated-support-${project}`, project, filter: '--grep' },
  ]);
  for (const cohort of cohorts) {
    const code = await run(
      process.execPath,
      [
        cli,
        'test',
        ...args,
        '--project',
        cohort.project,
        cohort.filter,
        '\\[support-cohort-b\\]',
        '--output',
        `test-results/${cohort.name}`,
      ],
      {
        signal,
        env: {
          ...process.env,
          STUDYMATE_FULLSTACK: '1',
          PLAYWRIGHT_HTML_OUTPUT_DIR: `playwright-report/${cohort.name}`,
        },
      },
    );
    if (code === 124 || code === 130 || code === 143) return code;
    if (result === 0 && code !== 0) result = code;
  }
  return result;
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const controller = new globalThis.AbortController();
  const interrupt = () => controller.abort({ signal: 'SIGINT', exitCode: 130 });
  const terminate = () => controller.abort({ signal: 'SIGTERM', exitCode: 143 });
  process.on('SIGINT', interrupt);
  process.on('SIGTERM', terminate);
  try {
    process.exitCode = await runFullstackMatrix(process.argv.slice(2), {
      signal: controller.signal,
    });
  } finally {
    process.off('SIGINT', interrupt);
    process.off('SIGTERM', terminate);
  }
}
