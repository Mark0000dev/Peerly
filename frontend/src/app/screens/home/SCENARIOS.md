# W01 public landing scenario matrix

V2 replaces the pre-design shell. Private session bootstrap now belongs to `/onboarding`, not the public landing.

| Scenario        | Behavioral checks                                                        | Screenshot           | State                             |
| --------------- | ------------------------------------------------------------------------ | -------------------- | --------------------------------- |
| Root            | Peerly title, actual app link, policy links, no `/me`, no browser errors | home.png             | Validation in progress            |
| Unknown URL     | Dedicated W06 not-found/recovery owner in screens/system                 | public-not-found.png | Defined, next coherent acceptance |
| Narrow/enlarged | 320px/200%, content retained, no horizontal overflow                     | small-large-text.png | Validation in progress            |

Each runs on mobile Chromium, mobile WebKit and desktop Chromium with reduced motion. Public content has no loading/empty/permission states because it is static. Existing private bootstrap/error/full-stack cases moved to the actual auth owner rather than being deleted. Built-artifact no-JavaScript verification is still outstanding; development-server rendering does not prove prerender acceptance.

## V2 correction cohort — 12 November

FAQ uses native details/summary with public Taiga CardLarge appearances because
the public landing must remain usable without JavaScript, following reference
disclosure semantics without private control styling. Four truthful questions
are available; the designer pricing placeholder stays omitted until an owner
statement exists. Built no-JavaScript regression opens deletion guidance and
checks its real route, with closed/open checkpoints. Definition only, not fresh
visual acceptance. Unknown-route recovery belongs to the real system owner.
