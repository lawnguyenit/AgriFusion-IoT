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
- `memory.windows`: thống kê rolling theo `6h`, `24h`, `72h`.
- `context`: giờ quan sát, interval lấy mẫu, transport, trend độ ẩm đất 24h.
- `derived_signals`: delta/trend mô tả như `n_delta_24h`, `ph_delta_24h`, `ec_delta_24h`, `soil_moisture_trend_24h`, `nutrient_spread_ratio`.

## Ghi chú về NPK

Giá trị NPK từ cảm biến đất phổ thông thường cần hiệu chuẩn thực địa nếu muốn dùng cho kết luận nông học mạnh. Vì vậy Layer 2 chỉ đưa ra dữ liệu quan sát và thống kê mô tả. Các kết luận như thiếu dinh dưỡng, mất cân bằng, mặn hóa, hoặc rửa trôi phải thuộc về tầng phân tích có cơ sở hiệu chuẩn riêng.
