# Bảng Canonical

`canonical/` chứa các bộ dựng bảng dữ liệu chuẩn cho mô hình.

Hiện tại package này có `tabnet_super_table.py`, dùng để chuyển bảng Layer 2.5 thành dataset sạch hơn cho benchmark, ví dụ TabNet.

Chạy từ thư mục `Backend`:

```powershell
python Core\canonical\tabnet_super_table.py
```

Chạy với label cụ thể:

```powershell
python Core\canonical\tabnet_super_table.py --label-column npk__npk_7in1_1__flags__nutrient_imbalance
```

Mục tiêu của package này là tách rõ dữ liệu vận hành khỏi dữ liệu dùng cho mô hình.
