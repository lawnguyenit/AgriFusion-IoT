# Bộ xử lý NPK

## 1. Mục đích

Module này chuẩn hóa dữ liệu cảm biến đất/NPK thành snapshot stream `npk` trong `Layer1`.

Nó lưu lại:

- N, P, K
- nhiệt độ đất
- độ ẩm đất
- pH
- EC

và sinh các thống kê cửa sổ thời gian để các tầng sau dùng lại.

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

- `packet.npk_data`
- `sensors.npk`
- metadata nguồn của `SourceRecord`

## 4. Output

- stream output: `Backend/Output_data/Layer1/npk/*`
- perception chính:
  - `n_ppm`
  - `p_ppm`
  - `k_ppm`
  - `soil_temp_c`
  - `soil_humidity_pct`
  - `soil_ph`
  - `soil_ec_us_cm`

## 5. Điều kiện chấp nhận record

- có `packet.npk_data`
- có đủ trường:
  - `N`
  - `P`
  - `K`
  - `temp`
  - `hum`
  - `ph`
  - `ec`
- `read_ok = true`
- `npk_values_valid = true`
- `frame_ok != false`
- `crc_ok != false`

## 6. Ví dụ kết quả

```json
{
  "processor_name": "npk_preprocessor",
  "sensor_id": "npk_7in1_1",
  "perception": {
    "n_ppm": 43.0,
    "p_ppm": 147.0,
    "k_ppm": 140.0,
    "soil_humidity_pct": 55.8,
    "soil_ph": 5.6,
    "soil_ec_us_cm": 394.0
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

- nếu payload thiếu `sensor_id` hoặc `sensor_type`, module fallback về cấu hình trong `Backend/Config/runtime.py`
- module chỉ chuẩn hóa và thống kê, không tự kết luận “đất tốt/xấu”

## 10. Rủi ro và giới hạn

- nhiễu từ cảm biến hoặc packet lỗi sẽ bị chặn ở bước accept, nên số lượng record có thể thấp hơn raw
- signal dinh dưỡng ở đây vẫn là tín hiệu kỹ thuật, chưa phải label cuối cùng
