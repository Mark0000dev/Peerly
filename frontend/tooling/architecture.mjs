import { existsSync, statSync } from 'node:fs';
import path from 'node:path';

export default {
  rules: {
    boundaries: {
      meta: {
        type: 'problem',
        schema: [],
        messages: {
          crossing:
            'Screen internals must not import another screen. Extract at the nearest common parent when there are three consumers.',
          unsupported: 'Use public Taiga APIs and the Angular defaults; this bypass is forbidden.',
        },
      },
      create(context) {
        const filename = context.filename.replaceAll('\\', '/');
        const screen = filename.match(/\/screens\/([^/]+)\//)?.[1];
        function checkImport(node, source) {
          if (typeof source !== 'string') return;
          const target = path.resolve(path.dirname(filename), source).replaceAll('\\', '/');
          const targetFile = [target, `${target}.ts`].find(
            (candidate) => existsSync(candidate) && statSync(candidate).isFile(),
          );
          const importedScreen =
            targetFile === undefined
              ? target.match(/\/screens\/([^/]+)(?:\/|$)/)?.[1]
              : targetFile.match(/\/screens\/([^/]+)\//)?.[1];
          if (screen && importedScreen && screen !== importedScreen)
            context.report({ node, messageId: 'crossing' });
        }
        return {
          ImportDeclaration(node) {
            checkImport(node, node.source.value);
          },
          ImportExpression(node) {
            checkImport(node, node.source.value);
          },
          MemberExpression(node) {
            if (
              [
                'bypassSecurityTrustHtml',
                'bypassSecurityTrustStyle',
                'bypassSecurityTrustScript',
                'bypassSecurityTrustUrl',
                'bypassSecurityTrustResourceUrl',
              ].includes(node.property.name) ||
              (node.object.name === 'ViewEncapsulation' && node.property.name === 'None') ||
              (node.object.name === 'ChangeDetectionStrategy' &&
                ['Default', 'Eager'].includes(node.property.name))
            )
              context.report({ node, messageId: 'unsupported' });
          },
        };
      },
    },
  },
};
