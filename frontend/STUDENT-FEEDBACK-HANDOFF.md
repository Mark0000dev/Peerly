# Student study check-in and peer feedback — active pilot priority

Aquinas owns ONLY new `src/app/screens/chats/study/**` and new
`docs/planning/student-feedback-progress.md` for F01/F02 after the bounded
FE06.5 meaningful unit/static checkpoint. Freeze unfinished operator history with
its actual unaccepted visual/PG limitations; no long operator fixture window.
Halley owns Chats parent files, routes/session/transport/generated contracts,
theme/tooling, all synthetic fixtures, and F03 own/public summary integration.
No own subagents/Git/deploy/provider/secret access. Parent coordinates ownership.

## Actual contract boundary

Noether's tested actual77 artifact adds five paths/seven operations to old72,
with no factory/settings/pool/DDL changes. Use generated DTOs ONLY after Halley's
successful regeneration of the corrected tested export; initial artifact exposed
a default422 documentation issue on public summary, being corrected by backend.
Never handwrite API shapes from this prose.

- GET/PUT `/api/v1/conversations/{conversation_id}/study-outcome`.
- GET/PUT `/api/v1/conversations/{conversation_id}/feedback`.
- POST `/api/v1/conversations/{conversation_id}/study-prompt-visits` with actual
  empty object body and Idempotency-Key.
- Own/public summary GETs are Halley's separate F03 consumer scope.

Writes use existing session-derived CSRF, trusted browser Origin, immutable
Idempotency-Key, expected_version for outcome/feedback and typed safe problems.
No automatic mutation retry. Current outcome and current feedback versions are
independent. Actual409 codes feedback_version_conflict and
worked_confirmation_required preserve draft and require explicit recovery.
Unknown network result is unknown: retain original payload/version/key for
explicit retry, don't claim nothing saved or overwrite a newer server value.

GET reads do not offer/dismiss prompts, acknowledge messages or submit feedback.
Only a genuine explicit foreground conversation visit may POST prompt admission.
The server owns eligibility, one-time offer, age/message requirements and response
`offered|no_offer`; do not derive from local time/message count, poll, replay on
query refetch/SSE/reconnect, or create new visit keys on render. Manual Study
progress remains available independently of automatic offer. Halley wires the
actual parent foreground visit entry; agree a small typed input/event boundary.
No speculative global event bus or mirrored prompt/session store.

## Approved F01/F02 behavior

F01-CheckIn: inline optional check-in, never steal focus, interrupt typing or open
an automatic blocking modal. Answers use actual yes/not_yet/did_not_work_out.
Dismiss only hides the offered UI; don't invent a server dismiss endpoint. Manual
reopen can read actual outcome and submit an explicit update. Do not infer peer's
answer. Yes permits a user action into feedback; other answers do not auto-submit
feedback. No fake support submission or unmounted support destination.

F02-Feedback: explicit worked-together confirmation is an actual own outcome PUT
(answer yes) when needed, followed by the two-question flow. Use actual own
feedback projection can_submit/current/current_publication/submission_publication;
never infer public admission from peer identity/message history. Again is
actual yes/maybe/no; optional three actual descriptors and optional team-only note.
Current own record can be updated without multiplying partner counts. Private-only
submission says so; removed/current/publication distinctions remain server-owned.
No reward, opt-out, public note/reviewer identity or AI quality score.

Use actual peer/academic context already authorized by parent Chats. Child may
receive minimal readonly actual actor/conversation/context inputs; never call
Discovery profile as a substitute or import another screen's internals. Use
existing shared HttpClient, safe ApiFailure, abort-aware QueryObserver and inherited
QueryClient. Keys include actor/conversation and purpose. No duplicate client,
DTO signal mirrors, storage/persistent credentials, mutable global FormGroups or
server-owned eligibility recomputation. Local typed form drafts/immutable pending
write intent are allowed; clear on actor replacement/logout/destroy/success.

Expose real `StudyProgress` component from an owned file when ready; Halley mounts
it in Chats and supplies the supported manual-open/foreground-visit boundary.
Do not edit parent Chats files or add fake routes. Use public Taiga mechanisms for
form/dialog layout; stable semantic actions/footer and scrollable content,
accessible labels/errors/focus/keyboard/320px/200% from the start. No pointer
choreography, hidden measurement controls, internal CSS or blanket budget changes.

## Evidence and fixtures

Meaningful units cover actual DTO guards, independent CAS versions, can_submit/
publication handling, immutable retry/409 recovery, no writes from GET/refetch,
no duplicate visit on query updates, no answer/feedback leakage to peer and actor
teardown. Every browser scenario includes behavior AND screenshot; loading,
empty/current/update/saved, eligible/private-only, prompt no_offer/offered/dismiss/
manual reopen, network unknown/retry,409,401/403/unavailable, keyboard/initial200%.
Use unchanged95 aggregate thresholds and strict runtime gate; existing globalRO
is not resolved by clean scoped runs and must never be filtered.

Request finite exact scenarios from Halley for real FastAPI/PostgreSQL fixtures.
No live messages/providers, invented mock-only production behavior, arbitrary
schema reset or new clock/UUID patch. Parent/main backend work has priority:
request short fresh named Noether READY/START/END only when ready. Serialize all
heavy/browser work with Halley; preserve complete stdout/stderr to unique temp
logs, inspect true exit code, review all actual PNGs. Clearly separate full raw
artifacts from compared stable source regions when genuine live values vary.
