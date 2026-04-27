# Exporters pipeline

`Backend/Services/exporters` chứa luồng xuất dữ liệu từ nguồn Layer 1 (Firebase RTDB hoặc JSON export) vào các artifact local có cấu trúc chuẩn. README này giải thích cách pipeline hoạt động và các thành phần chính.

## Mục tiêu

Pipeline này đảm bảo:

- lấy metadata mới nhất từ nguồn
- xác định xem có dữ liệu mới hay không
- ghi các artifact local có thể dùng cho downstream Layer 2
- lưu trạng thái đồng bộ để lần chạy sau so sánh
- hỗ trợ cả `firebase` và `json-export`

## Luồng chính

1. `ExportPipeline.run(full_history=False)` được gọi.
2. Tạo `source_adapter` dựa trên `settings.source_type`:
   - `firebase` → `FirebaseSourceAdapter`
   - `json-export` → `JsonExportSourceAdapter`
3. Tải `previous_sync_state` từ ổ lưu `sync_state.json`.
4. Gọi `source_adapter.fetch_latest_meta_payload()` để lấy payload metadata mới nhất.
   - Nếu không có payload, pipeline trả về `None`.
5. Chuyển metadata đó thành `LatestMetaSnapshot` bằng `parse_latest_meta()`.
6. Gọi `decide_sync()` để quyết định:
   - có dữ liệu mới (`new_data`)
   - chỉ refresh nguồn (`source_refresh`)
   - retry chờ dữ liệu mới (`retry_waiting`)
   - stale sau retry (`stale_after_retry`)
   - duplicate JSON import (`duplicate_source`)
7. Xây `sync_state` mới bằng `build_sync_state()`.
8. Nếu nguồn không phải duplicate, ghi:
   - `latest_meta`
   - `source_manifest`
   - `source_snapshot` (nếu có)
9. Nếu `decision.should_fetch_current` là True:
   - lấy payload hiện tại
   - ghi `latest_payload`
   - ghi snapshot lịch sử ngày sự kiện vào `history`
10. Nếu `full_history` bật và không duplicate source:
    - tải toàn bộ `telemetry`
    - ghi `history` đầy đủ
11. Lưu `sync_state.json` mới.
12. Trả về `ExportResult` chứa trạng thái, đường dẫn artifact, và metadata chạy.

## Thành phần chính

### `ExportPipeline`

- Quản lý luồng chạy chính của exporter.
- Xây `source_adapter` và gọi lần lượt các bước đọc nguồn, quyết định sync, ghi artifact, và lưu sync state.

### `SourceAdapter`

Hai adapter chính:

- `FirebaseSourceAdapter`
  - phát hiện hai chế độ Firebase:
    - `snapshot_root`: nguồn đã có toàn bộ snapshot node
    - `legacy_paths`: sử dụng `latest_meta`, `latest_current`, `telemetry` riêng
  - chuẩn hoá payload và xác định bản ghi mới nhất

- `JsonExportSourceAdapter`
  - đọc file JSON export từ `settings.input_json_path`
  - chuẩn hoá và tính `source_sha256`
  - cho phép phát hiện duplicate khi cùng `event_key` và cùng `sha256`

### `latest_sync`

- `parse_latest_meta()` biến metadata thành đối tượng snapshot chứa thời gian, event key, path, checksum và các thông số polling.
- `decide_sync()` xác định giá trị trả về như `new_data`, `retry_waiting`, `stale_after_retry`, `duplicate_source`.
- `build_sync_state()` sinh json trạng thái đồng bộ mới.

### `artifact_store`

Ghi các artifact local:

- `latest_meta.json`
- `latest_payload.json`
- `source_manifest.json`
- `source_snapshot.json`

### `telemetry_store`

Viết snapshot lịch sử cho các event đã chạy:

- `history/<date>/<event>.json`
- các asset lịch sử toàn bộ nếu `full_history` bật

## Đặc điểm quan trọng

- `canonicalize_json()` được dùng để sắp xếp khóa JSON theo quy tắc ngày/timestamp/number/string, giúp checksum và so sánh dữ liệu ổn định.
- `JsonExportSourceAdapter` dùng `source_sha256` để phát hiện duplicate khi nhập lại cùng file export.
- `FirebaseSourceAdapter` tự chuyển payload Firebase về định dạng chuẩn trước khi tính metadata.
- `full_history` là tùy chọn, không phải mặc định.

## Khi nào pipeline ghi thêm dữ liệu

- `new_data`: ghi `latest_payload` và snapshot history
- `source_refresh`: vẫn lấy payload hiện tại và ghi lại local artifacts
- `retry_waiting`: không ghi `latest_payload`, chỉ cập nhật `sync_state`
- `duplicate_source`: không ghi `latest_payload` hay full history

## Phạm vi ứng dụng

Pipeline này là lớp export Layer 1, tạo artifact local để downstream Layer 2 xử lý mà không cần truy xuất trực tiếp Firebase mỗi lần.

## Cách chạy

Pipeline được gọi từ `Backend/main.py` hoặc từ các công cụ export tương ứng trong dự án. `settings.source_type` quyết định nguồn dữ liệu.
