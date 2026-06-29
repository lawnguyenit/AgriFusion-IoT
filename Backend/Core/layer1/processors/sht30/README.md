# Bộ xử lý SHT30

## 1. Mục đích

Module này chuẩn hóa dữ liệu SHT30 từ raw telemetry thành snapshot stream `sht30` trong `Layer1`.

Nó xử lý 3 việc:

- lọc record SHT30 hợp lệ
- chuẩn hóa nhiệt độ và độ ẩm không khí
- tính cửa sổ thời gian và fuzzy signal tương ứng

## 2. Kiến trúc xử lý

```text
SourceRecord
-> extract_sensor_id()
-> should_accept_source_record()
-> build_snapshot()
    -> perception
    -> memory.windows
    -> fuzzy_signals
```

## 3. Input

- `packet.sht30_data`
- `sensors.sht30`
- `ts_server`, `ts_device`, `event_key`, `date_key`

## 4. Output

- stream output: `Backend/Output_data/Layer1/sht30/*`
- perception chính:
  - `temp_air_c`
  - `humidity_air_pct`

## 5. Điều kiện chấp nhận record

- có `packet.sht30_data`
- có đủ:
  - `sht_temp_c`
  - `sht_hum_pct`
- `sht_read_ok = true`
- `sht_sample_valid = true`

## 6. Ví dụ kết quả

```json
{
  "processor_name": "sht30_preprocessor",
  "sensor_id": "sht30_1",
  "perception": {
    "temp_air_c": 35.09,
    "humidity_air_pct": 69.09
  },
  "memory": {
    "window_hours": [3, 6, 24, 72]
  }
}
```

## 7. Cách tái lập

```powershell
python Backend\main.py --only-layer1
```

## 8. Thư viện cần cài

- không có package ngoài riêng
- dùng chung môi trường `Backend/requirements.txt`

## 9. Giả định xử lý

- nếu payload thiếu `sensor_id` hoặc `sensor_type`, module sẽ fallback về cấu hình trong `Backend/Config/runtime.py`
- `ts_server` được dùng làm mốc thời gian chính

## 10. Rủi ro và giới hạn

- module này không tự kết luận stress nhiệt hay bệnh
- nếu dữ liệu thưa, window sẽ ra `insufficient_samples`
