# AgriFusion IoT

## 1. Mục đích của repository

Repository này lưu toàn bộ phần việc chính của đồ án:

- Firmware và logic phía node IoT.
- Pipeline backend để kéo dữ liệu, chuẩn hóa, sinh đặc trưng và publish kết quả.
- Dashboard web để đọc kết quả đã publish từ Firebase RTDB.
- Benchmark và các nhánh thí nghiệm phục vụ phân tích mô hình.

Luồng nộp bài nên được đọc theo thứ tự:

1. `Backend/README.md`
2. `Backend/Config/README.md`
3. `Backend/Services/README.md`
4. `Backend/Core/README.md`
5. `Frontend/README.md`

## 2. Luồng dữ liệu chính

```text
IoT Node / Firebase RTDB / Open-Meteo
        |
        v
Backend/Services/clients
        |
        v
Backend/Services/layer0_ingestion
        |
        v
Backend/Output_data/Layer0
        |
        v
Backend/Core/layer1/pipelines
        |
        v
Backend/Output_data/Layer1
        |
        v
Backend/Core/fusion
        |
        v
Backend/Output_data/SuperTable
        |
        v
Backend/Services/result_publisher
        |
        v
Firebase RTDB: result/*
        |
        v
Frontend/public/app.js
```

## 3. Cấu trúc thư mục cần quan tâm khi đọc

```text
AgriFusion-IoT/
|-- Backend/
|   |-- main.py
|   |-- Config/
|   |-- Services/
|   |-- Core/
|   |-- DemoUI/
|   |-- Benchmark/
|   `-- requirements.txt
|-- Frontend/
|-- IoT_Node/
|-- Docs/
`-- README.md
```

## 4. Thư viện cần cài

### 4.1. Backend pipeline tối thiểu

Chạy trong thư mục `Backend/`:

```powershell
python -m pip install -r requirements.txt
```

Danh sách hiện đang dùng trong code:

- `firebase-admin`
- `python-dotenv`
- `openmeteo-requests`
- `requests-cache`
- `retry-requests`
- `numpy`
- `pandas`
- `scikit-learn`
- `joblib`
- `matplotlib`
- `xgboost`
- `pytorch-tabnet`
- `pandas-stubs`

### 4.2. Phụ thuộc bổ sung cho benchmark dùng Torch

Một số benchmark và nhánh cũ dùng `torch`. Nên cài theo hướng dẫn chính thức phù hợp với máy:

- CPU only
- CUDA tương ứng GPU nếu có

Ví dụ:

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### 4.3. Frontend

Frontend hiện là static dashboard, không có `npm install`. Chỉ cần:

- trình duyệt
- kết nối Internet để tải Firebase SDK CDN
- file `Frontend/public/config.local.json` nếu muốn đọc Firebase thật

## 5. Cách tái lập nhanh toàn bộ luồng

### 5.1. Chạy từ dữ liệu Firebase thật

```powershell
cd Backend
python main.py --to-layer super-table --source firebase --node-id Node1 --full-history --publish-result --result-mode snapshot
```

Ý nghĩa:

- Kéo dữ liệu về `Layer0`
- Tiền xử lý lên `Layer1`
- Hợp nhất thành `SuperTable`
- Publish `result/*` lên Firebase để web đọc

### 5.2. Chạy chỉ phần publish từ artifact local đã có

```powershell
cd Backend
python main.py --only-result --publish-result --result-mode snapshot --result-payload-scope full
```

### 5.3. Mở dashboard local

```powershell
python -m http.server 4173 -d Frontend/public
```

## 6. Ví dụ kết quả mong đợi

### 6.1. Output local

```text
Backend/Output_data/Layer0/...
Backend/Output_data/Layer1/...
Backend/Output_data/SuperTable/...
Backend/Output_data/Result_publish/latest_result_payload.json
```

### 6.2. Output Firebase

```text
result/meta
result/pipeline
result/latest
result/history/air
result/history/soil
result/history/npk
result/history/weather
result/analysis
```

### 6.3. Output web

Người đọc sẽ thấy:

- biểu đồ lịch sử
- trạng thái pipeline
- chẩn đoán runtime
- anomaly/recommendation do backend publish

## 7. Giới hạn hiện tại

- Cây `Benchmark/` đang có nhiều nhánh phát triển song song, không phải tất cả đều là đường chạy chính lên web.
- `Backend/Output_data/` là dữ liệu sinh ra, không nên nộp cùng source nếu mục tiêu là nộp mã nguồn.
- `Secrets/`, `Backend/Services/.env`, `Frontend/public/config.local.json`, `IoT_Node/lib/Config/src/Config.private.h` không được đưa vào gói nộp.
- `IoT_Node/lib/Config/src/Config.private.example.h` là file mẫu; copy thành `Config.private.h` rồi điền secret cục bộ khi cần chạy node thật.

## 8. Tài liệu đọc tiếp

- Tổng quan backend: `Backend/README.md`
- Cấu hình và môi trường: `Backend/Config/README.md`
- Service kéo dữ liệu và publish: `Backend/Services/README.md`
- Xử lý lõi: `Backend/Core/README.md`
- Dashboard web: `Frontend/README.md`
