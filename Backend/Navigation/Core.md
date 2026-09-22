# Core telemetry processing

[Open the Core package README](Core/README.md)

The canonical implementation is `Backend/Navigation/Core`:

- `infrastructure/` — Firebase adapter;
- `layer0/` — source loading, sync decisions and raw artifacts;
- `layer1/` — canonical telemetry processing and quality outputs;
- `layer2/` — reusable downstream feature builders;
- `utils/` — small Core-local compatibility helpers.

The public Python namespace is `Backend.Navigation.Core`. Core does not own
benchmark labels, model predictions or research conclusions.
