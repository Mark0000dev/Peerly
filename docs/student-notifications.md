# Core student notification delivery

Core notifications cover confirmed messages, new requests and accepted connections. Payloads use fixed metadata-only previews, including “New message about your study request”; message bodies and device tokens are never preview fields. Provider acceptance is not proof of device display.

The authenticated student API provides PUT `/api/v1/me/notification-delivery` and GET `/api/v1/me/notification-delivery/{installation_id}`. Registration uses the existing cookie/Origin/CSRF guards, actor-scoped intent keys and expected versions. Capability flags mean configured transport availability, not OS permission or live provider health. The client must obtain actual permission and registration on its supported platform. No provider is configured by default.

Logout retains its existing 204/cookie-clearing contract. An optional `X-Notification-Installation` header receives `X-Notification-Retirement: retired|unconfirmed`; no header is required to retire enrollments belonging to the revoked session. A stale/foreign installation cannot be retired as that session's device. Retirement is atomic with session revocation, not a promise to recall a notification already submitted to a provider. Deletion and ban retire subscriptions and eligible work in their existing lifecycle transaction.

Delivery consumption is disabled until the owner explicitly activates its no-backfill cutoff. The API never starts a delivery worker. The separate `python -m studymate.student_notifications_worker run` command needs explicit matching API/worker envelope material and selected provider settings. `python -m studymate.student_notifications_worker activate --confirm-no-backfill` is a distinct owner release action; it never silently replays historical events. There is no automatic activation on worker startup. Worker database pool size is1 with no overflow; existing core/admission pools and2s transaction budgets are unchanged.

Durable event/recipient uniqueness and device attempt fencing prevent automatic replay of accepted or ambiguous submissions. Only definite provider nonacceptance retries, at most3attempts; cancellation/timeout after send begins remains UNKNOWN. Fresh authorization precedes send. Revocation cannot recall an already accepted provider submission.

## Migration compatibility

The released revisions are carried unchanged in order: `0060_report_triage -> 0061_native_login -> 0062_google_display -> 0063_student_notifications -> 0064_notification_subscriptions`. Revision0061 contributes table metadata only in this port; native-login application code and native-login API routes remain a separate feature and are not mounted. Revision0062's nullable provider display columns are represented in ORM metadata without changing Google callback identity or authority behavior. A future native-login port must reuse the existing `native_login_models.NativeAttemptRecord` mapping rather than register that table twice.

Actual PostgreSQL upgrade/constraint/concurrency acceptance and owner-controlled deployment schema compatibility remain required. An offline Alembic head or compiled PostgreSQL dialect DDL is not migration execution. HTTP/2 dependency additions reuse exact canonical pins/integrities (h2 4.4.1, hpack 4.2.0, hyperframe 6.1.0); dependency installation and actual provider configuration are separate release steps.

## Optional updates

The saved notification mode remains independent of OS permission. The existing optional policy primitive supports quiet22:00–08:00 in the explicit device IANA timezone, max1per local date and2across rolling7local dates, failing closed for unknown timezone or opt-out. This core port does not add optional event kinds, quota reservation, scheduling, email, marketing/news or partner-suggestion producers. Their event/channel contract remains undecided; the policy primitive alone is not optional delivery acceptance. Authentication/security email behavior is unchanged.
