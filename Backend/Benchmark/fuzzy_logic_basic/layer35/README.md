# Layer 3.5 - Temporal Fuzzy Dynamics

Layer này tính động học theo `timestamp` gốc và `dt_hours` thực tế.
Nếu input đã được Layer 2 cắt warm-up, Layer 3.5 sẽ nhận `warmup_ready_24h = 1` và không warm-up lại từ đầu.

## Mục đích

- Tính accumulated pressure theo pressure-hour.
- Tính velocity và acceleration bằng rolling slope.
- Giữ temporal logic riêng, không trộn với instant pressure.

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_pressure.csv`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_temporal_dynamics.csv`

## Outputs chính

- `water_accumulated_pressure`
- `heat_accumulated_pressure`
- `dry_air_accumulated_pressure`
- `nutrient_accumulated_pressure`
- `water_velocity_to_boundary_3h`
- `heat_velocity_to_boundary_3h`
- `dry_air_velocity_to_boundary_3h`
- `water_acceleration_to_boundary`
- `heat_acceleration_to_boundary`
- `dry_air_acceleration_to_boundary`
- `recovery_signal`
- `recovery_debt`

## Config liên quan

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\configs\flb_dynamics_config.json`

## Debug nhanh

- Kiểm tra `dt_hours` có hợp lý không, đặc biệt nếu mẫu không đều.
- Nếu accumulated pressure tăng quá nhanh, xem tau trong config.
- Nếu velocity/acceleration nhảy bất thường, đối chiếu với rolling window trong `shared/timeseries.py`.
- Nếu `temporal_warmup_ratio` luôn bằng 1, đó là bình thường khi input đã qua warm-up 24 giờ ở Layer 2.

## Command

Chạy riêng:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer35\main.py
```
