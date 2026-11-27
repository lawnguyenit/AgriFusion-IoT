# Golden: JSON export -> Layer0 -> Layer1

Safety net for the data chain. `Backend/tests/test_golden_data_chain.py` runs the real
Layer0 (`--source json-export --full-history`) and Layer1 pipelines on a synthetic export
and compares the normalized outputs with the snapshot in `expected/`.

| File | Role |
|---|---|
| `make_fixture.py` | Deterministic generator of `input_export.json` (Node2, schema v2, 27 records over 2 local dates; includes a 3-sample gap, one SHT30 fault, one NPK fault, one replayed/buffered record). Shape follows `IoT_Node/lib/RawTelemetryReporter`. All values are made up. |
| `input_export.json` | Generated fixture (a test checks it equals the generator output; do not hand-edit). |
| `expected/` | Golden snapshot (normalized, see below). |
| `update_golden.py` | Regenerates `expected/`. |
| `../../golden_chain_support.py` | Runs the chain in a temp dir and normalizes outputs. |

## What is normalized

- Keys ending in `_utc` and `age_since_*` are dropped (run-specific times); temp paths become `<OUT>` / `<INPUT_DIR>`.
- Parquet is compared as CSV, rows sorted by `record.id`, floats printed with `%.10g`.
- `views/` (debug), `archive_runs/` and `source_snapshot.json` are skipped; `raw_history/` is reduced to its content-addressed file names (`INDEX.txt`).

## Update the golden on purpose

Only when a behavior change in Layer0/Layer1 is intended (e.g. a stage of the refactor that changes the output format):

```bash
# only if the fixture itself must change:
python Backend/tests/golden/data_chain/make_fixture.py
python Backend/tests/golden/data_chain/update_golden.py
git diff Backend/tests/golden/data_chain/expected     # review every changed line
python -m unittest Backend.tests.test_golden_data_chain
```

Commit the golden change in the same commit as the code change and explain the diff in the message.
A refactor that is meant to be behavior-neutral must NOT touch `expected/`.

## Notes

- The CLI tests run with `AGRIFUSION_HOME` pointing at a temp dir and do not need `firebase_admin` (GD1 bug B3 is fixed; one test blocks the import to prove it).
- The test is validated on pandas 2.3 and 3.x.
