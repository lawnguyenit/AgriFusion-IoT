# Backend tests

The test suite is split by ownership rather than by one monolithic end-to-end
runner.

## Focused checks

From the repository root:

```powershell
python -m unittest Backend.tests.test_layer1_packet_processors
python -m unittest Backend.tests.test_layer1_context_processor
python -m unittest Backend.tests.test_dataset_views_selection
python -m unittest Backend.tests.test_evaluation_protocols_smoke
python -m unittest Backend.tests.test_model_suite
```

## Broader checks

```powershell
python -m unittest discover -s Backend/tests -p "test*.py"
python -m compileall -q Backend
```

Tests should be run from the repository root so imports use the canonical
`Backend.Navigation.Core` namespace. Tests validate contracts and pure
processing logic; Firebase credentials and physical hardware are not implied
by a passing unit test.

## Safety net (refactor)

- Install: `python -m pip install -r Backend/requirements-dev.txt`
- Golden data chain (JSON export -> Layer0 -> Layer1): `test_golden_data_chain.py`, see `golden/data_chain/README.md` for how to update it on purpose.
- Import-graph guard: `test_architecture_import_graph.py`, allow-list in `architecture/allowed_import_edges.txt`.
- Optional packages (`torch`, `pytabkit`) are not installed in CI; the tests that need them are skipped with a reason.
- CI: `.github/workflows/test.yml` (Python 3.11 and 3.12).
