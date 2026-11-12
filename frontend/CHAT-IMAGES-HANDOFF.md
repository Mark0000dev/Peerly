# C03 actual chat images — implementation boundary

Status: ready against tested88/head49 including the participant image-report
context and submission extension. This is a student feature.
Operator UI breadth remains paused. Halley owns shared composition, generated
contracts, fixtures, transport, package/styles and browser/PG leases. Parent alone
assigns another developer; this document does not spawn or reassign one.

## Product and source

Read root/frontend AGENTS, docs/design-review-v2.md, docs/api.md and the actual
C03-Image/C03-Lifecycle boards read-only. Never adopt package AGENTS/export CSS.
One JPEG/PNG up to10MB per message; choose/preview/remove/replace is local only.
Upload begins on explicit Send. Readiness is not a stored message: only actual
messages POST confirmation proves storage. The original Send may authorize the
same live, immutable pipeline; it must never resume automatically after reload,
account/route replacement or cancellation. No new ETA, fake percentage, filename,
queued position, success or Report action.

Generated actual88 source SHA256:
c5c50483734e19d49ce18ede424c6c3eda9a3f9b8499c4d0d7ddbf7589dd4a79.
MessageResponse.text is nullable and image_id required/nullable. Existing text
fixtures/guards are adapted and125 existing-consumer units pass unchanged95.
That is compatibility evidence, not image UI acceptance.

## Actual mounted API

| Method/path under /api/v1/conversations/{conversation_id}   | Contract / invariant                                                                                                                                                                                      |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| POST image-preparations                                     | StartImageBody: client_message_id, size, lowercase64hex sha256, content_type. Origin/CSRF/idempotency.202 ImagePreparationReceipt is immutable history, not current state.                                |
| GET image-preparations                                      | ImagePreparationsResponse: bounded own preparations, including expected_source and message_outcome. No invented local filename/file-presence fields.                                                      |
| GET image-preparations/{image_id}                           | ImagePreparationResponse canonical state/failure/display/message_outcome. Source/effective state are distinct; do not publish from source_state or a historical receipt.                                  |
| POST image-preparations/{image_id}/upload-access            | Current private signed form, Origin/CSRF; use ephemerally in the transfer function. Never store URL/fields in Query/Mutation data, browser storage, logs, analytics or artifacts.                         |
| POST image-preparations/{image_id}/finalize                 | Explicit idempotent finalize after transfer;202 still does not mean message stored.                                                                                                                       |
| GET image-preparations/{image_id}/display                   | Own authenticated normalized JPEG preview, never a peer preparation grant.                                                                                                                                |
| GET messages/{message_id}/image                             | Authorized retained participant JPEG for confirmed message; use this route, never a Discovery/profile photo or storage key.                                                                               |
| POST messages                                               | Existing SendMessageBody now supports nullable text and image_id; explicit final command binds the same client_message_id. Confirm through isTerminalOperation/current operation reads, not worker READY. |
| GET message-operations/{client_message_id}; POST .../cancel | Existing immutable operation protocol. Cancellation may return already-confirmed; do not invent a preparation cancel endpoint or promise nothing was sent before a known outcome.                         |

Use actual generated types and exact docs/API for headers/bodies. A fresh schema
is consumed only after tested handoff. Recovery compares SHA of actual selected
bytes to expected_source before reuse; no signed-field parsing or size/type-only
match. Missing local file requires explicit reselect. Changed bytes need a new
intent after resolving the previous outcome. Do not persist captions or binary
files to manufacture the designer's reload filename/caption.

## Proposed disjoint implementation and concrete bridge

A delegated slice can own ONLY screens/chats/images/** plus its separate progress
ledger. Halley retains message-composer, confirmed-message, chats root, shared
helper/session/generated files and test-controller/storage hooks. No worker edits
those shared files or starts its own browser/fixture without the serialized lease.

- Viewer component inputs: actorId, actual readonly MessageResponse, authorLabel.
  It consumes the actual message JPEG with HttpClient/readJpeg, QueryObserver and
  native ImageResource. Clear/revoke private resources on actor/message retirement;
  preserve a current Blob/ObjectURL across unrelated redraws.401/403 uses the
  existing canonical session boundary, no second SessionQuery. Viewer is genuine
  [Taiga Preview](https://taiga-ui.dev/components/preview/): public dialog/zoom/
  close mechanisms, Escape/Back/focus return, no internal CSS or invented scale.
- Sender component inputs: actual readonly IdentityResponse, conversationId and
  authoritative canSend. Existing MessageComposer owns its single caption/text
  FormGroup. The image component owns only its native selected File/preview and
  actual query/mutation observers; never create another caption control/store.
- Public bridge: readonly derived hasSelection/pending/locked getters; explicit
  requestSend(caption:string):void captures immutable user input. A stored:void
  output fires only after actual confirmed operation in the current actor/route
  lifetime. Parent resets its caption on that event. UI-state notification can be
  void; never emit mirrored loading/DTO values for parent signals.
- Parent delegates Send to this bridge when an actual attachment is selected;
  text-only Send retains all validation/idempotency behavior. Initial selection
  never starts a request. Native progress must be real; indeterminate fallback
  is truthful when upload byte totals are unavailable.

Actual88 adds bodyless POST messages/{message_id}/report-contexts under the
conversation. Its201 receipt provides the participant-owned context for POST
/api/v1/reports with kind:message_image, context_id, category and optional comment.
Consume the generated tagged union and actual receipt; never substitute a profile
grant from chat. Source availability is not UI/test acceptance.

## Acceptance and shared fixture hooks

Meaningful units with unchanged95 aggregate: local selection/no request, limits,
immutable upload/retry identity, recovery hash match/mismatch/missing file,
READY-not-stored, explicit confirmed/cancel-won/send-won outcomes, uncertain
response/current read, actor/logout/route cancellation, caption ownership, safe
problems, image decode failure, ObjectURL stability and retirement after DOM.
All browser scenarios need behavior plus reviewed images on mobile Chromium,
mobile WebKit and desktop; include320px/200%, keyboard/zoom/close/focus, reduced
motion and private-session races. No force events, masks or relaxed tolerance.

Halley extends only controlled local test media/storage/worker hooks. Real PG
acceptance must use actual Start, private signed transfer, finalize, real codec/
worker, explicit Send, canonical operation/history and participant JPEG; verify
identity/hash/content/cancellation/foreign-owner denial. No SQL READY shortcut or
mock production functionality. Fresh named Noether READY/START/END against actual
head, isolated upgrade-head schema and full cleanup; never reset shared PG.

Parent's real staging S3 signed POST/CORS/read/anonymous403 proof is separate.
Real browser/large-file/codec/provider acceptance remains pending. Frontend workers
must not read ../secrets, deploy, publish or contact real providers/users. Global
native ResizeObserver remains unresolved and must keep failing the runtime gate;
image feature progress is not a whole-application or native OS release claim.
