# Bộ xử lý Meteo

## Mục đích

Package này quản lý dữ liệu thời tiết từ Open-Meteo và tạo snapshot Layer 2 cho fusion.

Layer 2 không tự tạo điểm tin cậy cho nhà cung cấp thời tiết. Nó chỉ kiểm tra các trường lõi có tồn tại, chuẩn hóa payload và tính thống kê mô tả theo thời gian.

## Cấu trúc file

| File | Vai trò |
| --- | --- |
| `fetcher.py` | Lấy dữ liệu Open-Meteo archive và ghi artifact thời tiết ở Layer 1. |
| `processor.py` | Tạo snapshot thời tiết Layer 2. |
| `__init__.py` | Export `MeteoProcessor`. |

## Output chính

- `perception`: nhiệt độ, độ ẩm, mưa, điểm sương, mây, nhiệt độ đất nông, ET0 và mã thời tiết.
- `quality`: kiểm tra trường lõi có mặt hay không và provider.
- `memory.windows`: thống kê rolling theo `3h`, `6h`, `24h`, `72h`.
- `context`: giờ quan sát, trạng thái ngày/đêm, timezone, provider.
- `derived_signals`: delta/trend mô tả như `temp_delta_24h`, `humidity_delta_24h`, `precipitation_delta_24h`, `et0_delta_24h`.

## Nguyên tắc

Các cảnh báo như heat stress, rain event có ý nghĩa canh tác, nhưng không nên đóng dấu ngay ở Layer 2 nếu chưa có ngưỡng theo cây trồng, giai đoạn sinh trưởng và điều kiện địa phương. Layer 2 chỉ chuẩn bị dữ liệu sạch để tầng sau đưa ra kết luận có căn cứ hơn.
