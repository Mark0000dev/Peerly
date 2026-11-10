# Person normal PG runtime diagnostic

Observed 7 November 2026, 23:16:00 Europe/Moscow (20:16:00 UTC).

Command: `npm run test:fullstack -- person/person.fullstack.visual.spec.ts --workers=1`,
Node24, test port38385, coherent backend head29, owned WebKit endpoint8879.
All nine Playwright behavior and PNG assertions passed in46.4seconds. The unchanged
browser wrapper correctly returned1 for a native ResizeObserver diagnostic. This is
not a clean normal PG gate, and no filtering, error exemption, screenshot masks or
threshold changes were introduced. The preceding snapshot update passed9/9 including
the wrapper gate.

## Verified ownership

Runtime context:
`chromium-mobile:51dadaaf70482320bbc5-53b122f8acb14d9d3ecf`.

The test ID was independently mapped using the Node-only Playwright `--list
--reporter=json` output to:
`actual person projection and current authorized JPEG use real activated student records`.
No browser or PG fixture was launched for that metadata listing. The mapped scenario
opens only the profile/JPEG view; no report form or block dialog is opened in it.

## Observed event order

1. Fresh fixture584290 and loopback HTTPS media server started successfully.
2. The chromium-mobile worker started the actual profile/JPEG scenario.
3. The owned runtime context warning below appeared, followed by Vite's unhandled
   error and Angular's ErrorEvent diagnostic.
4. The first scenario was reported passed; the remaining eight also passed.
5. Both fixture servers logged graceful shutdown and process completion.
6. Playwright printed `9 passed (46.4s)`; the browser wrapper emitted its diagnostic
   message and exited1.

A Chromium unit suite ran concurrently, as allowed by the delegation. This timing is
recorded as a possible resource-contention factor, not a causal conclusion. An isolated
normal replay would be a bounded comparison, not proof that an intermittent observer
problem has been fixed.

## Relevant verbatim stdout excerpt

The original command stdout was returned through execution session92935 and was not
redirected to a raw log file. This document preserves the relevant observed excerpt;
it is not represented as a complete unmodified CLI log. No provider payload, cookie,
session secret or report text is included.

```text
[WebServer] 11:16:00 PM [vite] (client) [console.warn] [peerly owned runtime context] chromium-mobile:51dadaaf70482320bbc5-53b122f8acb14d9d3ecf ResizeObserver loop completed with undelivered notifications.
[WebServer] 11:16:00 PM [vite] (client) [Unhandled error] Error: ResizeObserver loop completed with undelivered notifications.
[WebServer] 11:16:00 PM [vite] (client) [console.error] ERROR Error: An ErrorEvent with no error occurred. See Error.cause for details: ResizeObserver loop completed with undelivered notifications.
9 passed (46.4s)
Browser runtime diagnostic detected; see the unchanged runner output.
```

All Playwright scenarios passed, so the configured retain-on-failure policy did not
retain a failing per-test trace. The full-lifetime wrapper is what caught this event.
Shared diagnostics, the font-watcher correction and runtime instrumentation remain
Halley's responsibility. This slice does not claim to have established the observer's
cause or fixed the shared intermittent diagnostic.
