# Shared Helpers

Thư mục này chứa helper dùng chung cho toàn bộ fuzzy benchmark.

## Mục đích

- Tránh viết lại logic lặp đi lặp lại.
- Giữ hàm tính fuzzy, rolling slope và config loading ở một chỗ.
- Giúp Layer 2-5 có thể debug độc lập.

## File chính

- `config_loader.py`
  Đọc config JSON trong `configs/`.

- `fuzzy_math.py`
  Các hàm membership cơ bản:
  - shoulder
  - trapezoid / band context
  - clamp / weighted sum

- `timeseries.py`
  Helper theo `timestamp`:
  - load alignment CSV
  - attach master timeline features
  - rolling slope / rolling window theo thời gian thực

## Debug nhanh

- Nếu config không load được, kiểm tra path trong `config_loader.py`.
- Nếu rolling slope sai, kiểm tra kiểu `timestamp` và thứ tự sort trước khi tính.
- Nếu membership ra ngoài `[0, 1]`, xem lại hàm clip/clamp trong `fuzzy_math.py`.
