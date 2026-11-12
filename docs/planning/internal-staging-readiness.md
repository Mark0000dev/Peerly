# Internal staging readiness

## Current state — 12 November 2026

Internal staging remains at core `dd7a24d`, frontend `5f60d07` and database
`0054_identity_recreation`. The deployed hotfixes preserve verified S3 TLS,
explicit photo-transfer recovery, guarded shared identity reads and bounded
database lock waits. The owner-authenticated browser confirmed four parallel
profile/onboarding reads all return200, versus three500 responses before the
identity-lock correction. This is scoped acceptance, not full-app completion.
The subsequent photo-resume fix preserves its existing expiry writes; eight
real PostgreSQL checks pass, and five parallel authenticated browser reads
including photo resumption all return200. Other shared readers remain guarded.

The unchanged isolated AI deployment was reattested on the actual host without
restarting it, reading AI authentication material or making another model call.
The original provider-proof date remains11November09:02UTC. Root-only renewal
controls preserve immutable receipt fields and require matched durable audit
pairs. The actual systemd service passed; its six-hour timer is active/enabled,
next due12November06:00UTC. Current receipt expires13November02:38UTC. The worker
retained its accepted processes and a fresh ready/idle heartbeat. Any future AI
deployment change invalidates this anchor and requires fresh acceptance.

Canonical core `a12c9bf` is published on the staging feature branch and undergoing
CI43155409167; it is not deployed. Its predecessor failed eight checks; all eight
now pass focused regression checks. The refreshed54-to58 checklist preserves all
live fixes and targets the already published full frontend `2df3815`. A protected
point-in-time staging backup has passed a complete archive read; it must never
overwrite newer user history. Operator verification/history at revision58 is in
this CI candidate; human moderation and design-v2 corrections remain active
implementation batches. Technical
monitoring and encrypted telemetry archival are running; remaining provider,
delivery, visual and external-pilot acceptance must still be completed.

Parent operational receipts are outside Git under sibling
`.peerly-ops/canonical-release-20261112/`. No credentials, backup data, filled
runtime configuration or user content belongs in this document.

## Historical checkpoint — 10 November 2026

The internal core stack is deployed at https://peerly-staging.aleksei-orlov.dev through Portainer stack4. API, frontend, email, media, request-expiry, change-publication, dedicated AI worker and restricted AI egress services are running. HTTPS is valid; health/readiness return200. Managed `peerly_staging` is at `0052_student_support` with106 public tables. Google start redirects to the correct provider/callback with a Secure/HttpOnly transaction cookie; published Terms/Privacy return200. Actual SMTP TLS/authentication succeeds, without a test message being sent.

Frontend image was built, smoked and published by successful CI42740387262. Backend now uses successful full CI42748052835; AI uses successful image CI42796764491 with separately recorded focused runtime fixes and real-provider acceptance. Exact digests and receipts are recorded below. No main push or unrelated service modification occurred.

Current deployment is fully running for internal team testing. Canonical CI backend replaced the temporary diagnostic image; actual AI isolation/device authentication/managed refresh/text+image validation and durable worker readiness have passed. The authorised Telegram announcement was sent once to Peerly Dev (message3). Real Google callbacks created two accounts and SMTP accepted two verification messages. Institutional verification/registration/profile/media/chat browser flows still need the team’s manual pass; no completed institutional bindings were present at this check. Operator expansion, complete observability and external-student release acceptance remain unfinished.

ResizeObserver remains an explicit known issue, released by the owner from internal staging preparation/deployment blocking. Nine bounded production-image browser scenarios passed without the error; that is not a causal fix or a full runtime-green claim. Remote public-browser smoke is in progress. Historical entries below retain their original inspection-time state and must not override this current summary.

Owner priority: finish student functionality and real-service integration, then deploy an internal team/hackathon staging environment. Operator UI expansion is deferred. Production and external student invitations are outside this staging authorisation.

## Read-only infrastructure inspection — 8 November 2026

- Portainer authentication and environment listing succeeded; environment 1 is online. Docker is standalone, x86_64, two CPUs and approximately 4 GB RAM. Existing applications are running. Traefik is attached to the existing `proxy` bridge; management/socket networks are separate. No containers, networks or stacks were changed.
- Cloud.ru staging S3 authenticated `HeadBucket` succeeded using the bucket name from its provided hostname. The supplied bucket UUID is not the S3 `Bucket` argument: using that UUID returned `NoSuchBucket`.
- Per official Cloud.ru documentation, use `https://s3.cloud.ru`, signing region `ru-central-1`, path addressing and a tenant-prefixed access identifier. Credentials stay in the external secrets file.
- Staging has no CORS configuration. Browser direct upload will require an explicit origin/method/header policy before acceptance.
- Bucket versioning is not enabled. No bucket policy was returned. This alone does not prove that all objects are private; inspect ACL/public access and test a synthetic object's anonymous denial separately.
- No S3 objects were uploaded or deleted; production/archive buckets were not accessed. No SMTP/Telegram messages were sent. No deployment occurred during this inspection.

Sources: [Cloud.ru S3 API setup](https://cloud.ru/docs/s3e/ug/topics/api__getting-started), [Cloud.ru addressing/client setup](https://cloud.ru/docs/s3e/ug/topics/tools__rclone).

## Next integration work

1. Inspect available server memory/disk and proxy routing without disrupting existing workloads; budget containers for a shared 4 GB host.
2. Validate managed staging PostgreSQL, TLS, roles and migration access.
3. Configure staging-only S3 CORS; test synthetic signed upload/read and anonymous denial, preserving evidence and deleting only owned disposable probe objects if created.
4. Confirm sender and reply address; validate SMTP and approved-recipient delivery without using student data.
5. Prepare staging image publication/pull, isolated stack, secrets injection, migrations, TLS and health checks.
6. Validate Google login and isolated Codex authorisation in the actual staging runtime.
7. Keep known runtime defects explicit. Internal team diagnostics precede external pilot acceptance; full monitoring/dashboards/alerts and operational checks are required before inviting external users.

No secret values or authentication responses belong in this document or repository.

## Staging S3 integration — 8 November 2026

After the read-only inspection, configured staging bucket CORS for the exact staging origin extracted from the provided Google callback: POST only, content-type header, 600-second preflight cache. No wildcard origin, application credentials or production/archive changes.

Used the actual `S3MediaStorage.upload_access` adapter to sign a five-minute multipart POST for a disposable two-pixel PNG (79 bytes). Provider returned HTTP200 with the expected Access-Control-Allow-Origin. The actual adapter read back identical bytes. Anonymous object GET returned403. The uniquely owned disposable transport object was deleted successfully in cleanup. This confirms provider interoperability for this synthetic object; it is not browser UI, large-upload, all-object ACL or full media-worker acceptance. Presigned fields and credentials were not logged.

Versioning remains disabled. Staging bucket privacy was demonstrated for the owned probe; archive retention/versioning/restore policy still needs an explicit operational design before production data.

## Staging PostgreSQL TLS prerequisite — 8 November 2026

**Superseded for internal staging by the owner's explicit instruction on 9 November:** use ordinary non-TLS connectivity to the supplied Peerly database, not `default_db`; do not change the instance-wide security setting because other projects share this instance. The historical TLS inspection below is retained as evidence, not a current request for CA material.

Actual read-only connection to `peerly_staging` with its supplied staging role succeeded with TLS explicitly disabled. PostgreSQL reports16.8. The role has database CREATE and public-schema CREATE privileges; public schema contains zero visible tables. No migrations/data writes were performed. Production/default databases were not modified. CA/hostname provisioning is no longer an internal-staging blocker under this explicit owner decision.

Connection using the supplied IP and normal certificate verification stops at TLS with a self-signed certificate error. A separate credential-free PostgreSQL SSL handshake inspected only the public certificate: it is self-issued and identifies an internal DNS hostname, not the supplied IP. No SQL, migration or database credentials were sent over an unverified connection.

Requested provider-issued CA/server trust material and the supported connection hostname or official connection instructions from the owner. Do not silently replace verified TLS with `sslmode=require` or disable certificate checks. Database names, role grants and migration privileges remain unverified until the trusted connection is available.

## GitHub/GHCR and SMTP — 9 November 2026

- Published the immutable backend-only candidate to `feature/peerly-staging-backend`, commit `49b2ecee86d07e01227e060eec7cb31cc4d5e99e`. Shared implementation worktree/index and main were unchanged. A separate detached worktree ensured push checks were scoped to the actual checkpoint rather than unrelated frontend WIP.
- GitHub Backend workflow started at <https://github.com/Mark0000dev/StudyMate-AI/actions/runs/42536610060>; completion is not yet verified here.
- Published the previously built/smoke-tested backend image as `ghcr.io/lemonades-runner/peerly-backend:staging-49b2ecee86d0`; manifest digest `sha256:d21c08ad3281bcddcab54f6b390c2432f7846af27a8e58a7bec8b9dbe0084a87`. Use the digest for deployment. This does not include later first-boot provisioning CLI work.
- Registry authentication used a temporary Docker configuration removed after publication. GitHub credentials were supplied through a temporary askpass helper without embedding tokens in URLs or shell arguments. No credential files were committed.
- Actual Brevo SMTP connection verified TLS, STARTTLS and successful authentication. Zero messages sent; sender validation and real inbox delivery remain unverified.
- No staging stack has been deployed yet. PostgreSQL trust/hostname, first-boot policy/catalogue inputs, frontend image, environment secrets and full startup/provider smoke remain on the critical path.

## Required final delivery workflow — owner instruction, 9 November 2026

The first staging backend image was built/smoke-tested locally and pushed directly to GHCR. The GitHub Backend workflow validates the branch; it did not publish that image. The owner explicitly accepts this temporary staging approach, but requires repository cleanup and pipeline publication before project completion.

Final CI/CD must run required backend/frontend checks, build images from the exact checked commit, publish immutable commit-associated tags/digests to GHCR, and deploy the selected verified digests using environment-managed credentials. Record source/image provenance and recovery/rollback procedures. Keep application secrets, local exports, diagnostic artifacts and temporary staging files outside version control. Reconcile temporary workflows/runbooks and split reviewable branch changes; never push directly to main. Direct local publication is not the final release process or evidence of a CI-built image.

## Package placement correction — 9 November 2026

GitHub API confirmed the first local-push package is private under `lemonades-runner`, with `repository: null`. It therefore does not appear in the project repository's Packages section. Its digest still exists and is a valid temporary staging artifact; it is not a repository-linked release package.

Pushed workflow-only commit `faf029d1df6480fcb8186035bac469ee746dafad` on the same staging branch. Backend quality gates a separate least-privilege publication job using the repository's ephemeral GITHUB_TOKEN, target `ghcr.io/mark0000dev/peerly-backend`, immutable `staging-$GITHUB_SHA` tag, and OCI source/revision labels linking to `Mark0000dev/StudyMate-AI`. The job builds checked source and probes nonroot/read-only production imports before publication; temporary registry credentials are removed. Actionlint passes. Run <https://github.com/Mark0000dev/StudyMate-AI/actions/runs/42538737271> has started; publication/link visibility is not yet verified. The previous redundant branch-only validation run was superseded; do not count its cancellation as a successful gate.

Retain the old private package until a verified replacement exists and staging references have moved to the replacement digest. Final repository cleanup and complete frontend/deployment pipelines remain required; this backend workflow alone is not the finished CI/CD system.

### Verified pipeline publication

Run42538737271 completed successfully: Backend quality and Publish staging backend both passed. Downloaded quality log records **3642 passed in1703.11s**, including the repaired package marker in the checked commit. This is a single full-green CI run for the frozen head49 checkpoint, not a claim about later head50/bootstrap/frontend changes. Local log evidence: `/tmp/peerly-github-backend-42538737271-quality.log`.

GitHub API confirms `Mark0000dev` owns the new public `peerly-backend` package and its repository is `Mark0000dev/StudyMate-AI`. Package page: <https://github.com/users/Mark0000dev/packages/container/package/peerly-backend>. Published tag `staging-faf029d1df6480fcb8186035bac469ee746dafad`, digest `sha256:f4284196547c866a16f1123cc73f744cb30def36b86904385cbcc77328f7e64f`. This is the repository-linked CI-built replacement; no deployment has yet been made from it. The original robot-account package remains retained pending reference cleanup.

## Owner departure and staging announcement — 9 November 2026

The owner explicitly requests a Telegram announcement in the previously supplied developer group once the complete internal staging deployment is ready for phone testing. Parent owns this send. Do not announce a partial deployment, image publication or successful build as a complete staging environment. First verify the HTTPS URL, configured API/workers, migration/bootstrap state and representative student smoke; distinguish remaining restrictions honestly in the announcement. Do not include credentials, device-auth codes or private data in the group message.

SMTP From and Reply-To addresses are now present in the external secrets file; do not ask for them again. Sender/domain validation and delivery still need real acceptance. Core infrastructure access is available; the approved knowledge-area catalogue supersedes course-name input; eventual owner-interactive Codex device authorisation remains a separate dependency. Device authorisation should be requested only when the dedicated isolated runtime is ready; it may be completed from the owner's phone.


## Real staging database first boot — 9 November 2026

Applied the immutable accepted head50 bootstrap supplement to the provided `peerly_staging` database only, using the owner's explicit non-TLS choice. The first migration operation exceeded a 180-second administrative timeout; inspection confirmed complete transactional rollback, zero public tables and zero leftover sessions. The same source was rerun with a 900-second remote-operation limit and completed. No production/default database or shared-instance security setting was changed.

The schema now contains98 public tables. Explicitly applied the validated `policies.v1.json` (two authored internal staging documents) and `catalogue.v1.json` (ten self-declared knowledge areas/four aliases). Neither application startup nor this import created a student account, grant or registration receipt. Private first-boot logs and receipt are outside Git at `/tmp/peerly-staging-firstboot-receipt.json`; input SHA256 values are recorded there. Later code-only head51/52 changes are not applied yet. Application/API/workers have not been deployed as part of this operation.

Prepared generated, distinct envelope/browser/code secrets and service configuration outside the repository in a mode0600 runtime JSON file. Values were not printed. Frontend Dockerfile, default-deny build context, static Nginx route handling and resource-bounded staging Compose/runbook are authored but deliberately await the code-complete acceptance batch rather than repeated intermediate builds.

## Monitoring host read-only capacity inspection

Existing SSH access works. The observed x86_64 host has about4GB RAM, about0.57GB available and about2GB root-filesystem free at inspection time. Docker listing confirms Prometheus, Grafana, Loki and Umami names/images. Alertmanager, Tempo, OTel Collector and Alloy were not found in that Docker listing; this does not prove absence of host-installed services. No services/configuration were changed. Avoid placing an unbudgeted trace backend or archive on this nearly full host; use the planned private S3 archive and measured capacity before external pilot acceptance.


## Prepared ingress and resource configuration

Read-only Traefik inspection resolved the actual HTTPS entrypoint, ACME resolver and exact ingress-network IP into the private staging runtime configuration. No container/network/proxy command was changed. The prepared API trusts that exact proxy identity rather than every address on the shared network; revalidate it after proxy replacement. Filled runtime settings remain outside Git.

## 10 November: proceed with internal diagnostic staging

Owner explicitly released unresolved ResizeObserver from the preparation/deployment critical path. Preserve the diagnostic and assess production-build visible/functional effects; external release requirements remain unchanged. No observer suppression or speculative patch was adopted.

Published backend source checkpoint `be96dbf46baa3796e50bc270ec666bfa5e599c61` to `feature/peerly-staging-backend`, never main. It imports the verified 1,051-file corrected immutable head52 snapshot (manifest `70614a8fc73785313331ae6c665368a628fe05db30cf9267100b3841afe90076`). Fresh full CI and then conditional GHCR publication started: https://github.com/Mark0000dev/StudyMate-AI/actions/runs/42739543641 . This is a running workflow, not a successful image or deployed-service claim.

Private staging environment successfully passed `docker compose config --quiet` against the current stack with digest-shaped image placeholders; credentials were not printed. Actual final image digests remain to be selected. Local backend/frontend/AI production-image build and credential-free runtime proof tasks are active, with production-browser impact assessment separate from the known strict runtime gate.

Current host read-only preflight: two CPUs, 3.82 GiB physical memory, 11 existing unrelated running containers, approximately 760 MiB summed working container memory, no existing Peerly containers. This is not host MemAvailable or a final fit guarantee; retain initial limits and observe actual load. No existing container was changed.

Actual SMTP STARTTLS with certificate validation and supplied staging credentials authenticated successfully (235). No email was sent. Staging DNS resolves; pre-router TLS currently returns unrecognized-name, so verify certificate issuance again after the staging Traefik router exists. This is not an existing valid staging HTTPS receipt.

Actual staging migration completed successfully from the verified current local production image `sha256:e9609cb8763f44831d23a826d4146d8641f328cf1b46c880e33ec78be63472ec`. Read-only follow-up confirmed `current_database() = peerly_staging`, Alembic head `0052_student_support`, 106 public tables. Private receipt `/tmp/peerly-staging-head52-migration-receipt.json`, private migration log `/tmp/peerly-staging-head52-migration.log`. No production/default database or instance-wide TLS setting changed. This closes the pending51/52 staging migration step, not application deployment or AI readiness.

Actual deployment: Portainer standalone stack `peerly-staging`, ID4/endpoint1, created with API/frontend/email/media/requests/change-publication services. No existing unrelated container was changed. Frontend is CI-published commit `40bfddc964cac20ebc4738439b27f638ec9d5634`, run https://github.com/Mark0000dev/StudyMate-AI/actions/runs/42740387262 (success), digest `sha256:e03bb824448ba71133a0dfa9403bfb993ea3bad75ffdf24cc1c7695536e939eb`. Backend uses explicitly temporary local diagnostic publication `ghcr.io/mark0000dev/peerly-backend@sha256:0366ee9239ae9475918d3a69fd703e71763a87fc454857c073bc873c57b481f3` from the tested final image while full CI42739543641 is still running. Replace with canonical successful CI image afterward; do not describe the temporary backend publication as CI-built.

Traefik obtained a valid staging certificate via successful HTTP-01. Follow-up HTTPS checks: `/healthz`200, `/api/health`200, `/api/ready`200, root/profile documents200, unauthenticated `/api/v1/me`401. First checks during router/startup transition returned404 and are retained, subsequent health/readiness200 verified. Google start returns303 to accounts.google.com with exact staging callback and Secure/HttpOnly transaction cookie. Actual published Terms and Privacy return200. No personal Google login, membership verification, student actions or real AI inference proved yet; no Telegram announcement sent.

## Actual AI runtime boundary — SSH continuation

Owner supplied staging SSH access. Parent authenticated and verified the SSH host controls the exact same Docker engine as Portainer. Host real-UID thread counts were10001=54 and10002=0, confirming why UID-global NPROC32 cannot be shared with core services. AI now uses dedicated10002; core stays10001.

Installed only named enforcing AppArmor profile `peerly-ai-worker-v1`; no global reload/default-profile replacement or unrelated service restart. Initial profile hash8b52850e… passed outer isolation. Actual kernel audit identified finite UsrMerge bind-source/target mismatch; reviewed8-rule delta produced profile SHA256 `f324bdbd6bde005ca5b04a04a4905c0d3f2f7039afe4bbbabd82edf0b5f9e20a`. Actual-host proof then passed outer and native nested helper controls. Exact evidence `/tmp/peerly-ai-remote-profile-proof-evidence.json`. No generic mount, privileged/unconfined execution or global sysctl change was used.

AI image CI42744792917 succeeded for commit7abd510e0fd4a0216d97200bab07b830e324e5ed, digest `sha256:56ebd5499330f626806c17636477e3b462c7f7cd91cd0dc69e6cbcd7df3dbfb1`. Gateway CI42744567404 succeeded, digest `sha256:13b1cb822e172c7ddf5db1d085272d13791e28bb450893d8d8735ec2947fa8b2`; Portainer stack5 `peerly-ai-egress` deployed with no host ports. Actual gateway proof verified TLS certificates for the three allowed domains and fixed PostgreSQL reachability, rejecting unknown SNI/plaintext CONNECT/wrong ports/direct public IP/external DNS. `/tmp/peerly-ai-actual-transport-proof.json`.

Final persistent AI container `peerly-ai-staging-worker` started with empty dedicated credentials volume, private-only network, named AppArmor/proc-only/explicit seccomp/resource bounds, and owner-controlled provisioning hold. Fresh proof executed inside that actual persistent namespace passed; a private containment receipt is installed. No model jobs admitted. Dedicated native device authentication started after receipt validation, and the one-time owner action was requested directly in chat. No code/token is recorded here. Real model/text/image/refresh validation and provider receipt remain pending.

Fresh full backend CI42739543641 ended3898pass/2fail in49m17s; publication skipped. Both failures were bounded test-expectation issues, not product-source changes: aggregate SSE budget did not cover unchanged composed legal deadlines; burst saturation falsely required admission under rejection-permitted overload. Exact2-file fixes passed18 adjacent stream checks and2 saturation/heartbeat checks. Selective commit9511bf38d5e10ccf8a49ee3d6ad0fb3b628b5b2d pushed for background final CI; temporary staged application source remains unchanged. No fresh full-green claim yet.

## Internal staging live — final AI activation, 10 November

Core backend was promoted to successful full CI42748052835, source9511bf38d5e10ccf8a49ee3d6ad0fb3b628b5b2d, digest `sha256:a74c19b87fb30573efc84d87862740842f9308bf9dea221864842b336fd04ce0`. Frontend remains successful CI42740387262 digest e03bb824…. Temporary diagnostic backend is no longer selected for the live core stack.

Actual CLI lifecycle exposed asynchronous SIGKILL/group-reap false uncertainty. Focused84 checks passed for the shared5-second physical-stop confirmation fix; no early slot/cache release was introduced. Actual full turns also exhausted PID32 while loading unwanted AGENTS.md instructions. Pinned-source evidence showed public `project_doc_max_bytes=0` returns before sandbox lookup; bounded causal Subject/Photo tests passed without raising PID/CPU/RAM limits. The final policy contains that one fixed setting.

Final AI image CI42796764491/source95d2df74f193d70d10ffcc86a99a4db06dae448b succeeded, digest `sha256:5b9a469ac59ed3d0768536495a668e3dfa611409a6af13ad2159c3e916938ac1`. CI verified actual image bytes for process module SHA0ec98bd8… and policy module SHA0aadeddd…. Canonical policy digest `ee0382dae2d63e2bb64b1ee778cc15388aa8d58e21670cc8eb2f099a892a1bf8`. Fresh final-container proof passed before restoring the previously authorised dedicated credential cache; no second owner login, developer-home mount or credential import occurred.

On that exact canonical image/policy, actual managed credential refresh and fresh-context reuse passed. All3 sequential real-provider typed tasks passed: ClarifiedGoal, SubjectSuggestions, PhotoAssessment. The image was a generated in-memory JPEG, not a claimed live S3 user-photo flow. Provider acceptance and private activation were installed atomically in the same PID/network/cgroup; no model calls or SQL admission occurred before this acceptance. Runtime is now `ready`, heartbeat fresh, execution slot free. Actual acceptance resource counters: pids peak32, denied-by-cgroup events0, memory peak186241024 bytes under1GiB, CPU0.5; these are bounded smoke measurements, not a500-user real inference capacity claim.

Auth tokens/private bindings/config remain in the dedicated protected host/volume paths, never Git/ordinary logs/chat. Public provisioning helpers reused the fixed production stop routine after an explicitly confirmed-stop cache recovery; no uncertainty state was blindly deleted or retried.

Final HTTPS checks returned200 for root/health/readiness/published Terms/Privacy. Read-only actual integration counters: accounts2, external identities2, delivered-outbox2, institutional bindings0, registration receipts0, profiles0, photos0. This confirms actual Google callbacks and SMTP handoff, not completed user inbox verification or end-to-end profile/chat/media acceptance. The internal-team announcement explicitly requests those manual flows and excludes external student rollout. Telegram Peerly Dev message3 delivery was acknowledged; no duplicate announcement sent.

## Live test feedback — Outlook quarantine and fresh account generations

Owner reports Microsoft campus quarantine of verification messages and inability to create a fresh account after self-deletion. Operators are paused for these student fixes. Header evidence requested: Authentication-Results, X-Forefront-Antispam-Report and DKIM d/s, without OTP/body/recipient. Do not infer that SMTP outbox delivered means user inbox delivery.

Read-only public DNS checks found both Brevo DKIM CNAME selectors and their public key targets present for notify.aleksei-orlov.dev, plus a single DMARC p=none/rua record. Root domain SPF currently serves ImprovMX; it was not changed. The supplied secret is SMTP-specific, not a Brevo REST API credential, so domain/signing state was not queried using an unrelated key. Authentication actually applied to the quarantined message remains unknown until headers. These facts are not a deliverability fix claim. Official Brevo guidance says shared-IP domain authentication does not require adding SPF/MX yourself; do not blindly alter root SPF.

Frontend verification/help work now distinguishes accepted by mail service from inbox placement and links https://security.microsoft.com/quarantine with tenant-permission/release caveats. It retains real resend/expiry authority and support fallback. SMTP header polish uses the Peerly display name while preserving bare envelope sender, Reply-To, TLS and deterministic Message-ID; it is not claimed to change Microsoft's verdict.

Fresh account generations require code plus database changes: historical identity/mail associations are retained, active claims use partial uniqueness, and deletion retires claims atomically. Old sessions/history never transfer. New immutable policies.v2.json prepared/validated for the changed behavior; deployed v1 remains unchanged. Publish v2 only alongside the actual recreation fix, with informational policy updates rather than forced reacceptance of existing accounts.

Primary references: https://learn.microsoft.com/en-us/defender-office-365/quarantine-end-user ; https://help.brevo.com/hc/en-us/articles/12163873383186-Authenticate-your-domain-with-Brevo-Brevo-code-DKIM-DMARC ; https://help.brevo.com/hc/en-us/articles/36041739642642-Troubleshooting-Deliverability-issues-with-Microsoft-Outlook-Hotmail-Live-MSN .

### 10 November — deployed mail-delivery guidance

Frontend `3734199dccfaf1c0b95683b60418eea00e31e00b`, CI run42806273808 successful, image `ghcr.io/mark0000dev/peerly-frontend@sha256:57e990c476340e78f3df1ea69eb59fb5579d1b594cd78e43b955fbcd2271436b` is live in stack4. Root/help/scripts and API health/readiness return200. The six selected production files distinguish queue/sending/SMTP acceptance from inbox delivery and explain Microsoft quarantine permissions/help. Accepted1500 unit tests, unchanged95% coverage floors,39 ordinary screenshot comparisons and strict static/build gates belong to the frozen OTP handoff. This does not establish that Microsoft inbox placement is repaired. Actual quarantine authentication/antispam headers are still needed; no DNS or provider-policy mutation was made. Backend and separately provisioned AI image were unchanged by this rollout.

### 10 November — fresh account after deletion deployed

Backend commit `a828a8a376950c32f45e62fb9659622a2afa0a52` is live as internal diagnostic image `ghcr.io/mark0000dev/peerly-backend@sha256:cc5e8da572ebc81363aad3d75f7261af90e18686f496e74d12488bbdbfc09f2e`. Local publication of the exact committed image is temporary while full unchanged CI run42807085513 executes. No full-CI-green claim yet. Targeted acceptance is186 distinct identity cases (126unit+16PG+44PG split), plus38 SMTP regressions and strict source/static checks. Three real-PG account generations and52→53→54 migration passed.

Actual staging migration ran with API and four core workers quiesced. Head is `0054_identity_recreation`; three account and three external-identity records, one deleted account, and all pre-existing identity/mailbox/registration ownership digests were retained unchanged. One actual deleted Google claim was retired from its actual deletion source; zero invalid retirement links. API and four workers resumed on the new image, health/readiness200, isolated AI heartbeat remains fresh on its unchanged image. Portainer returned before replacement containers were visible; verification resumed after they started, without rerunning migration.

Immutable Terms/Privacy `internal-2026-11-10-v2` were explicitly published (two new documents), confirmed by both public policy APIs; v1 documents/old receipts were not edited. Fresh login creates a distinct unverified actor, requires fresh registration/mailbox proof and restores no previous sessions/content/roles. Historical bans and active-claim uniqueness remain enforced. The old binary is unsafe after new generations exist; use an identity-aware forward fix, never a history purge or blind binary downgrade. SMTP display name/body polish is deployed but actual Microsoft inbox placement remains unproven pending quarantine headers. No live test emails were sent by the deployment.

### 10 November — fresh-account UI candidate

Two production HTML templates now describe fresh registration rather than claiming Google sign-in is permanently blocked. Targeted32 behavior regressions and15 ordinary screenshot comparisons passed;30 changed references were reviewed. Commit `6d1fe2d8446e95c0e555fe331d0a517be0fee942` built successfully but its CI smoke hit ConnectionResetError during nginx first250ms; this was a missing startup-retry case, not evidence of a passing smoke. Commit `4f58b426e6e8c031aabb6f100ed490f90e40c575` adds that exception only to the existing45-second startup wait, with all later exact responses/security assertions unchanged. Actionlint passed; CI42807810466 passed and published image `ghcr.io/mark0000dev/peerly-frontend@sha256:5aa27097e141f124d19ebd71f821a3c200152d31d92ad71d747d8d4444144b4c`. Deployment verification follows separately. No full frontend matrix was repeated for this copy change.

Final rollout receipt: the frontend5aa270 immutable digest is verified in the running staging container; root/onboarding/APIhealth/readiness return200, Terms and Privacy both expose `internal-2026-11-10-v2`. BackendA828/cc5e8d and isolated AI were unchanged during this frontend rollout. Parent final receipts are `/tmp/peerly-fresh-account-final-smoke.json`, `/tmp/peerly-identity-deployed.json`, `/tmp/peerly-identity-runtime-smoke.json`; no credentials or private student content are included. Owner can retry real Google login after deletion. Actual university Outlook inbox-placement diagnosis is pending the requested message authentication/antispam headers, not considered repaired.

### 10 November — owner-approved staging verification applied

All four current active accounts are now verified: two actual submitted addresses and two explicitly owner-approved UUID-derived staging placeholders. One deleted account remains retained and untouched; total accounts5, active4, verified4. Command executed SHA6ae9b5d3fdf8f8d5de48043d545fe6c9063927e62e4ad2a78eb9fd1aaf2681c2 with private stdin, actualplan4eligible then4applied, canonicalmanual events4, noOTPconsumption/noemail send/noforeground activity. No new admission model/DDL/API/image was needed. See manual-staging-verification.md; private account manifests/receipts stay outsideGit0600. New registrations are not automatically verified. Owner also released idle developers to resume existing operator screens; operator manual-verification UI remains a later expansion.

Backend CI42807085513 completed with3921passed/2failed and96% coverage: the two failing historical-migration fixtures wrote the new retired_at ORM column into old schemas. Both fixtures have now been corrected with version-compatible explicit Core seeding; original assertions are unchanged and the two affected real-PG tests pass. This is not a green full-CI claim; publication of the corrective checkpoint is coordinated separately.

Reusable-command checkpoint `74e04a7f88c2bb6cfabfa51b009ee75fa4cfb618` is pushed only to `feature/peerly-staging-backend`; main is unchanged. Includes strict-clean commandSHA0857f31ed1ffaff775feb9c7629fb790f102076d05c585fd76b7799a6461875d,8 backend unit+5 actualPG tests, ordinary makecheck enforcement, reproducible root namespace imports, both historical fixture repairs and operator runbook. Exact selective publication candidate passed full strict mypy1040sourcefiles and strictRuff/format1042files, plus scoped13cases6.84s. Full CI42825022979 is running separately; no green full-CI claim. Actual live operation remains executed6ae9 receipt, not rerun by publication/format cleanup; existingA828 core image and4verified accounts remain unchanged. Operator shared integration is released back to Noether/Plato/Halley; technical monitoring candidate is being validated independently by Nash.
