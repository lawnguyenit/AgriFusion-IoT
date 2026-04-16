"""
Example usage of path_manager.py

This file demonstrates how to use the path_manager module to get paths
instead of hardcoding them in each file.
"""

from path_manager import (
    get_core_path,
    get_preprocessors_path,
    get_services_path,
    get_output_data_path,
    get_layer2_path,
    ensure_path_exists
)

# Example 1: Get path to Core directory
core_path = get_core_path()
print(f"Core path: {core_path}")

# Example 2: Get path to Preprocessors
preprocessors_path = get_preprocessors_path()
print(f"Preprocessors path: {preprocessors_path}")

# Example 3: Get path to Services
services_path = get_services_path()
print(f"Services path: {services_path}")

# Example 4: Get path to Layer2 output data
layer2_path = get_layer2_path()
print(f"Layer2 output path: {layer2_path}")

# Example 5: Ensure a path exists (useful for creating output directories)
output_dir = ensure_path_exists(get_output_data_path() / "custom_output")
print(f"Ensured output directory: {output_dir}")

# Example usage in real code:
# Instead of: data_path = Path("../Output_data/Layer2")
# Use: from path_manager import get_layer2_path; data_path = get_layer2_path()

# For loading data:
# import pandas as pd
# df = pd.read_csv(get_layer2_path() / "data.csv")

# For importing modules:
# import sys
# sys.path.append(str(get_core_path()))
# from L3_Tabnet import some_function