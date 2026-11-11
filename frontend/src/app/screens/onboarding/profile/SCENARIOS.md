# O01 profile draft — incremental implementation

Current bounded slice edits the display name through actual own-profile GET/PUT. It preserves other saved profile fields and revision, notifies the identity boundary on401/403, and never activates an account from a draft. Parent authentication owns entry/sign-out. The approved full O01/O02/O03 experience is unfinished: photo choice/crop/processing and task/goal/help setup follow; there is no pretend Continue/Discover action.

| Scenario                          | Behavioral assertion and screenshot                                                                         |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Initial loading → existing draft  | Controlled response gate; saved name appears only after GET                                                 |
| Versioned save → reload           | Correct actual payload/CSRF/idempotency; explicit saved status; reloaded server value                       |
| Uncertain result                  | Preserve draft/read-only field, no automatic retry, replay original key/body explicitly                     |
| Concurrent revision conflict      | Preserve draft, block overwrite, explicit reload adopts current revision                                    |
| Invalid name /320px keyboard      | No write; error/name/focus preserved; no horizontal overflow                                                |
| Read unavailable → explicit retry | No automatic retry/private server text; real loaded value after retry                                       |
| Save401                           | Identity revalidation, no private draft in guest screen                                                     |
| Real FastAPI/PostgreSQL           | Real Google/session/email verification with controlled providers, name PUT/read/reload, committed revision1 |

Each implemented row runs on mobile Chromium, mobile WebKit and desktop Chromium with named screenshots. Unit tests additionally validate malformed/nullable DTOs, exact same-origin photo URLs, mutation actor changes and missing fields. Query account replacement must use newly derived query options, not spread TanStack's defaulted queryHash. Read-only media display validation does not imply an implemented photo upload.

Remaining acceptance: photograph workflow, reference-data/language/optional-field editing, full study setup and real explicit registration/visibility now that actual27 is accepted; real open-keyboard/native device checks for the composed O01 experience. Current profile name layout is tested at320px/200% and all visual projects use reduced motion. No live Google/email/S3 calls or activation claim from draft tests.
