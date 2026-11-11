import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ESLint } from 'eslint';
import stylelint from 'stylelint';

const eslint = new ESLint();
const filePath = 'src/app/screens/home/home.ts';

for (const [name, code, rule] of [
  ['mutable fields', 'export class Example { public value = 1; }', 'no-restricted-syntax'],
  [
    'mutable DTOs',
    'export interface Example { value: string; }',
    'functional/prefer-readonly-type',
  ],
  [
    'array mutation',
    'export const values: number[] = []; values.push(1);',
    'functional/immutable-data',
  ],
  ['unsafe any', 'export const value: any = 1;', '@typescript-eslint/no-explicit-any'],
  ['screen imports', "import '../requests/request';", 'architecture/boundaries'],
  [
    'dynamic screen imports',
    "export const load = () => import('../requests/request');",
    'architecture/boundaries',
  ],
  [
    'sanitizer bypass',
    'export const sanitize = (service: Readonly<{ bypassSecurityTrustHtml: (value: string) => string }>) => service.bypassSecurityTrustHtml("html");',
    'architecture/boundaries',
  ],
]) {
  test(`ESLint rejects ${name}`, async () => {
    const [result] = await eslint.lintText(code, { filePath });
    assert.ok(
      result.messages.some((message) => message.ruleId === rule),
      JSON.stringify(result.messages),
    );
  });
}

test('readonly signals remain usable in templates', async () => {
  const results = await eslint.lintText(
    `
    import { Component, signal } from '@angular/core';
    @Component({ selector: 'app-example', template: '<p>{{ name() }}</p>' })
    export class Example { protected readonly name = signal('APU'); }
  `,
    { filePath },
  );
  assert.equal(
    results.reduce((count, result) => count + result.errorCount + result.warningCount, 0),
    0,
    JSON.stringify(results),
  );
});

for (const [name, code, rule] of [
  ['important', ':host { display: block !important; }', 'declaration-no-important'],
  [
    'deep overrides',
    ':host ::ng-deep { display: block; }',
    'selector-pseudo-element-disallowed-list',
  ],
  ['internal Taiga classes', '.t-wrapper { display: block; }', 'selector-class-pattern'],
  ['custom hex colors', ':host { color: #fff; }', 'color-no-hex'],
  ['pixel offsets', ':host { margin: 3px; }', 'unit-disallowed-list'],
]) {
  test(`Stylelint rejects ${name}`, async () => {
    const result = await stylelint.lint({ code, codeFilename: 'src/probe.less' });
    assert.ok(
      result.results.flatMap((entry) => entry.warnings).some((warning) => warning.rule === rule),
    );
  });
}

test('public Taiga theme tokens accept design colors', async () => {
  const result = await stylelint.lint({
    code: ':root { --tui-background-base: #fff; }',
    codeFilename: 'src/theme.less',
  });
  assert.equal(
    result.errored,
    false,
    JSON.stringify(result.results.flatMap((entry) => entry.warnings)),
  );
});

test('theme file cannot bypass tokens with control overrides', async () => {
  const result = await stylelint.lint({
    code: ':root { color: #fff; }',
    codeFilename: 'src/theme.less',
  });
  assert.ok(
    result.results
      .flatMap((entry) => entry.warnings)
      .some((warning) => warning.rule === 'peerly/theme-contract'),
  );
});

for (const [name, code] of [
  ['unapproved semantic token', ':root { --sp-unreviewed: #fff; }'],
  [
    'unreviewed appearance',
    "[tuiAppearance][data-appearance='invented'] { color: var(--tui-text-primary); }",
  ],
  ['literal appearance colour', "[tuiAppearance][data-appearance='sp-relevance'] { color: #fff; }"],
  ['theme layout override', ':root { padding: 1rem; }'],
  ['theme control selector', 'button { --tui-height-m: 9rem; }'],
]) {
  test(`theme contract rejects ${name}`, async () => {
    const result = await stylelint.lint({ code, codeFilename: 'src/theme.less' });
    assert.ok(
      result.results
        .flatMap((entry) => entry.warnings)
        .some((warning) => warning.rule === 'peerly/theme-contract'),
    );
  });
}

test('approved semantic tokens and public appearances work only in theme', async () => {
  const code = `:root {
  --sp-surface-teal: #e2f3f0;
  --sp-text-teal: #155e57;
}

[tuiAppearance][data-appearance='sp-relevance'] {
  background: var(--sp-surface-teal);
  color: var(--sp-text-teal);
}`;
  const allowed = await stylelint.lint({ code, codeFilename: 'src/theme.less' });
  assert.equal(
    allowed.errored,
    false,
    JSON.stringify(allowed.results.flatMap((entry) => entry.warnings)),
  );
  const forbidden = await stylelint.lint({ code, codeFilename: 'src/probe.less' });
  assert.ok(
    forbidden.results
      .flatMap((entry) => entry.warnings)
      .some((warning) => warning.rule === 'peerly/theme-contract'),
  );
});

test('three screen consumers may import a shared file at their common parent', async () => {
  const results = await eslint.lintText(
    "import {Brand} from '../brand'; export const example = Brand;",
    { filePath },
  );
  assert.equal(
    results
      .flatMap((result) => result.messages)
      .some((message) => message.ruleId === 'architecture/boundaries'),
    false,
  );
});

test('screen folder imports cannot bypass boundaries by omitting a filename', async () => {
  const results = await eslint.lintText(
    "import {Other} from '../other-screen'; export const example = Other;",
    { filePath },
  );
  assert.ok(
    results
      .flatMap((result) => result.messages)
      .some((message) => message.ruleId === 'architecture/boundaries'),
  );
});
