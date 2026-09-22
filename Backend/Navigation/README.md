# Backend navigation

This directory contains navigation documents for the backend implementation.
The source packages live under `Backend/Navigation/Core`; benchmark code lives
under `Backend/Benchmark`.

## Areas

- [Core telemetry processing](Core.md) — Layer0, Layer1 and Layer2;
- [Benchmark](Benchmark.md) — research dataset and model lanes;
- [Generated outputs](Output_data.md) — local Layer0/Layer1 artifacts;
- [Tests](Test.md) — backend test entry points.

## Import namespace

Use the canonical package namespace from the repository root:

```python
from Backend.Navigation.Core import PreprocessingPipeline
```

The historical `Backend.Core` and `Navigation.Core` aliases are not public
package paths.
