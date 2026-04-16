# Backend Navigation

This folder provides easy navigation to all subdirectories in the Backend.

Each .md file contains a clickable link to navigate to the corresponding folder.

## Available Navigations:
- [Core](Core.md) - Core processing modules
- [Benchmark](Benchmark.md) - Benchmark models
- [Output_data](Output_data.md) - Data outputs
- [Services](Services.md) - Service modules
- [Test](Test.md) - Test scripts

## Path Manager
For programmatic access to paths, use the `path_manager.py` module:
```python
from path_manager import get_core_path, get_services_path
core_path = get_core_path()
services_path = get_services_path()
```

See `example_usage.py` for detailed examples.

Use this when creating new processing files to easily find where to place them.