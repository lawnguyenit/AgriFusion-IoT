# Bộ xử lý NPK

## Mục đích

Package này chứa logic tiền xử lý Layer 2 cho dòng dữ liệu cảm biến đất RS485 7-in-1.

Layer này không đưa ra kết luận nông học cuối cùng. Nhiệm vụ chính là:

1. chuẩn hóa packet thô thành schema ổn định,
2. đánh giá độ tin cậy của mẫu NPK hiện tại,
3. xây dựng bộ nhớ theo cửa sổ thời gian cho tầng suy luận phía sau,
4. tạo payload sạch để bàn giao cho tầng domain agent.

## Cấu trúc file

| File | Vai trò |
| --- | --- |
| `__init__.py` | Export `NPKProcessor` cho pipeline dùng chung. |
| `processor.py` | Tạo snapshot Layer 2 gồm perception, window memory, context, inference hints và payload bàn giao. |
| `health.py` | Tính confidence/trust cho stream NPK từ cờ truyền thông, cờ sensor, rủi ro đất khô và trạng thái nguồn. |

## `processor.py` tạo ra gì

Mỗi record sau xử lý có các nhóm chính:

- `perception`: N, P, K, nhiệt độ đất, độ ẩm đất, pH, EC, chất lượng sensor.
- `memory.windows`: cửa sổ rolling `6h`, `24h`, `72h` để hỗ trợ suy luận theo xu hướng.
- `context`: giờ trong ngày, interval lấy mẫu, transport, pin và xu hướng độ ẩm đất.
- `inference_hints`: tín hiệu sớm cho tầng sau như mất cân bằng dinh dưỡng, rủi ro mặn, rủi ro độ tin cậy khi đất khô và khả năng rửa trôi.
- `layer3_interface`: contract rút gọn để bàn giao cho domain agent.

## `health.py` làm gì

`health.py` chuyển độ chắc chắn ở mức packet thành `confidence`.

Các penalty trong file này không phải số hiệu chuẩn từ nhà sản xuất. Chúng là trọng số nội bộ để cho tầng suy luận biết khi nào cần giảm độ tin cậy.

Logic dựa trên ba nhóm thông tin:

1. tín hiệu cứng từ protocol/driver:
   - `read_ok`
   - `frame_ok`
   - `crc_ok`
   - `npk_values_valid`
   - `retry_count`
   - `sensor_alarm`
2. lưu ý từ manual/vendor về nhóm cảm biến đất 7-in-1,
3. heuristic thực địa về mức giảm niềm tin trước khi dữ liệu được chuyển cho tầng sau.

## Ghi chú về ngưỡng

Một số ngưỡng đang dùng là heuristic và cần hiệu chỉnh bằng dữ liệu thực địa:

| Ngưỡng / trọng số | Ý nghĩa hiện tại |
| --- | --- |
| `LOW_MOISTURE_WARNING_PCT = 30` | Đất khô có thể làm sai lệch bối cảnh ion và giảm độ tin cậy của NPK. |
| `VERY_LOW_MOISTURE_PCT = 20` | Rủi ro sai lệch tăng mạnh khi đất rất khô. |
| `LOW_MOISTURE_PENALTY = 0.25` | Mức giảm trust khi độ ẩm đất dưới 30%. |
| `VERY_LOW_MOISTURE_EXTRA_PENALTY = 0.10` | Mức giảm trust bổ sung khi dưới 20%. |
| `SALINITY_RISK_BASELINE_US_CM = 1200` | Điểm cảnh báo sớm cho EC cao trong logic hiện tại. |
| `NUTRIENT_IMBALANCE_INDEX = 0.55` | Heuristic cho trường hợp tỷ lệ NPK lệch đủ lớn để cần xem xét. |
| `LEACHING_N_SHIFT_DELTA = -8` | Tín hiệu N giảm đáng kể trong điều kiện ẩm, gợi ý khả năng rửa trôi. |

Các giá trị này được tách khỏi cờ protocol để có thể hiệu chỉnh sau bằng nhãn thực địa.

## Ý đồ thiết kế

Layer 2 cần nghiêm ngặt về độ tin cậy nhưng chưa nên kết luận nông học cuối cùng.

Điều đó nghĩa là:

- `health.py` quyết định mẫu có đáng tin đến mức nào.
- `processor.py` đóng gói mẫu với đủ context và memory.
- kết luận cuối cùng nên thuộc về tầng domain agent, không nằm ở đây.
