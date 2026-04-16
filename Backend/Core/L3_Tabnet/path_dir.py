from pathlib import Path


## Path = Backend/Core/L3_Tabnet
L3_TABNET_DIR = Path(__file__).resolve().parent

## Path = Backend/Core
CORE_PATH = L3_TABNET_DIR.parent

## Path = Backend
BACKEND_DIR = CORE_PATH.parent

TABNET_OUTPUT_DIR = BACKEND_DIR / "Output_data" / "TabNet"
TABNET_MATRIX_PATH = TABNET_OUTPUT_DIR / "tabnet_matrix.csv"
