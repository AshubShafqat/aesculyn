# Aesculyn v2 — Data validation, model comparison, and federated experiments

## Status
Completed offline experiments. This is a process-isolated local federation, not a hospital deployment.

## Dataset audit
- rows: 38401
- columns: 35
- missing_cells: 0
- duplicate_collection_keys: 81
- repeated_feature_vectors: 229
- conflicting_feature_vectors: 4
- rows_with_conflicting_features: 161
- malicious_windows: 6749
- malicious_annotation_exact_matches: 6551
- malicious_annotation_matches_with_2s_tolerance: 6749
- benign_windows_inside_attack_intervals: 0
- unique_run_ids: 1

Conflicting feature-label groups are reported but are NOT used to filter training using evaluation labels. Repeated feature vectors are removed globally using target-independent partition and original-index precedence; contradictions remain a data-quality limitation. Timestamp boundaries are purged by 60 seconds and made globally chronological across sites. Annotation tolerance is diagnostic, not independently established capture-window semantics.

## Frozen experimental configuration
Three seeds: 17, 29, 43. Four centralized candidates: Gaussian naive Bayes, weighted multinomial logistic regression, a histogram-binned random forest, and a 25→64→32→8 ReLU MLP. All are NumPy reference implementations. MLP SGD learning rate .03, momentum .9, inverse-square-root training class weights, 20 rounds/blocks × 2 local epochs. FedAvg mu=0, FedProx mu=.01. Same architecture and initialization per seed. Checkpoints selected by validation macro-F1. Model family chosen by mean validation macro-F1 before test prediction.

Independent local-only site models are also trained. Centralized MLP optimizer steps and round/reset schedule match the stated training budget; local-only and federated models each see only local client training batches. Centralized pooled training naturally performs more minibatch updates per block than an individual client.

## Results

### unseen_site
Train/validation/test: 16,649 / 2,904 / 1,755. Training sites: A, B; test sites: C.
Validation-selected method: **central_mlp**.

| Method | Val macro F1 | Test accuracy | Test macro F1 (mean ± SD) | FN mean | FP mean | FPR |
|---|---:|---:|---:|---:|---:|---:|
| central_mlp | 91.25% | 93.87% | 91.08% ± 1.08 | 77.0 | 27.0 | 2.54% |
| fedavg | 90.11% | 93.11% | 89.48% ± 0.72 | 80.0 | 32.0 | 3.02% |
| random_forest | 90.09% | 91.00% | 86.82% ± 0.56 | 92.0 | 59.0 | 5.56% |
| fedprox | 89.79% | 92.38% | 88.59% ± 1.71 | 99.0 | 25.3 | 2.39% |
| logistic_regression | 88.37% | 74.95% | 77.40% ± 0.36 | 58.3 | 375.3 | 35.38% |
| local_A | 79.92% | 90.85% | 83.78% ± 0.37 | 115.7 | 23.3 | 2.20% |
| local_B | 77.96% | 86.21% | 76.90% ± 3.49 | 176.0 | 26.7 | 2.51% |
| gaussian_nb | 72.33% | 66.67% | 67.14% ± 0.00 | 80.0 | 441.0 | 41.56% |

### temporal_federation
Train/validation/test: 26,299 / 4,632 / 5,181. Training sites: A, B, C; test sites: A, B, C.
Validation-selected method: **central_mlp**.

| Method | Val macro F1 | Test accuracy | Test macro F1 (mean ± SD) | FN mean | FP mean | FPR |
|---|---:|---:|---:|---:|---:|---:|
| central_mlp | 88.98% | 90.95% | 87.01% ± 0.41 | 425.7 | 24.7 | 0.84% |
| random_forest | 87.04% | 88.94% | 84.50% ± 0.31 | 434.7 | 112.3 | 3.81% |
| fedavg | 86.56% | 90.25% | 85.36% ± 1.18 | 468.7 | 7.0 | 0.24% |
| fedprox | 85.06% | 89.97% | 84.76% ± 2.06 | 477.7 | 5.3 | 0.18% |
| logistic_regression | 84.81% | 82.38% | 79.48% ± 0.34 | 376.3 | 499.3 | 16.92% |
| local_B | 78.00% | 86.63% | 77.62% ± 2.04 | 590.0 | 15.3 | 0.52% |
| local_A | 75.30% | 86.60% | 78.83% ± 1.89 | 557.0 | 33.7 | 1.14% |
| local_C | 70.11% | 83.00% | 69.48% ± 3.49 | 791.0 | 22.7 | 0.77% |
| gaussian_nb | 62.79% | 73.27% | 64.83% ± 0.00 | 477.0 | 633.0 | 21.45% |

Standard deviation across seeds is not an uncertainty interval for unseen hospitals. The new test subsets differ from the original baseline evaluation; apparent improvements must not be treated as a same-test comparison. Compare methods only within the same v2 protocol.

## Federation implementation
One spawned process per site loads its own private partition. Each round sends global weights to clients, executes actual local SGD, and returns weights, sample counts, loss, and timing. FedAvg uses sample-count-weighted averaging. FedProx adds mu/2 times the squared distance to the received global parameters. Selected global checkpoints and all round logs are saved. Client training data never cross the coordinator pipe during rounds.

The coordinator prepares partitions locally and can access all files. Training normalization moments and label counts are aggregated without secure aggregation. Thus this is a genuine algorithmic federated experiment but not a privacy-secure distributed hospital system. Flower and PyTorch were not used in this execution.

## Environment constraints
An isolated PyTorch/scikit-learn installation hit low disk space; after a smaller installation, Windows Application Control blocked a native scikit-learn module. Security controls were preserved. NumPy reference implementations with analytic-gradient, split, probability, and aggregation tests were used instead. The partial dependency environment is not required to reproduce this study; only NumPy, pandas, and threadpoolctl are needed.

## Reproduction
```sh
python -m pip install -r requirements.txt
python -m research.run --archive "/path/to/dataset.zip" --output artifacts/research-v2-final
python research_report.py --experiment artifacts/research-v2-final --public public/research.json
python -m unittest test_research -v
python research_predict.py --experiment artifacts/research-v2-final --input batch.csv --output predictions.csv
```

The output directory must be new/empty. configuration.json is written before training; selection_lock.json before test prediction. Source, dataset, partition, and model digests are recorded. Private partitions, checkpoints and predictions remain under ignored artifacts/. No archive-extracted code is executed.

## Limitations
- Annotation agreement checks internal consistency, not independently verified truth.
- Two-second annotation tolerance is a diagnostic assumption; capture-window semantics are undocumented.
- One run_id prevents independent-run validation.
- Previously inspected data reused diagnostically; no fresh external holdout exists.
- Retrospective traffic windows: feature availability and live extraction unverified.
- Capture provenance, attack realism, and PCAP feature extraction require independent verification.
- Clients are real separate local processes, not independent hospitals or authenticated network services.
- Training normalization moments and class counts are shared without secure aggregation.
- No differential privacy, Byzantine defense, live network capture, clinical validation, or enforcement.
- All final test metrics are diagnostic reuse of this corpus; new independent capture data is required.
- Softmax and tree probabilities are uncalibrated and are not confidence guarantees.
- The baseline deployed inference endpoint remains unchanged; research checkpoints require the separate research inference interface.
- Model checkpoint selection uses validation; test results do not choose the winner.
- Conflicting feature-label groups are reported, not used to curate training. Duplicate representatives use target-independent partition/index precedence.
- Histogram gradient boosting and third-party ML backends were not run because of disk and native-module application-control constraints.
