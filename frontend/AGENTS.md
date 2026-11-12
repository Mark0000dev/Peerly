# Mandatory frontend rules

## Architecture

- Use standalone Angular22 components, strict TypeScript and the zoneless runtime.
  Angular22 defaults to OnPush; do not opt into Eager or add redundant declarations.
- Colocate templates, styles, queries, mutations, forms, helpers and tests under
  `src/app/screens/<screen>/`. Avoid global component/service/model/util dumping grounds.
- WET first: one or two consumers keep local code. At the third actual consumer,
  extract the common responsibility to their nearest common parent. No speculative
  facades, stores, generic repositories, base components or replacement Taiga controls.
- Screens must not import sibling-screen internals. No barrel exports, cycles or
  package-private deep imports. Root composition owns routing/providers; lazy-load screens.
- The server owns business decisions and typed capabilities. Generate deeply readonly
  DTOs from the actual enabled OpenAPI export; never invent endpoints or response fields.

## State and transport

- TanStack Query exclusively owns server data, loading/errors and mutation outcomes.
  Do not mirror these in signals, Subjects, services or persistent browser storage.
- URLs own shareable filters, paging and selected IDs. Typed forms own editable drafts.
  Necessary ephemeral UI state uses private writable signals and readonly exposures;
  derive values without effects that copy state. Effects require cleanup.
- Native image handles may retain Blob/source identity and owned ObjectURLs only to
  replace/release resources. Do not render DTO fields from this tracking or cache URLs
  as server state. Test release after DOM retirement and actor/view changes.
- Use Angular HttpClient and shared transport. Query functions consume their AbortSignal.
  Include all request parameters and actor ownership in keys; invalidate relevant reads
  after writes. Use the established public QueryObserver pattern for the pinned adapter.
- No automatic social-mutation retries. Preserve explicit CSRF/idempotency and original
  intent during uncertain recovery. Never resend actions merely on reconnect.
- Clear private data and drafts on logout/account replacement. Do not persist credentials,
  private messages, media or signed upload fields in browser storage. Native unsent
  files cannot be restored or silently sent after reload.
- A change stream invalidates query keys; it is not a mirrored event store. Keep private
  content out of ordinary telemetry. Privileged inspection uses authorized data APIs.

## Types and components

- Fields, injected dependencies, inputs/outputs, queries and exposed collections are
  readonly. Nested models must also be readonly. Update values immutably.
- Prefer const. No any, unsafe/double casts, non-null/definite-assignment assertions,
  ts-ignore, unchecked indexing or defaults hiding malformed data. Narrow unknown.
- No floating promises, nullable truthiness, swallowed failures or unused symbols.
  Template-only members are protected; implementation details are private. Use inject,
  signal inputs/outputs/view queries and required inputs where applicable.
- Components have one responsibility. Colocate substantial HTML/Less with matching TS.
  Use built-in @if/@for/@switch and stable domain tracking identities.
- Use class/style bindings and component host metadata. Do not manipulate application
  DOM directly or bypass sanitization. No nested subscriptions; imperative subscriptions
  require a real consumer and teardown, normally takeUntilDestroyed.
- Do not add SSR, service workers, offline caches or another HTTP/cache layer speculatively.

## Design and accessibility

- Taiga UI is the sole component/design system; Capacitor supplies native integration.
  Do not add Ionic UI, Material, Tailwind, resets or handmade substitutes for existing controls.
- Match approved designs through documented public Taiga tokens, appearances, sizes,
  providers and APIs. Use normal responsive layout for owned content. Explain supported
  approximations rather than forcing pixel alignment.
- No ng-deep, deep selectors, important, ViewEncapsulation.None, internal .t-* selectors,
  DOM-dependent overrides, arbitrary pixel offsets or alignment transforms.
- Only `src/theme.less` defines literal theme colors and approved public --tui-* and
  enumerated semantic tokens/appearances from `tooling/theme-policy.mjs`. Controls use
  public theme mechanisms, not custom fonts/colors/shadows/borders/radii.
- Mobile first: logical properties, rem spacing, safe areas, comfortable touch targets,
  scrollable content and no horizontal overflow or obscured focused controls.
- Require semantic labels, keyboard support, visible focus, contrast, reduced-motion
  support and honest status/error messages. Never disable viewport/font scaling.
- Keep local fonts. Curated artwork requires provenance; do not copy design-export
  runtime or styles into application code. Regression goldens do not prove design fidelity.

## Quality and tests

- Run npm run check for complete acceptance. Zero warnings. Do not lower thresholds,
  add blanket ignores/disables/Knip exclusions, bypass hooks or hide failed checks.
  When execution is incomplete, report exact failures and unrun gates rather than green.
- Pin dependencies and lockfile. Adapter upgrades require public documentation, actual
  compatibility tests and measured build evidence; no forks/private attributes for byte savings.
- Initial warning/error budgets are both550kB; component styles are both4kB. Further
  increases require explicit owner approval and measured evidence, never automatic growth.
- Use ngc --noEmit for template checks. Never emit sibling JS/maps into src; production
  output belongs under the build directory.
- Unit tests run Angular/Vitest in real Chromium and cover behavior/validation/failures.
  Maintain95% statements, branches, functions and lines, including untested application files.
  Do not add implementation-mirroring tests or broad coverage exclusions.
- Integration scenarios run real screens through testing/visual imports and require
  BOTH behavioral assertions and named screenshot checkpoints. Cover success, loading,
  empty, validation, network/server error, retry, authority expiry, stale and relationship states.
- HTTP fixtures reproduce boundaries, not components/query/router behavior. Real-stack
  tests verify actual FastAPI/PostgreSQL composition with isolated schemas and controlled
  external services; do not call mock-only tests full-stack/provider acceptance.
- Required projects: mobile Chromium, mobile WebKit and desktop Chromium; include320px,
  200% text, keyboard/focus, reduced motion and relevant media/keyboard behavior.
- Use role/label locators and observable assertions. No fixed sleeps, only/skips,
  swallowed runtime failures, masks, increased tolerances or loading-as-success references.
- Review every changed baseline; normal runs fail missing references. CI never updates
  them. Keep browser versions, locale/timezone, source data and local fonts reproducible.
- Runtime JS/rejection/console guards remain active, including ResizeObserver. A known
  internal-preview issue is not a test pass. Do not change unrelated dependencies or
  conduct blind broad reruns to hide intermittent failures.
- The narrow WebKit TuiPreview OPEN/ZOOM capture exception uses the public pinned
  screencast helper: three fresh independent full-viewport frames must match exact bytes,
  dimensions and strict JPEG references. Keep ordinary PNGs, source/DOM assertions and
  diagnostics. Other engines/states use normal PNG; no masks/crops/private protocol.
- Refer to testing/README.md and patches/README.md for stable test/dependency mechanisms.

Primary references: https://angular.dev/style-guide, https://angular.dev/guide/signals,
https://angular.dev/best-practices/a11y, https://taiga-ui.dev,
https://tanstack.com/query/latest/docs/framework/angular/installation,
https://capacitorjs.com/docs.
