# G02 helper-subject draft editor

Actual GET/PUT `/me/help-subjects` and `/subjects` power this verified setup editor. Ordered form rows contain canonical choices and optional notes; zero choices are allowed, five is the current product maximum. No custom-label mapping, credentials, ability rating, automatic registration or fake Discover transition. A public Taiga dialog owns the picker and focus lifecycle; Back to setup returns to a real local view and destroys the editor/draft.

| Scenario                                      | Behavioral and screenshot coverage in Chromium mobile, WebKit mobile and desktop                               |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Initial loading and saved selection           | Delayed own selection, actual label/note hydration                                                             |
| Empty, picker, draft, saving, success, reload | Explicit canonical selection via alias; exact closed request/version/CSRF/idempotency; no writes while editing |
| Existing selections and maximum               | Duplicate canonical option disabled; fifth choice removes Add action; honest maximum note                      |
| Remove final selection                        | Explicit empty save; no inference of activation or chat loss                                                   |
| Validation/320px/200%/keyboard                | Overlong optional note sends nothing; keyboard focus and no horizontal overflow                                |
| Catalogue failure/loading/retry/empty         | Explicit response gate; no automatic retry or raw problem title                                                |
| Catalogue pagination and Escape               | Opaque server cursor, draft preserved, actual dialog closes on Escape                                          |
| Own selection read failure                    | Safe message and explicit retry                                                                                |
| Unknown save                                  | Original immutable body/key replay only after explicit Retry; no automatic mutation retry                      |
| Stale revision/retired subject                | Draft retained/read-only, safe actual409 copy and explicit saved-state reload                                  |
| Save401                                       | Session bootstrap revalidation and private draft removed from guest UI                                         |
| Actor replacement                             | Unit and browser old200/401 callback isolation; replacement draft stays private and unchanged                  |

Picker screenshots use the actual viewport with before/after geometry equality, containment and no horizontal overflow. Closed-form checkpoints capture the whole document. No generic crop, mask, forced direction or tolerance exception. Reduced motion is the required browser preference; real device keyboards/OS font settings remain external checks.

Unit coverage additionally checks strict malformed DTO handling, zero revision, optional blank notes, saved label metadata exclusion from requests, ordered IDs, duplicate prevention, cursor/search cancellation, safe422 and idempotency conflicts, deny/cache clearing and identity replacement.

Real FastAPI/PostgreSQL test verifies a canonical alias choice, version1 note save/reload, explicit empty version2 save/reload and return to setup. Provider boundaries are controlled; database, OAuth state/session, durable email delivery and membership are real. This test is prepared against the actual30 exporter and separate bounded AI/core fixture pools; passing evidence belongs in the frontend ledger, not this scenario inventory. Do not equate baseline creation or per-scenario assertions with a clean runtime/full gate.

Current production limitations: full profile/photo/readiness/registration/visibility/freshness flows remain other FE03 tasks. AI contract generation is not AI UI, and an unavailable executor never becomes a fictional successful job.
