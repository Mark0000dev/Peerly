# Mandatory frontend rules

## Architecture and colocation

- Angular standalone components, strict TypeScript, zoneless runtime. Angular 22 defaults to OnPush: do not opt into Eager or add redundant OnPush declarations.
- Organize by screens: `src/app/screens/<screen>/`. Keep templates, styles, queries, mutations, types, forms, helpers, and meaningful tests beside their consumers. No global `components/`, `services/`, `models/`, or `utils/` dumping grounds.
- WET first. One or two consumers keep their own code. At the third actual consumer, extract the common responsibility to the nearest common parent. Do not create speculative abstractions or generic repositories, facades, base components, or wrappers around Taiga UI.
- Screens must not import another screen's internals. Share through their nearest common parent. No barrel exports, circular imports, or deep imports into package internals.
- Root composition is for routing and application providers. Lazy-load screens. Create directories only when they contain real code.

## State: one owner

- Server state lives exclusively in TanStack Query. Never mirror query data, loading/error state, or mutation state in writable signals, Subjects, services, stores, or localStorage.
- A native image-resource handle may retain the source Blob identity and its owned ObjectURL solely for replacing/releasing that native resource. This is client resource state, not a second business/query projection. Never render DTO fields from it or put ObjectURLs in the query cache; clear it with its actor/view lifetime and test retirement after the relevant DOM update/removal.
- Define typed query keys and query options near their screen. Include every request parameter in the key. Invalidate the relevant keys after writes; optimistic updates require explicit rollback and a useful user benefit.
- Use Angular HttpClient for HTTP. A query function must consume TanStack's AbortSignal (unsubscribe the HTTP request when cancelled); use an adapter only when a real query needs one. Do not introduce another transport/cache.
- URL owns shareable filters, sorting, paging, and selected resource IDs. Forms own editable drafts. Use typed Angular forms supported by the installed Taiga UI controls; do not mirror form values into signals.
- Only unavoidable ephemeral UI state may use private writable signals. Expose read-only signals when sharing. Derived state uses `computed`, never an `effect` that copies state. Effects are for external side effects with cleanup.
- No NgRx, NGXS, Akita, global application stores, or speculative persistence. Do not persist credentials or sensitive student data in browser storage.
- Use query defaults deliberately. Retry only transient failures; never blindly retry validation/authentication errors or non-idempotent mutations. Design loading, empty, failure, and retry states with each screen.

## Types and immutability

- All fields are readonly by default, including injected dependencies, signals, inputs, outputs, and view queries. Use readonly properties in DTOs and `readonly T[]` / `ReadonlyArray<T>` / `ReadonlyMap` / `ReadonlySet` for data collections.
- Never mutate inputs, query cache data, DTOs, arrays, objects, or function parameters. Use new values (`map`, `filter`, spread, `toSorted`). `readonly` is shallow: nested models must be readonly too.
- `const` by default. No `any`, unsafe casts, non-null assertions, `@ts-ignore`, definite assignment assertions, or double casts. Narrow `unknown` at boundaries. Do not invent defaults that hide malformed responses.
- No floating promises, implicit truthiness of nullable/non-boolean values, unused symbols, or unchecked indexing. Handle errors explicitly without swallowing them.
- Keep APIs small. Template-only members are `protected`; implementation details are `private`. Use `inject()` and signal-based `input`, `output`, and view queries. Use `input.required` for required inputs.
- Use type inference for obvious locals and explicit types for exported contracts. Use `import type` for type-only imports.

## Components and templates

- Small components with one responsibility. Keep simple templates inline; colocate substantial templates/styles in matching files.
- Use built-in `@if`, `@for`, `@switch`; track lists by stable domain identity. No index tracking for reorderable data. Avoid nontrivial calculations in templates.
- Use class/style bindings rather than ngClass/ngStyle. Use component `host` instead of HostBinding/HostListener. Do not manipulate the DOM directly or bypass Angular sanitization.
- No nested subscriptions. Prefer query signals and async pipe; use `takeUntilDestroyed` when an imperative subscription is truly necessary.
- Use NgOptimizedImage for static raster images. Do not introduce SSR, service workers, or offline caches without an actual requirement.

## Design and mobile

- Taiga UI is the only component/design system. Do not add Ionic UI, Material, Tailwind, CSS resets, or handwritten replacements for existing Taiga controls. Capacitor supplies Android/iOS integration.
- Follow supplied mockups closely through documented Taiga tokens, CSS custom properties, appearances, sizes, providers, and public component APIs. Document a design constraint when the public API cannot express a detail; prefer a clean supported approximation.
- Never use `::ng-deep`, `/deep/`, `!important`, ViewEncapsulation.None, internal `.t-*` selectors, DOM-dependent overrides, arbitrary pixel offsets, or transforms to force mockup alignment.
- When mockups arrive, place public Taiga CSS custom property overrides in `src/theme.less`; this is the only file allowed literal theme colors and may declare public `--tui-*` plus the exact approved semantic tokens in `tooling/theme-policy.mjs`. Only the four documented `sp-relevance`, `sp-shared`, `sp-offer`, `sp-subject` public appearances may assign color/background there, using approved tokens; arbitrary selectors, variables and control overrides remain forbidden. Do not create it before real theme values are needed.
- Component styles may describe layout, spacing, responsive behavior, and safe areas. Visual styling of controls uses Taiga's documented theme mechanisms only. No custom colors, fonts, shadows, borders, or radii to reproduce controls.
- Mobile first: flexible layout, logical properties, rem units, safe-area insets, usable touch targets, no horizontal overflow. Expand with min-width media queries only when content requires it.
- Semantic HTML, labels, keyboard interaction, visible focus, contrast, reduced motion, and accessible status/error feedback are required. Never disable viewport scaling. Check real mobile viewport sizes when screens are implemented.

## Quality gates and changes

- Run `npm run check` before handing off frontend work. It checks formatting, typed TS/template ESLint, styles, unused files/exports/dependencies, type checking, unit tests with coverage, screenshot integration, and production compilation. Zero warnings.
- Template-only Angular compiler checks must use `ngc --noEmit`. Never emit sibling JavaScript into `src`; the tooling gate rejects compiler-emitted JavaScript/maps beside their TypeScript source. Production output belongs in the configured build directory.
- Do not weaken checks, add blanket ignores, eslint/stylelint disable comments, Knip exclusions, or bypass hooks to make a change pass. Fix the cause. Any necessary exception must be narrow, justified, and reviewed.
- Test meaningful behavior and regressions. Do not write tests that mirror implementation. Unit and screenshot integration coverage are mandatory; follow the testing contract below. Accessibility and native device checks supplement static checks.
- Version-specific TanStack note: with pinned `5.106.1`, first use of `injectQuery` retained Angular namespace compatibility code and increased the measured initial bundle from499.91kB to679.02kB. Use the established public `QueryObserver` pattern here; reevaluate a newer adapter only with measured build evidence. Do not bypass public exports, fork the dependency or relax the budget to work around this.
- Pin dependencies exactly and commit the lockfile when commits are authorized. TanStack Angular is experimental: upgrades require reading release notes and running checks.
- Local Git hooks are convenience checks; CI is the enforceable review gate. Branch protection must require the frontend check before merging when remote administration becomes available. Hooks can be bypassed; do not claim they provide an absolute guarantee.

## Primary references

Consult documentation for the installed versions; user requirements above take priority.

- https://angular.dev/style-guide
- https://github.com/angular/angular/blob/main/packages/core/resources/best-practices.md
- https://angular.dev/guide/signals
- https://angular.dev/best-practices/security
- https://angular.dev/best-practices/a11y
- https://taiga-ui.dev/getting-started
- https://tanstack.com/query/latest/docs/framework/angular/installation
- https://capacitorjs.com/docs/getting-started

## Mandatory testing contract

- User requirement: unit tests and integration tests are mandatory for frontend features. Every implemented integration scenario must include screenshot assertions. This supersedes the earlier recommendation against snapshots for trivial layout.
- Unit tests use Vitest via Angular CLI, running real headless Chromium for reliable Angular/Taiga platform behavior. Cover meaningful component/form/query/helper behavior, validation and failure paths without using screenshot comparisons as unit assertions.
- Maintain at least 95% unit coverage for statements, branches, functions and lines across application code, including files without tests. No broad coverage exclusions; only test files are excluded. Coverage never substitutes for scenario completeness.
- Integration tests use Playwright and live Angular screens. Import `test` and `expect` from `testing/visual`; direct runtime imports from `@playwright/test` are forbidden in screen scenarios. The auto fixture fails passing scenarios without at least one named `checkpoint(...)` screenshot assertion.
- Colocate unit `*.spec.ts`, browser `*.visual.spec.ts` and reference PNGs under their owning screen/capability. Unit runner excludes visual specs; application build excludes all specs. Keep the shared browser gate in `testing/visual.ts` as test infrastructure.
- Each new screen needs an explicit scenario matrix mapped to specification/handoff IDs: success, loading, empty, validation, server/network failure, retry, authorization/session expiry, stale data and relevant relationship states. Mark irrelevant cases with a reason. Every implemented scenario/state in that matrix requires behavioral assertions and a screenshot checkpoint. Cover intermediate overlays and states, not only the final screen.
- Browser integration may use deterministic HTTP boundary fixtures to reproduce loading/failure/race states; do not mock components, query hooks, routing or state transitions under test. Full-stack integration additionally verifies actual API contracts when product endpoints exist. Do not call fixture-only visual tests full-stack coverage.
- Required visual projects are mobile Chromium, mobile WebKit and desktop Chromium. Also check 320px reflow, 200% text, reduced motion, keyboard/focus, safe areas and open keyboard behavior as the feature makes them relevant. Desktop screenshots alone do not satisfy mobile coverage.
- Use semantic role/label locators, observable assertions and request interception. No fixed sleeps, `.only`, skipped tests, swallowed failures, increased diff tolerance, masks hiding meaningful content, or snapshots of loading states used as final success baselines.
- Keep application fonts local; do not rely on Google Fonts or another external network request for rendering.
- Fixed locale/timezone, deterministic data/time, stable image/font loading and disabled decorative animation keep screenshots repeatable. Assert the state before capturing. Every passing integration test must have a screenshot; additional failure screenshots are diagnostic only.
- Baselines are tracked, colocated PNG files. Missing baselines fail normal runs (`updateSnapshots: none`). Generate/update only with `npm run test:integration:update`, inspect every changed image and explain the design change. CI must never update baselines automatically. Pin browser/test versions and use the documented Linux environment.
- Explicit owner-approved capture exception: WebKit TuiPreview OPEN/ZOOM may use the public pinned Playwright screencast helper in `testing/webkit-preview-frame.mts`. Require three independently started fresh full-viewport frames with exact-byte equality and strict JPEG baseline comparison (zero pixel threshold/difference); preserve ordinary PNG artifacts, all runtime diagnostics and scoped trace DOM/source data. Other states and engines retain standard PNG. No masks, cropping, scaling, private protocol or app/dependency styling patches. See `WEBKIT-PREVIEW-CAPTURE.md`; this does not resolve the separate ResizeObserver gate.
- `npm run check` includes units, coverage, screenshot integration and production build. CI uploads diffs, HTML report, traces and coverage. Do not delete failing scenarios or lower thresholds to pass.
- Current shell coverage is not product-scenario coverage. As screens are implemented, update their scenario matrix and tests in the same change; unimplemented specification scenarios remain outstanding.

Testing references:

- https://angular.dev/guide/testing
- https://playwright.dev/docs/test-snapshots
- https://playwright.dev/docs/test-fixtures
- https://playwright.dev/docs/best-practices

## Current system interaction design

Use the proposed contracts in `../docs/architecture.md` and `../docs/api.md`. The server owns domain decisions and returns typed capabilities/reason codes; Angular owns presentation, forms, navigation and recovery. Generate readonly DTOs from actual OpenAPI schemas when product endpoints exist. A single change stream invalidates query keys; no mirrored stream store and no automatic resend of social actions after reconnect. Native streaming/authentication needs a verified platform adapter; no credentials in URLs. Privileged data inspection reads full business records through authorized operator endpoints, not through log contents.

## Bounded dependency source correction

Parent explicitly authorised the reviewed version-pinned font-watcher source bugfix mechanism in
`patches/@taiga-ui+font-watcher+0.6.0.patch`; provenance/hash/removal requirements are in README.
This is limited to the library-owned iframe border sizing in all distributed implementations.
Keep public font scaling enabled, no DOM/global CSS overrides or diagnostic suppression. Any
observer feedback correction needs separate causal evidence, scheduling/teardown regression tests
and a minimal source patch; this exception does not relax theme or application-code rules.

## Bundle budget decision —8 November2026

- Initial bundle maximumWarning and maximumError are both525kB, explicitly approved
  by the user after measured504.04kB and supported native-form dependency attribution.
  Component-style maximumWarning/maximumError remain4kB. Preserve zero-warning
  failure behavior; never increase automatically as features grow.
- Any further budget increase requires measured import-graph evidence and explicit
  user approval. Do not trade public APIs, accessibility, form semantics or clean
  state ownership for a few bytes. No undocumented attributes or broad framework
  migration solely to satisfy a numeric budget. See BUNDLE-BUDGET.md for evidence.
