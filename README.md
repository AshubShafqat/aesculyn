# Aesculyn

**Medical Network Intelligence** · Explainable intrusion-detection research for DICOM/PACS environments.

A hospital-inspired dashboard with clinical white surfaces, teal accents, medical scanner artwork, a cross-and-shield identity, responsive navigation, and transparent model reporting.

## Authenticated application

The new `app.py` release adds real accounts, private workspaces, validated CSV uploads, background MLP inference, persistent analysis history, local integrated-gradient explanations, model cards, evaluation and report downloads. The latest release adds an offline PCAP rules-only parser, manual incident review, a configurable dry-run risk ladder, real training-job logs, and interactive charts from saved experiment results. Download the private-weight local bundle as `outputs/aesculyn-application-local.zip`. Use [Start-Aesculyn.ps1](Start-Aesculyn.ps1) on Windows or see [APPLICATION.md](APPLICATION.md) for setup, the full flow and hosting instructions. Start with `python app.py` and open http://127.0.0.1:8780 after provisioning the private model package. Public source excludes weights and account data. GitHub Pages continues to serve the static research showcase; the authenticated Python backend is not publicly hosted.

## Public showcase

Public showcase: https://AshubShafqat.github.io/aesculyn/

Source repository: https://github.com/AshubShafqat/aesculyn

Deployment status is shown in the repository Actions tab.

The public edition in `public/` shows aggregate baseline and v2 research measurements. Open the Research Lab and Federated Learning pages for the new study. It does not accept uploads, expose individual telemetry, or perform online inference. The complete local Python application supports dataset inspection, CSV batch inference, exact Gaussian decision explanations, model evaluation, and session events. The v2 study adds actual local-process FedAvg/FedProx experiments. Distributed hospital deployment and network enforcement are not implemented.

## Run locally

Requires Python 3.11+, NumPy, pandas. From this directory:

```sh
python -m pip install -r requirements.txt
python engine.py --archive /path/to/authorized/dataset.zip
python server.py
```

Open http://127.0.0.1:8765. The original dataset and model artifacts are deliberately not distributed. You must have permission to use the input dataset. Required schema and label mapping are defined in engine.py. Set AESCULYN_DATASET to change the default archive path.

## Validation

With the server running:

```sh
python -m unittest discover -v
node --check static/app.js
```

Full dataset integration tests expect the originally supplied labeled dataset and generated artifacts. See VERIFICATION.md for actual prior measurements; these are not promises for another dataset.

## GitHub and Pages deployment

Upload this directory to a new repository named `aesculyn`. GitHub CLI alternative:

```sh
gh auth login
git init -b main
git add .
git commit -m "Create Aesculyn medical security research application"
gh repo create aesculyn --public --source=. --remote=origin --push
```

In repository Settings → Pages, select **GitHub Actions**. The included workflow builds an allowlisted source-code download and deploys the aggregate-only `public/` directory. Run `python build_public.py` to prepare the source download for another static host. Python inference is a separate local app and cannot run on static Pages. Private datasets and artifacts are ignored by Git.

## Measured baseline

Site C holdout, 13,962 test flows: multiclass accuracy 69.57%, macro F1 61.99%, false negatives 207, false positives 3,875. The false-positive rate is 33.02%; this baseline is unsuitable for automatic blocking. Explanations are exact Gaussian likelihood contributions, not SHAP/LIME or causal effects. No patient data, hospital connectivity, real-time protection, or clinical validation is claimed.

## Publication

No explicit open-source license is assigned. Add a license appropriate to your ownership before licensing redistribution to others. Third-party dataset rights are not granted by this repository.


## New: model comparison and federated experiments

The new Research Lab and Federated Experiments views report measured results from a reproducible local study. The original Gaussian baseline and its inference endpoint are preserved separately.

```sh
python -m pip install -r requirements.txt
python -m research.run --archive /path/to/authorized/dataset.zip --output artifacts/research-v2-final
python research_report.py --experiment artifacts/research-v2-final --public public/research.json
python -m unittest test_research -v
python research_predict.py --experiment artifacts/research-v2-final --input batch.csv --output predictions.csv
python server.py
```

Use a new output directory for each run. `requirements-research-lock.txt` records the NumPy/pandas/threadpoolctl versions used here. `RESEARCH_RESULTS.md` explains the protocols and measured results. `research/` contains the actual training implementation; `test_research.py` checks its gradients, CART splitting, probability metrics, and client aggregation.

Experiments compare Gaussian naive Bayes, weighted multinomial logistic regression, a histogram-binned bootstrap CART random forest, and a small 25→64→32→8 MLP, plus local-only MLP, FedAvg, and FedProx runs. Implementations are NumPy reference implementations, not scikit-learn, PyTorch, or Flower. A native-module application-control restriction prevented those third-party ML backends from being used. Nothing bypasses Windows security policy.

One spawned process per simulated site performs real local SGD. The coordinator shares parameters and aggregate normalization statistics and averages returned models by sample count. This is an offline single-machine federation experiment, not an authenticated hospital deployment, secure aggregation system, or differential privacy guarantee.

The unseen-site protocol trains/validates only on A and B and tests later C windows. The temporal protocol trains three site clients and tests later windows from all three; site C is not unseen in this protocol. A 60-second purge and global time ordering separate partitions. Exact feature vectors are deduplicated using label-independent precedence. Four conflicting feature-label groups are audited; evaluation labels never curate training membership.

The corpus was inspected previously. These are diagnostic reused-corpus tests, not a fresh independent benchmark. The v2 partitions also differ from the original site-holdout baseline, so their raw scores must not be compared as if they used the same test set. Three seeds measure initialization variability, not independence of data.

The research inference CLI and `/api/research/predict` endpoint use saved, checksum-verified research checkpoints. Inputs require the same 25 features and integer counters. Scores are uncalibrated. The original `/api/predict` endpoint continues to use the original Gaussian baseline. No model has been silently substituted.

Private client partitions, model weights, per-record predictions, and draft experiment artifacts stay under ignored `artifacts/`. Only aggregate results are exported to `public/research.json`. The public website runs no training or inference.
