# Bảng Canonical

`canonical/` chứa các bộ dựng bảng dữ liệu chuẩn cho mô hình.

Hiện tại `tabnet_super_table.py` đọc trực tiếp:

```text
Output_data/Layer2.5/super_table/super_table.csv
```

và tạo:

```text
Output_data/TabNet/tabnet_matrix.csv
Output_data/TabNet/tabnet_schema.json
```

Package này không phụ thuộc vào `tabnet_ready.csv`, `present__*`, `health`, `handoff` hoặc `confidence`. Các field đó đã bị loại khỏi contract mới.

Chạy từ thư mục `Backend`:

```powershell
python Core\canonical\tabnet_super_table.py
```
