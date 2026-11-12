# Mandatory design v2 fidelity inventory

Prepared11 November2026 from the original approved ZIP and current route source.
This is the review inventory, NOT a visual-compliance verdict. Implementation and
bounded original-reference browser comparisons resumed on 12 November after the
parent handoff. Existing golden comparisons do not establish design fidelity.

## Current implementation cohort — 12 November

The route/state tables below retain Pending until their complete comparison and
regression evidence is recorded; they must not be read as a claim that no source
work exists. Current production-build cohort completed at05:17:44Z, initial
524.85kB, zero compiler warnings. Receipt:
`../.peerly-ops/frontend-fidelity-20261112/integration-cohort/build.log`.
This local controlled-boundary build is not a staging deployment or real-provider
acceptance.

- W01, A01–A03, O01, P01: shared native navigation, compact composition and
  auth/profile layout corrections implemented; first matched reference captures
  belong to an earlier build and do not automatically verify this newer cohort.
- W02/W03/L01/L02, W04/A04 and W06: public header/footer, plaintext policy layout,
  native help accordion with genuine support form and standalone404 recovery
  implemented. Policy-history reads now use the actual published metadata contract;
  pagination and complete responsive acceptance remain pending. No maintenance
  state or document metadata is fabricated.
- C01–C04/F01/F02: Aquinas source candidate beb88f44 integrated into this build.
  Bounded original-versus-actual captures are recorded, not full-state acceptance. Its
  capture driver required correcting reference-only fragment selectors; these
  failures are not application failures or visual approvals.
- P02/P05/W05: exclusive next source slice delegated to Aquinas; latest build
  includes preliminary P02 public AppBar/cards only. Preserve device-delivery
  truthfulness, account retirement and fresh-registration behavior.
- Mascots: shared native picture renderer preserves original animated SVG and
  reduced-motion fallback. Prior real-build motion evidence is historical;
  changed consumer composition still needs the final cohort's actual motion check.

No whole-matrix, complete50-ID fidelity, mobile200% or global-runtime-green claim
is made by this checkpoint. Preserve the known ResizeObserver issue separately.

Reference:84board JSONs,50active IDs (including global X), retired A05 retained
only for historical traceability. Shared multi-screen boards are not new routes.
Original source/runtime/designer instructions remain outside application source.
Archive SHA256: `fa46732a9bc76d799958a69bc0d0ce7460190f6c55ac20bf6c26a525bf28ee75`.

## Observed differences and bounded correction evidence

| Surface         | Observed difference                                                                                        | Supported correction / decision                                                                                                       | Evidence boundary                                                                                                        |
| --------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| W01 closing CTA | Actual390px capture overflowed to406px: declared width excluded its padding                                | Normal border-box sizing; no clipping or hidden overflow                                                                              | Final05:29 build, actual320/390 normal+200% geometry and full screenshots, public-cohort/affected-proof-report.json      |
| C02             | Extra Chats title and tall always-open accepted-context block displaced composer                           | Single peer H1 and native Taiga collapsed accordion, preserving actual fields and explicit expansion                                  | compact-cohort-capture:8original+8actual, no native/application/resource diagnostics; only390px cohort                   |
| F01/F02         | Inline progress/feedback placement still differs from contextual check-in / dedicated feedback composition | Contextual inline check-in and explicit native fullscreen feedback dialog implemented; preserve eligibility, drafts and actual writes | study-dialog-cohort original/actual captures; full state and responsive acceptance remain open                           |
| W04/A02         | Original reference predates real university quarantine behavior                                            | Preserve truthful SMTP-versus-inbox distinction and conditional official quarantine guidance                                          | Approved functional requirement, not an unexplained design simplification                                                |
| W01 FAQ         | Original includes an unspecified owner pricing statement                                                   | Four truthful native disclosures; pricing placeholder omitted, no invented price                                                      | Actual built no-JavaScript disclosure click and route proof; remaining original-layout comparison open                   |
| W06             | Old wildcard silently redirected home                                                                      | Real not-found route retains unknown URL and offers actual recovery links with public Taiga BlockStatus                               | Original+actual captures, no mobile overflow; no invented maintenance API/state                                          |
| L03             | Published-version list was previously unavailable                                                          | Actual tested metadata-only history API, opaque pagination and existing safe plaintext version reader                                 | Source/regression definitions integrated, actual390 history capture; full pagination acceptance pending                  |
| Mascot W06      | Shared picture renderer needs real-build evidence, not static goldens                                      | Original animated SVG normally; native reduced-motion static fallback                                                                 | Chromium actual404 normal frames differ at600ms; reduced frames byte-identical. Full6asset/all-engine phase remains open |

Source checkpoint ef4835b3 is frozen outside the application tree. Subsequent
profile navigation/blocked-cell and own-photo-review source is a later cohort,
not silently covered by those build/capture receipts. Full state tables below
remain Pending until their actual acceptance boundary is recorded.

## Actual surface mapping

| Reference ID | Reference boards                  | Actual consumer / boundary                                                                  | Visual comparison |
| ------------ | --------------------------------- | ------------------------------------------------------------------------------------------- | ----------------- |
| A01          | A01-Google, A01-Welcome           | /onboarding · Google entry/callback/recovery                                                | Pending           |
| A02          | A02-Email                         | /onboarding · institutional email                                                           | Pending           |
| A03          | A03-Code                          | /onboarding · challenge status/code                                                         | Pending           |
| A04          | A04-Support                       | /help/contact; /help/contact/status · access support                                        | Pending           |
| C01          | C01-ChatList                      | /chats · list                                                                               | Pending           |
| C02          | C02-Conversation, C02-Delivery    | /chats · selected conversation/SSE                                                          | Pending           |
| C03          | C03-Image, C03-Lifecycle          | /chats · image composer/preview/recovery                                                    | Pending           |
| C04          | C04-SharedGoal                    | /chats · shared goal actions                                                                | Pending           |
| D01          | D01-Discover                      | /discover                                                                                   | Pending           |
| D02          | D02-Profile                       | /people/:personId                                                                           | Pending           |
| D03          | D03-Preview, D03-States           | Discover/person/Requests composer sheets                                                    | Pending           |
| D04          | D04-Empty                         | /discover · empty projections                                                               | Pending           |
| D05          | D05-Passed                        | /discover · passed profiles                                                                 | Pending           |
| F01          | F01-CheckIn                       | /chats · study check-in                                                                     | Pending           |
| F02          | F02-Feedback                      | /chats · peer feedback                                                                      | Pending           |
| F03          | F03-Summary                       | /profile and /people/:personId · summary                                                    | Pending           |
| G01          | G01-Assist, G01-GoalEditor        | /onboarding; /profile/goal · manual/AI goal                                                 | Pending           |
| G02          | G02-HelpSubjects                  | /onboarding; /profile/help                                                                  | Pending           |
| L01          | L01-Terms, LX-Responsive          | /terms                                                                                      | Pending           |
| L02          | L02-Privacy, LX-Responsive        | /privacy                                                                                    | Pending           |
| L03          | L03-Documents, LX-Responsive      | Profile document links/history                                                              | Pending           |
| L04          | L04-Updated, LX-Responsive        | Informational policy-update surfaces                                                        | Pending           |
| M01          | M01-Queue, M01-Triage             | /operator/reports · queue/AI triage                                                         | Pending           |
| M02          | M02-Case                          | /operator/reports · selected report                                                         | Pending           |
| M03          | M03-Search, MX-Responsive         | /operator/accounts + implemented inspector searches                                         | Pending           |
| M04          | M04-User, MX-Responsive           | /operator/accounts · selected account                                                       | Pending           |
| M05          | M05-Conversation, MX-Responsive   | /operator/conversations                                                                     | Pending           |
| M06          | M06-Records, MX-Responsive        | Implemented operator source/relationship panels; exact substate mapping pending             | Pending           |
| M07          | M07-Audit, MX-Responsive          | Implemented operator audit detail panels; collection-entry mapping pending                  | Pending           |
| O01          | O01-Profile                       | /onboarding; /profile/edit · basics                                                         | Pending           |
| O02          | O02-Assist, O02-Photo             | /onboarding; /profile/edit · photo/crop/AI                                                  | Pending           |
| O03          | O03-StudySetup                    | /onboarding · study setup                                                                   | Pending           |
| P01          | P01-OwnProfile                    | /profile                                                                                    | Pending           |
| P02          | P02-Notifications                 | /profile/notifications                                                                      | Pending           |
| P03          | P03-Hide                          | /profile/visibility                                                                         | Pending           |
| P04          | P04-Blocked                       | /profile/blocks                                                                             | Pending           |
| P05          | P05-Delete                        | /account/delete; /account/deletion-status                                                   | Pending           |
| R01          | R01-Decline, R01-Received         | /requests · received                                                                        | Pending           |
| R02          | R02-Sent                          | /requests · sent                                                                            | Pending           |
| R03          | R03-Detail, R03-Pair              | /requests · detail/pair projections                                                         | Pending           |
| R04          | R04-AltResponse                   | /requests · alternative response                                                            | Pending           |
| S01          | S01-Report, S01-Results           | Person/chat report and block sheets                                                         | Pending           |
| S02          | S02-Capabilities, S02-Restriction | Actual session/account restriction projections                                              | Pending           |
| W01          | W01-Landing                       | /                                                                                           | Pending           |
| W02          | W02-Terms                         | /terms                                                                                      | Pending           |
| W03          | W03-Privacy                       | /privacy                                                                                    | Pending           |
| W04          | W04-Help                          | /help; /help/contact; /help/contact/status                                                  | Pending           |
| W05          | W05-Deletion                      | /account/delete; /account/deletion-status                                                   | Pending           |
| W06          | W06-System                        | Dedicated real404 implemented; maintenance/offline availability remains explicit dependency | Pending           |
| X            | X-System                          | Cross-feature loading/network/uncertain/unavailable states                                  | Pending           |

## Required comparison and deviation record

For every applicable frame below record actual browser state/setup, reference and
actual screenshot locators, viewport/text scale/motion mode, mismatch and severity,
approved owner exception, smallest supported Taiga correction, behavior regression
and final evidence. Mark unreachable/API-dependent states explicitly; do not fake
capabilities, counts, role flags, routes or successful submissions to fill a board.

Cover mobile360/320,200% text, desktop, keyboard/focus, real scroll/overlay behavior
and normal/reduced motion as relevant. Compare originals versus actual production
build, not only current goldens versus themselves. Review fixes in coherent batches
and retain all strict diagnostics; known global RO is not resolved by this inventory.

## Owner decisions that override literal designer copying

- W01/W05: conditions/retention/analytics disclosures only in Terms/Privacy; ordinary functional consequences and links remain.
- A01: actual Google plus institutional proof, explicit registration context/completion; no callback-fabricated legal receipt or invented next field.
- A02/A03: SMTP acceptance is not inbox delivery; unknown outcome, real deadlines and tenant-dependent quarantine/support guidance remain truthful.
- P05: owner10 November permits a distinct fresh account after deletion with fresh Google/OTP/legal/profile; old records/history are retained and never restored to the new account.
- P03/D01: hidden affects discovery only; existing chats continue. Thirty-day freshness pause is exposure only, restored only by actual explicit confirmation.
- R01: Undo10seconds, authoritative server deadlines and immutable manual replay.
- L03/L04: no analytics choices/checkboxes/reacceptance; document changes informational under approved policy.
- G01/G02: broad self-declared knowledge areas, task/module optional context; no course-enrolment or AI semantic matching guarantees.
- D03: supported fullscreen dialog/stable footer approximation was approved where public Taiga cannot express a bounded footer safely; never restore pointer/validation-layout hacks.
- AI: manual paths remain functional; use actual availability/queue/cancel/outcomes, no fabricated jobs/ETA/autosave.
- P02: persisted preferences do not establish native/background delivery; preview delivery limitation stays explicit, independent of OS permission/security mail/mandatory analytics.
- Operator surfaces: exhaustive privileged inspection through actual audited APIs, no fake moderation actions or hardcoded grants.

## Confirmed source facts / unresolved findings

| ID          | Evidence                                                                                                                 | Status / required proof                                                                                                               |
| ----------- | ------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| MOTION-001  | Six old SVGs were exact originals minus style/class animation hooks; original assets have native reduced-motion support. | Original six restored after telemetry freeze; production three-project normal/reduced proof pending.                                  |
| ROUTE-001   | app.routes.ts wildcard currently redirects to the landing page; W06 includes an explicit not-found reference.            | Verify actual public UX against W06, then implement supported behavior if still required; do not invent a maintenance API/projection. |
| VISUAL-OPEN | Owner reports oversimplification and departures on staging; no complete reference-versus-current audit exists.           | All mapped screens/states remain pending actual comparison; current golden passes do not close this finding.                          |

## Complete structured reference-frame checklist

The index includes foundation/shared boards and retired references for traceability.
These are designer-reference frames, not a declaration that every export annotation
is an approved feature or API. Record runtime applicability during the actual pass.

| Board / frame        | Screen IDs              | Reference state label                                   | Review status                               |
| -------------------- | ----------------------- | ------------------------------------------------------- | ------------------------------------------- |
| A01-Google #1        | A01                     | After Google returns · routes                           | Pending                                     |
| A01-Google #2        | A01                     | 1 · Opening Google                                      | Pending                                     |
| A01-Google #3        | A01                     | 2 · Finishing sign-in                                   | Pending                                     |
| A01-Google #4        | A01                     | 3 · Cancelled at Google                                 | Pending                                     |
| A01-Google #5        | A01                     | 4 · Sign-in failed                                      | Pending                                     |
| A01-Google #6        | A01                     | 5 · Resume unfinished verification                      | Pending                                     |
| A01-Google #7        | A01                     | 6 · Wrong Google account                                | Pending                                     |
| A01-Google #8        | A01                     | 7 · Account unavailable · deleted                       | Pending                                     |
| A01-Google #9        | A01                     | 8 · Restricted account · ban                            | Pending                                     |
| A01-Welcome #1       | A01                     | New or returning · welcome                              | Pending                                     |
| A01-Welcome #2       | A01                     | Signed out · session ended                              | Pending                                     |
| A01-Welcome #3       | A01                     | Help, terms and privacy                                 | Pending                                     |
| A02-Email #1         | A02                     | Empty                                                   | Pending                                     |
| A02-Email #2         | A02                     | Valid                                                   | Pending                                     |
| A02-Email #3         | A02                     | Not an APU student address                              | Pending                                     |
| A02-Email #4         | A02                     | Sending                                                 | Pending                                     |
| A02-Email #5         | A02                     | Rate limited                                            | Pending                                     |
| A02-Email #6         | A02                     | Network failure                                         | Pending                                     |
| A03-Code #1          | A03                     | Code sent                                               | Pending                                     |
| A03-Code #2          | A03                     | Pasted · checking                                       | Pending                                     |
| A03-Code #3          | A03                     | Incorrect                                               | Pending                                     |
| A03-Code #4          | A03                     | Expired                                                 | Pending                                     |
| A03-Code #5          | A03                     | Resent                                                  | Pending                                     |
| A03-Code #6          | A03                     | Delivery problem                                        | Pending                                     |
| A03-Code #7          | A03                     | Change email                                            | Pending                                     |
| A03-Code #8          | A03                     | Confirmed                                               | Pending                                     |
| A03-Code #9          | A03                     | Address already in use                                  | Pending                                     |
| A04-Support #1       | A04                     | Draft · signed in                                       | Pending                                     |
| A04-Support #2       | A04                     | Address already in use                                  | Pending                                     |
| A04-Support #3       | A04                     | Can’t sign in · signed out                              | Pending                                     |
| A04-Support #4       | A04                     | Submitted                                               | Pending                                     |
| A04-Support #5       | A04                     | Failed                                                  | Pending                                     |
| A04-Support #6       | A04                     | Follow-up status                                        | Pending                                     |
| A05-BeforeStart #1   | A05                     | What replaced it                                        | Retired; no implementation                  |
| C01-ChatList #1      | C01                     | Conversations                                           | Pending                                     |
| C01-ChatList #2      | C01                     | Empty                                                   | Pending                                     |
| C01-ChatList #3      | C01                     | Loading · reconnecting                                  | Pending                                     |
| C02-Conversation #1  | C02                     | Just connected · learner                                | Pending                                     |
| C02-Conversation #2  | C02                     | Just connected · helper                                 | Pending                                     |
| C02-Conversation #3  | C02                     | Draft · keyboard open                                   | Pending                                     |
| C02-Conversation #4  | C02                     | Sending and failed                                      | Pending                                     |
| C02-Conversation #5  | C02                     | Reconnecting · new messages                             | Pending                                     |
| C02-Conversation #6  | C02                     | Read-only conversation                                  | Pending                                     |
| C02-Conversation #7  | C02                     | Study check-in in context                               | Pending                                     |
| C02-Delivery #1      | C02                     | Mobile · mixed thread                                   | Pending                                     |
| C02-Delivery #2      | C02                     | Mobile · after reload, back online                      | Pending                                     |
| C02-Delivery #3      | C02                     | Mobile · another account on this device                 | Pending                                     |
| C02-Delivery #4      | C02                     | Desktop 1440 · split view                               | Pending                                     |
| C03-Image #1         | C03                     | Preview before sending                                  | Pending                                     |
| C03-Image #2         | C03                     | Uploading                                               | Pending                                     |
| C03-Image #3         | C03                     | Failed or too large                                     | Pending                                     |
| C03-Image #4         | C03                     | Fullscreen viewer                                       | Pending                                     |
| C03-Lifecycle #1     | C03                     | 1 · Choose a file                                       | Pending                                     |
| C03-Lifecycle #2     | C03                     | 2 · Local preview                                       | Pending                                     |
| C03-Lifecycle #3     | C03                     | 3 · Remove or replace                                   | Pending                                     |
| C03-Lifecycle #4     | C03                     | 4 · Unsupported or too large                            | Pending                                     |
| C03-Lifecycle #5     | C03                     | 5 · Sent · uploading                                    | Pending                                     |
| C03-Lifecycle #6     | C03                     | 6 · Upload or processing failed                         | Pending                                     |
| C03-Lifecycle #7     | C03                     | 7 · Outcome uncertain                                   | Pending                                     |
| C03-Lifecycle #8     | C03                     | 8 · Confirmed by the server                             | Pending                                     |
| C03-Lifecycle #9     | C03                     | 9 · Explicit retry                                      | Pending                                     |
| C03-Lifecycle #10    | C03                     | 10 · Discard an unsent item                             | Pending                                     |
| C03-Lifecycle #11    | C03                     | 11 · After reload · file no longer available            | Pending                                     |
| C03-Lifecycle #12    | C03                     | 12 · Cancel tapped · cancelling                         | Pending                                     |
| C03-Lifecycle #13    | C03                     | 12a · Cancelled · confirmed                             | Pending                                     |
| C03-Lifecycle #14    | C03                     | 12b · Already sent                                      | Pending                                     |
| C03-Lifecycle #15    | C03                     | 12c · Checking                                          | Pending                                     |
| C04-SharedGoal #1    | C04                     | Your current goal, pinned                               | Pending                                     |
| C04-SharedGoal #2    | C04                     | Share current goal                                      | Pending                                     |
| C04-SharedGoal #3    | C04                     | Mark goal done?                                         | Pending                                     |
| C04-SharedGoal #4    | C04                     | After done                                              | Pending                                     |
| CMP-Overlays #1      | foundation              | Sheet anatomy                                           | Foundation/reference; applicability pending |
| CMP-Overlays #2      | foundation              | Confirmation dialog                                     | Foundation/reference; applicability pending |
| CMP-Overlays #3      | foundation              | Notification permission invite                          | Foundation/reference; applicability pending |
| CMP-Overlays #4      | foundation              | Empty and loading                                       | Foundation/reference; applicability pending |
| CMP-PersonCard #1    | foundation              | Default · Find help                                     | Foundation/reference; applicability pending |
| CMP-PersonCard #2    | foundation              | Newcomer · no bio, no feedback yet                      | Foundation/reference; applicability pending |
| CMP-PersonCard #3    | foundation              | Long name and long subject                              | Foundation/reference; applicability pending |
| CMP-PersonCard #4    | foundation              | Photo failed to load                                    | Foundation/reference; applicability pending |
| CMP-PersonCard #5    | foundation              | Drag right · Review request                             | Foundation/reference; applicability pending |
| CMP-PersonCard #6    | foundation              | Drag left · Pass                                        | Foundation/reference; applicability pending |
| CMP-PersonCard #7    | foundation              | Reduced motion · dragging right                         | Foundation/reference; applicability pending |
| CMP-PersonCard #8    | foundation              | Other modes                                             | Foundation/reference; applicability pending |
| D01-Discover #1      | D01                     | Find help · first deck                                  | Pending                                     |
| D01-Discover #2      | D01                     | Find help · relevant card                               | Pending                                     |
| D01-Discover #3      | D01                     | Offer help                                              | Pending                                     |
| D01-Discover #4      | D01                     | Study together · first entry                            | Pending                                     |
| D01-Discover #5      | D01                     | Drag right · preview                                    | Pending                                     |
| D01-Discover #6      | D01                     | Drag left · pass                                        | Pending                                     |
| D01-Discover #7      | D01                     | Passed · next card                                      | Pending                                     |
| D01-Discover #8      | D01                     | Photo failed to load                                    | Pending                                     |
| D02-Profile #1       | D02                     | New person                                              | Pending                                     |
| D02-Profile #2       | D02                     | Lower on the same profile                               | Pending                                     |
| D02-Profile #3       | D02                     | They sent you a request                                 | Pending                                     |
| D02-Profile #4       | D02                     | Pending                                                 | Pending                                     |
| D02-Profile #5       | D02                     | Connected                                               | Pending                                     |
| D02-Profile #6       | D02                     | Unavailable                                             | Pending                                     |
| D02-Profile #7       | D02                     | Overflow menu · photo failed                            | Pending                                     |
| D03-Preview #1       | D03                     | Help request · first use                                | Pending                                     |
| D03-Preview #2       | D03                     | Subject only                                            | Pending                                     |
| D03-Preview #3       | D03                     | Help offer                                              | Pending                                     |
| D03-Preview #4       | D03                     | Study together                                          | Pending                                     |
| D03-Preview #5       | D03                     | Note added · keyboard open                              | Pending                                     |
| D03-Preview #6       | D03                     | Editing the request text                                | Pending                                     |
| D03-Preview #7       | D03                     | Sending                                                 | Pending                                     |
| D03-Preview #8       | D03                     | Failed                                                  | Pending                                     |
| D03-Preview #9       | D03                     | At the pending limit                                    | Pending                                     |
| D03-Preview #10      | D03                     | Goal changed meanwhile                                  | Pending                                     |
| D03-Preview #11      | D03                     | Maya has already sent you a request                     | Pending                                     |
| D03-Preview #12      | D03                     | Request sent                                            | Pending                                     |
| D03-States #1        | D03                     | 1 · Suggested text                                      | Pending                                     |
| D03-States #2        | D03                     | 2 · Edited text, with a note                            | Pending                                     |
| D03-States #3        | D03                     | 3 · Request text empty                                  | Pending                                     |
| D03-States #4        | D03                     | 4 · Over the limit · kept, not cut                      | Pending                                     |
| D03-States #5        | D03                     | 5 · Saved goal changed while open                       | Pending                                     |
| D03-States #6        | D03                     | 6 · Recipient became unavailable                        | Pending                                     |
| D03-States #7        | D03                     | 7 · Submission in progress                              | Pending                                     |
| D03-States #8        | D03                     | 8 · Not sent · draft kept                               | Pending                                     |
| D03-States #9        | D03                     | 9 · Outcome uncertain · checking                        | Pending                                     |
| D03-States #10       | D03                     | 10 · Sent                                               | Pending                                     |
| D04-Empty #1         | D04                     | No partners for this topic yet                          | Pending                                     |
| D04-Empty #2         | D04                     | Broader subject matches                                 | Pending                                     |
| D04-Empty #3         | D04                     | You have seen everyone for now                          | Pending                                     |
| D04-Empty #4         | D04                     | Offline                                                 | Pending                                     |
| D04-Empty #5         | D04                     | No goal and no help subjects                            | Pending                                     |
| D04-Empty #6         | D04                     | Offer help without subjects                             | Pending                                     |
| D05-Passed #1        | D05                     | Empty                                                   | Pending                                     |
| D05-Passed #2        | D05                     | List                                                    | Pending                                     |
| D05-Passed #3        | D05                     | Restored candidate                                      | Pending                                     |
| F01-CheckIn #1       | F01                     | Eligible                                                | Pending                                     |
| F01-CheckIn #2       | F01                     | Yes                                                     | Pending                                     |
| F01-CheckIn #3       | F01                     | Not yet                                                 | Pending                                     |
| F01-CheckIn #4       | F01                     | It didn’t work out                                      | Pending                                     |
| F01-CheckIn #5       | F01                     | Dismissed · manual route                                | Pending                                     |
| F02-Feedback #1      | F02                     | Did you work together?                                  | Pending                                     |
| F02-Feedback #2      | F02                     | Would you study together again?                         | Pending                                     |
| F02-Feedback #3      | F02                     | Saved                                                   | Pending                                     |
| F02-Feedback #4      | F02                     | Failed                                                  | Pending                                     |
| F02-Feedback #5      | F02                     | Moved off the app                                       | Pending                                     |
| F02-Feedback #6      | F02                     | Updating earlier feedback                               | Pending                                     |
| F03-Summary #1       | F03                     | Fewer than 3 partners                                   | Pending                                     |
| F03-Summary #2       | F03                     | Full counts                                             | Pending                                     |
| F03-Summary #3       | F03                     | How this works                                          | Pending                                     |
| G01-Assist #1        | G01                     | 1 · Offered, nothing sent                               | Pending                                     |
| G01-Assist #2        | G01                     | 2 · Suggestion ready                                    | Pending                                     |
| G01-Assist #3        | G01                     | 3 · Used · not saved yet                                | Pending                                     |
| G01-Assist #4        | G01                     | 4 · Catalogue suggestion                                | Pending                                     |
| G01-Assist #5        | G01                     | a · Queued                                              | Pending                                     |
| G01-Assist #6        | G01                     | b · Running                                             | Pending                                     |
| G01-Assist #7        | G01                     | c · Suggestion ready                                    | Pending                                     |
| G01-Assist #8        | G01                     | d · Cancelled                                           | Pending                                     |
| G01-Assist #9        | G01                     | e · Expired                                             | Pending                                     |
| G01-Assist #10       | G01                     | f · Busy · rate limited                                 | Pending                                     |
| G01-Assist #11       | G01                     | g · Provider unavailable                                | Pending                                     |
| G01-Assist #12       | G01                     | h · Failed                                              | Pending                                     |
| G01-Assist #13       | G01                     | i · Source changed                                      | Pending                                     |
| G01-GoalEditor #1    | G01                     | Subject only                                            | Pending                                     |
| G01-GoalEditor #2    | G01                     | Full goal                                               | Pending                                     |
| G01-GoalEditor #3    | G01                     | Suggested wording                                       | Pending                                     |
| G01-GoalEditor #4    | G01                     | Custom subject                                          | Pending                                     |
| G01-GoalEditor #5    | G01                     | Full screen · keyboard open · save failed               | Pending                                     |
| G01-GoalEditor #6    | G01                     | Discard changes?                                        | Pending                                     |
| G01-GoalEditor #7    | G01                     | Saved                                                   | Pending                                     |
| G02-HelpSubjects #1  | G02                     | Empty                                                   | Pending                                     |
| G02-HelpSubjects #2  | G02                     | Subjects with topic notes                               | Pending                                     |
| G02-HelpSubjects #3  | G02                     | Limit reached                                           | Pending                                     |
| G02-HelpSubjects #4  | G02                     | Add or edit a subject                                   | Pending                                     |
| L01-Terms #1         | L01                     | Top · from settings or the welcome sentence             | Pending                                     |
| L01-Terms #2         | L01                     | Sections 1–4                                            | Pending                                     |
| L01-Terms #3         | L01                     | Sections 6–7                                            | Pending                                     |
| L01-Terms #4         | L01                     | Sections 8–10                                           | Pending                                     |
| L01-Terms #5         | L01                     | Loading · failed                                        | Pending                                     |
| L02-Privacy #1       | L02                     | Top · in short                                          | Pending                                     |
| L02-Privacy #2       | L02                     | 1–3 · who, what, why                                    | Pending                                     |
| L02-Privacy #3       | L02                     | 4–5 · analytics and team access                         | Pending                                     |
| L02-Privacy #4       | L02                     | 6–7 · storage and AI                                    | Pending                                     |
| L02-Privacy #5       | L02                     | 8 · deleting your account                               | Pending                                     |
| L02-Privacy #6       | L02                     | 9–13 · retention, processors, rights, updates           | Pending                                     |
| L03-Documents #1     | L03                     | Terms and Privacy Policy                                | Pending                                     |
| L03-Documents #2     | L03                     | Version history                                         | Pending                                     |
| L03-Documents #3     | L03                     | Older version open                                      | Pending                                     |
| L03-Documents #4     | L03                     | Offline                                                 | Pending                                     |
| L04-Updated #1       | L04                     | 1 · Update note · once per version                      | Pending                                     |
| L04-Updated #2       | L04                     | 2 · What changed                                        | Pending                                     |
| L04-Updated #3       | L04                     | 3 · Full document · changes marked                      | Pending                                     |
| L04-Updated #4       | L04                     | 4 · Elsewhere                                           | Pending                                     |
| LX-Responsive #1     | L01, L02, L03, L04      | Desktop 1280 · L02 Privacy Policy                       | Pending                                     |
| LX-Responsive #2     | L01, L02, L03, L04      | Tablet 768 · L04 update note                            | Pending                                     |
| M01-Queue #1         | M01                     | Empty                                                   | Pending                                     |
| M01-Queue #2         | M01                     | Filtered, no results                                    | Pending                                     |
| M01-Queue #3         | M01                     | Resolved                                                | Pending                                     |
| M01-Queue #4         | M01                     | Main layout                                             | Pending                                     |
| M01-Triage #1        | M01                     | Queue · triage column                                   | Pending                                     |
| M01-Triage #2        | M01                     | Case · triage panel                                     | Pending                                     |
| M01-Triage #3        | M01                     | a · Pending                                             | Pending                                     |
| M01-Triage #4        | M01                     | b · Ready                                               | Pending                                     |
| M01-Triage #5        | M01                     | c · Unavailable                                         | Pending                                     |
| M01-Triage #6        | M01                     | d · Failed                                              | Pending                                     |
| M01-Triage #7        | M01                     | e · Source changed                                      | Pending                                     |
| M02-Case #1          | M02                     | Main layout                                             | Pending                                     |
| M03-Search #1        | M03                     | Conversations by participant                            | Pending                                     |
| M03-Search #2        | M03                     | Exact ID · message                                      | Pending                                     |
| M03-Search #3        | M03                     | Loading                                                 | Pending                                     |
| M03-Search #4        | M03                     | No results                                              | Pending                                     |
| M03-Search #5        | M03                     | Invalid input                                           | Pending                                     |
| M03-Search #6        | M03                     | End of results                                          | Pending                                     |
| M03-Search #7        | M03                     | Search failed                                           | Pending                                     |
| M03-Search #8        | M03                     | Session expired                                         | Pending                                     |
| M03-Search #9        | M03                     | Main layout                                             | Pending                                     |
| M03-Search #10       | M03                     | Main layout                                             | Pending                                     |
| M04-User #1          | M04                     | Requests tab · both directions                          | Pending                                     |
| M04-User #2          | M04                     | Partial failure                                         | Pending                                     |
| M04-User #3          | M04                     | Deleted account                                         | Pending                                     |
| M04-User #4          | M04                     | Main layout                                             | Pending                                     |
| M05-Conversation #1  | M05                     | Authenticated viewer                                    | Pending                                     |
| M05-Conversation #2  | M05                     | Stored file can’t be read                               | Pending                                     |
| M05-Conversation #3  | M05                     | Loading earlier history · failure                       | Pending                                     |
| M05-Conversation #4  | M05                     | Main layout                                             | Pending                                     |
| M06-Records #1       | M06                     | Stored object missing                                   | Pending                                     |
| M06-Records #2       | M06                     | Related account deleted                                 | Pending                                     |
| M06-Records #3       | M06                     | History not available · partial failure                 | Pending                                     |
| M06-Records #4       | M06                     | Main layout                                             | Pending                                     |
| M07-Audit #1         | M07                     | No entries for these filters                            | Pending                                     |
| M07-Audit #2         | M07                     | Failed to load                                          | Pending                                     |
| M07-Audit #3         | M07                     | Session expired                                         | Pending                                     |
| M07-Audit #4         | M07                     | Main layout                                             | Pending                                     |
| MX-Responsive #1     | M03, M04, M05, M06, M07 | Tablet 768 · M04 user overview                          | Pending                                     |
| MX-Responsive #2     | M03, M04, M05, M06, M07 | Narrow 390 · M03 search                                 | Pending                                     |
| MX-Responsive #3     | M03, M04, M05, M06, M07 | Narrow 390 · M05 conversation                           | Pending                                     |
| O01-Profile #1       | O01                     | Empty                                                   | Pending                                     |
| O01-Profile #2       | O01                     | Valid                                                   | Pending                                     |
| O01-Profile #3       | O01                     | Upload in progress                                      | Pending                                     |
| O01-Profile #4       | O01                     | Photo required                                          | Pending                                     |
| O02-Assist #1        | O02                     | 1 · Offered                                             | Pending                                     |
| O02-Assist #2        | O02                     | 2 · Tips ready                                          | Pending                                     |
| O02-Assist #3        | O02                     | 3 · During a required replacement                       | Pending                                     |
| O02-Assist #4        | O02                     | a · Queued                                              | Pending                                     |
| O02-Assist #5        | O02                     | b · Running                                             | Pending                                     |
| O02-Assist #6        | O02                     | c · Tips ready                                          | Pending                                     |
| O02-Assist #7        | O02                     | d · Cancelled                                           | Pending                                     |
| O02-Assist #8        | O02                     | e · Expired                                             | Pending                                     |
| O02-Assist #9        | O02                     | f · Busy · rate limited                                 | Pending                                     |
| O02-Assist #10       | O02                     | g · Provider unavailable                                | Pending                                     |
| O02-Assist #11       | O02                     | h · Failed                                              | Pending                                     |
| O02-Assist #12       | O02                     | i · Source changed                                      | Pending                                     |
| O02-Photo #1         | O02                     | Choose a source                                         | Pending                                     |
| O02-Photo #2         | O02                     | Crop                                                    | Pending                                     |
| O02-Photo #3         | O02                     | Photo tips · advisory                                   | Pending                                     |
| O02-Photo #4         | O02                     | Camera access denied                                    | Pending                                     |
| O02-Photo #5         | O02                     | Unsupported or too large                                | Pending                                     |
| O02-Photo #6         | O02                     | Upload failed                                           | Pending                                     |
| O03-StudySetup #1    | O03                     | Find help · preselected                                 | Pending                                     |
| O03-StudySetup #2    | O03                     | Choosing a subject                                      | Pending                                     |
| O03-StudySetup #3    | O03                     | Optional help subject                                   | Pending                                     |
| O03-StudySetup #4    | O03                     | I’m here to help                                        | Pending                                     |
| O03-StudySetup #5    | O03                     | Saved draft · returning                                 | Pending                                     |
| P01-OwnProfile #1    | P01                     | Complete                                                | Pending                                     |
| P01-OwnProfile #2    | P01                     | No active goal                                          | Pending                                     |
| P01-OwnProfile #3    | P01                     | Helper only                                             | Pending                                     |
| P01-OwnProfile #4    | P01                     | Edit profile                                            | Pending                                     |
| P01-OwnProfile #5    | P01                     | Required correction                                     | Pending                                     |
| P02-Notifications #1 | P02                     | Messages and requests · on                              | Pending                                     |
| P02-Notifications #2 | P02                     | All updates · explicit choice                           | Pending                                     |
| P02-Notifications #3 | P02                     | Permission not asked                                    | Pending                                     |
| P02-Notifications #4 | P02                     | Denied                                                  | Pending                                     |
| P02-Notifications #5 | P02                     | Unsupported                                             | Pending                                     |
| P03-Hide #1          | P03                     | Visibility                                              | Pending                                     |
| P03-Hide #2          | P03                     | Confirmation                                            | Pending                                     |
| P03-Hide #3          | P03                     | Saving · failed                                         | Pending                                     |
| P03-Hide #4          | P03                     | Hidden                                                  | Pending                                     |
| P03-Hide #5          | P03                     | Restored                                                | Pending                                     |
| P03-Hide #6          | P03                     | Restore blocked                                         | Pending                                     |
| P04-Blocked #1       | P04                     | Empty                                                   | Pending                                     |
| P04-Blocked #2       | P04                     | List                                                    | Pending                                     |
| P04-Blocked #3       | P04                     | Unblock confirmation                                    | Pending                                     |
| P05-Delete #1        | P05                     | 1 · Explain                                             | Pending                                     |
| P05-Delete #2        | P05                     | 2 · Confirm                                             | Pending                                     |
| P05-Delete #3        | P05                     | 3 · Deleting                                            | Pending                                     |
| P05-Delete #4        | P05                     | 4 · Done · signed out                                   | Pending                                     |
| P05-Delete #5        | P05                     | 5 · Failed                                              | Pending                                     |
| P05-Delete #6        | P05                     | 6 · Uncertain · checking                                | Pending                                     |
| P05-Delete #7        | P05                     | 7 · Peer view · deleted partner                         | Pending                                     |
| P05-Delete #8        | P05                     | 8 · Operators                                           | Pending                                     |
| Proto-App #1         | foundation              | Main layout                                             | Foundation/reference; applicability pending |
| Proto-App #2         | foundation              | Main layout                                             | Foundation/reference; applicability pending |
| Proto-Onboarding #1  | foundation              | Main layout                                             | Foundation/reference; applicability pending |
| Proto-Onboarding #2  | foundation              | Main layout                                             | Foundation/reference; applicability pending |
| R01-Decline #1       | R01                     | 1 · Decline being submitted                             | Pending                                     |
| R01-Decline #2       | R01                     | 2 · Undo available                                      | Pending                                     |
| R01-Decline #3       | R01                     | 3 · Undo being submitted                                | Pending                                     |
| R01-Decline #4       | R01                     | 4 · Undo succeeded · row restored                       | Pending                                     |
| R01-Decline #5       | R01                     | 5 · Undo failed · deadline passed                       | Pending                                     |
| R01-Decline #6       | R01                     | 6 · Request became unavailable during the window        | Pending                                     |
| R01-Decline #7       | R01                     | 7 · Connection lost · outcome uncertain                 | Pending                                     |
| R01-Decline #8       | R01                     | 8 · Reopened while a window is still active             | Pending                                     |
| R01-Decline #9       | R01                     | 9 · Several declines in a row                           | Pending                                     |
| R01-Decline #10      | R01                     | 10 · Same flow from request detail                      | Pending                                     |
| R01-Received #1      | R01                     | New and viewed                                          | Pending                                     |
| R01-Received #2      | R01                     | Empty                                                   | Pending                                     |
| R01-Received #3      | R01                     | Declined · Undo available                               | Pending                                     |
| R01-Received #4      | R01                     | Unavailable and expired                                 | Pending                                     |
| R02-Sent #1          | R02                     | Pending and accepted                                    | Pending                                     |
| R02-Sent #2          | R02                     | Closed history                                          | Pending                                     |
| R02-Sent #3          | R02                     | Withdraw confirmation                                   | Pending                                     |
| R02-Sent #4          | R02                     | Limits reached                                          | Pending                                     |
| R03-Detail #1        | R03                     | Received · immutable context                            | Pending                                     |
| R03-Detail #2        | R03                     | Accepting                                               | Pending                                     |
| R03-Detail #3        | R03                     | No longer available                                     | Pending                                     |
| R03-Detail #4        | R03                     | Already connected                                       | Pending                                     |
| R03-Detail #5        | R03                     | Reached from Discover · Maya already sent you a request | Pending                                     |
| R03-Detail #6        | R03                     | Sent · pending detail                                   | Pending                                     |
| R03-Pair #1          | R03                     | 1 · Checking the pair                                   | Pending                                     |
| R03-Pair #2          | R03                     | 2 · An incoming request already exists                  | Pending                                     |
| R03-Pair #3          | R03                     | 3 · Her request arrives while you are writing           | Pending                                     |
| R03-Pair #4          | R03                     | 4 · Reviewing, with your text kept                      | Pending                                     |
| R03-Pair #5          | R03                     | 5 · After accepting                                     | Pending                                     |
| R03-Pair #6          | R03                     | 6 · You already sent a request                          | Pending                                     |
| R03-Pair #7          | R03                     | 7 · A conversation already exists                       | Pending                                     |
| R03-Pair #8          | R03                     | 8 · No longer actionable · actions refreshed            | Pending                                     |
| R04-AltResponse #1   | R04                     | Suggested · learning it too                             | Pending                                     |
| R04-AltResponse #2   | R04                     | Edited · general reply                                  | Pending                                     |
| R04-AltResponse #3   | R04                     | Swap suggestion                                         | Pending                                     |
| R04-AltResponse #4   | R04                     | Accepted, message failed                                | Pending                                     |
| RSP-Desktop #1       | foundation              | Main layout                                             | Foundation/reference; applicability pending |
| RSP-DesktopChats #1  | foundation              | Main layout                                             | Foundation/reference; applicability pending |
| RSP-Small #1         | foundation              | 320 × 640                                               | Foundation/reference; applicability pending |
| RSP-Small #2         | foundation              | 390 · text at 200 %                                     | Foundation/reference; applicability pending |
| RSP-Small #3         | foundation              | 360 · keyboard open                                     | Foundation/reference; applicability pending |
| RSP-Small #4         | foundation              | Landscape 844 × 390                                     | Foundation/reference; applicability pending |
| RSP-Tablet #1        | foundation              | Discover · portrait 768 × 1024                          | Foundation/reference; applicability pending |
| RSP-Tablet #2        | foundation              | Request preview · dialog at 768                         | Foundation/reference; applicability pending |
| S01-Report #1        | S01                     | Reasons                                                 | Pending                                     |
| S01-Report #2        | S01                     | What’s included · comment                               | Pending                                     |
| S01-Report #3        | S01                     | Submitted                                               | Pending                                     |
| S01-Report #4        | S01                     | Couldn’t send · retry                                   | Pending                                     |
| S01-Report #5        | S01                     | Block confirmation                                      | Pending                                     |
| S01-Results #1       | S01                     | 1 · Review before sending                               | Pending                                     |
| S01-Results #2       | S01                     | 2 · Both in progress                                    | Pending                                     |
| S01-Results #3       | S01                     | 3 · Report submitted · block succeeded                  | Pending                                     |
| S01-Results #4       | S01                     | 4 · Report submitted · block failed                     | Pending                                     |
| S01-Results #5       | S01                     | 5 · Report failed · block succeeded                     | Pending                                     |
| S01-Results #6       | S01                     | 6 · Both failed                                         | Pending                                     |
| S01-Results #7       | S01                     | 7 · Still being checked                                 | Pending                                     |
| S01-Results #8       | S01                     | 8 · What Daniel sees                                    | Pending                                     |
| S02-Capabilities #1  | S02                     | Hidden · own Discover                                   | Pending                                     |
| S02-Capabilities #2  | S02                     | Partner hid · existing chat                             | Pending                                     |
| S02-Capabilities #3  | S02                     | Replacement photo · own Requests                        | Pending                                     |
| S02-Capabilities #4  | S02                     | Replacement photo · partner’s chat                      | Pending                                     |
| S02-Capabilities #5  | S02                     | Restricted from new contact · own Discover              | Pending                                     |
| S02-Capabilities #6  | S02                     | Ban or block · the other person’s chat                  | Pending                                     |
| S02-Capabilities #7  | S02                     | Chat list · every state at once                         | Pending                                     |
| S02-Restriction #1   | S02                     | Temporarily restricted                                  | Pending                                     |
| S02-Restriction #2   | S02                     | Photo replacement requested                             | Pending                                     |
| S02-Restriction #3   | S02                     | Review pending                                          | Pending                                     |
| S02-Restriction #4   | S02                     | Ask for a review                                        | Pending                                     |
| W01-Landing #1       | W01                     | Desktop 1440                                            | Pending                                     |
| W01-Landing #2       | W01                     | Mobile 390                                              | Pending                                     |
| W02-Terms #1         | W02                     | Desktop 1440 · /terms                                   | Pending                                     |
| W02-Terms #2         | W02                     | Mobile 390                                              | Pending                                     |
| W03-Privacy #1       | W03                     | Desktop 1440 · /privacy                                 | Pending                                     |
| W03-Privacy #2       | W03                     | Mobile 390                                              | Pending                                     |
| W04-Help #1          | W04                     | Desktop 1440 · /help                                    | Pending                                     |
| W04-Help #2          | W04                     | Mobile 390 · sent                                       | Pending                                     |
| W05-Deletion #1      | W05                     | Desktop 1440 · /delete-account                          | Pending                                     |
| W05-Deletion #2      | W05                     | Mobile 390                                              | Pending                                     |
| W06-System #1        | W06                     | 404 · desktop                                           | Pending                                     |
| W06-System #2        | W06                     | Maintenance · mobile                                    | Pending                                     |
| W06-System #3        | W06                     | Offline · mobile                                        | Pending                                     |
| X-System #1          | X                       | Loading · Discover                                      | Pending                                     |
| X-System #2          | X                       | Network failure · Requests                              | Pending                                     |
| X-System #3          | X                       | Session expired · Chats                                 | Pending                                     |
| X-System #4          | X                       | Offline with cache · server error                       | Pending                                     |

## Current integration boundary

The later source receipt66c6564 and subsequent M02 report-review integration do
not close this inventory. Report-review regression candidates compare application
behavior, not original-design fidelity. Their fixed open confirmation is compared
in its actual complete viewport, with focus, geometry and overflow assertions;
the retained closed form keeps its full-document comparison. No clipping, masks
or tolerance changes substitute for layout fixes.

After the current integration acceptance, complete the Pending screen/state rows
against the original reference: normal/mobile/200% layout, keyboard and error/empty/
loading states, public Taiga mechanisms, then each animated mascot consumer in the
actual production build with both normal and prefers-reduced-motion settings.
One Chromium404 animation proof cannot establish all-consumer/all-engine motion.
Known aggregate ResizeObserver diagnostics remain a separate open acceptance issue.
