# D03 request composer handoff

Parent authorizes the next concrete implementation slice. Aquinas owns ONLY
`src/app/screens/discovery/compose/**` and
`../docs/planning/request-compose-progress.md` for this slice. Existing Requests,
Person and Discovery outer production files are frozen. Halley owns the Discovery
integration, URL/modal/session/logout wiring, routes/providers, generated DTOs,
shared transport, fixtures, theme and serialized browser resource. No subagents,
Git, provider calls, external messages or secrets reads.

## Actual entry and public component

Implement standalone `RequestComposer` exported from `discovery/compose/compose.ts`.
This is a real embedded D03 sheet in Discovery, NOT another route or a global store.
Halley mounts its stable instance beside the selected-card UI and keeps that
instance alive when its own sheet is closed. The component uses public Taiga
Dialog/form/textarea/buttons. No export runtime/CSS, internal selectors, custom
control styles, decorative assets or new font/theme changes.

Proposed narrow integration interface (confirm actual names with Halley before
integration): required readonly Identity actor, recipientId and DiscoveryMode;
open boolean; closed/sent/expired outputs. A sent output reports an actual generated
receipt, never optimistic success. A reconciliation output may request restoring
its original actor/recipient/mode selection; coordinate exact UI URL snapshot if
necessary. Parent controls open via an actual compose URL flag while retaining the
selected person/mode/cursor. Closing removes only that flag and sends nothing.
No contact CTA is added until this actual consumer is importable and tested.

The initial consumer is Discovery, so code stays colocated there. Do not import
Requests or Person internals. Shared sessionOptions/readJson/writeJson/ApiFailure/
isUncertain and the existing single QueryClient remain the public boundaries.
For existing request navigation use actual /requests?box=sent|received&request=id;
connected may link /requests?request=id without inventing direction. No Chats link
until a genuine Chat screen exists.

## Explicit client-draft exception: ONE feature-owned draft

FormGroups belong to the composer component. Keep one actual unsent text/note form
alive across its own sheet close/reopen; do not copy form values into signals,
query data or another model. Lifetime is that feature component; count is one.
No global Map of FormGroups, injected draft service, local/sessionStorage, route
reuse strategy or application store. Navigating out destroys and clears this
feature; persistence across unrelated navigation is not required by this slice.

Only the identity/source intent needed to bind that unsent form may be a private
immutable readonly signal value: actor, recipient, mode and actual preview/source
scope. Never mirror context, quotas, capabilities, loading/errors or other server
query/mutation data. Actor change/logout/destroy and confirmed successful send
clear inputs/source intent and owned sensitive mutation cache. Halley ensures the
shared session/logout lifecycle unmounts/resets the child, including while closed.
Ignore stale actor/lifetime callbacks. Unknown send freezes the original body/key;
closing and reopening must not silently create a different send intent.

Recipient/mode/source changes with an unsent draft require explicit reconciliation:
keep the original draft/scope or deliberately discard/review the new context.
Never overwrite edited text or silently attach it to another source. Reopening the
same retained source preserves user edits. A new server default may initialize a
new/pristine form only as part of an explicit review/reconciliation action.

## Actual backend baseline and pending additive projection

Generated Api is actual60, source SHA256
`ba3862f2e9a641090c2d415ea0bf6e379f660565c5db502c549f3bfad26f3067`.
Actual export /tmp/peerly-actual60-operator-openapi.json. Old54 paths/components
unchanged; generation/drift,app/spec/e2e types and6 generator tests passed.
Read docs/api.md Implemented Requests, actual generated schemas and backend
presentation/requests/{inputs,outputs,read_outputs,router}.py read-only.

POST /api/v1/requests/preview currently takes {person_id,mode} with CSRF/Origin and
immutable Idempotency-Key. It returns a generated PreviewResponse (retained id,
academic context,created_at), RequestMutationResponse (existing_outgoing/incoming)
or ConnectedResponse. Optional discriminator defaults in schemas remain optional;
validate the actual union shape, no String(enum) coercion. No send/autoaccept on
preview, GET, render, close, retry of a read or pair recovery.

IMPORTANT: current60 PreviewResponse has NO suggested text, quota or canSend fields.
Parent instructed Noether to add a real tested additive projection. Do not invent
those DTO fields, synthesize default request text/AI suggestions, hardcode quotas,
or infer canSend by comparing counters. Noether owns exact names/semantics and
will provide a tested export; Halley regenerates before binding. Until then,
prepare actual preview/retained-context/existing-pair guards and their recovery
states; leave dependent default/quota/send-cap binding visibly pending in the
ledger. No mock-only future production functionality or guessed schema interfaces.

POST /api/v1/requests takes generated SendRequestBody
{person_id,preview_id,text,note?}. Only explicit Send request submits. Actual text
and note limits are240 Unicode code points, server final validation authoritative.
Use typed forms, no accidental UTF16 rejection of valid emoji or unsafe control
characters. Preserve actual raw user intent, optional empty note maps deliberately
to the documented nullable/absent value. Academic source is read-only, not another
editable goal; changing a goal goes through the actual editor and explicit review.

No automatic social retry. Unknown response preserves exact body/preview/key;
manual replay can return its original immutable receipt. After confirmation reread
canonical Requests/Discovery state, clear the sent draft and advance only through
actual server eligibility. Newer pair state can differ from an old replay receipt;
never manufacture a fresh pending request, greeting, pass or conversation.
Existing outgoing/incoming/connected outcomes are recovery screens/links, not new
preview IDs or permission to send. Current profile/avatar access remains separately
guarded; request context grants no extra photo/profile disclosure.

## Design, checks and coordination

Read root/frontend AGENTS, autonomous workflow and docs/design-review-v2.md.
Use reviewed v2 D03-Preview,D03-States,R03-Pair. Apply recorded corrections: actual
API wins, no invented deadlines/countdowns/quota values/AI ETA, no store links or
fake messaging. No analytics opt-out/checkbox or extra legal step.

Colocate scenario matrix, meaningful units, visual specs and PNGs. Cover all three
modes, default vs edited text/note, read-only source, close/reopen, explicit source
reconcile, quota denied, existing pairs, validation, pending/unknown/replay/conflict,
actor/logout isolation, canonical outcome recovery, keyboard/focus and320px/200%.
Every browser case needs behavioral assertions and named PNG checkpoints. Real
FastAPI+Postgres supplements boundary doubles. Halley owns needed fixture seeding;
request exact cases, never fabricate domain state in production or reset shared PG.

Every justified check redirects full stdout+stderr to an owned /tmp file and keeps
its exit status; inspect bounded tails afterward, no masking pipeline. Acquire the
browser resource from Halley FIRST, then request a fresh lease-specific backend
READY from Noether for PG. Only then send matching START; send matching END after
own fixture/schema/TLS cleanup. Never reuse a released READY or confuse a browser
grant with backend READY. No concurrent browser/unit suites or unknown process kills.

Global native RO blocker remains open. Accepted scoped PG18 and unit770 do not fix
old HTTP60/runtimeCLI1 or whole-app aggregate failure. Do not repeat a whole gate,
launch observer probes, suppress errors or rerun solely to recapture lost output.
Continue actual dependency-ready implementation and report exact acceptance limits.
