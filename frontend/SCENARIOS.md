## F03 public feedback summary — implementation checkpoint

The actual Person surface now consumes the thresholded public summary. New
`person/feedback-summary.visual.spec.ts` defines five scenarios per required
browser project: building0/building2 (no rating cells), exact available counts and
explicit functional explanation, failed read plus explicit retry without writes,
and publicly_visible=false without disclosure. Their named image checkpoints are
required; baselines and browser acceptance are pending the current serialized
student feedback lease.31 guard/component units are green at unchanged95
thresholds. The generated optional default discriminator may be omitted on valid
responses; corrupt totals/thresholds still fail closed.401/403 propagate to the
actual parent session boundary, and actor/target replacement cancels old reads.
No individual note, identity, descriptor aggregate or proficiency score is
invented. A remount reads current server counts rather than treating a recent
cached summary as permanently current after feedback changes.

### F03 own profile summary and reflow

Actual activated Profile now consumes GET /me/feedback-summary with actor-scoped
QueryObserver/native cancellation, no new session query or private DTO mirror.
Both public and own summary matrices now contain18 cases each across required
projects,24 named image states per surface, including320px/200% text and keyboard
About expansion. Own private/non-public projection displays no aggregate;404 is
generic unavailable rather than an inferred hidden/deleted reason. Own31 and
Profile integration51 units pass unchanged95 thresholds. These browser scenarios
are authored/static checked; reference capture/review and ordinary comparison are
pending serialized browser availability. Existing Profile/Person references must
be reviewed for the intentional card addition. No current whole-gate claim.

### C02 empty drafts and validation timing

An empty unsent composer is valid draft state. Required-content validation remains
mandatory on explicit Send; edited invalid content reports its error before blur.
The UI uses public [TuiError.error](https://taiga-ui.dev/next/components/error/)
and existing Angular form submitted/dirty/invalid flags, without mirrored state,
fixed error height or pointer interception. Associated errors are included in the
textarea description. Deterministic empty-blur RED→GREEN and successful-reset/
invalid-edit regressions are covered in current125 feature units. A prior native
WebKit click miss remains causally unproven; one instrumented passing trace does
not establish its cause, and the global RO blocker is separate.
