# Result Publisher

## Purpose

This module reads local Layer1 artifacts, rebuilds runtime features, and publishes the dashboard-ready `result` payload back to Firebase RTDB.

Runtime settings and shared IO helpers are now resolved from the centralized `Backend/Config` layer rather than being duplicated inside Services.

The current runtime preference is:

1. `FT-Transformer option2_4class` from `Backend/Benchmark/context_classifier`
2. fallback to the older runtime-compatible `xgboost` artifact if FT is unavailable

## Input

- `Backend/Output_data/Layer1/sht30/history.jsonl`
- `Backend/Output_data/Layer1/sht30/latest.json`
- `Backend/Output_data/Layer1/npk/history.jsonl`
- `Backend/Output_data/Layer1/npk/latest.json`
- `Backend/Benchmark/context_classifier/outputs_option2_4class/training/**`
- fallback runtime artifacts from `Backend/Benchmark/direct_benchmark/outputs/**`
- `Backend/Services/.env`

## Output

Firebase RTDB:

- `result/meta`
- `result/pipeline`
- `result/latest`
- `result/history/{air,soil,npk,weather}`
- `result/analysis`

Local debug artifacts:

- `Backend/Output_data/Result_publish/latest_result_payload.json`
- `Backend/Output_data/Result_publish/latest_publish_manifest.json`
- `Backend/Output_data/Result_publish/result_sync_state.json`

## Runtime diagnosis behavior

- Publishes the predicted 4-class label directly when FT runtime is active:
  - `normal_context`
  - `packet_loss_outage`
  - `water_deficit`
  - `moisture_or_intervention_context`
- Publishes `labelId` so frontend can map the diagnosis to localized Vietnamese UI text without depending on backend display strings
- Publishes `abnormalProbability = 1 - P(normal_context)`
- Rebuilds packet-loss runtime features from timestamp gaps so the runtime path remains consistent with training assumptions
- Loads trusted local FT checkpoints with `weights_only=True` and suppresses `scikit-learn` cross-version warning noise for persisted scaler/imputer artifacts so the runtime log stays clean

## Commands

Snapshot publish from local artifacts:

```powershell
python Backend\main.py --only-result --publish-result --result-mode snapshot
```

Append only new local records:

```powershell
python Backend\main.py --only-result --publish-result --result-mode append
```

Dry-run local payload generation:

```powershell
python Backend\main.py --only-result --publish-result --result-mode snapshot --result-dry-run
```

## Assumptions

- Layer1 artifacts already exist and are current.
- The best FT runtime artifact is taken from the strongest `option2_4class` training run currently discoverable.
- Frontend consumes the `result/analysis/diagnosis` payload directly.

## Risks / current limits

- If FT runtime artifacts are missing or incompatible, the module falls back to XGBoost.
- Runtime packet-loss detection is driven by timestamp-gap features; if online timestamps are malformed, diagnosis quality drops.
- Forecast output remains heuristic and is separate from the FT diagnosis model.
