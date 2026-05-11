# Bộ xử lý NPK

## Mục đích

Package này tạo snapshot Layer 2 cho cảm biến đất RS485/NPK.

Hướng thiết kế hiện tại là thận trọng: Layer 2 không tự đánh giá “đất tốt/xấu”, không tự tính `confidence`, và không kết luận rửa trôi hay mất cân bằng dinh dưỡng. Nó chỉ giữ dữ liệu đã chuẩn hóa và các thống kê mô tả để tầng sau phân tích tiếp.

## Cấu trúc file

| File | Vai trò |
| --- | --- |
| `__init__.py` | Export `NPKProcessor` cho pipeline dùng chung. |
| `processor.py` | Lọc packet NPK hợp lệ, chuẩn hóa perception, tính rolling windows và derived signals. |

## Output chính

- `perception`: `n_ppm`, `p_ppm`, `k_ppm`, `soil_temp_c`, `soil_humidity_pct`, `soil_ph`, `soil_ec_us_cm`.
- `quality`: các cờ trực tiếp từ packet như `read_ok`, `frame_ok`, `crc_ok`, `values_valid`, `sensor_alarm`, `retry_count`.
- `memory.windows`: thống kê rolling theo `3h`, `6h`, `24h`, `72h`.
- `derived_signals`: feature phẳng được rút từ `memory.windows` cho mọi lát thời gian, ví dụ `n_delta_from_start_3h`, `n_trend_24h`, `soil_moisture_avg_72h`, `ec_trend_per_hour_24h`.
- `context`: metadata vận hành như giờ quan sát, interval lấy mẫu và transport.

## Nguyên tắc downstream

`memory.windows` là bản đầy đủ để debug và audit. `derived_signals` không tính lại số liệu, chỉ flatten các thống kê đã có để Layer 2.5, TabNet hoặc notebook dùng nhanh hơn.

Các kết luận như thiếu dinh dưỡng, mất cân bằng, mặn hóa hoặc rửa trôi phải thuộc về tầng phân tích có cơ sở hiệu chuẩn riêng.
