from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import pandas as pd
import json


@dataclass
class SourceSpec:
    name: str
    path: Path
    fields: dict[str, str]  # output_col -> flattened_input_col
    time_field: str = "timestamps.ts_hour_bucket"
    observed_at_field: str | None = "timestamps.observed_at_local"
    add_present_flag: bool = True
    
def load_flat_json(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return pd.json_normalize(payload)

def load_flat_jsonl(path: Path) -> pd.DataFrame:
    raw = pd.read_json(path, lines=True)
    flat = pd.json_normalize(raw.to_dict(orient="records"), sep=".")
    return flat

def _require_columns(df: pd.DataFrame, required_cols: list[str], source_name: str) -> None:
    """
    Kiểm tra xem DataFrame có chứa tất cả các cột cần thiết hay không. Nếu thiếu cột nào, raise KeyError với thông báo rõ ràng.
        - df: DataFrame cần kiểm tra
        - required_cols: Danh sách tên cột cần thiết
        - source_name: Tên của nguồn dữ liệu (dùng để hiển thị trong thông báo lỗi)
        - Nếu có cột nào trong required_cols không tồn tại trong df.columns, raise Key
    """
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise KeyError(f"[{source_name}] Missing columns: {missing}")

def prepare_source_df(spec: SourceSpec) -> pd.DataFrame:
    """"
    Xử lý một nguồn dữ liệu theo SourceSpec:
        - Đọc JSONL phẳng
        - Kiểm tra cột cần thiết
        - Đổi tên cột theo spec
        - Nếu có nhiều dòng cùng time_key, giữ dòng cuối (mới nhất)
        - Thêm cột present nếu spec yêu cầu
    Trả về DataFrame đã chuẩn hóa với cột time_key và các cột dữ liệu đã đổi tên bao gồm
        - time_key: từ spec.time_field
        - Các cột dữ liệu: từ spec.fields, đổi tên theo format "{spec.name}_{out_col}"
        - observed_at_local (nếu spec.observed_at_field không None): đổi tên theo format "{spec.name}_observed_at_local"
        - present (nếu spec.add_present_flag): cột boolean thể hiện có dữ liệu cho time_key đó hay không
    """
    
    # Đọc dữ liệu phẳng từ JSONL
    raw = load_flat_jsonl(spec.path)

    # Kiểm tra cột cần thiết
    required_cols = [spec.time_field, *spec.fields.values()]

    # Nếu có observed_at_field, cũng thêm vào danh sách cột cần kiểm tra
    if spec.observed_at_field is not None:
        required_cols.append(spec.observed_at_field)

    # Kiểm tra cột cần thiết có tồn tại trong DataFrame không
    _require_columns(raw, required_cols, spec.name)

    # Đổi tên cột theo spec
    rename_map: dict[str, str] = {
        spec.time_field: "time_key",
    }

    # Nếu có observed_at_field, đổi tên nó theo spec
    if spec.observed_at_field is not None:
        rename_map[spec.observed_at_field] = f"{spec.name}_observed_at_local"

    # Đổi tên các cột dữ liệu theo spec
    for out_col, in_col in spec.fields.items():
        rename_map[in_col] = f"{spec.name}_{out_col}"

    # Chỉ giữ lại các cột cần thiết và đổi tên chúng
    df = raw[required_cols].rename(columns=rename_map)

    # Thêm cột present nếu spec yêu cầu
    if spec.add_present_flag:
        df[f"{spec.name}_present"] = 1

    # Nếu cùng time_key có nhiều dòng, tạm giữ dòng cuối
    df = df.sort_values("time_key").drop_duplicates(subset=["time_key"], keep="last")

    return df


def merge_sources(specs: list[SourceSpec]) -> pd.DataFrame:
    """"
    Đầu vào là list các SourceSpec ở đây hiện tại là 3 json đã chuẩn bị.
    Mục tiêu:
    - Dùng time_key làm khóa chung để merge các nguồn dữ liệu lại với nhau ( merge kiểu outer để giữ tất cả time_key từ tất cả nguồn)
    - Nếu một source không có dữ liệu cho time_key nào đó, các cột của source đó sẽ là NaN, và cột present sẽ là 0 (nếu spec yêu cầu)
    - Trả về DataFrame đã merge, sắp xếp theo time_key
    """
    if not specs:
        return pd.DataFrame()

    merged: pd.DataFrame | None = None

    for spec in specs:
        source_df = prepare_source_df(spec)

        if merged is None:
            merged = source_df
        else:
            merged = merged.merge(source_df, on="time_key", how="outer")

    assert merged is not None

    for spec in specs:
        present_col = f"{spec.name}_present"
        if present_col in merged.columns:
            merged[present_col] = merged[present_col].fillna(0).astype(int)

    return merged.sort_values("time_key").reset_index(drop=True)


def write_csv(df: pd.DataFrame, csv_path: Path) -> None:
    """"
    Kiểm tra csv_path là gì:
    - Nếu csv_path là file (có suffix .csv), ghi trực tiếp vào đó
    - Nếu csv_path là thư mục (không có suffix .csv), tạo thư mục nếu chưa tồn tại và ghi file "fushion.csv" vào đó
    """
    if csv_path.suffix != ".csv":
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_file = csv_path/"fushion.csv"
    else:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_file = csv_path    
    df.to_csv(csv_file, index=False)


def convert_multi_jsonl_to_csv(specs: list[SourceSpec], csv_path: Path) -> pd.DataFrame:
    df = merge_sources(specs)
    write_csv(df, csv_path)
    return df