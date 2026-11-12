# Pinned font-watcher correction

`@taiga-ui/font-watcher` is overridden to0.6.0. The tracked patch adds only
`border: '0'` to its own iframe styles in the distributed ESM and CommonJS sources.
Native borders otherwise enlarge its viewport-width iframe and cause narrow-screen
overflow. Public font scaling stays enabled; this is not an application theme override.

Upstream source: https://github.com/taiga-family/utils/blob/main/projects/font-watcher/index.ts

Exact original/patched SHA-256 values for all five distributed entrypoints are in
`../tooling/font-watcher-hashes.json`; wrappers/types remain unchanged. Pinned
patch-package8.0.1 applies the patch during npm ci. The before/after verifier rejects
wrong versions, source hashes and failed patches; npm run check also verifies the
installed result. Do not modify node_modules manually or download install-time replacements.

Remove the patch, override, verifier and regression fixtures together after an upstream
upgrade fixes border sizing and passes narrow/enlarged-text, real font scaling and
teardown regressions. This border-only patch does not resolve native ResizeObserver
diagnostics. Broader corrections need independent causal evidence; never suppress errors
or disable scaling to obtain a green result.
