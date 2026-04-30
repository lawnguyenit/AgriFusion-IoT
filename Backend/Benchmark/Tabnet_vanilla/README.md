# TabNet Vanilla Benchmark

Thư mục này chứa pipeline chuẩn bị dữ liệu và benchmark cho mô hình TabNet baseline. Mục đích chính là tạo dataset chuẩn để so sánh hiệu suất của các mô hình ML khác với TabNet, một mô hình gradient boosting tree-based.

## Cấu trúc thư mục

```
Tabnet_vanilla/
├── config/                    # Cấu hình và schema
│   ├── settings.py           # Cài đặt tỷ lệ chia data, cột features, targets
│   └── feature_schema.py     # Logic xác định và build feature/target views
├── Input/                     # Dữ liệu đầu vào và đầu ra đã xử lý
│   ├── fushion.csv           # CSV gốc từ Preprocessor.py (merge 3 nguồn: NPK ,SHT, METEO)
│   └── Prepared/             # Dữ liệu đã chuẩn bị cho training
│       ├── manifest.json     # Metadata về dataset (số lượng rows, features, etc.)
│       ├── origin_dataset/   # Dataset đầy đủ với tất cả cột
│       │   ├── train_full.csv
│       │   ├── valid_full.csv
│       │   └── test_full.csv
│       └── dataset/          # Feature views (chỉ cột features, đã fill NaN)
│           ├── X_train.csv
│           ├── X_valid.csv
│           ├── X_test.csv
│           ├── y_train.csv    # (Nếu có target_col được set)
│           ├── y_valid.csv
│           └── y_test.csv
├── threshhold/               # Scripts tính toán và quản lý thresholds cho evaluation
│   ├── thresh_hold_condition.py
│   └── thresh_hold_handbook.py
├── Preprocessor.py           # Script đầu tiên: Merge JSONL từ 3 nguồn thành CSV
├── prepare_train_tabnet.py   # Script chính: Xử lý data, split train/val/test, build features
├── prepare_utils.py          # Utilities cho data processing (time features, fill NaN, split)
├── test.py                   # Script test đơn giản để kiểm tra CSV
└── __pycache__/              # Python bytecode (tự động tạo)
```

## Luồng xử lý dữ liệu (Data Pipeline)

Pipeline gồm 2 bước chính, chạy tuần tự để tạo dataset cho TabNet:

### Bước 1: Preprocessor.py - Tạo CSV gốc
- **Mục đích**: Merge dữ liệu từ 3 nguồn JSONL (NPK, SHT, METEO) thành một CSV duy nhất.
- **Input**: 
  - `Backend/Config/IO/` paths đến JSONL files (npk.jsonl, sht30.jsonl, meteo.jsonl).
- **Xử lý**:
  - Load và flatten JSONL từ mỗi nguồn.
  - Đổi tên cột theo schema trong `settings.py` (e.g., `perception.n_ppm` → `npk_n_ppm`).
  - Thêm cột `present` cho mỗi nguồn (1 nếu có data, 0 nếu thiếu).
  - Merge outer join theo `time_key` (thời gian bucket theo giờ).
  - Fill `present=0` cho các time_key thiếu data từ nguồn nào đó.
- **Output**: `Input/fushion.csv` với tất cả cột từ 3 nguồn.
- **Cách chạy**:
  ```bash
  cd D:\AgriFusion-IoT\Backend\Benchmark\Tabnet_vanilla
  python Preprocessor.py
  ```

### Bước 2: prepare_train_tabnet.py - Chuẩn bị dataset cho training
- **Mục đích**: Xử lý `fushion.csv`, thêm features, split data, chuẩn bị cho ML.
- **Input**: `Input/fushion.csv` từ bước 1.
- **Xử lý**:
  1. **Load và clean**: Load CSV, xóa cột trace nếu có (theo `DROP_COLS_IF_EXIST` trong `settings.py`).
  2. **Thêm time features**: Sử dụng `prepare_utils.add_time_features()` để thêm `hour_of_day`, `day_of_week`, `hour_sin`, `hour_cos`.
  3. **Sort by time**: Sắp xếp theo `time_key` để đảm bảo temporal order.
  4. **Split train/val/test**: Chia theo thời gian (không random) với tỷ lệ trong `settings.py` (TRAIN_RATIO=0.7, VALID_RATIO=0.15, TEST_RATIO=0.15).
  5. **Compute fill values**: Tính giá trị fill NaN từ train set (trung bình, median) để tránh data leakage.
  6. **Apply fill values**: Điền NaN cho val/test bằng fill values từ train.
  7. **Build feature views**: Sử dụng `feature_schema.py` để chọn cột features từ `BASE_FEATURE_COLS` + derived features (soil_humidity_mean_24h, etc.) + time features.
  8. **Build target views**: Nếu `TARGET_COL` được set trong script, tạo y_train/y_valid/y_test.
  9. **Save outputs**: Xuất CSVs vào `Input/Prepared/`.
- **Output**:
  - `origin_dataset/`: Full datasets với tất cả cột (cho analysis).
  - `dataset/`: Feature-only datasets (X_*.csv) và targets (y_*.csv nếu có).
  - `manifest.json`: Summary (số rows, features, etc.).
- **Cách chạy**:
  ```bash
  cd D:\AgriFusion-IoT\Backend\Benchmark\Tabnet_vanilla
  python prepare_train_tabnet.py
  ```

### Các file utilities
- **prepare_utils.py**: Chứa functions chính cho processing:
  - `add_time_features()`: Thêm time-based features.
  - `split_by_time()`: Chia data theo thời gian.
  - `compute_fill_values()`: Tính fill strategy từ train.
  - `apply_fill_values()`: Điền NaN.
  - `ensure_dir()`, `save_dataframe()`, `save_series()`: Helpers cho I/O.
- **config/settings.py**: Cấu hình toàn bộ:
  - Tỷ lệ split.
  - Đường dẫn I/O.
  - Danh sách cột features, derived features, targets.
  - Cột cần drop.
- **config/feature_schema.py**: Logic build views (feature/target selection).

## Cách tách train/validation/test
- **Không random**: Dùng `split_by_time()` để chia theo thời gian (temporal split), đảm bảo val/test là future data so với train.
- Tỷ lệ: 70% train, 15% valid, 15% test (có thể chỉnh trong `settings.py`).
- Đảm bảo không data leakage: Fill NaN cho val/test dùng statistics từ train only.

## Sử dụng cho benchmark
1. Chạy pipeline trên để tạo dataset.
2. Train TabNet trên `X_train.csv`, `y_train.csv` (nếu có target).
3. Evaluate trên `X_valid.csv`/`X_test.csv`.
4. So sánh metrics với models của bạn (e.g., accuracy, F1 cho classification tasks).
5. Sử dụng `threshhold/` để set evaluation thresholds nếu cần.

## Lưu ý
- Đảm bảo JSONL sources tồn tại trước khi chạy Preprocessor.py.
- Nếu thay đổi `settings.py`, cần re-run cả 2 scripts.
- `TARGET_COL` trong `prepare_train_tabnet.py` hiện là `None` – set nếu có target column.
- Dữ liệu output được ignore trong .gitignore để tránh commit large files.</content>
<parameter name="filePath">d:\AgriFusion-IoT\Backend\Benchmark\Tabnet_vanilla\README.md