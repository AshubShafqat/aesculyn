# Aesculyn redesign and publication status

## Completed
- New name and visual identity: Aesculyn, Medical Network Intelligence.
- Clinical white and soft teal palette, cross-and-shield brand mark, medical scanner illustration, updated dashboard cards, typography, charts, and responsive layouts.
- Redesigned full local app remains in ../dicom-sentinel.
- Public static showcase prepared in public/. Aggregate metrics only; no individual flows, private packet captures, model weights, or user machine paths.
- GitHub-ready source and GitHub Pages deployment workflow included.

## Verification
- Local model/API suite: 15 tests passed after the redesign.
- Local app and public showcase JavaScript syntax checks passed.
- Actual browser check: all eight public routes rendered, desktop 1440px and phone 375px inspected, no document overflow at phone width.
- Public source bundle checked for private data files and machine paths.
- No model retraining or metric change was made for the visual redesign.

## Publication

Repository: https://github.com/AshubShafqat/aesculyn

The public showcase is deployed from public/ with the GitHub Pages workflow. Check the repository Actions tab for the latest deployment result. Full Python inference remains local; no dataset files or trained model weights are published.
