# Backend Navigation

This folder provides simple navigation links to major backend areas.

## Available Navigations

- [Core](Core.md) - Core processing modules
- [Benchmark](Benchmark.md) - Benchmark models
- [Output_data](Output_data.md) - Data outputs
- [Test](Test.md) - Test modules

## Path Access

For programmatic path access, use `Backend/Config/paths.py`:

```python
from Backend.Config.paths import BACKEND_PATHS

core_dir = BACKEND_PATHS.core_dir
benchmark_dir = BACKEND_PATHS.benchmark_dir
```
