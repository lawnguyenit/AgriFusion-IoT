# Fusion

`fusion/` chứa logic hợp nhất nhiều snapshot Layer 2 thành bảng Layer 2.5.

Implementation chính hiện tại là `layer25.py`. File này đọc history của từng sensor, gom các snapshot theo `ts_hour_bucket`, sau đó flatten các nhóm dữ liệu quan trọng thành một hàng bảng.

## Đầu vào

- `Output_data/Layer2/<stream>/<sensor_id>/history.jsonl`

## Đầu ra

- `Output_data/Layer2.5/super_table/super_table.jsonl`
- `Output_data/Layer2.5/super_table/super_table.csv`
- `Output_data/Layer2.5/super_table/tabnet_ready.jsonl`
- `Output_data/Layer2.5/super_table/tabnet_ready.csv`

## Nhóm dữ liệu được flatten

- `perception`: giá trị đo đã chuẩn hóa.
- `quality`: cờ chất lượng trực tiếp từ packet hoặc provider.
- `context`: metadata thời gian/nguồn.
- `derived_signals`: thống kê mô tả như delta và trend.

Fusion không lọc theo `health`, `confidence` hoặc `handoff ready` vì các trường đó đã bị loại khỏi Layer 2. Điều kiện `tabnet_ready` hiện chỉ phản ánh độ phủ nguồn dữ liệu trong cùng bucket thời gian.
