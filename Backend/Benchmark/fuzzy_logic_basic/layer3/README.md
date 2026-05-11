# Layer 3 - Fuzzy Rule Inference

Layer này lấy membership ở Layer 2 để gom thành áp lực tức thời và confidence.

## Mục đích

- Gom membership thành pressure logic.
- Tách plant pressure ra khỏi sensor uncertainty.
- Giữ rủi ro sinh học tách riêng với độ tin cậy sensor.

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_membership.csv`

Trong input này, Layer 3 dùng:
- `gap_hours_since_prev` để ước lượng stale data
- `warmup_ready_24h` để nhận biết dữ liệu đã qua warm-up
- `EC_rising` và `EC_shift_24h` để suy ra bối cảnh hậu bón phân / EC biến động

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_pressure.csv`

## Outputs chính

- `water_pressure`
- `heat_pressure`
- `dry_air_pressure`
- `nutrient_context_pressure`
- `sensor_uncertainty`
- `instant_pressure_total`
- `plant_pressure`
- `confidence`

## Config liên quan

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\configs\flb_pressure_weights.json`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\configs\flb_membership_thresholds.json`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\configs\flb_dynamics_config.json`

## Debug nhanh

- Nếu `confidence` quá thấp, xem lại `sensor_uncertainty` trước.
- Nếu `plant_pressure` cao mà membership thấp, xem lại weight trong config.
- Nếu pressure tăng bất thường, đối chiếu với Layer 2 và Layer 1.

## Command

Chạy riêng:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer3\main.py
```
