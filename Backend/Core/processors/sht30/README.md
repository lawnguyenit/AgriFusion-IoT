# Bộ xử lý SHT30

## Mục đích

Package này tạo snapshot Layer 2 cho dữ liệu nhiệt độ và độ ẩm không khí từ SHT30.

Layer 2 ở đây chỉ làm ba việc có thể bảo vệ được:

1. chuẩn hóa packet thô thành `perception`,
2. giữ lại các cờ chất lượng trực tiếp từ packet trong `quality`,
3. tính thống kê mô tả theo cửa sổ thời gian trong `memory` và `derived_signals`.

Layer này không kết luận cây đang stress, không tự tạo `confidence`, và không quyết định record có sẵn sàng cho agent hay không.

## Cấu trúc file

| File | Vai trò |
| --- | --- |
| `__init__.py` | Export `SHT30Processor` cho pipeline dùng chung. |
| `processor.py` | Lọc record SHT30 hợp lệ và tạo snapshot Layer 2. |

## Output chính

- `perception`: `temp_air_c`, `humidity_air_pct`.
- `quality`: `read_ok`, `sample_valid`, `sensor_sample_valid`, `sample_interval_ms`.
- `memory.windows`: thống kê rolling theo `3h`, `6h`, `24h`, `72h`.
- `derived_signals`: feature phẳng được rút từ `memory.windows`, ví dụ `temp_delta_from_start_6h`, `humidity_trend_24h`, `humidity_avg_72h`.
- `context`: metadata thời gian và nhãn short window đang dùng.

## Nguyên tắc

Các giá trị trong package này phải là dữ liệu đo, metadata hoặc thống kê mô tả. Nếu cần suy luận như ngưng tụ, stress nhiệt, bệnh hại hoặc khuyến nghị hành động, phần đó nên nằm ở tầng domain model hoặc rule engine có tài liệu khoa học/nhãn thực địa đi kèm.
