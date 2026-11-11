# A01–A04 actual authentication scenarios

All browser rows require behavioral assertions plus named screenshots on mobile Chromium, mobile WebKit and desktop Chromium. Current matrix is in progress, not full acceptance.

| Scenario                                                     | Boundary evidence                                                                              | Screenshots                             |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- | --------------------------------------- |
| Guest / authenticated / server unavailable / network failure | Actual `/me` consumer, no automatic retry, no credentials exposed or persisted                 | guest/authenticated/unavailable/network |
| Six allowlisted callback failures                            | Only fixed copy and valid UUID diagnostic; query removed; identity still checked independently | one per code                            |
| Resume active/locked/expired/delivery-failed challenge       | Actor-owned status and exact server verify/resend capabilities                                 | one per state                           |
| Support-required reload                                      | Terminal outcome remains visible without verification action                                   | challenge-support-required              |
| Invalid institutional domain                                 | Draft preserved; no command sent                                                               | email-invalid                           |
| Actual guest                                                 | Real FastAPI 401 and PostgreSQL readiness                                                      | guest (full stack)                      |
| Actual signed-in/logout                                      | Secure HttpOnly session; CSRF rejection; UI sign-out and real revocation                       | authenticated + guest (full stack)      |

Still outstanding: loading intermediates, retry success, uncertain send/reconciliation, actual send/code flow, wrong code, quotas/deadlines, account restrictions, in-flight 401, keyboard/320px auth reflow, real callback browser redirects, explicit profile/registration completion when actual profile API exists. Unit evidence supplements these rows and does not replace browser screenshots. Google/email providers are not contacted by these tests; full-stack session fixtures are controlled and do not establish live provider compatibility.

Additional implemented browser cases: session loading/resolution; explicit retry from failed bootstrap; network-uncertain send reconciled through server-owned challenge; wrong-code outcome with server attempts remaining. Each has separate intermediate/final screenshots where appropriate. Real callback success/cancelled/provider-unavailable and real durable email delivery/verification/reload now run against FastAPI/PostgreSQL with controlled Google and email provider boundaries. The ordinary comparison run passed 18 full-stack cases. Synthetic diagnostic UUID is fixed in the isolated fixture for stable screenshots; production request-ID uniqueness and live provider compatibility are separate backend/external checks. Earlier outstanding list is historical for these completed additions; quotas, remaining account restriction/expiry/keyboard matrices and full FE02 gate remain pending.

Identity replacement regression: actual bootstrap account-ID changes clear verification drafts and
private mutation cache, including profile editing presentation. A late old-account send success/401/503
cannot refresh or sign out the replacement actor; callbacks are scoped to actor and component lifetime.
Unit tests cover all three outcomes, browser tests cover draft replacement and late401 across all
three projects with nine reviewed PNGs. These additions do not resolve the independent intermittent
font-watcher runtime gate, which remains open in the progress ledger.
