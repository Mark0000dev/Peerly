import stylelint from 'stylelint';

const ruleName = 'peerly/theme-contract';
const messages = stylelint.utils.ruleMessages(ruleName, {
  rejected: (property) => `Unsupported theme declaration: ${property}`,
});
const semanticTokens = Object.freeze([
  '--sp-surface-indigo',
  '--sp-text-indigo',
  '--sp-surface-teal',
  '--sp-text-teal',
  '--sp-surface-sand',
  '--sp-text-sand',
  '--sp-surface-sakura',
  '--sp-text-sakura',
  '--sp-ease',
  '--sp-washi',
  '--sp-sakura',
  '--sp-fuji',
  '--sp-asagi',
]);
const appearances = new Set(['sp-relevance', 'sp-shared', 'sp-offer', 'sp-subject']);
const token = /^var\(--(?:tui-[a-z0-9-]+|sp-(?:surface|text)-(?:indigo|teal|sand|sakura))\)$/;

export default stylelint.createPlugin(ruleName, (enabled) => (root, result) => {
  if (!enabled) return;
  const isTheme = (root.source?.input.file ?? '').replaceAll('\\', '/').endsWith('/src/theme.less');
  root.walkDecls((declaration) => {
    const property = declaration.prop;
    const selector = declaration.parent?.selector ?? '';
    const appearance = /^\[tuiAppearance\]\[data-appearance=['"]([a-z-]+)['"]\]$/.exec(
      selector,
    )?.[1];
    const themeToken =
      isTheme &&
      selector === ':root' &&
      (property.startsWith('--tui-') || semanticTokens.includes(property));
    const appearanceProperty =
      isTheme &&
      appearances.has(appearance) &&
      ['background', 'color'].includes(property) &&
      token.test(declaration.value);
    if (
      (isTheme && !themeToken && !appearanceProperty) ||
      (!isTheme && property.startsWith('--'))
    ) {
      stylelint.utils.report({
        ruleName,
        result,
        node: declaration,
        message: messages.rejected(property),
      });
    }
  });
});
