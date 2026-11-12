# P02 saved notification preference: code-first final matrix

Source: approved P02 frames1–5 corrected to actual head52 PreferenceBody/Response.
Export NotificationPreferences from notification-preferences.ts; route
/profile/notifications, public canLeave():Promise<boolean>. Lead owns routing,
Profile links, shared helpers/session/query client, fixture namespaces/config.

| State/behavior                                                       | Authored unit/HTTP evidence                                             | Actual final boundary                                                                 |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Active verified preactivation account; no activation requirement     | Shared verified actor authority + component/query units                 | Real notification-pref Google/institution namespace                                   |
| Exactly messages_and_requests/all_updates; version0 unchosen default | DTO/enum units, HTTP default screenshot                                 | Real canonical current GET                                                            |
| Explicit save mode/expected_version with session CSRF+key            | Actual component wire assertions, HTTP saved/current screenshots        | Real PG explicit non-no-op version increment + canonical reload                       |
| Unknown save same immutable key/body, no new selection               | Bounded write + component units, HTTP unknown/replay screenshots        | No auto retry, optimistic save/delivery or automatic new key                          |
| CAS conflict current canonical read before new choice                | Component unit + HTTP conflict/current screenshots                      | Fresh read required; old replay receipt never overwrites newer query state            |
| Read/storage failure, session required, retry                        | Query abort + HTTP loaderror/denied screenshots                         | Fresh identity needed before command; preserve same-actor draft while pending/error   |
| Actor replacement/logout/destroy, late callbacks                     | Component/query lifetime tests authored                                 | Abort reads/local wait; remove owned mutations/private query, no late form population |
| Leave dirty or unconfirmed save                                      | Shared public canLeave contract                                         | Parent guard and final leave-dialog screenshots                                       |
| 320px/200%, reduced motion, keyboard/focus/overflow                  | HTTP narrow keyboard screenshot                                         | Three pinned projects and batch reference review                                      |
| Device permission denied/not-asked/on/unsupported                    | Not rendered as facts: delivery channel has no consumer in this preview | No permission call, token registration, fake grant, open-settings CTA or push proof   |

Mode is desired product choice, not two booleans, analytics/security-email opt-out,
OS permission, marketing consent or delivered notification. Extra updates copy
mentions partner suggestions/product news/promotions before explicit choice;
no quiet hours, frequency limit or email channel invented. Device delivery is
truthfully unavailable in this preview; in-app Requests/Chats counts continue.

notification-preferences.fullstack.visual.spec.ts uses lead-owned notification-pref
verified-student namespace, real current DTO/version, actual PUT and canonical
reload. Only existing controlled Google provider/inbox helper is intercepted;
no product API mocked. This source is not an executed or accepted PG/provider run.

Final candidate gates remain unchanged95allmetric units, static/build and one
browser+PG/reference batch, then staging smoke. No suites/captures launched here;
global ResizeObserver failures must not be filtered/masked or declared resolved.

## Design v2 implementation batch · 12 November 2026

Targets P02-Notifications1/2 actual enum choice and5 unsupported-delivery correction.
Preserved lead native AppBar/cards; added clear mode labels, public appearance binding,
readable secondary descriptions and all-side safe areas. Existing stable save-button
wrap remains. The device panel states preview delivery is unavailable; no claim about
OS permission, registration, quiet hours/frequency/email delivery or open-settings
capability is inferred. All desired-mode CAS/version/replay/session/draft/leave guards
are unchanged. No analytics consent/toggle or extra preference field is introduced.

Original not-asked/denied/on states remain API/runtime-dependent, not simulated as
facts in production. Matched source/reference captures and affected acceptance await
lead combined batch; historical test receipts do not accept this changed layout.
