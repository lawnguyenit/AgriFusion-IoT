# Bộ xử lý Meteo

`processors/meteo` quản lý dữ liệu thời tiết và snapshot Layer 2 cho nguồn Open-Meteo.

- `fetcher.py`: lấy dữ liệu Open-Meteo archive và ghi artifact thời tiết ở Layer 1.
- `processor.py`: tạo snapshot thời tiết ở Layer 2.
- `health.py`: đánh giá độ tin cậy của payload thời tiết.

Việc tách `fetcher.py` khỏi `processor.py` giúp phân biệt rõ phần truy cập API bên ngoài và phần tiền xử lý dữ liệu nội bộ.
