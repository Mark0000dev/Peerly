# Mascot production motion proof — 11 November 2026

This is a bounded artwork/consumer acceptance, not the mandatory all-screen
design-v2 fidelity review. That review remains pending in
`DESIGN-V2-FIDELITY-INVENTORY.md`. Existing visual goldens do not establish design
compliance. The known aggregate ResizeObserver issue remains separate and open.

## Source and supported mechanism

The old six mascot SVGs were static derivatives with the supplied animation style
and class hooks removed. The six originals are restored byte-for-byte, with
provenance in `src/assets/brand/PROVENANCE.md`. Only Home and Onboarding consume
these images. Native `picture/source media` chooses the preserved static vectors
for reduced motion; normal mode selects the original artwork. No animation store,
Taiga override, dependency change, CSS timing override or forced animation exists.
Onboarding changes are decorative image markup only; OTP/auth text and bindings
are preserved.

The reduced-motion fallback is intentional: in the initial native browser proof,
the page's emulated reduced-motion preference did not stop the external SVG image,
although a top-level SVG document correctly disabled all animations. Native
picture selection avoids relying on propagation into the separate image document.

## Production boundary and diagnostics

The local diagnostic nginx image is
`sha256:19555b985dfb23b8424a615e448165afbb96f34ffdceadecec8fa165e270f6e4`.
It was built from the parent's clean publication commit
`7a755f3992e67d458e76d9445eb3c64311df2d64` plus the explicitly authorised 13-file
fallback delta. It is not a newly committed or deployed release. The source
selection receipt and raw logs are under sibling
`.peerly-ops/frontend-client-observations-20261111/picture-fallback-delta/`.

`npm run test:mascot-motion -- --origin <owned-image-origin> --output <artifacts>
--webkit-endpoint <owned-official-playwright-endpoint>` exercises the three pinned
browser projects in both motion modes. It checks actual HTTP SVG bytes/hashes,
native selected sources, full-viewport PNGs, loaded assets, stable unclipped outer
geometry and all native page/console errors. All six artwork variants also appear
in an explicitly synthetic asset worksheet; this is not an invented product page.
Reduced motion requires zero changed pixels across frames and zero-difference
reviewed references; normal motion requires changed pixels within each mascot.

Consecutive screenshot requests initially gave a false-negative WebKit normal
result. A retained visible top-level SVG control showed progressing animation
clocks but unchanged computed transforms over the first 324ms. The bounded public
requestAnimationFrame control then showed changing transforms at 1000/1462/1921ms.
The runner now samples distinct rendered phases over 600ms frame-clock intervals,
a quarter of the artwork's shortest continuous 2.4s cycle. The same interval is
used for reduced motion. It changes observation only, with no pixel tolerance,
cropping, masks, animation mutation, screencast substitution or error filtering.
The affected WebKit normal-only proof passed with empty diagnostics after this
correction. Historical negative reports remain intact.

## Acceptance receipt

Existing App/Onboarding behavior: 32 targeted tests passed. Template compilation,
styles and production build passed; initial bundle remains 522.73kB against the
unchanged 525kB limit. Final runner lint and formatting passed. Six reduced-motion
references (landing and asset worksheet for each project) were visually reviewed
as complete, unclipped artwork. Final normal comparison results are recorded in
the frontend progress ledger and the frozen supplement manifest, not inferred
from reference generation. No Google login, email, AI, S3 or private credentials
were used. Parent owns eventual commit/publication/deployment.
