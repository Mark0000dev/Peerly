import assert from 'node:assert/strict';
import { test } from 'node:test';
import { runFullstackMatrix } from './fullstack-matrix.mjs';

test('isolates browser source and support quotas, preserves each artifact set and the first failed runtime result', async () => {
  const calls = [];
  const result = await runFullstackMatrix([], {
    run: async (command, args, options) => {
      calls.push({ command, args, options });
      return calls.length === 1 ? 1 : 0;
    },
  });
  assert.equal(result, 1);
  assert.equal(calls.length, 6);
  assert.ok(calls[0].args.includes('--grep-invert'));
  assert.ok(calls[1].args.includes('--grep'));
  const identities = calls.map((call) => {
    const index = call.args.indexOf('--project');
    assert.notEqual(index, -1);
    return [call.args[index + 1], call.args.includes('--grep') ? 'authenticated' : 'ordinary'];
  });
  assert.deepEqual(identities, [
    ['chromium-mobile', 'ordinary'],
    ['chromium-mobile', 'authenticated'],
    ['webkit-mobile', 'ordinary'],
    ['webkit-mobile', 'authenticated'],
    ['chromium-desktop', 'ordinary'],
    ['chromium-desktop', 'authenticated'],
  ]);
  assert.equal(new Set(calls.map((call) => call.options.env.PLAYWRIGHT_HTML_OUTPUT_DIR)).size, 6);
  assert.equal(new Set(calls.map((call) => call.args.at(-1))).size, 6);
  for (const call of calls) {
    assert.ok(call.args.includes('\\[support-cohort-b\\]'));
    assert.equal(call.options.env.STUDYMATE_FULLSTACK, '1');
    assert.equal(call.command, process.execPath);
  }
  assert.notEqual(
    calls[0].options.env.PLAYWRIGHT_HTML_OUTPUT_DIR,
    calls[1].options.env.PLAYWRIGHT_HTML_OUTPUT_DIR,
  );
  assert.notEqual(calls[0].args.at(-1), calls[1].args.at(-1));
});

for (const code of [124, 130, 143]) {
  test(`does not start another fixture after timeout or cancellation ${code}`, async () => {
    let calls = 0;
    const result = await runFullstackMatrix([], {
      run: async () => {
        calls += 1;
        return code;
      },
    });
    assert.equal(result, code);
    assert.equal(calls, 1);
  });
}

test('rejects overriding cohort filters instead of silently omitting or double-counting cases', async () => {
  await assert.rejects(runFullstackMatrix(['--grep', 'some-case']), /owns cohort filters/);
});

test('rejects a project override instead of reusing one source quota across engines', async () => {
  await assert.rejects(runFullstackMatrix(['--project=webkit-mobile']), /owns cohort filters/);
  await assert.rejects(runFullstackMatrix(['--project', 'webkit-mobile']), /owns cohort filters/);
});
