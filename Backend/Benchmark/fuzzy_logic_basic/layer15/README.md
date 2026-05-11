# Layer 1.5 - Event Annotation

Layer nay danh nhan event cho CSV dau ra cua Layer 1 truoc khi dua vao fuzzy membership.

## Muc dich

- Giu nguyen `flb_input_aligned.csv` va sinh mot CSV annotation rieng.
- Sua dung nghia thoi gian:
  - `timestamp` = server time de join voi pipeline cu.
  - `sample_time_local` = thoi diem sensor lay mau that, lookup tu `Layer0/Firebase_data`.
  - `upload_time_local` = thoi diem gui len server.
- Tao multi-label dataset co event 0/1, `event_labels`, `event_primary`, `event_source`, `event_confidence`, `event_reason`.

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`
- Lookup bo sung tu `D:\AgriFusion-IoT\Backend\Output_data\Layer0\Firebase_data`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`

## Event chinh

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

## Metadata de audit

- `event_source`
- `event_confidence`
- `event_reason`
- `event_primary`
- `event_labels`
- `big_label`

Luu y:
- `event_primary` chi dung de hien thi / thong ke uu tien.
- Target multi-label dung de train van la cac cot event 0/1.

## Cot thoi gian va debug

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

## Command

Chay rieng:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer15\main.py
```

Trong pipeline:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\prepare_layer2_fuzzy.py
```

## Gia dinh xu ly

- `pH <= 3.05` duoc xem la `event_system_reset`.
- `event_post_reset_warmup` duoc gan khi pH con thap trong 6h sau reset.
- Telemetry gap duoc danh nhan theo sample gap > 60 phut.
- Ban ghi sat nhau bat thuong duoc danh nhan `event_debug_sensor_pull_candidate`, khong xem la confirmed.
- `event_fertilizer_context_candidate`, `event_morning_irrigation_candidate`, `event_rain_weather_candidate` deu la rule-inferred candidate.

## Rui ro va gioi han

- Rule hien tai la heuristic theo data debug va mo ta nghiep vu hien co.
- `event_source`, `event_confidence`, `event_reason` hien la row-level audit metadata; chua tach rieng theo tung event thanh bang doc lap.
- Neu sau nay co human log xac nhan tuoi / bon phan / mua, nen bo sung cot confirmed rieng thay vi day candidate len 1.
