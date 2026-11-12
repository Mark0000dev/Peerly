## Current deliberate cap — 12 November 2026

Owner-authorized, parent-confirmed initial warning and error caps are now both
550kB; component-style caps remain4kB. Zero-warning failure behavior is unchanged.
The historical525kB decision and measurements below remain evidence, not the
current threshold. The integrated production build at05:17:44Z measured524.85kB
with actual public/shared navigation and native Taiga AppBar/TabBar consumers,
leaving only150bytes under the previous cap. The new bounded25.15kB (~4.8%)
headroom permits required supported design components without stripping behavior,
private API shortcuts or topology experiments. It is not an automatic growth rule;
further increases still require measured evidence and explicit owner authorization.
The next coherent production build will record its actual measured result in the
frontend progress ledger and sibling fidelity integration-cohort logs.

# Production bundle budget

On 8 November 2026 the owner explicitly approved a bounded increase of the initial
production budget from 500 kB to 525 kB. Both `maximumWarning` and `maximumError`
are 525 kB; component styles retain both 4 kB thresholds. Budget warnings remain
failures. A future increase requires measured evidence and explicit owner approval.

## Measurements

Angular uses decimal kB here. Initial bytes include the main entry point, its
static JavaScript import closure, and global styles, excluding lazy chunks.

| Source                           | Initial bytes | Result with approved 525,000-byte limit |
| -------------------------------- | ------------: | --------------------------------------- |
| Accepted FE06.1 immutable source |       504,035 | Pass                                    |
| Current FE06.2 source            |       506,633 | Pass; 18,367 bytes remaining            |

Both production CLI builds exited 0 without budget warnings and prerendered one
public route. The baseline copy changes only the approved budget configuration;
its original 135-file production source snapshot remains unchanged. These builds
use the existing pinned installation; they do not establish clean-install or
whole-application acceptance.

Current stats SHA256:
`44f651ff3cb568254ae26720bff8fcf4cd4e4d3fb06a924e1a521adc0655e9b5`.
Baseline stats SHA256:
`16af9220e3d9a2cbeada4637d784571b8940c51da64c1de2a593c32197e0fe59`.
Raw CLI logs: `/tmp/peerly-budget-525-production-build.log` and
`/tmp/peerly-budget-525-fe061-baseline-build.log`. Baseline source manifest SHA256:
`bf133ef629216d0182a7791293bb19a8200a0e5d75a9b448067d77f4faebfe34`.

## Attribution and rejected alternatives

Import-graph isolation identified shared Angular forms/common code used by the
operator's legitimate native form controls, including SelectControlValueAccessor
and NgTemplateOutlet. Diagnostic Architect comparisons attributed approximately
2,105 bytes to forms and 1,574 bytes to common. Those diagnostic builds use a
different build context and are attribution evidence, not exact production totals.
Public NativeSelect import narrowing remains a valid cleanup, but did not resolve
the original budget overrun.

One Signal Forms prototype was evaluated only in an immutable temporary copy.
Its production build reached 504.69 kB and failed the old 500 kB limit: larger than
the 504.04 kB baseline. It was rejected without adoption; accessibility and form
semantic equivalence were not established. No framework/forms migration,
undocumented `ngNoCva` attribute, private API, or feature removal was adopted.
Further byte-shaving topology experiments are stopped.

The independent aggregate ResizeObserver runtime blocker remains open. Passing
this production budget does not resolve it or establish a passing full gate.

## FE06.3 production checkpoint

After mounting the actual lazy reports consumer, production CLI0 in6.035s with no
budget warnings and one prerendered public route. Initial506651bytes,18349bytes
headroom; component style4kB threshold unchanged. Raw
`/tmp/peerly-reports-production-build1.log`, exact stats SHA256
`dd7d0a3bd8d779c3304474403f15b3aae056965818b5630b1c12d872374ccd77`.
This checkpoint follows48 passing scoped operator units, but browser/real-PG
acceptance of FE06.3 is still pending; global RO remains open.

## FE06.4 M05 production checkpoint

The actual lazy text inspector and shared operator authority extraction retain
initial506651bytes (18349bytes headroom). Production CLI0 in4.607s, no warnings,
one prerendered public route; component styles remain4kB. Raw
`/tmp/peerly-operator-conversation-production-build1.log`; stats SHA256
`9fe137fb336bf9311fc1cc29991e98c56a94818f6b881f3496623aeb37d9fed3`.
61 scoped units pass, HTTP33 behavioral cases pass with the independent nativeRO
runtime failure still preserved. New images/real-PG acceptance remain in progress.

## Student P05/C03 source checkpoint —9 November2026

Production build `/tmp/peerly-student-p05-c03-build1.log` exited0 without warnings,
with P05 lazy routes and C03 shared composition/public Files control mounted.
CLI rounded initial total:513.26kB, below the unchanged525kB warning/error limits;
component styles remain4kB. This is a pinned-install production build, not a
clean-install, browser, native-platform or whole-application acceptance claim.
No byte-shaving framework workaround or further budget increase was introduced.

9 November2026 student source checkpoint after P05 and minimal knowledge-area
copy: production build CLI0, initial513.26kB, unchanged525kB warning/error and4kB
component-style bounds, zero warnings. Public root prerendered1 static route.
Raw `/tmp/peerly-student-areas-build2.log`, SHA-256
`0af161a186a5b95ce75ca67ce27472fc8935a340d3aa5bbbc2073163fa590c05`.
This validates the production compilation/budget only; it does not imply clean
install, all screenshot comparisons, native devices or live providers passed.

The subsequent C03 same-actor draft/confirmed-receipt lifetime correction also
passes production compilation:513.26kB initial, zero warnings, same limits.
`/tmp/peerly-c03-lifetime-build3.log`, SHA-256
`6c5c15ce685d07548cedbf5903d60a42b3e6ff97d308fd50d6e0ba3843edf010`.
Whole unit checkpoint is1293/1293 with unchanged95 thresholds; browser/real-provider
acceptance remains separate.
