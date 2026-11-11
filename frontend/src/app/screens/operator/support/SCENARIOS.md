# Operator support — M03 / M06 / MX

Scope: actual head54 support inbox, explicit private case/history and status-only CAS.
No replies, verification, assignment, moderation, totals or invented student rights.
All rows/DTOs remain in the inherited TanStack cache; status draft and immutable
manual-replay intent are local. Root guards and authority bridge belong to Halley.

Lead acceptance complete for source, behavior and reviewed layouts: whole frontend
1552 tests /93 files, CLI0; coverage statements95.77%, branches95.02%, functions96.79%,
lines98.15%. Static checks/build CLI0; production initial bundle514.10kB. HTTP39 normal
screenshot comparisons passed, with process CLI1 retaining the known ResizeObserver
diagnostic. Affected MX3 normal passed CLI0. RealPG24 normal passed CLI0 with72 reviewed
references; fixture cleanup reported no errors. No separate strict-all-runtime-green
claim, no ResizeObserver suppression. All runners were coordinated by Halley.

| Requirement                                           | Controlled HTTP / unit definitions                                                     | Real PostgreSQL definition                                                                 |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| M03 metadata only, explicit lazy private reads        | metadata/detail/history; no markup; close                                              | metadata53 with no private fan-out, audit linkage, literal source                          |
| M03 explicit filters, validation, independent cursors | anon/account conflict, topic, keyset reset; contract time/UUID validation              | genuine inbox50+3, unique IDs, received order                                              |
| M06 anonymous / linked / retained source              | null/empty details, literal text and actual account link                               | anonymous null details and deleted-account link                                            |
| M06 empty / missing                                   | empty inbox;404                                                                        | empty fixture and genuine404                                                               |
| M06 retained versions/provenance                      | history50;422 first-page reset; nullable provenance unit                               | genuine53 revisions50+3, anchor53, null v1 provenance                                      |
| M06 local loading / unavailable / retry               | held503/release/retry; history503/404/422 unit                                         | local failure is controlled HTTP only; no backend outage injection                         |
| M06 explicit status confirmation/CAS                  | exact body/key/CSRF; confirmation; dirty draft                                         | real PUT53→54, exact receipt DOM and persisted revision                                    |
| M06 version conflict / explicit reconciliation        | 409, fresh version/new key, dialog                                                     | genuine competing PUT54 then original409; reconciled PUT55/new key                         |
| M06 uncertain write / same-intent replay              | 503, same key/body; matching current not proof; original receipt vs newer canonical    | real committed PUT response aborted, current GET not proof, exact same-key replay receipt  |
| M06 authority retirement                              | settled PUT403 cancels sibling reads;401; late actor result unit                       | revoked PUT403 and explicit restored grant; owner replacement resets signed history cursor |
| M06 navigation intent lifetime                        | real Account records route + Keep/Leave; real browser Back same component + Keep/Leave | HTTP boundary isolates the unknown-outcome guard deterministically                         |
| MX320/200%, reduced motion, labels and keyboard       | real viewport/text scaling, geometry and Enter confirmation                            | shared production DOM; responsive acceptance is controlled HTTP                            |

Every browser test has named screenshot assertions. Fifty-row regions keep all50
DOM rows and source assertions; start/end real viewport checkpoints avoid WebKit's
32767px image limit. No masks, hidden rows, increased diff tolerance or clock patch
in PostgreSQL tests. Controlled HTTP fixtures alone use a deterministic fixed clock.

Real PUT receipts have native current timestamps. Lead approved full raw runtime
artifacts plus exact DOM checks of actual ID/status/version/timestamps, paired with
strict screenshot comparison of the COMPLETE stable semantic status-choice form.
The real-PG reconciliation dialog retains a full raw runtime artifact and exact
public heading/message/both-button assertions. Its public dialog bounds include
underlying native current timestamps, observed during the24-pass PG capture;
therefore that PG overlay artifact is not a deterministic comparison. This same
scenario retains COMPLETE status-choice form comparisons before/after reconciliation.
Controlled HTTP still compares the whole deterministic dialog. No masks/private
selectors/fake clocks were introduced. Newly written revision is asserted
against the real receipt/source and retained in a raw viewport artifact. Full
controlled-HTTP receipts/history remain ordinary deterministic full-layout goldens.
Runtime artifacts are evidence, not claimed deterministic full-page baselines.

Fixture scopes: support / support-references / support-status / support-unknown /
support-conflict / support-empty / support-revocation / support-replacement;
all cohorts, current grants, synthetic sessions and audit hooks are lead-owned.
No production role provisioning or external student/provider access in definitions.

Acceptance evidence remains under
`/tmp/peerly-operator-support-acceptance-20261110/`, including preserved original
failures and reviewed raw native-time artifacts. Root Router Back history correction
was lead-owned; actual source guard behavior is covered in HTTP navigation scenarios.
No additional source changes or verification followed this documentation closure.
