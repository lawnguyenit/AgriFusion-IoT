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

## Firebase contract

The dashboard reads exactly the `result/*` contract in
[`docs/contracts/result.md`](../docs/contracts/result.md) (machine-readable copy:
`public/contract.js`):

```text
result/
|-- meta
|-- latest/{air,soil,npk}
`-- history/{air,soil,npk}/{ts}
```

- Loading: one `limitToLast(800)` query per history group with
  `onChildAdded`/`onChildRemoved`, plus `onValue` on `meta` and `latest`.
  There is no full-tree `get()`, so history is not downloaded twice.
- NPK values are **proxies** (`n_proxy/p_proxy/k_proxy`, uncalibrated), not ppm.
  The EC unit is not asserted by the canonical catalog (chua kiem chung).
- Weather, forecast, diagnosis, recommendations and anomalies have no data
  source. Their panels (including the "Du doan" tab) were removed rather than
  kept as placeholders: a permanent empty panel suggests a feature that is
  about to arrive, while the contract has no path for it. Add them back only
  together with a contract version bump and a real publisher.
- Retention on the server is 7 days, so the 30-day range preset was removed.

## Integration status

No backend publisher writes `result/*` yet (it will be written against the
contract). Until then the dashboard runs in demo mode with sample data from
`public/sample-data.js`, which is the single source of demo data and follows the
contract exactly. In live mode with an empty `result/` the UI shows
"Chua co du lieu", not sample data.

## Security rules (`database.rules.json`)

Public read only under `result`; no public write anywhere; `Node2`, `debug`,
`control` and `ops` need non-anonymous auth.

**The rules deployed on Firebase are NOT verified by this repo.** The owner must
open the Firebase console (Realtime Database > Rules) and confirm they match this
file; deploy with `firebase deploy --only database` from `Frontend/` if not.
Also check that the Anonymous sign-in provider is disabled or unused.

The firmware currently writes with a legacy database secret
(`APP_FIREBASE_LEGACY_TOKEN`). That credential is admin-level and **bypasses these
rules entirely**. Moving the firmware to a scoped credential is plan node s6e
(owner action); until then the rules above do not protect against anyone holding
that secret.

## Tests

No dependencies, Node 18+:

```bash
cd Frontend && node --test test/*.test.js
```

The test validates the demo sample data, the UI metric list and
`database.rules.json` against the contract. CI: `.github/workflows/frontend.yml`.

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
- `public/contract.js` — machine-readable `result/*` contract and validator;
- `public/dashboard-model.js` — metric and group definitions;
- `public/sample-data.js` — demo data following the contract;
- `test/contract.test.js` — contract drift check;
- `database.rules.json` — RTDB security rules;
- `public/config.js` — safe defaults plus local override loading;
- `public/config.local.example.json` — configuration template;
- `firebase.json` — Hosting configuration.
