# W01 public landing scenario matrix

V2 replaces the pre-design shell. Private session bootstrap now belongs to `/onboarding`, not the public landing.

| Scenario        | Behavioral checks                                                        | Screenshot           | State                  |
| --------------- | ------------------------------------------------------------------------ | -------------------- | ---------------------- |
| Root            | Peerly title, actual app link, policy links, no `/me`, no browser errors | home.png             | Validation in progress |
| Unknown URL     | Redirect to root, same public behavior                                   | unknown-route.png    | Validation in progress |
| Narrow/enlarged | 320px/200%, content retained, no horizontal overflow                     | small-large-text.png | Validation in progress |

Each runs on mobile Chromium, mobile WebKit and desktop Chromium with reduced motion. Public content has no loading/empty/permission states because it is static. Existing private bootstrap/error/full-stack cases moved to the actual auth owner rather than being deleted. Built-artifact no-JavaScript verification is still outstanding; development-server rendering does not prove prerender acceptance.
