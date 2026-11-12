import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { URL } from 'node:url';
import { runInNewContext } from 'node:vm';
import { verifyWatcher } from './font-watcher-patch.mjs';

const root = new URL('../node_modules/@taiga-ui/font-watcher/', import.meta.url);
const hashes = JSON.parse(
  readFileSync(new URL('./font-watcher-hashes.json', import.meta.url), 'utf8'),
);
const contents = Object.fromEntries(
  Object.keys(hashes).map((name) => [name, readFileSync(new URL(name, root), 'utf8')]),
);

test('patch gate fails closed on drift, missing entrypoints and version changes', () => {
  verifyWatcher('0.6.0', contents, hashes, 'after');
  assert.throws(() => verifyWatcher('0.7.0', contents, hashes, 'after'));
  assert.throws(() => verifyWatcher('0.6.0', contents, {}, 'after'));
  assert.throws(() =>
    verifyWatcher('0.6.0', contents, { ...hashes, '../unexpected': {} }, 'before'),
  );
  assert.throws(() =>
    verifyWatcher('0.6.0', { ...contents, 'index.esm.js': 'unreviewed' }, hashes, 'before'),
  );
  assert.throws(() => verifyWatcher('0.6.0', {}, hashes, 'after'));
  const original = {
    ...contents,
    'index.esm.js': contents['index.esm.js'].replace("    border: '0',\n", ''),
  };
  verifyWatcher('0.6.0', original, hashes, 'before');
  assert.throws(() => verifyWatcher('0.6.0', original, hashes, 'after'));
});

for (const name of ['index.esm.js', 'index.cjs.js']) {
  test(`${name}: border correction preserves font measurements, resize and teardown`, () => {
    let observed;
    let disconnected = false;
    let removed = false;
    let callback;
    const listeners = new Map();
    const values = [];
    const body = { offsetHeight: 17, style: {}, insertAdjacentText() {} };
    const frame = {
      style: {},
      contentDocument: {
        body,
        head: { insertAdjacentHTML() {} },
        documentElement: { style: { setProperty() {} } },
      },
      ownerDocument: {
        body: { append() {} },
        defaultView: {
          innerWidth: 320,
          outerWidth: 320,
          devicePixelRatio: 1,
          addEventListener(name, fn) {
            listeners.set(name, fn);
          },
          removeEventListener(name) {
            listeners.delete(name);
          },
        },
      },
      remove() {
        removed = true;
      },
    };
    class ResizeObserver {
      constructor(fn) {
        callback = fn;
      }
      observe(target) {
        observed = target;
      }
      disconnect() {
        disconnected = true;
      }
    }
    const context = { exports: {}, ResizeObserver };
    const source = contents[name].replace(
      'export { tuiFontSizeWatcher };',
      'globalThis.watch = tuiFontSizeWatcher;',
    );
    runInNewContext(source, context);
    const watch = name === 'index.esm.js' ? context.watch : context.exports.tuiFontSizeWatcher;
    const cleanup = watch((size) => values.push(size), frame);
    assert.equal(frame.style.border, '0');
    assert.equal(frame.width, '320');
    assert.equal(observed, body);
    callback();
    body.offsetHeight = 28;
    callback();
    assert.deepEqual(values, [17, 28]);
    frame.ownerDocument.defaultView.innerWidth = 400;
    frame.ownerDocument.defaultView.outerWidth = 400;
    listeners.get('resize')();
    assert.equal(frame.width, '400');
    cleanup();
    assert.equal(disconnected, true);
    assert.equal(removed, true);
    assert.equal(listeners.size, 0);
  });
}
