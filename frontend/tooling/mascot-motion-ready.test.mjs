import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { setImmediate } from 'node:timers/promises';
import { setTimeout, clearTimeout } from 'node:timers';
import { URL } from 'node:url';
import vm from 'node:vm';
import ts from 'typescript';

const sourcePath =
  process.env['MASCOT_READY_SOURCE'] ?? new URL('../testing/mascot-motion.mjs', import.meta.url);
const source = await readFile(sourcePath, 'utf8');
const ast = ts.createSourceFile(
  'mascot-motion.mjs',
  source,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.JS,
);
const declaration = ast.statements.find(
  (node) => ts.isFunctionDeclaration(node) && node.name?.text === 'ready',
);
if (declaration === undefined) throw new Error('Native motion readiness consumer missing');

function fixture(decode, timers = { setTimeout, clearTimeout }) {
  class Image {
    decode() {
      return decode();
    }
  }
  const image = new Image();
  const ready = vm.runInNewContext(`(${declaration.getText(ast)})`, {
    HTMLImageElement: Image,
    ...timers,
    document: { fonts: { status: 'loaded' }, getAnimations: () => [] },
    requestAnimationFrame: (callback) => callback(0),
  });
  const page = {
    waitForFunction: async (predicate) => {
      assert.equal(predicate(), true);
    },
    evaluate: async (callback) => callback(),
    locator: (selector) => {
      assert.equal(selector, 'peerly-mascot img');
      return { evaluateAll: async (callback) => callback([image]) };
    },
  };
  return () => ready(page, 'peerly-mascot img');
}

test('a ready heading/font cannot advance capture before its SVG decode finishes', async () => {
  let release;
  const decoding = new Promise((resolve) => {
    release = resolve;
  });
  const run = fixture(() => decoding);
  let complete = false;
  const ready = run().then(() => {
    complete = true;
  });
  try {
    await setImmediate();
    assert.equal(complete, false, 'Still-loading image must block geometry and motion capture');
  } finally {
    release();
    await ready;
  }
  assert.equal(complete, true);
});

test('a broken image decode remains a real failure instead of being reported as ready', async () => {
  const failure = new Error('Controlled image decode failure');
  const run = fixture(() => Promise.reject(failure));
  await assert.rejects(run, (error) => error === failure);
});

test('a stalled SVG decode fails at the existing10s budget rather than hanging capture', async () => {
  let expire;
  let cleared = false;
  const run = fixture(() => new Promise(() => {}), {
    setTimeout: (callback, delay) => {
      assert.equal(delay, 10_000);
      expire = callback;
      return 7;
    },
    clearTimeout: (id) => {
      assert.equal(id, 7);
      cleared = true;
    },
  });
  const pending = run();
  await setImmediate();
  assert.equal(typeof expire, 'function');
  expire();
  await assert.rejects(pending, /Mascot SVG decode timed out/);
  assert.equal(cleared, true);
});
