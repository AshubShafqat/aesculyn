# Aesculyn application

A working local research application for offline DICOM network-feature analysis. This release adds accounts, private workspaces, background inference, persisted history, per-record explanations and exports. The public GitHub Pages site remains a static research showcase; this backend has not been deployed publicly.

## Start the application

Use Python 3.11 or newer. From the extracted application folder:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-research-lock.txt
python app.py
```

On Windows, from PowerShell in the extracted folder, run `& .\Start-Aesculyn.ps1 -DatasetPath "C:\Users\Malik\OneDrive\Attachments\Netsol project dataset.zip"` to enable local training against your attached dataset, or `& .\Start-Aesculyn.ps1` to run with training disabled. On macOS/Linux, run `python app.py`. Open http://127.0.0.1:8780 and create your own account. There are no default credentials. Stop with Ctrl+C. Restarting preserves accounts and analysis history in `appdata/`. Pending jobs are marked failed after a restart and can be retried. Passwords cannot be recovered by email in this release.

The private `aesculyn-application-local.zip` includes the three small inference checkpoints in `modelstore/`. The public source ZIP deliberately excludes weights, account databases, uploads and raw data. If starting from public source, provision an authorized completed study first:

```sh
python -m application.provision --experiment artifacts/research-v2-final --output modelstore
```

That command verifies saved checkpoint hashes and creates the registry from the study report and training-only normalization/ranges. It requires the complete private experiment, including client training partitions. It does not retrain. Keep the resulting registry and checkpoints together. A checkpoint hash detects a change relative to its manifest; it is not a signature from an independent authority.

## Application flow

1. Create an account or sign in. Each account owns one private workspace on this server.
2. Overview shows actual saved analysis counts. New workspaces start empty.
3. New analysis accepts a UTF-8 feature CSV, up to 5 MB and 10,000 rows. Download the header template from that screen.
4. Select a checkpoint. The default is the centralized MLP family selected by validation macro-F1; deployment uses fixed study seed 17. FedAvg and FedProx checkpoints are also available for comparison.
5. Schema checks reject missing columns, missing/nonfinite/negative values, fractional counters, duplicate headers and unknown optional labels. Extra columns are discarded before input persistence. Do not upload identifiers, patient data or secrets; the original filename is retained as the analysis title.
6. A bounded background job runs genuine NumPy inference. Leave the page and return through history. Cancel unfinished jobs, retry failed/cancelled jobs, or delete completed/cancelled/failed inputs and results.
7. Review predicted classes, input min/max range flags and individual rows. Explain computes approximate integrated gradients of the winning-versus-runner-up logit margin against training log-feature means, with numerical completeness residual. These are local attributions, not SHAP, causal proof or confidence guarantees.
8. Download prediction CSV, a JSON report or printable HTML report. Open the HTML in a browser and use its print dialog for a PDF if needed. No native PDF exporter is claimed.
9. Optional `label_class` enables evaluation against your supplied labels. Labels are never fed into inference and are not independently verified. Macro-F1 includes all eight classes, assigning zero to absent classes.
10. Model registry shows individual checkpoint metrics separately from three-seed family means. Research evidence explains the original experiment. Workspace settings support renaming, password changes (revoke all sessions), and recent activity.

The schema is the `FEATURES` list in `engine.py`: 25 non-negative numeric features. `mean_pkt`, `std_pkt`, `mean_iat`, `std_iat` can be fractional; the remaining event/packet counters must be integers. Optional labels are `benign`, `recon`, `ae_bruteforce`, `assoc_flood`, `malformed_pdu`, `ransomware_like`, `exfiltration`, `preamble_polyglot`. Row IDs in results are zero-based input positions.

## What is real, and what remains

The model was trained in the included `research/` pipeline, before this application release. Uploading a file performs inference on frozen weights. It does not train a new model. The neural architecture is 25 → 64 → 32 → 8 with ReLU, training-only log1p standardization, and uncalibrated softmax outputs. Gaussian naive Bayes remains a historical baseline in the separate original dashboard.

The original experiment compared classical models and performed process-isolated FedAvg/FedProx with actual client optimization and sample-weighted aggregation. This application is a central inference service; selecting a federated checkpoint does not connect real hospitals. See `RESEARCH_RESULTS.md` for measured results and reproducible training commands.

Not implemented: packet capture or PCAP-to-feature extraction, live PACS integration, DICOM image/patient processing, automatic blocking, distributed hospital enrollment, encrypted/secure aggregation, differential privacy, email recovery, administrative user management, SSO, or clinical certification. No substitute telemetry is displayed as live hospital activity. Training min/max flags are descriptive, not a validated drift detector. A new independent collection, calibrated thresholds and external false-negative evaluation remain necessary before operational decisions.

## Hosting a pilot

The application requires a Python server and persistent disk. GitHub Pages cannot execute this backend. Included Docker/Caddy files are a starting configuration for a small supervised pilot, not a tested production deployment. Docker and public HTTPS were not available for deployment verification in the development environment.

1. Obtain a server with Docker Compose, persistent storage and a domain pointing to it.
2. Copy the source and private `modelstore/` to that server using a secure channel. Never commit `appdata/`, model packages or patient data to a public repository.
3. Copy `.env.example` to `.env`, set `AESCULYN_PUBLIC_URL=https://your-domain.example`, and configure `Caddyfile` with the real domain.
4. Run `docker compose up --build -d`. It exposes port 8780 only on server loopback. Run Caddy on the host with the included `Caddyfile` for HTTPS, preserving the request Host header. The app requires matching Host/Origin and sets Secure cookies when using HTTPS.
5. Verify signup, account isolation, upload, inference, export and restart persistence on the actual host. Monitor storage and keep authenticated access restricted during evaluation. Add operational monitoring, request/concurrency controls at the proxy, independent security review and your organization’s access policies before wider use.

The Python standard-library HTTP server is intended for local use / supervised pilots behind a hardened proxy. It is not an enterprise deployment claim. Authentication throttles are per direct client IP; behind a proxy this can become a shared limit. Do not trust arbitrary forwarded headers to bypass it. No CORS access is enabled.

Data directory: `AESCULYN_DATA` (default `appdata/`); model directory: `AESCULYN_MODELS` (default `modelstore/`); listening host: `AESCULYN_HOST` (default loopback); port: `PORT` (default 8780). Use `--public-url` or `AESCULYN_PUBLIC_URL` for an HTTPS deployment. Secrets, passwords and uploads are not written into source files. At-rest encryption is not implemented: use encrypted storage and OS access controls where required. Back up the entire data directory with the application stopped, then back up the immutable model directory. Deleting an analysis removes its active input/result files, not external backups; an activity reference remains.

## Verification

```sh
python -m unittest test_application -v
```

Application tests requiring checkpoints skip when `modelstore/` is absent. The `ids/` modules add evidence-based offline PCAP indicators and manual review with a dry-run response ladder; packet-derived ML inference is disabled because these extracted feature semantics are not validated against the training generator. The full private development run passed all 12 tests (none skipped); existing engine/research/integration suites passed another 42 tests. Research integration tests require the completed private experiment and the original research server on port 8767. See `APPLICATION_VERIFICATION.md` for scope and current browser verification limitations.
