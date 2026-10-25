> Historical baseline verification. For the newer data audit, model comparison, and federated study see RESEARCH_RESULTS.md.

# Verification report — 24 October 2026

## Delivered application
New local application; no existing source repository was supplied. Static HTML/CSS/JavaScript frontend, Python threaded loopback API, NumPy model, pandas CSV processing. No external services or installations were used.

## Dataset inspection
- Archive: 397 entries, 2,152,040,031 compressed bytes. Directory paths validated; files not blindly extracted.
- Feature table: 38,401 rows × 35 columns; 25 model inputs.
- Separate labels.csv: 198 run/scenario annotation rows, not row-aligned flow labels.
- Additional Parquet, NPZ sequences, and PCAP captures exist and are not used for this baseline.
- Missing values: 0; complete-row duplicates: 0; repeated feature vectors: 229.
- Benign: 31,652 (82.42%); malicious: 6,749 (17.58%). Class counts appear in the JSON report and dashboard.
- Binary mapping explicitly checked: benign = 0, every other supported class = 1.
- Feature CSV SHA-256: `2babb39fedc77a53bcd6f2437219c5671156b982177944fb764a6079fa4b0059`.

## Primary evaluation
Predefined site split. Train: 20,690; validation: 3,608; test: 13,962. Test site: C. Removed cross-partition feature repeats: {'train': 0, 'val': 42, 'test': 99}.

| Metric | Measured |
|---|---:|
| Multiclass accuracy | 69.57% |
| Macro precision | 61.40% |
| Macro recall | 78.60% |
| Macro F1 | 61.99% |
| Weighted F1 | 76.81% |
| Binary false-negative rate | 9.30% |
| Binary false-positive rate | 33.02% |
| False negatives | 207 |
| False positives | 3875 |

Always-benign test accuracy is 84.05%, higher than the model's accuracy. This highlights why accuracy alone is misleading. Uniform priors trade many false positives for attack recall. Exfiltration precision is particularly weak (6.48%). This model is unsuitable for operational blocking.

## Reproducibility and leakage checks
Fixed Gaussian naive Bayes baseline, log1p features, uniform priors, training-only means/variances and fixed variance smoothing. No random split or stochastic fit, and no tuning against test results. Label columns, split assignments, IPs, timestamp, run_id, scenario_id, and site are excluded. Same model artifact and feature order are used for inference and explanation. Test predictions reproduce saved metrics exactly.

Secondary diagnostic experiments:
| Split | Test records | Accuracy | Macro F1 |
|---|---:|---:|---:|
| split_time | 5,673 | 78.83% | 73.18% |
| split_block | 5,865 | 73.54% | 61.88% |

## Commands executed and observed outcomes
- Bundled Python `engine.py`: successful; generated summary, sanitized flows, test predictions, and model artifact.
- Bundled Python `server.py`: running at http://127.0.0.1:8765.
- Bundled Python `-m unittest discover -s outputs/dicom-sentinel -v`: 15 tests passed.
- Bundled Node `--check outputs/dicom-sentinel/static/app.js`: passed.
- Python compilation of engine.py, server.py, and test_engine.py: passed.

## Browser verification
Opened actual app in the in-app browser. All eight navigation routes rendered. Checked evaluation protocol switching, dataset class filtering and pagination, and actual per-prediction explanations. Inspected desktop (1440), tablet (768), and phone (375) layouts. Fixed long-fingerprint overflow and stale-page asynchronous navigation errors. After the fix, the phone document width stayed within its viewport; tables scroll inside their containers. No browser console errors were observed on the checked pages. Dashboard screenshot saved alongside this project.

API tests exercised valid batch CSV inference, real aggregate event creation, invalid uploads, bad explanation indices, safe row previews, and health status. Browser file-picker upload and download controls were not exercised end to end. No configured linter, type checker, or frontend build pipeline exists.

## Known gaps and risk
- Offline baseline; no clinical or deployment validation.
- All feature rows share one run_id; independent-run generalization cannot be measured.
- Raw PCAP and sequence data are not parsed or exposed.
- Labels are supplied annotations; capture provenance and attack realism are unverified.
- Feature independence assumption and uniform priors limit score interpretation.
- No SHAP/LIME, federated clients, differential privacy, or enforcement integration.
- Three predefined split experiments reuse the corpus; they are not independent replications.
- No ROC/PR curves, calibration study, hyperparameter search, cross-validation, or independently collected evaluation corpus.
- Arbitrary dataset loading and retraining use the CLI contract, not a UI workflow.
- Only the Gaussian baseline was measured; no claim of model optimization is made.
- All sites share the same run_id, and duplicates are only one form of dependence. Shared temporal/collection artifacts may remain.
- Model NPZ and summary JSON must be regenerated together; artifacts do not provide cryptographic integrity verification.
- This HTTP service is a bounded local research tool, not an internet deployment.
