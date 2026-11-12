# Minimal knowledge-area adaptation

Approved owner decision:9 November2026, docs/planning/product-decisions-v1.md.
P05 scoped acceptance reached47 units/45 HTTP/6 realPG; C03 images remain the
parallel priority. The bounded source-copy pass is now implemented after that
boundary. It is not a redesign or a new taxonomy. Whole frontend units1286 CLI0
with unchanged95 thresholds; typed ESLint/e2e/ngc and owned fixture Ruff/format
pass. Updated screen-reference capture/review/normal comparisons remain pending.

Noether confirms the actual88/98 schema and hash remain unchanged. Existing
canonical subject IDs represent knowledge areas. Keep generated field/path names;
do not handwrite renamed DTOs or invent course/enrolment permissions.

The seed proposal contains10 broad areas and4 genuine equivalent aliases; the
earlier course-only proposal was never deployed and is replaced. Render the actual
server catalogue rather than embedding that proposal in frontend code. Examples
for the bounded copy/test pass are Databases + JOIN + optional IDB context,
Malay language + optional BMK2 context, and Computer systems + optional SSCC
context. These module codes are context, never implicit aliases or verified badges.
The owner explicitly reserves an independent later redesign of this section.

| Actual consumer                                                                                | Minimal change                                                                                                                                                                                                                                                                                 |
| ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| onboarding/study/goal.html and goal.ts                                                         | Subject/another subject/catalogue/errors become knowledge area/another area. Keep a separate specific topic/task and optional context, including module codes. Preserve explicit canonical/custom selection and the honest custom-goal relevance limitation.                                   |
| onboarding/study/help.html and help.ts                                                         | Help subjects become help areas. Explain self-declared knowledge, including work/self-study/another course; no same-module requirement. Existing optional topic note can carry module context.                                                                                                 |
| onboarding/setup/setup.html and setup.ts                                                       | Edit links and actual missing-study-context messages use area wording. Keep actual server activation requirements.                                                                                                                                                                             |
| Subject catalogue pickers                                                                      | Search server-provided area names/true equivalent aliases. Do not add IDB/SSCC/BMK2 as broad-area aliases, hardcode a new client catalogue or auto-map typed module codes.                                                                                                                     |
| discovery/discovery.html and discovery-contract.ts                                             | Saved help areas, listed-area requirements and exact-ID relevance wording. No semantic-match, course-completion or competence-verification claim.                                                                                                                                              |
| discovery/compose/compose.html, requests/requests.html, chats/chats.html and goal-sharing.html | Context labels say help area; render actual area plus specific task/context. Do not rewrite stored request/message text or immutable historical context.                                                                                                                                       |
| person/person.html                                                                             | Self-declared help-area labels only; APU email verification remains membership verification. No verified-course badges.                                                                                                                                                                        |
| AI                                                                                             | Nash owns backend prompt wording. Existing composer server suggestions remain server-owned and are not relabelled AI. Student AI UI is not currently implemented; later real consumers must use area/task/optional-module wording without claiming AI grants eligibility or semantic matching. |

Runtime constraints already match the approved model: goal topic80/context240,
both optional in the actual API; help up to5 canonical IDs, optional topic_note80.
Do not infer a new required course or mandatory module field. Keep explicit area
selection, normal length validation, source/version/CAS rules and manual save.

Scoped verification after the copy pass:

- Goal: Databases + SQL JOIN task + optional IDB context saves; absent module
  context remains valid. Canonical and explicit custom goals keep their actual
  different relevance behavior.
- Help: self-declared Databases area requires no course record/checkbox; optional
  note remains bounded; empty/overlength and max5 behavior stay unchanged.
- Catalogue: real aliases are searchable; a module code is not silently converted
  into an area. Preserve server pagination, empty/error/retry and selection identity.
- Discovery: actual canonical-ID relevance remains honest across distinct module
  contexts; account/pair/visibility restrictions are unchanged.
- Composer/history/profile: current and retained contexts render area/task/note
  consistently; private unsent drafts and original sent text remain intact.
- Update affected accessible-name unit/browser locators and screenshot references,
  review changed images, then normal comparisons. No blanket snapshots or tolerance
  change, new tag cloud, broad form migration or automatic matching/permission.

Accepted reflow subset:112 study unit checks95.95/95.28/100/100 and6 ordinary
320px/200% comparisons across3 projects,12 reviewed references. Longer visual
labels were rejected when Taiga elided them. Concise Area/Task/Context/Note labels
retain complete native accessible names and visible optional context hints; glyph
bounds are asserted. Other changed states/screens still need updated references.
