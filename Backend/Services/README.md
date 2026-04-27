# Firebase services v2

Tài liệu này mô tả luồng hoạt động chính của `firebase_services_v2.py` khi kết nối và làm việc với Firebase.

## Luồng hoạt động chung

1. `FirebaseServiceV2()` được tạo
   - đặt `env_path` về `Backend/Services/.env`
   - khởi tạo các trường `key_path` và `db_url` là `None`

2. `initialize_firebase_connection()` được gọi
   - kiểm tra xem `firebase_admin` đã cài chưa
   - gọi `load_env()` để nạp cấu hình từ file `.env`
     - nếu `.env` không tồn tại thì lỗi ngay
     - nếu `FIREBASE_KEY_PATH` hoặc `DATABASE_URL` thiếu thì lỗi
   - `FIREBASE_KEY_PATH` được resolve thành đường dẫn tuyệt đối
     - với path tương đối, resolve dựa trên thư mục `Backend/Services`
   - kiểm tra file key Firebase tồn tại
   - kiểm tra app Firebase hiện tại
     - nếu chưa có app, khởi tạo app mới bằng `initialize_app(...)`

3. Sau khi kết nối thành công
   - `firebase_admin` có app sẵn sàng
   - các phương thức `pull_data()` và `save_data()` sử dụng `firebase_admin.db`

4. `pull_data(path)`
   - gọi `db.reference(path)`
   - lấy dữ liệu `ref.get()`
   - nếu không có dữ liệu, trả về `{}`

5. `save_data(path, data)`
   - gọi `db.reference(path)`
   - ghi dữ liệu bằng `ref.set(data)`

## Cập nhật quan trọng

- `load_env()` chỉ đọc file `.env` tại `Backend/Services`, không tìm file ở thư mục chạy.
- `FIREBASE_KEY_PATH` nên được định nghĩa tương đối với `Backend/Services` hoặc là đường dẫn tuyệt đối.
- `initialize_firebase_connection()` sẽ không khởi tạo app Firebase mới nếu app đã tồn tại.

## Yêu cầu môi trường

- `python-dotenv`
- `firebase-admin`

## Cách chuẩn bị

Tạo file `Backend/Services/.env` từ `Backend/Services/.env.example` và khai báo:

```text
FIREBASE_KEY_PATH=path/to/service-account.json
DATABASE_URL=https://<your-project>.firebaseio.com
```

## Triển khai nhanh

```python
from firebase_services_v2 import FirebaseServiceV2

service = FirebaseServiceV2()
service.initialize_firebase_connection()
print(service.pull_data("Node1"))
```

## Ghi chú

- Thư mục `Backend/Services` là nơi tập trung cấu hình `.env` cho service này.
- Nếu có nhiều service trong tương lai, nên duy trì file `.env` hoặc cấu hình riêng cho từng service.
