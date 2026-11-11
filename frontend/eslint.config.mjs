import js from '@eslint/js';
import angular from 'angular-eslint';
import functional from 'eslint-plugin-functional';
import playwright from 'eslint-plugin-playwright';
import importX from 'eslint-plugin-import-x';
import { createTypeScriptImportResolver } from 'eslint-import-resolver-typescript';
import tseslint from 'typescript-eslint';
import architecture from './tooling/architecture.mjs';

export default tseslint.config(
  {
    ignores: [
      'dist/**',
      '.angular/**',
      'node_modules/**',
      'android/**',
      'ios/**',
      'coverage/**',
      'playwright-report/**',
      'test-results/**',
    ],
  },
  {
    files: ['src/**/*.ts', 'testing/**/*.{ts,mts}', 'playwright.config.ts'],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.strictTypeChecked,
      ...tseslint.configs.stylisticTypeChecked,
      ...angular.configs.tsRecommended,
    ],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    processor: angular.processInlineTemplates,
    plugins: { functional, 'import-x': importX, architecture },
    settings: { 'import-x/resolver-next': [createTypeScriptImportResolver()] },
    linterOptions: { noInlineConfig: true, reportUnusedDisableDirectives: 'error' },
    rules: {
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],
      '@typescript-eslint/explicit-member-accessibility': ['error', { accessibility: 'explicit' }],
      '@typescript-eslint/strict-boolean-expressions': [
        'error',
        { allowString: false, allowNumber: false, allowNullableObject: false },
      ],
      '@typescript-eslint/prefer-readonly': 'error',
      '@typescript-eslint/no-extraneous-class': ['error', { allowWithDecorator: true }],
      '@typescript-eslint/no-non-null-assertion': 'error',
      '@typescript-eslint/no-import-type-side-effects': 'error',
      '@angular-eslint/prefer-inject': 'error',
      '@angular-eslint/prefer-signals': 'error',
      '@angular-eslint/prefer-output-readonly': 'error',
      '@angular-eslint/prefer-on-push-component-change-detection': 'off',
      'functional/immutable-data': 'error',
      'functional/prefer-readonly-type': 'error',
      'functional/prefer-immutable-types': [
        'error',
        {
          parameters: { enforcement: 'ReadonlyShallow' },
          returnTypes: { enforcement: 'None' },
          variables: { enforcement: 'None' },
        },
      ],
      'import-x/no-cycle': 'error',
      'import-x/no-duplicates': 'error',
      'architecture/boundaries': 'error',
      'no-console': 'error',
      'no-param-reassign': ['error', { props: true }],
      'no-restricted-syntax': [
        'error',
        {
          selector: 'PropertyDefinition[readonly!=true]',
          message: 'Fields must be readonly; update signal values immutably.',
        },
        {
          selector: 'ExportAllDeclaration',
          message: 'Import from the owning file; barrel exports are forbidden.',
        },
        { selector: 'TSEnumDeclaration', message: 'Use a literal union instead of an enum.' },
      ],
      'no-restricted-imports': [
        'error',
        { patterns: ['@ionic/*', '@angular/material/*', '@ngrx/*', '@ngxs/*'] },
      ],
    },
  },
  {
    files: ['src/**/*.visual.spec.ts'],
    plugins: { playwright },
    rules: {
      ...playwright.configs['flat/recommended'].rules,
      'playwright/no-skipped-test': 'error',
      'playwright/no-focused-test': 'error',
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: '@playwright/test',
              allowTypeImports: true,
              message:
                'Import test/expect from testing/visual so every scenario requires screenshots.',
            },
          ],
        },
      ],
    },
  },
  {
    files: ['src/**/*.html'],
    extends: [...angular.configs.templateRecommended, ...angular.configs.templateAccessibility],
    linterOptions: { noInlineConfig: true, reportUnusedDisableDirectives: 'error' },
    rules: {
      '@angular-eslint/template/prefer-control-flow': 'error',
    },
  },
  {
    files: ['*.mjs', 'tooling/**/*.mjs'],
    extends: [js.configs.recommended],
    languageOptions: { globals: { process: 'readonly' } },
  },
);
