# Backend Data Pipelines

## 1. Mục đích

`Backend/` là phần điều phối toàn bộ luồng xử lý dữ liệu từ lúc lấy dữ liệu thô về máy cho đến lúc publish kết quả để web đọc được.

Backend hiện phục vụ 4 việc chính:

- Kéo dữ liệu từ Firebase RTDB, JSON export và Open-Meteo.
- Chuẩn hóa dữ liệu thô thành snapshot có cấu trúc theo từng stream.
- Hợp nhất snapshot thành bảng chung phục vụ benchmark và tái sử dụng feature.
- Publish kết quả runtime lên nhánh `result/*` trong Firebase RTDB.

## 2. Kiến trúc xử lý

```text
Backend/main.py
    |
    +-- Config/
    |     `-- env, path, runtime setting, helper IO
    |
    +-- Services/
    |     +-- clients/                 -> giao tiếp Firebase RTDB
    |     +-- layer0_ingestion/        -> kéo raw data về Layer0
    |     +-- telemetry_runtime_simulator/
    |     +-- telemetry_orchestrator/
    |     +-- result_publisher/        -> đẩy result/* lên Firebase
    |     `-- output_cutoff_maintenance/
    |
    +-- Core/
    |     +-- layer1/                  -> chuẩn hóa raw thành snapshot theo stream
    |     +-- fusion/                  -> tạo SuperTable
    |     +-- layer2/                  -> helper sinh feature time-series cho benchmark
    |     `-- canonical/
    |
    +-- DemoUI/
    `-- Benchmark/
```

## 3. Các giai đoạn chính trong flow

### Giai đoạn 1. Chuẩn bị môi trường

- Đọc `Backend/Services/.env`
- Xác định đường dẫn output
- Xác định nguồn dữ liệu và thông số runtime

### Giai đoạn 2. Layer0 ingestion

- Kéo metadata `latest/meta`
- Quyết định có fetch `latest/current` hay bỏ qua
- Ghi audit artifact và lịch sử raw về local

### Giai đoạn 3. Layer1 preprocessing

- Đọc raw artifact từ `Layer0`
- Phân luồng qua `SHT30Processor`, `NPKProcessor`, `MeteoProcessor`
- Tạo snapshot có `perception`, `memory`, `fuzzy_signals`, `external_weather`

### Giai đoạn 4. Fusion

- Gộp các snapshot theo `ts_server`
- Flatten thành một hàng chung trong `SuperTable`

### Giai đoạn 5. Result publish

- Đọc `Layer1`
- Dựng lại feature runtime
- Nạp model runtime
- Tạo payload `result/*`
- Ghi local debug artifact và publish lên Firebase

## 4. Input

- `Backend/Services/.env`
- Firebase RTDB hoặc file JSON export
- Open-Meteo API nếu bật sync meteo
- các artifact local trong `Backend/Output_data`
- model artifact trong `Backend/Benchmark`

## 5. Output

- `Backend/Output_data/Layer0/**`
- `Backend/Output_data/Layer1/**`
- `Backend/Output_data/SuperTable/**`
- `Backend/Output_data/Result_publish/**`
- dữ liệu `result/*` trên Firebase RTDB

## 6. Ví dụ kết quả

### 6.1. Ví dụ output sau Layer1

```json
{
  "sensor_id": "sht30_1",
  "timestamps": {
    "ts_server": 1778387046,
    "observed_at_local": "2026-05-10T11:24:06+07:00"
  },
  "perception": {
    "temp_air_c": 35.09,
    "humidity_air_pct": 69.09
  }
}
```

### 6.2. Ví dụ output sau publish

```json
{
  "meta": {
    "source": "server"
  },
  "latest": {
    "air": {},
    "soil": {},
    "npk": {},
    "weather": {}
  },
  "analysis": {
    "diagnosis": {},
    "forecast": {},
    "anomalies": {}
  }
}
```

## 7. Cách tái lập

### 7.1. Cài thư viện

```powershell
cd Backend
python -m pip install -r requirements.txt
```

### 7.2. Xem toàn bộ command hỗ trợ

```powershell
python main.py --help
```

### 7.3. Chạy từng lớp độc lập

```powershell
python main.py --only-layer0 --source firebase --node-id Node1
python main.py --only-layer1
python main.py --only-super-table
python main.py --only-result --publish-result --result-mode snapshot
```

### 7.4. Chạy full flow từ Layer0 đến publish

```powershell
python main.py --to-layer super-table --source firebase --node-id Node1 --full-history --publish-result --result-mode snapshot
```

## 8. Thư viện cần cài

- Nhóm bắt buộc cho flow chính: `firebase-admin`, `python-dotenv`, `openmeteo-requests`, `requests-cache`, `retry-requests`, `numpy`, `pandas`, `scikit-learn`, `joblib`, `matplotlib`, `xgboost`
- Nhóm benchmark mở rộng: `pytorch-tabnet`
- Nhóm benchmark Torch: `torch` cài riêng theo CPU/CUDA

## 9. Giả định xử lý

- `ts_server` là trục thời gian chính.
- `Backend/main.py` là entrypoint chuẩn của toàn bộ backend.
- `Config/` không chứa business logic lớn.
- `Services/` không thay thế `Core/`; nó chỉ giao tiếp với nguồn ngoài và runtime online.

## 10. Rủi ro và giới hạn

- Một số nhánh benchmark vẫn tồn tại vì mục đích nghiên cứu, nên không nên nhầm toàn bộ `Benchmark/` là đường chạy production.
- Snapshot trong `Layer1` vẫn mang trường `layer = "layer2"` do legacy contract; README sẽ ghi rõ, nhưng code không đổi schema ở đợt này.
- Các command có tương tác Firebase là command ghi dữ liệu thật.
