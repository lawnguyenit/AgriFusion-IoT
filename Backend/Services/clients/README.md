# Firebase Client Boundary

## 1. Mục đích

`Backend/Services/clients` là lớp biên chuẩn để mọi service khác nói chuyện với Firebase RTDB. Ý tưởng là:

- gom logic kết nối vào một chỗ
- tránh mỗi pipeline tự khởi tạo `firebase_admin`
- giúp audit dễ hơn khi cần chứng minh bước nào đọc và bước nào ghi dữ liệu

## 2. Kiến trúc xử lý

```text
clients/
|-- __init__.py
`-- firebase_rtdb.py
```

`firebase_rtdb.py` hiện cung cấp:

- `pull_data(node_path)`
- `pull_sensor_data(node_path)`
- `set_data(node_path, payload)`
- `update_data(node_path, payload)`

## 3. Input

- `FIREBASE_KEY_PATH` trong `Backend/Services/.env`
- `DATABASE_URL` trong `Backend/Services/.env`
- đường dẫn node như:
  - `Node1/latest/current`
  - `Node1/latest/meta`
  - `Node1/telemetry/2026-05-20`
  - `result`

## 4. Output

- object JSON đọc từ RTDB
- thao tác ghi `set` hoặc `update` lên RTDB

## 5. Ví dụ kết quả

### 5.1. Ví dụ đọc

```python
client.pull_data("Node1/latest/current")
```

Kết quả mong đợi:

```json
{
  "packet": {},
  "sensors": {},
  "ts_server": 1778387046
}
```

### 5.2. Ví dụ ghi

```python
client.set_data("result/meta", {"source": "server"})
```

## 6. Cách tái lập

- Copy `Backend/Services/.env.example` thành `Backend/Services/.env`
- Điền đúng `FIREBASE_KEY_PATH` và `DATABASE_URL`
- Gọi client thông qua:
  - `Layer0IngestionPipeline`
  - `TelemetryRuntimeTemplateInjector`
  - `ResultPublisherPipeline`

## 7. Thư viện cần cài

- `firebase-admin`
- `python-dotenv`

## 8. Giả định xử lý

- Khóa service account tồn tại và còn hiệu lực.
- `firebase_admin.initialize_app(...)` chỉ cần khởi tạo một lần.

## 9. Rủi ro và giới hạn

- Client hiện là wrapper mỏng, chưa có retry policy riêng cho từng loại lỗi.
- `set_data` ghi đè toàn bộ node đích; vì vậy các pipeline phải chọn đúng path trước khi gọi.
