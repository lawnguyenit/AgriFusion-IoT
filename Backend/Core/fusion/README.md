# SuperTable Fusion

## 1. Mục đích

`Backend/Core/fusion` hợp nhất các snapshot theo stream thành một bảng chung tên là `SuperTable`.

Mục tiêu:

- tạo một hàng chung theo `ts_server`
- flatten dữ liệu để benchmark và downstream đọc nhanh
- giữ trace ngược về stream nguồn và event nguồn

## 2. Kiến trúc xử lý

```text
Layer1/history.jsonl của từng stream
-> load snapshot
-> dedupe theo ts_server trong từng stream
-> group theo ts_server toàn cục
-> flatten perception/memory/fuzzy/external_weather
-> ghi SuperTable
```

## 3. Input

- `Backend/Output_data/Layer1/**/history.jsonl`

## 4. Output

- `Backend/Output_data/SuperTable/super_table.jsonl`
- `Backend/Output_data/SuperTable/super_table.csv`
- `Backend/Output_data/SuperTable/latest.json`
- `Backend/Output_data/SuperTable/manifest.json`

## 5. Ví dụ kết quả

```json
{
  "ts_server": 1778387046,
  "observed_at_local": "2026-05-10T11:24:06+07:00",
  "sht30__sht30_1__perception__temp_air_c": 35.09,
  "npk__npk_7in1_1__perception__n_ppm": 43.0,
  "meteo__meteo__perception__cloud_cover_pct": 99.0
}
```

## 6. Cách tái lập

```powershell
python Backend\main.py --only-super-table
```

Hoặc chạy liền từ đầu:

```powershell
python Backend\main.py --to-layer super-table --source firebase --node-id Node1 --full-history
```

## 7. Thư viện cần cài

- không có package ngoài riêng
- dùng chung môi trường `Backend/requirements.txt`

## 8. Giả định xử lý

- `ts_server` là khóa ghép chính.
- Snapshot stream đã được chuẩn hóa trước khi vào fusion.

## 9. Rủi ro và giới hạn

- Fusion hiện là thao tác flatten kỹ thuật, chưa sinh thêm field nghiệp vụ mới.
- Nếu một stream bị thưa dữ liệu, hàng trong `SuperTable` có thể chỉ có cột của một phần sensor tại timestamp đó.
