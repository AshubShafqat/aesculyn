# Architecture audit · 26 October 2026

The PDF specifies six site layers plus federation. Page 2 says seven attacks, but page 3 excludes A6: new ML experiments must use benign plus six attacks and handle preamble_polyglot in rules. Existing eight-class v2 results remain unchanged.

The available ZIP contains 38,401 feature rows, 35 columns, 25 predictors, three sites, timestamps, predefined splits, 390 PCAPs and 698,812 sequences shaped 32×3. Feature class counts: benign 31,652; recon 1,540; ae_bruteforce 1,205; assoc_flood 984; malformed_pdu 910; ransomware_like 780; exfiltration 774; preamble_polyglot 556. Zero missing feature-table cells, 229 repeated feature vectors, one collection run. Sequence split_time/split_site contain object arrays and will not be unpickled. Overlapping sequences require additional isolation.

Current v2 evidence: 51 actual checkpoints, 240 aggregation rounds, two diagnostic protocols. Current app: private accounts, CSV inference, history, integrated-gradient explanations and exports. Missing architecture components are tracked separately; existing results must not be relabeled LightGBM/PyTorch/CNN/SHAP.

Implementation sequence: expose local work/training; add rules, risk and incident persistence; add bounded offline PCAP ingestion; implement separate seven-class training and calibration; integrate real analytics/exports; deploy supported components to connected hosting and verify actual runtime behavior. No guarantee that federation beats centralized training is scientifically justified.

Disk space is now about 7.3 GB. Package installation uses workspace temporary storage. Native PyTorch currently reports WinError 126 for shm.dll. Docker is unavailable. GitHub Pages is static; the connected Sites project has no live version and cannot directly run a Python training server. Browser infrastructure is currently failing to initialize. These are verification limits, not successful features.
