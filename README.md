# Aesculyn

**Medical Network Intelligence** · Explainable intrusion-detection research for DICOM/PACS environments.

A hospital-inspired dashboard with clinical white surfaces, teal accents, medical scanner artwork, a cross-and-shield identity, responsive navigation, and transparent model reporting.

## Public showcase

Public showcase: https://AshubShafqat.github.io/aesculyn/

Source repository: https://github.com/AshubShafqat/aesculyn

Deployment status is shown in the repository Actions tab.

The public edition in `public/` shows aggregate evaluation measurements. It does not accept uploads, expose individual telemetry, or perform online inference. The complete local Python application supports dataset inspection, CSV batch inference, exact Gaussian decision explanations, model evaluation, and session events. Federated learning and enforcement are not implemented.

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
