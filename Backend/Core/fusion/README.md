# Fusion

`fusion/` hợp nhất các snapshot Layer 2 thành bảng Layer 2.5.

`layer25.py` đọc `history.jsonl` của từng sensor, gom snapshot theo `ts_hour_bucket`, rồi flatten các nhóm dữ liệu đang còn sống trong schema Layer 2.

## Đầu vào

- `Output_data/Layer2/<stream>/<sensor_id>/history.jsonl`

## Đầu ra

- `Output_data/Layer2.5/super_table/super_table.jsonl`
- `Output_data/Layer2.5/super_table/super_table.csv`
- `Output_data/Layer2.5/super_table/latest.json`
- `Output_data/Layer2.5/super_table/manifest.json`

## Nhóm dữ liệu được flatten

- `perception`: giá trị đo đã chuẩn hóa.
- `quality`: cờ chất lượng trực tiếp từ packet hoặc provider.
- `context`: metadata thời gian/nguồn.
- `derived_signals`: thống kê mô tả như delta, trend và coverage metadata đã được expose từ Layer 2.

Fusion không tạo `health`, `confidence`, `handoff`, `ready`, `present`, `source coverage` hoặc `tabnet_ready`. Những thuộc tính đó không còn thuộc contract hiện tại.
