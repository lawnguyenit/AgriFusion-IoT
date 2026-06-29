# Backend Config

## 1. Mục đích

`Backend/Config` là lớp cấu hình dùng chung cho toàn bộ backend. Đây là nơi gom:

- đọc biến môi trường
- chuẩn hóa path
- runtime setting
- helper thời gian
- helper JSON, JSONL, CSV

Mục tiêu của module này là làm cho mọi bước trong pipeline tái lập được và không phải hard-code đường dẫn trong từng service.

## 2. Kiến trúc xử lý

```text
Config/
|-- env.py        -> đọc .env và ép kiểu biến môi trường
|-- paths.py      -> registry các path chuẩn của backend
|-- runtime.py    -> BackendSettings và override từ CLI
|-- common.py     -> helper thời gian, ép kiểu, thống kê nhỏ
|-- storage.py    -> đọc/ghi JSON, JSONL, gzip, hash
`-- IO/
    `-- io_csv.py -> helper đọc/ghi CSV
```

## 3. Input

- `Backend/Services/.env`
- vị trí thật của repository trên máy
- dữ liệu JSON, JSONL, CSV do các module khác truyền vào

## 4. Output

- object `BackendSettings`
- object `BackendPaths`
- helper IO ổn định cho `Services`, `Core`, `Benchmark`

## 5. Ví dụ kết quả

### 5.1. Ví dụ `BackendSettings`

```python
settings.source_type == "firebase"
settings.node_id == "Node1"
settings.layer1_root == Path(".../Backend/Output_data/Layer1")
```

### 5.2. Ví dụ path được chuẩn hóa

```text
Backend/Output_data/Layer0
Backend/Output_data/Layer1
Backend/Output_data/SuperTable
Backend/Output_data/Result_publish
```

## 6. Cách tái lập

- Tạo file `Backend/Services/.env`
- Điền tối thiểu:
  - `FIREBASE_KEY_PATH`
  - `DATABASE_URL`
  - `EXPORT_SOURCE`
  - `EXPORT_NODE_ID`
- Chạy các command qua `Backend/main.py`

## 7. Thư viện cần cài

- `python-dotenv`
- `pandas`

Ngoài ra module này chỉ dùng thư viện chuẩn của Python cho phần còn lại.

## 8. Giả định xử lý

- `runtime.py` là nguồn chuẩn cho toàn bộ setting runtime.
- `paths.py` là nguồn chuẩn cho path nội bộ backend.
- `storage.py` là helper chuẩn cho JSON/JSONL.

## 9. Rủi ro và giới hạn

- Nếu `.env` thiếu hoặc sai, lỗi sẽ xuất hiện từ rất sớm ở service client hoặc Layer0.
- Thay đổi path chuẩn trong `Config` có thể ảnh hưởng dây chuyền đến `Core`, `Services`, `Benchmark`.
