# Frontend dashboard

`Frontend/public` is a static Firebase RTDB dashboard. It has no local model
runtime and no build-time npm dependency.

## Runtime modes

- `demo` — the safe default in `public/config.js`; renders deterministic local
  sample data without Firebase credentials.
- `auto`/live — enabled through the untracked
  `public/config.local.json`; reads Firebase RTDB using the configured
  `resultPath`.

The dashboard is presentation-only. It does not read
`Backend/Output_data/Layer1` directly.

## Current Firebase contract

The frontend subscribes to these paths below `resultPath` (normally
`result`):

```text
result/
|-- meta
|-- pipeline
|-- latest
|-- history/{air,soil,npk,weather}
`-- analysis/
    |-- diagnosis
    |-- forecast/{air,soil,npk,weather}
    |-- anomalies
    `-- recommendations
```

The runtime diagnosis supports both:

- four-class labels such as `normal_context`, `packet_loss_outage`,
  `water_deficit` and `rain_or_fertigation_context`;
- binary `normal`/`abnormal` fallback.

The UI must inspect `model.labelScheme` before interpreting a diagnosis.

## Important integration status

The current tracked backend owns Layer0/Layer1 canonical telemetry and does
not publish the `result/*` dashboard contract. Therefore this frontend is a
separate presentation contract and currently works in demo mode unless an
external publisher populates Firebase. Do not document `python -m Backend.main`
as a command that automatically updates this dashboard.

## Local preview

From the repository root:

```powershell
python -m http.server 4173 -d Frontend/public
```

For a live Firebase preview:

```powershell
Copy-Item Frontend/public/config.local.example.json Frontend/public/config.local.json
```

Fill in the local Firebase values, then open `http://localhost:4173`.
Never commit the local file or credentials.

## Hosting

`Frontend/firebase.json` configures Firebase Hosting with no-cache headers
for the HTML, JavaScript and CSS assets. Deployment requires the Firebase CLI:

```powershell
cd Frontend
firebase deploy --only hosting
```

## Files

- `public/index.html` — page structure;
- `public/style.css` — dashboard styling;
- `public/app.js` — Firebase listeners, normalization and rendering;
- `public/config.js` — safe defaults plus local override loading;
- `public/config.local.example.json` — configuration template;
- `firebase.json` — Hosting configuration.
