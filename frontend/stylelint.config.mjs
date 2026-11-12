import themePolicy from './tooling/theme-policy.mjs';

export default {
  plugins: [themePolicy],
  extends: ['stylelint-config-standard-less'],
  overrides: [
    {
      files: ['src/theme.less'],
      rules: { 'color-no-hex': null },
    },
  ],
  reportNeedlessDisables: true,
  reportInvalidScopeDisables: true,
  rules: {
    'peerly/theme-contract': true,
    'declaration-no-important': true,
    'color-no-hex': true,
    'selector-max-id': 0,
    'selector-class-pattern': '^(?!t-)[a-z][a-z0-9]*(?:-[a-z0-9]+)*$',
    'selector-pseudo-element-disallowed-list': ['ng-deep'],
    'selector-disallowed-list': [/\/deep\//],
    'unit-disallowed-list': ['px'],
    'comment-pattern': '^(?!.*stylelint-disable).*$',
  },
};
