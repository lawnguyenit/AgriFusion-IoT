# Fusion

`fusion/` chứa logic hợp nhất nhiều nguồn dữ liệu.

Hiện tại implementation chính là `layer25.py`. File này đọc snapshot Layer 2 theo từng sensor, sau đó ghép chúng thành hàng dữ liệu Layer 2.5 để phục vụ phân tích và mô hình học máy.

Đầu vào:

- `Output_data/Layer2/<stream>/<sensor_id>/history.jsonl`

Đầu ra:

- `Output_data/Layer2.5/super_table/super_table.jsonl`
- `Output_data/Layer2.5/super_table/super_table.csv`
- `Output_data/Layer2.5/super_table/tabnet_ready.jsonl`
- `Output_data/Layer2.5/super_table/tabnet_ready.csv`

Package này tồn tại để logic fusion không bị trộn với logic xử lý riêng của từng sensor.
