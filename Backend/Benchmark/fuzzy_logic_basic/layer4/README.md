# Layer 4 - FLB Prediction Output

Layer này tổng hợp Layer 2, 3 và 3.5 thành output risk cuối cùng.

## Mục đích

- Tính risk_score.
- Phân loại risk_level.
- Đề xuất recommendation.
- Ghi reason-code columns và audit text.

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_membership.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_pressure.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_temporal_dynamics.csv`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_output_prediction.csv`

## Outputs chính

- `risk_score`
- `risk_level`
- `recommendation`
- `confidence`
- `audit_reason_text`
- reason-code columns cho water/heat/dry-air/nutrient/sensor/post-intervention

## Config liên quan

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\configs\flb_risk_levels.json`

## Debug nhanh

- Nếu `risk_level` không hợp lý, xem lại:
  - Layer 2 membership
  - Layer 3 pressure
  - Layer 3.5 accumulated / velocity / acceleration
- Nếu recommendation sai, kiểm tra rule priority trong config và code.

## Command

Chạy riêng:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer4\main.py
```
