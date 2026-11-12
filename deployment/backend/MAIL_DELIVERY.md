# Peerly verification mail: operational diagnosis

Scope: APU Malaysia; Google login followed by a code to `mail.apu.edu.my`.
This offline helper diagnoses header-reported claims. It neither verifies SPF,
DKIM signatures or DMARC alignment, nor proves inbox delivery or current quarantine.
SMTP 250 and provider “delivered” mean acceptance/handoff, not inbox acceptance.
A manual staging grant/placeholder is never production email verification proof.

## Source-backed sending path

`backend/src/studymate/infrastructure/email/smtp.py` constructs From, To, Date,
Message-ID and plain-text verification mail. Both visible From and envelope sender
use `configuration.sender`; Message-ID uses the durable delivery UUID and sender
domain. Reply-To is optional. Submission uses aiosmtplib, certificate validation,
a five-second timeout and explicit STARTTLS or TLS. No local DKIM signing occurs
in this adapter; provider signing/return-path rewriting must be established from
a received sample and provider configuration. Reply-To and inbound MX forwarding
are not outbound authentication evidence.

`backend/src/studymate/config.py` defines SMTP configuration;
`deployment/staging/compose.yml` passes `PEERLY_SMTP_*` into `SMTP__*` fields.
`deployment/staging/stack.env.example` names smtp-relay.brevo.com:587/starttls.
These checked-in sources establish wiring/examples, not the active provider,
verified domain, signing configuration, production deployment or inbox receipt.
No actual credentials or environment files were inspected for this package.
Existing ImprovMX inbound forwarding does not establish outbound deliverability
or override APU Microsoft policy. Do not change provider on that assumption.

## Safe local use after integration

Use a recipient-side **header-only export**, ending with an empty line. Never
supply an entire message, message preview, body, OTP or credentials. Do not paste
real headers into chat, CI, issue trackers or shell arguments. The input remains
private and can contain identifying header values; the helper emits none of them.

```sh
python deployment/backend/mail_delivery_diagnostics.py < /private/recipient.headers
```

No arguments, network, DNS, environment/config reads, telemetry or dependencies.
CLI uses unbuffered stdin and reads one byte at a time through the first blank
line; it does not consume body bytes. Limit: 64 KiB total headers, 8 KiB per physical
line. LF/CRLF and folding are accepted; missing separator, malformed names,
non-ASCII/control bytes and oversize fail with a fixed error (exit 2). A header-only
export missing the separator must have an empty line added locally. APIs require
an unbuffered BinaryIO to avoid caller-side prefetch.

Output contains only fixed keys and allowlisted tokens, separately for each
Authentication-Results and filtering header. Missing headers produce empty lists;
unknown results become `unknown`; duplicates/conflicts remain visible. It ignores
ARC results and never chooses an authoritative hop. Authentication-Results with
comments/quotes/backslashes produce an empty claim object conservatively: this is
an unsupported syntax, not an authentication failure. Common legitimate headers
contain comments; obtain a trusted IT interpretation when the helper abstains.

- SPF/DKIM pass alone does not establish DMARC alignment. DMARC pass is only the
  header's authentication/alignment claim; no registrable-domain comparison is done.
- DMARC fail, none, temperror and permerror are distinct. Compauth softpass,
  bestguesspass and pass remain distinct and are not promoted to DMARC pass.
- `dmarc_action=quarantine` reports the header action, not tenant disposition.
  `SFV:SKQ` reports release from quarantine; it does not prove future delivery.
  SCL/SFV/CAT are reported classifications, never an inferred delivery verdict.
- Headers can be forged and earlier hops can disagree. Even all pass results can
  coexist with recipient policy quarantine. Output cannot certify authenticity.

## Operator evidence checklist

First inventory existing authorized connected/configured sources and prior
operational evidence. Check their availability before requesting additional evidence. Keep full trace identifiers and exact
addresses in restricted operational systems, never this helper's output or public
release notes. Do not fetch provider email content/previews or bodies.

1. Correlate an existing real verification attempt: UTC request/worker/provider
   handoff times and delivery UUID. In restricted tooling, the generated Message-ID
   can correlate the provider event and recipient trace. Distinguish SMTP accepted,
   deferred/bounced, remote-server accepted and recipient-confirmed placement.
2. Locate recipient-side original Authentication-Results (SPF, DKIM, DMARC,
   compauth), X-Forefront-Antispam-Report (SCL/SFV/CAT), and any organization SCL.
   Header source/hop trust and actual signing/envelope/From domains require a
   private trusted operator assessment; this helper intentionally outputs no domains.
   Provider-side headers alone cannot explain APU's final classification.
3. Check provider transactional event metadata for remote response/status and
   actual sending/signing domain configuration. If existing evidence is insufficient,
   request metadata-only trace from the configured provider owner. A Brevo example
   is not permission to access Brevo or proof that it is the active provider.
4. If university quarantine remains unexplained, ask authorized APU Microsoft 365
   IT to correlate the existing Message-ID/time privately in Exchange message trace
   and Defender quarantine, identify the actual policy/rule/verdict and recipient
   disposition, and assess legitimate false-positive remediation. User access and
   release rights depend on tenant policy. Ask for tenant-approved remediation,
   not blanket filtering bypass or a provider switch. No IT message is sent here.
5. Where trusted results show authentication failure, domain/provider owners must
   check actual SPF, DKIM and DMARC alignment/configuration before proposing a
   narrowly reviewed correction. Where results pass, investigate recipient policy
   and reputation with IT; repeated sends are not a diagnostic fix.

After authorized remediation, production readiness still requires a separately
approved real-email test on the production sending path: Google login, request a
fresh code, timely ordinary receipt at an actual APU student mailbox, successful
latest-code verification and expected application access. Record sanitized UTC
latency/outcome and correlated evidence privately; never record code, body, local
part, credentials or raw headers in ordinary logs. An IT release of an old message,
a manual verification grant, SMTP 250, a provider event, or this synthetic test
suite alone does not satisfy that acceptance. Run live tests only through an authorized operator and retain the evidence
privately.

## Official references

- [Microsoft header meanings](https://learn.microsoft.com/en-us/defender-office-365/message-headers-eop-mdo): authentication, SCL/SFV/CAT and SKQ semantics.
- [Microsoft authentication operations](https://learn.microsoft.com/en-us/defender-office-365/email-auth-sec-ops-guide): alignment and authentication interpretation.
- [Exchange message trace](https://learn.microsoft.com/en-us/exchange/monitoring/trace-an-email-message/message-trace-modern-eac): recipient-tenant tracing.
- [Microsoft admin quarantine](https://learn.microsoft.com/en-us/defender-office-365/manage-quarantined-messages-and-files): actual quarantine reason and disposition.
- [Brevo event logs](https://help.brevo.com/hc/en-us/articles/35699922048146-View-and-export-your-event-logs): delivered is recipient-server handoff, not an inbox guarantee; applicable only if Brevo is confirmed.
