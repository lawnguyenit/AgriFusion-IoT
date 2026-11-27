# agrifusion.settings

## 1. Mục đích

`src/agrifusion/settings` là lớp cấu hình dùng chung cho toàn bộ backend. Đây là nơi gom:

- đọc biến môi trường
- chuẩn hóa path
- runtime setting
- helper thời gian
- helper JSON, JSONL, CSV

Mục tiêu của module này là làm cho mọi bước trong pipeline tái lập được và không phải hard-code đường dẫn trong từng stage hay adapter.

## 2. Kiến trúc xử lý

```text
settings/
|-- env.py        -> đọc .env và ép kiểu biến môi trường
|-- paths.py      -> registry các path chuẩn của backend
|-- runtime.py    -> BackendSettings và override từ CLI
`-- (helper thời gian/ép kiểu/JSON/gzip/hash nằm ở agrifusion/io/)
```

## 3. Input

- `.env` (repo root; legacy `Backend/.env` is still read)
- vị trí thật của repository trên máy
- dữ liệu JSON, JSONL, CSV do các module khác truyền vào

## 4. Output

- object `BackendSettings`
- object `BackendPaths`
- helper IO ổn định cho `ingest`, `canonical`, `Benchmark`

## 5. Ví dụ kết quả

### 5.1. Ví dụ `BackendSettings`

```python
settings.source_type == "firebase"
settings.node_id == "Node1"
settings.layer1_root == Path(".../output/Layer1")
```

### 5.2. Ví dụ path được chuẩn hóa

```text
output/Layer0
output/Layer1
```

## 6. Cách tái lập

- Tạo file `.env` (repo root; legacy `Backend/.env` is still read)
- Điền tối thiểu:
  - `FIREBASE_KEY_PATH`
  - `DATABASE_URL`
  - `EXPORT_SOURCE`
  - `EXPORT_NODE_ID`
- Chạy các command qua `src/agrifusion/cli.py`

## 7. Thư viện cần cài

- `python-dotenv`
- `pandas`

Ngoài ra module này chỉ dùng thư viện chuẩn của Python cho phần còn lại.

## 8. Giả định xử lý

- `runtime.py` là nguồn chuẩn cho toàn bộ setting runtime.
- `paths.py` là nguồn chuẩn cho path nội bộ backend.
- `storage.py` là helper chuẩn cho JSON/JSONL.

## 9. Rủi ro và giới hạn

- Nếu `.env` thiếu hoặc sai, lỗi sẽ xuất hiện từ rất sớm ở infrastructure adapter hoặc Layer0.
- Thay đổi path chuẩn trong `Config` có thể ảnh hưởng dây chuyền đến `Core` và `Benchmark`.
