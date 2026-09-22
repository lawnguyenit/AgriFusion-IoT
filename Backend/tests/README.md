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
