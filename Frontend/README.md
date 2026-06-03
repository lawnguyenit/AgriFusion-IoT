# Frontend Dashboard

## Purpose

`Frontend/` contains the static dashboard that reads processed telemetry and server-side diagnosis from Firebase RTDB.

The current UI keeps the existing layout and focuses on:

- historical charts and current snapshot
- server-side diagnosis/prediction in the same screen
- realtime reading of the published `result` payload
- direct display of the 4-class FT-Transformer diagnosis label
- frontend-side mapping from runtime `labelId` to Vietnamese diagnosis copy so the UI does not depend on backend display strings
- short preset windows automatically borrow a few nearest prior points when realtime history is too sparse, so the chart does not collapse into an empty panel
- runtime Firebase config is loaded from a local untracked file so repo commits do not carry environment-specific tokens or endpoints

## Input

Frontend expects Firebase RTDB branches:

- `result/meta`
- `result/latest`
- `result/history/air`
- `result/history/soil`
- `result/history/npk`
- `result/history/weather`
- `result/pipeline` or `result/meta/pipeline`
- `result/analysis`
- `result/analysis/diagnosis`
- `result/analysis/forecast/{air,soil,npk,weather}`
- `result/analysis/anomalies`
- `result/analysis/recommendations`

Frontend also expects a local runtime config file when live Firebase mode is needed:

- `public/config.local.json` (untracked, copied from `public/config.local.example.json`)

## Output

The dashboard renders:

- main historical chart
- summary, snapshot, and prediction side views
- pipeline status card
- FT-Transformer diagnosis label from `result/analysis/diagnosis`
- recommendation card from server output
- fallback demo mode when no local Firebase config is present

## Prediction view behavior

When the backend publishes FT runtime diagnosis, the prediction tab shows:

- predicted label directly from `analysis.diagnosis.displayLabel`
- model name from `analysis.modelName`
- server recommendation text if available

The preferred runtime contract is:

- backend sends stable keys such as `label`, `labelId`, `abnormalProbability`, `severity`
- frontend maps `labelId` to Vietnamese accented UI text and visual tone locally

The current 4-class diagnosis labels are:

- `normal_context`
- `packet_loss_outage`
- `water_deficit`
- `moisture_or_intervention_context`

## Command

Preview locally:

```powershell
python -m http.server 4173 -d Frontend/public
```

To enable live Firebase data without committing secrets:

```powershell
Copy-Item Frontend/public/config.local.example.json Frontend/public/config.local.json
```

## Assumptions

- Hosting remains static; data updates come from Firebase listeners.
- Backend publishes the normalized `result` schema already expected by the dashboard.
- If no live Firebase result exists, frontend can still fall back to demo data.
- `public/config.local.json` is created locally and stays out of git via `Frontend/.gitignore`.

## Risks / current limits

- The prediction panel depends on the server-published `analysis` payload; if the backend falls back or omits diagnosis, the UI will show the default waiting text.
- The dashboard does not run FT locally; it only reads the server-published result.
- `public/config.local.json` is optional; when missing or incomplete the dashboard intentionally remains in demo mode.
