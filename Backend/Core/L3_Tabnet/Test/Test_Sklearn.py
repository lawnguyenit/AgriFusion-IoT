from pathlib import Path

import pandas as pd
from sklearn import preprocessing

from Backend.Core.L3_Tabnet.path_dir import TABNET_MATRIX_PATH

def get_standard_scaler():
    return preprocessing.StandardScaler()

def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return pd.read_csv(path)

if __name__ == "__main__":    
    try:
        o = read_csv(TABNET_MATRIX_PATH)
        scaler = get_standard_scaler()
        o_scaled = scaler.fit_transform(o)

        print("CSV file read successfully.")
        print(o.head())  # Print the first few rows of the DataFrame
        print("Scaled data:")
        print(o_scaled)
    except FileNotFoundError as e:
        print(f"Error: {e}")
