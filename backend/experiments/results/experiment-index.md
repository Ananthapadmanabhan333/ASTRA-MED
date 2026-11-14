# Experiment index

Every registered model version, oldest first. All results are on **simulated** data (chronological test split); they are not clinical performance. Full details: `backend/artifacts/<version>/report.md`.

| Version | Latest | Commit | Config | Dataset | Seed | Ensemble F1 | AUROC | FPR | FNR | Events | XGB HR MAE 1h | 24h | Coverage 1h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `v20261112-163656-e1a07e27` |  | 79f7060 | e1a07e27 | bd39cdd978d7 | 7 | 0.554 | 0.874 | 0.0111 | 0.547 | 0.77 | 2.423 | 2.958 | 0.904 |
| `v20261112-164739-9c1cd54f` |  | 79f7060 | 9c1cd54f | eabfda075aa4 | 7 | 0.826 | 0.953 | 0.0087 | 0.261 | 0.96 | 2.336 | 3.411 | 0.900 |
| `v20261114-115210-9c1cd54f` | yes | 8fae33c | 9c1cd54f | eabfda075aa4 | 7 | 0.826 | 0.953 | 0.0087 | 0.261 | 0.96 | 2.336 | 3.411 | 0.900 |

Versions with the same config hash and dataset fingerprint were trained from the same configuration; identical metrics between them show the pipeline is reproducible.
