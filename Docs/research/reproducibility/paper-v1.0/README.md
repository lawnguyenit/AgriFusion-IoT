# WADE paper v1.0 reproducibility

This folder documents the frozen analysis behind the current WADE manuscript
draft. The research configuration remains frozen: no model, target, split,
seed, or bootstrap is changed by the table-rebuild command below.

## Stuard source verification

Stuard Version 2 is the official Mendeley Data release
[10.17632/35wh56287y.2](https://data.mendeley.com/datasets/35wh56287y/2).
The three CSV streams used by the pipeline were downloaded from the official
file links and compared with the raw files referenced by the frozen analysis.
Their SHA-256 digests and byte sizes match exactly. See
[stuard-source-verification.json](stuard-source-verification.json).

The source registry now downloads Stuard from the version-specific Mendeley
file IDs. The files are preserved as separate raw evidence; do not edit or
normalize the raw CSVs in place.

## Frozen result bundle

The GitHub release asset `paper-v1.0-results.zip` contains the 202-file
result bundle and its SHA-256 `package_manifest.json`. It is a 23 MB ZIP
(about 75 MB when extracted) containing:

- target, feature, intake, model, and artifact manifests;
- the feature contracts, temporal split assignments, eligibility and support
audits;
- held-out predictions and per-anchor log-loss/Brier values;
- persisted bootstrap contrasts, metrics, models, and reports;
- package-level SHA-256 values for every included file.

The three analysis lanes and authoritative runs are:

| Paper content | Authoritative run | Bundle path |
| --- | --- | --- |
| Table 2, AgriFusion online target | `rq1_structured_program_20261001_103843` | `datasets/agri_fusion/rq1_structured_run/` |
| Table 3, UCI test heads | `multilabel_xgboost_20261001T073258471478Z` | `datasets/uci_air_quality/model_run/` and `metrics_summary.csv` |
| Table 4, Stuard nested controls | `acquisition_controls_nested_final_20261001T1215` | `datasets/stuard/acquisition_controls/` |

The AgriFusion per-anchor table uses the 832 matched online-target test
anchors across three temporal folds. Its log-loss is pooled over those
anchors; macro-F1 is the unweighted mean of the fold scores. UCI results are
test-only metrics over known targets and observable features; rows without
any selected X are retained as abstentions. Stuard Table 4 uses the same
linked holdout across all nested arms. The CSV outputs contain the persisted
UTC-day bootstrap intervals; the table builder does not refit models or
resample those intervals.

## Rebuild Tables 2–4

Clone the repository at the release tag, download
`paper-v1.0-results.zip` from the GitHub release assets, then install the
table-rendering environment:

```powershell
git clone https://github.com/lawnguyenit/AgriFusion-IoT.git
Set-Location AgriFusion-IoT
git checkout paper-v1.0
python -m pip install -r Docs/research/reproducibility/paper-v1.0/paper-requirements.txt
python -m Backend.Benchmark.model_suite.reporting.paper_tables_main --bundle C:\path\to\paper-v1.0-results.zip --output-dir output\paper-v1.0\tables
```

The command verifies every file against `package_manifest.json`, then writes
`tables-2-to-4.md` and one CSV per table. It uses the saved predictions and
bootstrap results; it does not train or evaluate another model.

To download and re-hash the official Stuard inputs into a new raw release:

```powershell
python -m Backend.Benchmark.external_intake.main --dataset stuard_tomato_irrigation_2023 --download --release-id stuard-mendeley-v2-recheck
```

This writes a new immutable raw release and canonical intake run under
`Backend/Output_data/`; it does not alter the frozen model runs. Compare the
three new raw file hashes with the verification JSON above.

## Environment and sources

The table-rebuild environment is Python 3.13.9 with NumPy 2.3.5, pandas
2.3.3, scikit-learn 1.8.0, and PyArrow 25.0.0. Frozen run manifests record
the training libraries, XGBoost profile, random seeds, feature hashes,
training masks, and split IDs.

Stuard is cited from Mendeley Data Version 2 (DOI
`10.17632/35wh56287y.2`, CC BY 4.0). UCI Air Quality is identified in its
included raw intake and run manifests (DOI `10.24432/C59K5F`). Raw datasets
are not duplicated in the release asset; download them from their official
repositories using the provenance recorded in the manifests.

## Git release identity

The release tag `paper-v1.0` identifies the exact source commit. To print its
full commit SHA:

```powershell
git rev-parse 'paper-v1.0^{commit}'
```

The tag excludes local scratch files and changes that were not committed to
the paper release.
