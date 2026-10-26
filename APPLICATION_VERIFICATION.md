# Application verification · 25 October 2026

- 12 application tests passed with real provisioned checkpoints, none skipped. Checked password hashing/revocation, stable session CSRF, Host/Origin rejection, account ownership for reads/exports/deletes/explanations, schema rejection, optional-label metrics, real inference equality, cancellation/retry, checkpoint rejection, explanation completeness, downloads and deletion of persisted inputs/results.
- Existing 42 engine/research/integration tests passed against the preserved completed study and research server. All 51 checkpoint hashes, source fingerprints, selection policy, 240 aggregation rounds and stored prediction metrics remain valid.
- `app.js` passed Node syntax checking. The local application starts on port 8780 and serves the actual API/UI.
- Desktop and mobile rendered-page inspection is **not verified in this release**: the in-app browser twice timed out attaching to its webview; Chrome was unavailable. Responsive CSS is implemented, but no new screenshot or visual QA result is claimed.
- Docker image build, container permissions, TLS, public hosting, load/concurrency behavior, email recovery, and production security review are **not verified**. The hosting files are configuration examples requiring a real deployment pass.
- Existing public GitHub Pages deployment is a static research showcase. No new live authenticated backend has been published.

The application runs inference using frozen research checkpoints. Study results are diagnostic single-corpus measurements, not external hospital validation. For individual seed-17 checkpoint measurements inspect `modelstore/registry.json`; family means are separately labeled in the interface.

- Latest dry-run additions: five IDS unit tests and three privacy/incidents/capture unit tests passed; fourteen total in this group, plus the six application schema/store tests (see command below). Browser attachment and local API requests remain blocked by this Windows environment socket policy; only a successful loopback bind message is observed.
- Local HTTP listener startup at 127.0.0.1:8780 succeeded, but API GETs from the shell receive WinError 10013 and the in-app browser reports ERR_CONNECTION_TIMED_OUT. Treat the listener as unverified from clients until verified on the user machine.
- The new rule/capture/incident screens, analytics charts and private training screen are implemented; no desktop/mobile screenshot verification is claimed.
