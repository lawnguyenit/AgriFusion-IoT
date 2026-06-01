# DemoUI

## Purpose

`Backend/DemoUI` provides a local web control panel for demo commands.

It does not implement data logic itself. It only launches commands that already exist in the repo and shows their `stdout/stderr` in the browser.

## Input

- active Python environment for this repo
- commands exposed by:
  - `D:\AgriFusion-IoT\Backend\main.py`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\main.py`

UI parameters:

- `date_key`
- `template_id`
- `packet_gap_minutes`
- `skip_layer25`

## Output

- local web page at `http://127.0.0.1:8787` by default
- command logs rendered in the browser
- original pipeline outputs remain in their normal folders because DemoUI is only a control layer

## Commands

From repo root:

```powershell
python -m Backend.DemoUI.server
```

Open browser automatically:

```powershell
python -m Backend.DemoUI.server --open-browser
```

Use another port:

```powershell
python -m Backend.DemoUI.server --port 8899
```

## UI Action Mapping

- `Bootstrap 00:00 -> 12:00`
  - `python Backend\main.py --demo-bootstrap-day --inject-date-key <date_key>`
- `Inject Template`
  - `python Backend\main.py --inject-telemetry-template <template_id> --inject-date-key <date_key> --inject-packet-gap-minutes <gap>`
- `Run Demo Cycle`
  - `python Backend\main.py --server-cycle-demo --inject-telemetry-template <template_id> --inject-date-key <date_key> --inject-packet-gap-minutes <gap>`
- `Build FLB Dataset`
  - `python Backend\Benchmark\fuzzy_logic_basic\main.py`

When `skip_layer25` is enabled, DemoUI adds `--server-cycle-skip-layer25` to the backend commands that support it.

## Assumptions

- the web server uses only Python stdlib
- only one command is allowed at a time to avoid overlapping writes during demo sessions

## Risks / Limits

- logs are shown after command completion, not streamed live
- commands still perform real writes to Firebase/local output whenever the underlying command does so
- the FLB dataset action now also rebuilds the managed `flb_input_with_events.csv` artifact unless `--skip-real-event-labeling` is used
