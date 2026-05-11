# Bộ xử lý Meteo

Package này chỉ chứa logic Layer 2 cho snapshot thời tiết.

Nguồn Open-Meteo/API fetch không nằm ở đây nữa. Phần lấy dữ liệu Layer 1 thuộc `Backend/Services/exporters/sources/open_meteo.py`.

## Cấu trúc

| File | Vai trò |
| --- | --- |
| `processor.py` | Chuẩn hóa payload meteo Layer 1 thành snapshot Layer 2. |
| `__init__.py` | Export `MeteoProcessor`. |

## Output chính

- `perception`: nhiệt độ, độ ẩm, mưa, điểm sương, mây, nhiệt độ đất nông, ET0 và mã thời tiết.
- `quality`: kiểm tra trường lõi có mặt hay không và provider.
- `memory.windows`: thống kê rolling theo `3h`, `6h`, `24h`, `72h`.
- `derived_signals`: feature phẳng được rút từ `memory.windows`, ví dụ `temp_trend_24h`, `humidity_delta_from_start_6h`, `precipitation_avg_72h`.
- `context`: giờ quan sát, trạng thái ngày/đêm, timezone và provider.

## Nguyên tắc

Layer 2 không sinh `health`, `confidence`, `handoff`, `ready` hoặc cảnh báo nông học cuối cùng. Những kết luận đó phải thuộc tầng phân tích có ngưỡng và cơ sở hiệu chuẩn riêng.
