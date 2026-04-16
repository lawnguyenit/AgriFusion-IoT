"""
Path Manager for Backend Directories

This module provides centralized path management for all Backend subdirectories.
Instead of hardcoding paths in each file, import this module and use the functions
to get the correct paths for loading data or calling functions.
"""

from pathlib import Path

# Base directory is the Backend folder
BASE_DIR = Path(__file__).parent

def get_core_path() -> Path:
    """Get path to Core directory containing L3_Tabnet and Preprocessors."""
    return BASE_DIR / "Core"

def get_l3_tabnet_path() -> Path:
    """Get path to L3_Tabnet subdirectory."""
    return get_core_path() / "L3_Tabnet"

def get_preprocessors_path() -> Path:
    """Get path to Preprocessors subdirectory."""
    return get_core_path() / "Preprocessors"

def get_benchmark_path() -> Path:
    """Get path to Benchmark directory."""
    return BASE_DIR / "Benchmark"

def get_output_data_path() -> Path:
    """Get path to Output_data directory."""
    return BASE_DIR / "Output_data"

def get_layer1_path() -> Path:
    """Get path to Layer1 output data."""
    return get_output_data_path() / "Layer1"

def get_layer2_path() -> Path:
    """Get path to Layer2 output data."""
    return get_output_data_path() / "Layer2"

def get_layer25_path() -> Path:
    """Get path to Layer2.5 output data."""
    return get_output_data_path() / "Layer2.5"

def get_services_path() -> Path:
    """Get path to Services directory."""
    return BASE_DIR / "Services"

def get_test_path() -> Path:
    """Get path to Test directory."""
    return BASE_DIR / "Test"

def get_navigation_path() -> Path:
    """Get path to Navigation directory."""
    return BASE_DIR / "Navigation"

# Utility functions
def ensure_path_exists(path: Path) -> Path:
    """Ensure the path exists, create if necessary."""
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_relative_path_from_base(target_path: Path) -> str:
    """Get relative path from BASE_DIR to target_path."""
    try:
        return target_path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return str(target_path)