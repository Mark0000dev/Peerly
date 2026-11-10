# Internal diagnostic frontend image checkpoint

This branch captures only the 202 allowlisted production image inputs from the locally verified student frontend candidate. Full source/test/reference integration will follow separately; this is not the final repository consolidation.

Source candidate manifest: dc8d0bb2bb461c03cd9171e85aa137347eac4b958c21a90da8e2583fd6be311c. Build-input manifest: d37df57a54d7de069b9872f08cc05265c6c37aa73fe739fd21c186b4e1b9c7e2. Parent-owned Docker/Nginx inputs are explicitly additional to the source snapshot.

Known unresolved ResizeObserver diagnostic is accepted by the owner for preparation/deployment of internal diagnostic staging only. No suppression or full browser-green claim. Real provider and deployed smoke acceptance remain required before announcing the completed internal stack; external-user monitoring and release gates remain in force.

Local production image smoke: 17 HTTP checks plus nginx configuration validation passed, nonroot/read-only runtime. Corrected cache filename matching to include URL-safe underscore/hyphen. Real deployed browser/provider acceptance remains separate.
