# Student AI implementation handoff

Parent authorises Aquinas to own only `src/app/screens/onboarding/study/ai/**`
and `../docs/planning/student-ai-progress.md`. This supersedes the completed C03
assignment after its final evidence. Halley owns Goal template/form integration,
shared session/transport/query infrastructure, generated types, routes, styles,
fixtures and all browser/resource leases. Do not edit those shared files.
No subagents/Git/deploy/provider credentials/live messages.

Start with the actual G01-Assist clearer-context and catalogue-suggestion surfaces;
G01-GoalEditor supplies the parent form. Use approved broad knowledge-area wording,
not course enrolment/verification. Photo advice O02 is a separate later consumer,
not an excuse to import/change the photo screen. No operator work.

## Actual boundary

Read `../docs/api.md` AI section, current generated `src/app/api.generated.ts`
and actual enabled OpenAPI. Actual current export88 paths/98 operations hash
`c5c50483734e19d49ce18ede424c6c3eda9a3f9b8499c4d0d7ddbf7589dd4a79`.
Do not regenerate/edit shared files or handwrite server DTOs.

- POST `/api/v1/ai/jobs`: generated ClarifyRequest/SuggestRequest/PhotoRequest,
  required `idempotency-key` and same-origin session Origin/CSRF. Clarify supports
  `source:{kind:'draft',id,version}`, explicit target context240/topic80, text.
  Suggest accepts actual typed label80 and1..20 captured actual catalogue IDs.
- GET `/api/v1/ai/jobs/{job_id}`: generated JobResponse, actual state/failure/result,
  source and target, `poll_after_ms`. Use server polling hints, no invented ETA.
- POST `/api/v1/ai/jobs/{job_id}/cancel`: empty body, CSRF, no invented idempotency
  header. Actual owned cancellation is not a promise that an already won result
  was undone. Unknown/foreign/internal jobs404.
- Runtime admission is **hard OFF**. Valid verified live actors receive real503
  `ai_unavailable`, no admitted job. Manual Goal save must remain fully usable.
  Controlled positive202 fixtures test UI state only; never describe them as a
  working executor or real provider. No UI enable flag or fabricated production job.

## Component interface for real parent consumer

Export a standalone `GoalAssistance` from `goal-assistance.ts`, selector
`peerly-goal-assistance`. Export only the actual small readonly input/output
contracts needed by Halley's Goal consumer, no speculative service/facade.

- `actor`: generated IdentityResponse input.
- `draft`: readonly form-view input containing generated DraftSourceRequest,
  context/topic strings, typed areaLabel, and at most20 actual catalogue
  `{id,name}` candidates typed as Pick of generated SubjectResponse. This is
  editable parent form input, not a second query/server projection.
- `applyText`: output `{source:DraftSourceRequest,target:GoalTextTarget,value:string}`.
- `applyArea`: output `{source:DraftSourceRequest,id:string}`.
- `expired`: output carrying actual actor ID and ApiFailure for guarded parent
  session retirement.

Halley will own the stable per-form draft UUID and monotonic client edit revision,
pass current form values without signal text mirrors, wire outputs only after
rechecking the current source/actor, and mark fields dirty. Applying a suggestion
never saves/publishes the goal; normal CAS Save remains a separate explicit action.
Implement the component/real unit boundary first, then send exported interface
readiness so Halley can mount it. Do not invent a mock-only production route.

Use context wording action as G01-Assist first. Topic target is allowed by the
actual API but do not clutter the UI with a speculative second editor. Catalogue
suggestion must only return/offer captured IDs, use actual query-owned labels,
and never manufacture a topic or semantic matching guarantee absent in DTO.
No edits after source change can silently reuse/apply an earlier result.

## Transport, state and lifetime

Use `readJson`/`writeJson`/ApiFailure from parent `api-http.ts`, public QueryObserver
and MutationObserver, one existing QueryClient. Query keys include actor/job/source.
Mutation retry:false; immutable request body/key in mutation variables. Unknown
admission can only explicitly replay the identical intent/key, never automatic
resubmission/new intent while uncertain. Server job state/result lives only in
TanStack Query. Store no credentials/drafts/jobs in local/sessionStorage.

Do not import Chats' screen internals. Before every new private request/command,
inspect existing session query state: success+fetchStatus idle, same actor,
account active, membership verified. AI onboarding is allowed before activation;
do not require `can_use_student_features` if backend does not. Pending/failed
revalidation is not authority. Preserve local editable inputs during a same-actor
check but block new commands/apply until restored; real actor retirement/logout/
destroy clears feature intent and aborts polling. Guard late responses and outputs.
Read requests are abort-aware. Bounded deadlines/cancellation must distinguish a
local timeout/lost response from a confirmed server failure. Use actual DTO codes,
no raw provider text or telemetry containing private drafts.

## Acceptance and coordination

Meaningful units95% all four metrics, strict lint/compiler/formatter/build budget.
Cover actual input bounds, manual save after503, queued/running/result, cancel,
failed/expired,429/503, lost admission/same-key explicit retry, edited source,
malformed/wrong-kind/source/hash result, pending/error auth, actor replacement,
logout/destroy, late replies and bounded polling cleanup. No endpoint/source guesses.

Every actual integration scenario needs behavior and reviewed screenshots on all
three projects,320px/200%, keyboard/focus/overflow. Positive states use controlled
HTTP only; actual FastAPI/Postgres must prove disabled503/no admitted job and
manual Goal save still works. Halley owns fixture hooks and real mounting, request
concrete additions instead of changing the fixture yourself. No concurrent WebKit,
heavy units/build/browser suites; request lead browser lease and fresh named
Noether READY for each realPG START/END+cleanup. Preserve raw stdout/stderr and
strict diagnostics. Global ResizeObserver remains unresolved; do not filter it.

Continue through ready implementation tasks autonomously; batch reports at real
interface/feature acceptance or concrete blocker. Do not ask routine permission
or return to historical C03/operator scope. Parent owns any next delegation.
