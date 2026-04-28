# Bộ xử lý SHT30

## Mục đích

Package này chứa logic tiền xử lý Layer 2 cho dòng dữ liệu khí hậu không khí từ SHT30.

Mục tiêu là chuyển packet thô thành snapshot sẵn sàng cho domain agent, gồm:

- perception đã chuẩn hóa,
- điểm tin cậy,
- bộ nhớ ngắn và trung hạn,
- gợi ý ngữ cảnh cho suy luận khí hậu vi mô.

## Cấu trúc file

| File | Vai trò |
| --- | --- |
| `__init__.py` | Export `SHT30Processor` cho pipeline dùng chung. |
| `processor.py` | Tạo output Layer 2 gồm perception, windows, context, anomaly hints và payload bàn giao. |
| `health.py` | Chuyển cờ sensor/driver thành confidence cho tầng suy luận. |

## `processor.py` tạo ra gì

Mỗi record sau xử lý có:

- `perception`: nhiệt độ không khí, độ ẩm không khí, chất lượng sensor.
- `memory.windows`: cửa sổ rolling `3h`, `6h`, `24h`, `72h` để hỗ trợ suy luận theo xu hướng.
- `context`: giờ trong ngày, transport, pin và xu hướng độ ẩm lớn.
- `inference_hints`: humidity spike, condensation risk, heat stress và weather-driven likelihood.
- `layer3_interface`: output rút gọn cho domain agent.

`temp_trend_short_horizon` được lấy từ short trend window cấu hình trong processor. `temp_trend_window_key` ghi lại window nào thật sự được dùng để tránh hard-code nhãn cửa sổ khi cấu hình thay đổi.

## `health.py` làm gì

`health.py` chuyển độ chắc chắn từ driver thành trust score.

Các penalty trong file này không phải copy trực tiếp từ datasheet Sensirion. Chúng là trọng số nội bộ để giảm confidence khi driver báo điều kiện đọc không tốt.

Logic dựa trên:

1. tín hiệu cứng từ driver:
   - `sht_read_ok`
   - `sht_sample_valid`
   - `sht_error`
   - `sht_invalid_streak`
   - `sht_retry_count`
2. giả định rằng SHT30 có độ chính xác tốt khi sample hợp lệ,
3. nhu cầu tách rõ lỗi sensor khỏi biến động khí hậu vi mô thật.

## Ghi chú về ngưỡng

Một số ngưỡng đang là heuristic và cần hiệu chỉnh bằng dữ liệu thực tế:

| Ngưỡng / trọng số | Ý nghĩa hiện tại |
| --- | --- |
| `HEAT_STRESS_TEMPERATURE_C = 31` | Điểm cảnh báo sớm cho stress nhiệt trong logic hiện tại. |
| `AIR_STRESS_HUMIDITY_BASE_PCT = 80` | Mốc độ ẩm dùng khi tính air-stress score. |
| `CONDENSATION_HUMIDITY_BASE_PCT = 85` | Mốc độ ẩm cao dùng để nghi ngờ ngưng tụ. |
| `HUMIDITY_SPIKE_DELTA_PCT = 7.5` | Độ lệch so với trung bình 24h đủ lớn để xem là spike. |
| `WEATHER_SHIFT_REFERENCE_PCT = 12` | Mốc delta tham chiếu để scale weather-driven likelihood. |
| `READ_FAIL_PENALTY = 0.35` | Giảm trust mạnh vì lỗi đọc phá vỡ contract cảm biến. |
| `INVALID_SAMPLE_PENALTY = 0.25` | Giảm trust mạnh vì packet tự đánh dấu sample không hợp lệ. |

Các ngưỡng này là ngưỡng suy luận, không phải giới hạn phần cứng. Chúng cần được hiệu chỉnh bằng dữ liệu vườn/nhà màng thực tế.

## Ý đồ thiết kế

Layer 2 nên trả lời:

- sensor đã đọc gì,
- dữ liệu đáng tin đến đâu,
- context gần đây nên được nhớ như thế nào.

Layer 2 không nên kết luận:

- cây chắc chắn đang stress,
- có nên phát cảnh báo cuối cùng hay không.

Các kết luận đó thuộc về tầng domain agent.
