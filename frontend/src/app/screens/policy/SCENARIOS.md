# W02 / W03 and L01 / L02 policy reader

| Scenario                                 | Behavioral checks                                                                             | Screenshot / layer                                             |
| ---------------------------------------- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Published Terms/Privacy                  | Actual requested kind/version, safe literal text, no agreement controls, app navigation       | terms/privacy-published; HTTP boundary                         |
| Publication unavailable → explicit retry | Error feedback, deliberate retry, correct published result                                    | publication-unavailable + publication-recovered; HTTP boundary |
| Published PostgreSQL document            | Actual FastAPI200 and stored reference/content, version URL, rendered title/text, no checkbox | terms/privacy-published-postgres; full stack                   |

Every row runs on mobile Chromium/WebKit and desktop Chromium. Real fixture documents are synthetic and do not establish publication of final legal copy. Document authoring, profile-registration completion and native presentation remain separate dependencies. Loading/version navigation/invalid-content validation have unit coverage; extended loading/staleness browser matrix remains FE02 work and is not waived by this checkpoint.

## Actual public history contract — source integration 12 November

Generated from accepted122/136 safe422 exporter a400b2d5. Explicit URL
view=history reads metadata-only versions with actor-independent Query keys and
abort-aware HttpClient, opaque cursor pagination and kind validation. Selecting
a version uses the existing plaintext reader. No draft/body listing, fake
effective dates/current flags, agreement controls or consent mutation. Unit
definitions cover no implicit document read, scoped pagination and rejected
cross-kind references; both Terms/Privacy browser definitions capture first page,
older page and selected safe plaintext. Definitions have not yet run.
