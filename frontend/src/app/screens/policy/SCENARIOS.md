# W02 / W03 and L01 / L02 policy reader

| Scenario                                 | Behavioral checks                                                                             | Screenshot / layer                                             |
| ---------------------------------------- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Published Terms/Privacy                  | Actual requested kind/version, safe literal text, no agreement controls, app navigation       | terms/privacy-published; HTTP boundary                         |
| Publication unavailable → explicit retry | Error feedback, deliberate retry, correct published result                                    | publication-unavailable + publication-recovered; HTTP boundary |
| Published PostgreSQL document            | Actual FastAPI200 and stored reference/content, version URL, rendered title/text, no checkbox | terms/privacy-published-postgres; full stack                   |

Every row runs on mobile Chromium/WebKit and desktop Chromium. Real fixture documents are synthetic and do not establish publication of final legal copy. Document authoring, profile-registration completion and native presentation remain separate dependencies. Loading/version navigation/invalid-content validation have unit coverage; extended loading/staleness browser matrix remains FE02 work and is not waived by this checkpoint.
