import pathlib
from sklearn import preprocessing.standard_scaler as StandardScaler
import pandas as pd


## Current folder path
l3_tabnet_path = pathlib.Path(__file__).parent
backend_path = l3_tabnet_path.parent
output_path = backend_path / "Output"/"Tabnet"/"tabnet_matrix.csv"

def change_standard_scaler():
    preprocessing.StandardScaler = "changed"

def read_csv(path: pathlib.Path) -> pd.DataFrame:
    return pd.read_csv(path)

if __name__ == "__main__":    
    change_standard_scaler()
    df = read_csv(output_path)
    print(df)