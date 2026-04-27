# Pipeline Map — Export / Sync Telemetry

## 1. Mục tiêu của pipeline

Pipeline này dùng để đồng bộ dữ liệu telemetry mới nhất từ source hiện tại, có thể là Firebase hoặc JSON export, về local files.

Mục tiêu chính:

- lấy thông tin record mới nhất;
- quyết định có cần fetch dữ liệu mới hay không;
- ghi latest payload, history snapshot, audit artifacts;
- lưu sync state để lần chạy sau biết trạng thái trước đó.

---

## 2. Main flow

Source
→ SourceAdapter
→ latest_meta_payload
→ LatestMetaSnapshot
→ SyncDecision
→ sync_state
→ latest_current_payload
→ local artifacts
→ ExportResult

---

## 3. Stage 1 — Load previous sync state

**Owner file:** `sync_state_store.py`

**Hàm chính:**

- `load_sync_state()`
- `_default_sync_state()`

**Input:**

- `settings.sync_state_path`

**Output:**

- `previous_sync_state: dict`

**Ý nghĩa:**

Đọc trạng thái sync của lần chạy trước. Nếu chưa có file state hoặc file state bị lỗi JSON, tạo default state.

**Failure behavior:**

- Nếu file không tồn tại → dùng default state.
- Nếu file lỗi JSON → dùng default state.
- Không trực tiếp quyết định có fetch dữ liệu mới hay không.

---

## 4. Stage 2 — Build source adapter

**Owner file:** `pipeline.py`

**Hàm chính:**

- `ExportPipeline._build_source_adapter()`

**Input:**

- `settings.source_type`
- `firebase_service`
- `settings`

**Output:**

- `FirebaseSourceAdapter` nếu source là Firebase
- `JsonExportSourceAdapter` nếu source là JSON export

**Ý nghĩa:**

Chọn adapter phù hợp để pipeline không phải quan tâm source thật là Firebase hay file JSON.

**Failure behavior:**

- Nếu `source_type == "firebase"` nhưng thiếu `firebase_service` → lỗi.
- Nếu `source_type` không được hỗ trợ → lỗi.

---

## 5. Stage 3 — Fetch latest meta payload

**Owner file:** `source_adapters.py`

**Hàm chính:**

- `fetch_latest_meta_payload()`

**Input:**

- Firebase node hoặc JSON export file
- `settings`

**Output:**

- `latest_meta_payload: dict | None`

**Ý nghĩa:**

Lấy metadata của record mới nhất. Đây chưa phải dữ liệu sensor đầy đủ, mà là thông tin tóm tắt để pipeline biết record mới nhất là gì.

**Failure behavior:**

- Nếu không lấy được meta → `ExportPipeline.run()` trả `None`.
- Nếu source payload sai shape → có thể raise `ValueError`.

---

## 6. Stage 4 — Describe source

**Owner file:** `source_adapters.py`

**Hàm chính:**

- `describe_source()`

**Input:**

- trạng thái hiện tại của adapter

**Output:**

- `SourceDescriptor`
  - `source_type`
  - `source_uri`
  - `source_sha256`

**Ý nghĩa:**

Tạo mô tả nguồn dữ liệu để gắn vào sync state và audit artifact.

**Failure behavior:**

- Nếu source chưa được chuẩn bị đúng, thông tin hash/source có thể thiếu hoặc chưa chính xác.

---

## 7. Stage 5 — Parse latest meta

**Owner file:** `latest_sync.py`

**Hàm chính:**

- `parse_latest_meta()`

**Input:**

- `latest_meta_payload`
- `settings`
- `source_descriptor`

**Output:**

- `LatestMetaSnapshot`

**Ý nghĩa:**

Chuyển dict metadata thô thành object có cấu trúc rõ ràng để các bước sau dùng an toàn hơn.

**Failure behavior:**

- Nếu thiếu key bắt buộc như `latest_event_key`, `latest_date_key`, `ts_device`, `ts_server` → lỗi.

---

## 8. Stage 6 — Decide sync

**Owner file:** `latest_sync.py`

**Hàm chính:**

- `decide_sync()`

**Input:**

- `LatestMetaSnapshot`
- `previous_sync_state`
- `checked_at`
- `settings`

**Output:**

- `SyncDecision`

**Ý nghĩa:**

Quyết định lần chạy này thuộc trạng thái nào:

- `new_data`
- `source_refresh`
- `duplicate_source`
- `retry_waiting`
- `stale_after_retry`

Quan trọng nhất là field:

- `should_fetch_current: bool`

**Failure behavior:**

- Nếu decision sai, pipeline có thể fetch thiếu, fetch thừa, hoặc đánh dấu stale sai.

---

## 9. Stage 7 — Build sync state

**Owner file:** `latest_sync.py`

**Hàm chính:**

- `build_sync_state()`

**Input:**

- `LatestMetaSnapshot`
- `SyncDecision`
- `checked_at`
- `previous_sync_state`
- `settings`

**Output:**

- `sync_state: dict`

**Ý nghĩa:**

Tạo trạng thái mới để lưu lại cho lần chạy sau.

**Lưu ý:**

`decide_sync()` là nơi quyết định.  
`build_sync_state()` là nơi đóng gói kết quả quyết định thành state để lưu.

**Failure behavior:**

- Nếu state build sai, lần chạy sau có thể hiểu nhầm dữ liệu cũ/mới.

---

## 10. Stage 8 — Write latest meta and audit artifacts

**Owner files:**

- `artifact_store.py`
- `source_adapters.py`

**Hàm chính:**

- `write_latest_meta()`
- `build_audit_artifacts()`
- `write_source_audit_artifacts()`

**Input:**

- `latest_meta_payload`
- `source_descriptor`
- `checked_at`

**Output:**

- latest meta local file
- source manifest file
- source snapshot file nếu có

**Ý nghĩa:**

Ghi lại metadata mới nhất và tạo bằng chứng audit về source.

**Failure behavior:**

- Nếu ghi lỗi, mất khả năng truy vết source.
- Nếu audit thiếu, vẫn có thể có dữ liệu chính nhưng khó debug/tái lập sau này.

---

## 11. Stage 9 — Fetch current payload

**Owner file:** `source_adapters.py`

**Hàm chính:**

- `fetch_latest_current_payload()`

**Input:**

- `latest_meta_payload`

**Output:**

- `latest_current_payload: dict | None`

**Điều kiện chạy:**

Chỉ chạy nếu:

```python
decision.should_fetch_current == True