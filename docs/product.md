# Peerly product contract

Peerly helps APU students in Malaysia find help, offer help and start useful
one-to-one study conversations. The UI is English and mobile first. Groups,
bookings, study-hour tracking, streaks and percentage compatibility are outside
this MVP. Native packaging is separate from verified Android/iOS release.

## Identity and registration

Login uses personal Google OIDC, bound to trusted issuer/sub rather than email.
University membership is separate email-code verification of the exact domain
`mail.apu.edu.my`; it never creates a login session. No university SSO, mailbox
access, course attendance, grades or skill certification is implied.

A limited logged-in account completes real registration, membership and required
profile steps. At explicit registration completion show concise Terms/Privacy
links and record the versions/wording actually displayed. No legal onboarding
screen, consent checkbox, analytics opt-out or terms reacceptance gate. Policy
updates are informational; never rewrite historical receipts or infer reading.

## Knowledge areas and discovery

A goal uses a broad canonical knowledge area plus optional topic/task/module
context. Helpers self-declare their areas, including knowledge from work or
independent study. Course codes are context, not enrolment gates or area aliases.
Aliases express genuine equivalent labels. Relevance is deterministic from
actual shared sources; no semantic-match or competence claim is inferred.

Server capabilities govern discovery, full-profile disclosure, passes and new
contact. Visibility, lifecycle, photo requirements, source versions and blocks
are independent facts. A freshness exposure pause needs an explicit return
confirmation; background activity/login/polling does not silently confirm it.

## Requests and chat

Users review server-grounded text and explicitly send an immutable request.
Current defaults allow5 outstanding outgoing requests and10 successful sends
per Asia/Kuala_Lumpur calendar day. Pending lifetime is7 days; final decline
cooldown is7 days and withdrawal cooldown24 hours. Text and optional note each
allow240 Unicode code points; goal topic/context bounds are80/240. These remain
server-owned values, not duplicated client permissions.
Server quotas, pair uniqueness, deadlines, source revalidation and idempotency
resolve opposite sends, retries and races. Decline Undo is10 seconds by server
time; refresh/navigation never extends it. Editing a resolved failed payload is
a new intent, not a mutation under the original key. Unknown outcome stays unknown
until recovered; cancellation is not proof that nothing was sent.

Acceptance creates the real conversation for the pair. Confirmed messages use
monotonic conversation sequence, not timestamp ordering. Reads/polls do not
acknowledge human viewing. Explicit read position is caller-private; no fabricated
peer read/delivery receipt. Images use bounded private upload/processing and
protected display; pending and uncertain media states remain recoverable.

Hidden profiles cannot discover or make new contact; both directions of pending
requests close and do not reopen when shown again. Existing accepted chats remain
usable with their own minimal current name/avatar authority, including while
hidden/freshness-paused or after goal changes. Request disclosure itself grants
no hidden profile/photo access. Block/ban/deletion restrictions remain effective.

## Safety, deletion and privileged access

Blocking, reports, admin ban and soft deletion are distinct. Human photo
replacement requirements independently restrict discovery/new contact; ordinary
READY photos have no global review gate. A new replacement still needs explicit
human approval. Advisory AI never applies moderation automatically.

Soft deletion revokes sessions/transactions, removes student exposure/contact and
closes pending requests. Peers retain shared history labelled Deleted account
with neutral identity. All internal business/media/analytics history remains
linked and privileged-inspectable; deletion is not a claim of physical erasure.

Fresh Google authentication may create a NEW account after self-deletion, with
fresh registration and institutional verification. Old identity/mail associations
are retired and retained, not overwritten. No chats, role, session, proof or
profile authority transfers; active claim uniqueness and bans cannot be bypassed.

Explicit operators can inspect retained application data and relationships,
including messages/media, without a case assignment. Current role/session and
source ownership are checked; sensitive access is audited. Grafana access does
not grant application operator authority. No global account suspension modes,
automatic identity merging or mailbox reassignment are implied.

## AI, notifications and analytics

Optional student AI clarifies goal text, suggests areas and assesses profile
photos. Internal report prioritisation is advisory. One isolated native executor
serves a durable bounded queue; overload may delay/reject AI, not core actions.
Manual workflows remain available; no guaranteed model completion time.

Notification preferences are server-owned and distinct from OS permission,
mandatory security email and mandatory analytics. Do not claim native push
transport or store availability before the corresponding platform acceptance.

Analytics is mandatory and accurately account-linked, with action/request/job/
trace correlation. Never put private text, images, emails, credentials, raw SQL or
arbitrary bodies into ordinary telemetry. No keystroke/DOM/session recording is
implied. Prior analytics survives soft deletion. Temporary auth/transport secrets
still expire and are cleaned; retained history has separate archive obligations.

## Completion criteria

Implemented flows and internal staging are not a complete release. The final
phase compares every screen/state with design v2, restores intended layout and
mascot animation, checks mobile sizes and accessibility/reduced motion, and uses
supported Taiga components/themes/tokens/extensions instead of CSS hacks.
Operational/provider/restore/monitoring and native-platform acceptance are
separate, with truthful unresolved outcomes and no production-readiness claim
based solely on a build or screenshot.
