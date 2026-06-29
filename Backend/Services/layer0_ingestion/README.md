# Layer0 Ingestion

## 1. Mục đích

`Backend/Services/layer0_ingestion` là package chuẩn để đưa dữ liệu nguồn về local dưới dạng raw artifact có thể audit và tái lập được.

Nó không làm tiền xử lý theo nghĩa phân tích sensor. Nó chỉ:

- xác định record mới hay trùng
- kéo payload mới nhất
- ghi lịch sử raw về đĩa
- ghi metadata và trạng thái đồng bộ

## 2. Kiến trúc xử lý

```text
layer0_ingestion/
|-- pipeline.py
|-- sources/
|   |-- firebase.py
|   |-- json_export.py
|   `-- open_meteo.py
|-- stores/
|   |-- artifact_store.py
|   |-- telemetry_store.py
|   `-- sync_state_store.py
|-- sync/
|   `-- latest_sync.py
|-- models/
|   `-- telemetry.py
|-- utils/
`-- docs/
```

Luồng xử lý chuẩn:

```text
fetch latest meta
-> parse snapshot
-> compare with sync_state cũ
-> quyết định fetch current hay bỏ qua
-> ghi latest/raw/history/audit
-> cập nhật sync_state
```

## 3. Input

- Firebase RTDB
- file JSON export
- Open-Meteo API
- `Backend/Services/.env`
- tham số CLI từ `Backend/main.py`

## 4. Output

- `Backend/Output_data/Layer0/Firebase_data/new_raw/latest.json`
- `Backend/Output_data/Layer0/Firebase_data/new_raw/latest_meta.json`
- `Backend/Output_data/Layer0/Firebase_data/new_raw/source_manifest.json`
- `Backend/Output_data/Layer0/Firebase_data/new_raw/source_snapshot.json`
- `Backend/Output_data/Layer0/Firebase_data/new_raw/sync_state.json`
- `Backend/Output_data/Layer0/Firebase_data/history/**`
- `Backend/Output_data/Layer0/OpenMeteo_Data/**`

## 5. Ví dụ kết quả

### 5.1. Ví dụ `sync_state.json`

```json
{
  "status": "new_data",
  "latest_event_key": "1778386998",
  "latest_date_key": "2026-05-10"
}
```

### 5.2. Ví dụ file lịch sử raw

```json
{
  "date_key": "2026-05-10",
  "event_key": "1778386998",
  "path": "Node1/telemetry/2026-05-10/1778386998",
  "record": {
    "packet": {},
    "sensors": {}
  }
}
```

## 6. Cách tái lập

### 6.1. Kéo latest từ Firebase

```powershell
python Backend\main.py --only-layer0 --source firebase --node-id Node1
```

### 6.2. Kéo full history từ Firebase

```powershell
python Backend\main.py --only-layer0 --source firebase --node-id Node1 --full-history
```

### 6.3. Dùng file JSON export

```powershell
python Backend\main.py --only-layer0 --source json-export --input-json C:\path\export.json --node-id Node1 --full-history
```

### 6.4. Sync thêm meteo

```powershell
python Backend\main.py --only-layer0 --source firebase --node-id Node1 --sync-meteo --meteo-mode all
```

## 7. Thư viện cần cài

- `firebase-admin`
- `python-dotenv`
- `openmeteo-requests`
- `requests-cache`
- `retry-requests`

## 8. Giả định xử lý

- `Layer0IngestionPipeline` là entrypoint chuẩn.
- `latest/meta` là nguồn chính để quyết định có dữ liệu mới hay không.
- raw history phải giữ nguyên để audit; không tự ý sửa dữ liệu nguồn ở bước này.

## 9. Rủi ro và giới hạn

- Source Firebase vẫn phải hỗ trợ cả root dữ liệu chuẩn hiện tại và một số path legacy để không làm gãy hệ đang có.
- Nếu metadata mới nhưng `latest/current` bị thiếu, pipeline sẽ trả về trạng thái lỗi và không giả lập dữ liệu thay thế.
