# C03 chat image acceptance matrix

Actual API source: `frontend/CHAT-IMAGES-HANDOFF.md`, tested88 image (runtime head50 bootstrap, unchanged actual88)
contracts. UI design source: approved C03 Image/Lifecycle boards and repository
review corrections. Parent owns caption form, message composition, routing,
session and shared fixtures. This slice owns native attachment selection,
preparation recovery, explicit image Send, retained participant JPEG and report.

| Behavior                                                                      | Unit evidence                 | HTTP scenario                                                         | Real PostgreSQL source                                               |
| ----------------------------------------------------------------------------- | ----------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Local choose/replace/remove; caption retained; no upload before Send          | sender/contract               | local picker                                                          | pipeline selected-unsent                                             |
| JPEG/PNG, exact10MB; invalid selected file cannot silently send caption       | contract/sender               | invalid type/size                                                     | no large-file/provider claim                                         |
| Actual bytes SHA and immutable retry operation/caption                        | contract/send/sender/transfer | access failure and explicit retry                                     | queued expected_source matches actual PNG                            |
| Start, private signed POST, finalize, real processing, confirmation           | send/transfer                 | full pipeline                                                         | actual controlled TLS transfer + real worker/codec + message/history |
| READY owner preview, distinct grants, no reload auto-send                     | preparation/sender/send       | owner collection/reload                                               | recovery READY remains unsent until explicit Send                    |
| Missing original, different bytes, bounded-list eviction                      | sender/send                   | outstanding additional wire scenarios                                 | outstanding real uploading-resume/hash mismatch                      |
| Cancel-won versus already-confirmed result                                    | sender/send                   | additional wire races outstanding                                     | queued cancel-won PASS; send-won race outstanding                    |
| Participant normalized JPEG, native URL lifetime/decode/auth retirement       | message-image/preparation     | peer viewer + browser Back                                            | retained JPEG magic/dimensions and peer owner-display404             |
| Public Preview zoom/Escape/focus,320px/200%, reduced motion                   | message-image                 | Preview/reflow/Back                                                   | participant JPEG tested; overlay verified in HTTP3                   |
| Peer-only actual message-image context and report receipt                     | report/contract               | Other-required + actual context                                       | actual peer context/source IDs and report receipt                    |
| Unknown report retry identity, known rejection restart, current auth boundary | report                        | additional failure wire scenarios outstanding                         | outstanding failure/race scenarios                                   |
| Current401/403/actor/route retirement, no late stored output                  | sender/send/image/report      | browser Back covers route; additional auth wire scenarios outstanding | outstanding private-session races                                    |

Every authored browser case has named screenshot checkpoints and behavior checks.

Current scoped acceptance:

- Owned units80/80 PASS; unchanged95 threshold, coverage statements95.79,
  branches95.26, functions98.70, lines99.22. Production unchanged since unit24.
- HTTP9 cases ×3 projects,20 checkpoints/project: ordinary PASS in separate
  bounded12+3+12 runs, not a single full27 run. Active60 references reviewed
  (58PNG+2JPEG), hash stable after each ordinary run.
- RealPG5 cases ×3 projects: coherent ordinary15/15 PASS CLI0/1.7m,36 reviewed
  PNGs unchanged. Actual88/head50 disposable fixtures and real worker/codec.
- Latest owned visual source11 typed ESLint/e2e TypeScript/formatter CLI0.

HTTP ordinary logs:

- `/tmp/peerly-c03-http-area12-normal3.log`:12/12 PASS/32.8s — local choose,
  replace/remove; invalid type/size; owner READY reload; peer report/Other.
- `/tmp/peerly-c03-preview3-normal4.log`:3/3 PASS/14.3s — genuine peer Preview
  OPEN/ZOOM, Escape/focus. WebKit compares full native JPEG after3 independent
  fresh exact-byte frames with zero decoded pixel/threshold differences;
  Chromium and all CLOSED states retain ordinary PNG. Public fonts/decode/finite
  animation completion awaited. Ordinary WebKit same-state PNGs are diagnostic
  artifacts, not successful comparisons. Two obsolete WK OPEN/ZOOM PNG baselines
  archived with SHA and retired after accepted END; active JPEGs retained.
- `/tmp/peerly-c03-remaining12-normal5.log`:12/12 PASS/26.1s — own320px/200%
  no report, actual browser Back retirement, explicit caption pipeline and
  immutable access-failure Retry with original caption/normalized JPEG.

RealPG ordinary `/tmp/peerly-c03-normal15-run1.log` covers:

1. `image-pipeline`: actual PNG private transfer, queued/empty history, real
   worker, confirmed owner JPEG/image FK and peer report. READY alone never
   proves storage; original explicit Send authorizes that live pipeline only.
2. `image-recovery`: known finalize202, reload retires original Send, worker READY
   remains unsent until owner preview and a new explicit Send/current caption.
3. `image-cancel`: queued cancel-won actual terminal operation, canonical cancelled
   preparation, no stored message.
4. `image-finalize-unknown`: real upstream finalize202 followed by browser response
   loss; canonical queued/empty history, reload unsent, real worker and explicit
   Send preserve actual preparation/client-message/image identity.
5. `image-auth-pause`: real Start202 response loss and genuine SSE/ME revalidation;
   original File/caption retained, commands disabled under unknown authority,
   only explicit Retry after actual ME200 reuses original body/key/IDs and stores.

All browser leases ended; ports closed and owned TLS cleanup recorded. RealPG
initial shutdown session1 followed by readonly postcheck0 is preserved honestly
in cleanup evidence. No SQL READY shortcuts, fake Requests/chat grants, live S3,
provider credentials, application/dependency screenshot patches or error filters.
No specific database lock owner proven from idle worker ticks. Global
ResizeObserver/native-device/full-app acceptance remains outside scoped passes.
Additional optional failure/race scenarios marked outstanding in the table are
not claimed covered. See progress ledger for exact logs, review/hash manifests,
original failures, fixes, shared capture contract and acceptance boundaries.

## Design v2 source batch · 12 November 2026

Native image thumbnail gains bounded proportional containment; existing picker/preparation/owner-resume/viewer/report and explicit Send behavior remain intact.

See parent Chats SCENARIOS current-batch mapping. Earlier green receipts predate
this layout; matched original/current captures and affected acceptance are pending.
No capture/golden updates or current real-stack pass claimed.
