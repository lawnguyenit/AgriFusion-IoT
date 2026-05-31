# Layer0 Ingestion Pipeline Map

## Mục đích

Pipeline này đồng bộ telemetry mới nhất từ source hiện tại như Firebase hoặc JSON export về local Layer0 artifacts.

## Main flow

```text
Source
-> SourceAdapter
-> latest_meta_payload
-> LatestMetaSnapshot
-> SyncDecision
-> sync_state
-> latest_current_payload
-> local artifacts
-> Layer0IngestionResult
```

## Thành phần chính

- `pipeline.py`
  Vai trò: điều phối toàn bộ run và trả `Layer0IngestionResult`.
- `sources/`
  Vai trò: đọc source ngoài hoặc source offline.
- `sync/latest_sync.py`
  Vai trò: parse latest meta, quyết định trạng thái sync, build sync state.
- `stores/`
  Vai trò: ghi latest payload/meta, history snapshot, source manifest.
- `utils/`
  Vai trò: helper kỹ thuật của package ingest.

## Input

- source data từ Firebase / JSON export / Open-Meteo
- runtime settings từ `Backend/Config/runtime.py`
- storage helper từ `Backend/Config/storage.py`

## Output

- latest payload/meta local
- history snapshot local
- sync state local
- source manifest và source snapshot audit

## Rủi ro / giới hạn hiện tại

- Nếu latest meta thiếu key bắt buộc, pipeline sẽ fail sớm.
- Sai decision ở `latest_sync.py` có thể làm fetch thiếu hoặc fetch thừa.
- Package hỗ trợ cả normalized snapshot root lẫn legacy latest/current path để tương thích dữ liệu RTDB hiện tại.
