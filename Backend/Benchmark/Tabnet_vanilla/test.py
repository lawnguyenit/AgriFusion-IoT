import json 
import pandas as pd
import Backend.Config.path_manager as pm


if __name__ == "__main__":
    # Đọc file CSV đã được tạo bởi Preprocessor
    tabnet_csv = pm.get_test_path() / "tabnet_input.csv"
    df = pd.read_csv(tabnet_csv)

    # In ra vài dòng đầu để kiểm tra
    print(df.head())