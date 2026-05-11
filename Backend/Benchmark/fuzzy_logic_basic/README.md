# Fuzzy Logic Basic

Đây là pipeline benchmark cho fuzzy logic của AgriFusion-IoT. Thư mục này chỉ dùng để tái cấu trúc và sinh dữ liệu cho Layer 1 → Layer 5, không phải nguồn dữ liệu gốc.

## Tổng quan

- `prepare_layer2_fuzzy.py`
  Entry point chạy toàn bộ chuỗi:
  `layer1 -> layer15 -> layer2 -> layer3 -> layer35 -> layer4 -> layer5`

- `layer1/`
  FLB input alignment. Lấy dữ liệu từ `Backend/Output_data/Layer1` và xuất CSV input sạch cho fuzzy.

- `layer15/`
  Event annotation. Đánh nhãn reset, debug pull sensor, anomaly sau replug, candidate tưới buổi sáng, candidate mưa/thời tiết cho CSV Layer 1.

- `layer2/`
  Fuzzy membership. Biến tín hiệu sensor/context thành membership trong `[0, 1]`.

- `layer3/`
  Fuzzy rule inference. Gom membership thành áp lực tức thời và confidence.

- `layer35/`
  Temporal fuzzy dynamics. Tính accumulated pressure, velocity, acceleration, recovery theo `timestamp` gốc.

- `layer4/`
  FLB prediction output. Tổng hợp risk score, risk level, recommendation và reason codes.

- `layer5/`
  Risk pathway interpretation. Giải thích hệ thống đang drift về pathway nào.

- `shared/`
  Helper dùng chung cho config, fuzzy math, alignment theo timestamp và rolling slope.

- `configs/`
  Config JSON cho threshold, weight, dynamics, risk level và pathway mapping.

- `dataset/`
  Output CSV được sinh từ pipeline. Đây là artifact, không phải input gốc.

## Input mặc định

- `D:\AgriFusion-IoT\Backend\Output_data\Layer1`

## Output mặc định

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_membership.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_pressure.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_temporal_dynamics.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_output_prediction.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_pathway_interpretation.csv`

## Schema Layer 1

`flb_input_aligned.csv` chỉ giữ input để phục vụ fuzzy:

- `timestamp`
- `soil_temp`
- `soil_humidity`
- `air_temp`
- `air_humidity`
- `EC`
- `pH`
- `N`
- `P`
- `K`
- `ec_npk_consistency_score`
- `ec_npk_consistency_flag`

Quy ước:
- `ec_npk_consistency_flag = 1` nếu `ec_npk_consistency_score >= 0.9`
- `ec_npk_consistency_flag = 0` nếu thấp hơn ngưỡng trên

Không đưa `ec_npk_reason` hoặc `optional_quality_flags` vào CSV Layer 1 này.

## Schema Layer 1.5

`flb_input_with_events.csv` giữ toàn bộ cột của Layer 1 và thêm event/context để debug:

- `sample_time_local`
- `upload_time_local`
- `sample_time_reconstructed`
- `gap_minutes_since_prev`
- `gap_minutes_to_next`
- `upload_gap_minutes_since_prev`
- `upload_gap_minutes_to_next`
- `soil_humidity_delta`
- `air_humidity_delta`
- `EC_delta`
- `pH_delta`
- `N_delta`
- `P_delta`
- `K_delta`
- `event_system_reset`
- `event_telemetry_gap_since_prev`
- `event_telemetry_gap_to_next`
- `event_post_reset_warmup`
- `event_sensor_missing_row`
- `event_npk_sensor_fault`
- `event_sht30_sensor_fault`
- `event_debug_sensor_pull_candidate`
- `event_ec_npk_replug_low_candidate`
- `event_post_replug_recovery_candidate`
- `event_morning_irrigation_candidate`
- `event_rain_weather_candidate`
- `event_fertilizer_context_candidate`
- `event_ec_npk_anomaly`
- `event_heat_episode`
- `event_dry_soil_episode`
- `event_source`
- `event_confidence`
- `event_reason`
- `event_primary`
- `event_labels`
- `big_label`

Lưu ý:
- `event_primary` chỉ là nhãn hiển thị / ưu tiên thống kê.
- Target multi-label nên dùng các cột event 0/1.

## Cách chạy

Mặc định:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\prepare_layer2_fuzzy.py
```

Dry run:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\prepare_layer2_fuzzy.py --limit 50
```

## Debug nhanh

- Nếu layer nào lỗi import khi chạy trực tiếp, kiểm tra bootstrap `sys.path` trong `layer*/main.py`.
- Nếu số dòng CSV khác nhau giữa các layer, kiểm tra output trung gian trong `dataset/` theo thứ tự layer.
- Nếu risk/pathway không hợp lý, xem lại config trong `configs/` trước khi sửa code.

## Giả định xử lý

- Master timeline cho Layer 2-5 là `timestamp` đã align trong `flb_input_aligned.csv`.
- Không ép resample về `1h`; dữ liệu đi theo `timestamp` gốc và `dt_hours` thực tế.
- `pH` là context risk chậm, không dùng để tính đạo hàm nhanh.
- `EC`, `N`, `P`, `K` là proxy electrochemical / nutrient context, không phải lab truth.
- `sensor_uncertainty` và `plant_pressure` được tách riêng.

## Giới hạn hiện tại

- Threshold và weight vẫn là prototype heuristic, chưa calibrate bằng field event log đầy đủ.
- Heuristic cho `recent_irrigation_signal` và `recent_fertilization_signal` chỉ là tạm thời.
- `layer5` chỉ giải thích risk pathway, không khẳng định bệnh lý.

## Preview export JSON nhanh

Khi cần đổi một file export RTDB tải về thành CSV có cấu trúc giống `flb_input_aligned.csv`, chạy:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\preview_download_export_to_flb_csv.py --input "C:\Users\lawng\Downloads\agri-fusion-iot-default-rtdb-telemetry-export (12).json"
```

Script sinh 2 file:

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\download_export_preview.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\download_export_preview_readable.csv`

File đầu giữ schema giống `flb_input_aligned.csv`. File thứ hai thêm `sample_time_local` để nhìn trực quan hơn khi debug.
