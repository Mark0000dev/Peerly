# M02 actual human report review

Controlled browser definitions use the real parent route and leaf, actual59 DTOs and HTTP boundary fixtures. They are NOT live API acceptance; screenshot baselines await Halley serialized capture. No browser run or golden claim here.

| Boundary                                                                          | Authored definition / checkpoint                          |
| --------------------------------------------------------------------------------- | --------------------------------------------------------- |
| Empty, action/reason validation, local review without POST                        | review-empty / review-validation / review-before-record   |
| Explicit immutable CAS write, separately fetched head                             | review-stored                                             |
| Fifty-row anchored history, newer current, same-report draft, original provenance | review-anchored-history / review-earlier-provenance-draft |
| Unknown transport outcome, same body/key replay                                   | review-unknown / review-original-receipt                  |
| CAS conflict and explicit canonical reload                                        | review-conflict / review-conflict-fresh-state             |
| Read service failure and real403 retirement                                       | review-read-unavailable / review-authority-retired        |

Unit definitions cover original whitespace and Unicode scalar length, closed actions, lineage/provenance validation, malformed pagination and immutable replay with renewed canonical CSRF. Parent navigation guard definitions belong to Halley; leaf exposes actual confirmLeave and retires on actor/report change. Pending/loading,401, stale confirmation ownership and parent back/forward guard cases need the coordinated integration batch; do not call this list full acceptance. No image/photo, assignment, ban or user notification exists in this API. Private reason is never telemetry.
