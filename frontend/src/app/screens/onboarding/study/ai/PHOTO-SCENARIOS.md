# O02-Assist photo advice: code-complete contract and final matrix

Actual source: O02-Assist design board, generated actual88 PhotoRequest,
PhotoResultResponse, Observation and JobResponse; backend SqlAiTransaction.prepare.
This is advisory only. It does not accept, reject, replace, verify identity or
satisfy a human-requested replacement. No face-size/darkness/score fields exist
in the actual DTO and none are invented here.

Export PhotoAssistance from photo-assistance.ts; selector peerly-photo-assistance.
Required inputs: actor: IdentityResponse and source: ResourceSourceRequest|null.
Additional sourceChecking input defaultsfalse. The parent keeps the widget
mounted through same-actor queries even when the current photo projection is
unknown. null+sourceChecking retains original intent/job and blocks new Ask/manual
Choose. Fresh-authority GET/cancel remain available. Once checkingfalse, null or
a different actual photo withdraws old tips. No DTO/URL mirror is introduced.
Public readonly hasRequest getter derives from the existing intent and lets the
parent retain the editor during an unknown photo projection, even with blank
manual fields. Keep the widget mounted; supply a non-null source only for a
current owned READY saved photo, using
{kind:'resource', id:CurrentPhotoResponse.upload_id,
version:CurrentPhotoResponse.version}. Upload revision.version is NOT the source
version. Parent retains ownership of file picking, photo resources, upload,
review/publication, session and layout. No profile/photo source edited here.

Outputs: expired:{actorId,failure:ApiFailure} and chooseAnother:void. The latter
only requests a manual parent action; the child keeps its advice until parent
changes source or the student dismisses it. Keep this photo is a local dismissal,
never a saved-photo confirmation/approval or network write. Parent's existing
manual flow stays independent, including when AI503 or unknown.

One inherited QueryClient; canonical job/result only in public QueryObserver and
MutationObserver. Source identity and immutable request/key are bounded client
intent. Fresh shared trustedVerifiedActor is required before each private read,
command and chooseAnother event, without activation capability. Same-actor
pending/error blocks actions but retains intent; actual retirement aborts reads
and removes owned private cache/mutations. Idle observer is nonprivate. Cancellation
aborts an older poll before its empty body/no-idempotency-header command. No
automatic admission retry, source reuse or stale result. Unknown admission can
only explicitly replay original source/body/key. Known terminal Ask again uses a
new key; edited saved photo needs explicit Get tips for this photo.

| Behavior                                                | Authored meaningful unit evidence                                               | Final browser/realPG evidence required                                                              |
| ------------------------------------------------------- | ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Offered/no request; verified preactivation              | Initial no HTTP, no private idle query, no activation gate                      | Real mounted current photo; optional tips do not block manual controls                              |
| Exact saved photo resource; no URL/file/revision extras | Exact assess_photo body, minimised source fields, generated resource validation | Actual CurrentPhoto upload_id/current version vs upload revision, genuine source503 or accepted job |
| Actual503/429/409/422 preserve manual path              | Actual HttpTesting responses, no photo writes or manual-action output           | Reviewed unavailable/quota/changed source screens, real503/no admitted SQL job                      |
| Queued/running/loading; actual poll hint/deadline       | Public QueryObserver polling and deadline/destroy cancellation                  | Named screenshots of waiting/running/restore checking; no ETA                                       |
| All yes/no/uncertain observations                       | Strict three-field result guard and all nine static advisory mappings           | Reviewed photo tips, including uncertain observations; no invented verdict                          |
| Keep vs manual choose                                   | Explicit choose output, advice retained, Keep has no output/network write       | Real parent picker only after user action; Keep does not publish/change photo                       |
| Saved photo source changes                              | Old tip withdrawal, new explicit resource request, old action blocked           | Actual parent new current photo hides earlier result; source/version proof                          |
| Unknown admission                                       | Original body/key preserved despite new current photo                           | Lost response → explicit identical retry; no auto/replacement request                               |
| Unknown/canonical cancellation and result-won           | Empty cancel, older GET aborted, explicit retry and actual terminal/result      | Cancellation pending/unknown/cancelled/result-won screenshots                                       |
| Failed/expired/cancelled                                | Explicit fresh-key retry only                                                   | Actual terminal screens, manual path retained                                                       |
| Wrong-kind/source/id/version/result                     | Contract boundary table and actual bad GET rejection                            | Malformed controlled boundary rejection; no provider text rendering                                 |
| Pending/error/replaced/logout actor                     | Shared fresh guard, stale output blocked, old response ignored                  | Root keeps same-actor editor while commands blocked; actual actor retirement                        |
| Narrow/reduced-motion/keyboard                          | Public Taiga buttons and semantic list; tests authored for final candidate      | 320px/200%, keyboard Choose/Keep, focus, overflow, safe-area/native checks                          |

Code and meaningful unit sources are authored; these NEW photo tests have NOT
been executed. Latest user workflow requires code-complete candidate FIRST,
then final combined units/static, one browser+realPG matrix with references
reviewed in a batch. No intermediate capture/normal or coverage loops.

Current runtime remains hard OFF until the separate backend/runtime proof.
Positive controlled HTTP is UI evidence only. Live provider/credentials/staging
smoke requires its separately authorised bounded proof, not a UI flag. Global
ResizeObserver and prior failures remain preserved, with no filters or waivers.
