# Benchmark Workspace

## Mục đích

`Backend/Benchmark` là workspace nghiên cứu cho pipeline benchmark tái lập, độc lập với `Backend/Core` và `Backend/Services`.

Kiến trúc active hiện tại:

- `fuzzy_logic_basic/`
- `direct_benchmark/`
- `reporting/`

## Active Architecture

### `fuzzy_logic_basic/`

- sinh dữ liệu benchmark gốc
- giữ `flb_input_aligned.csv`
- giữ `flb_input_with_events.csv`
- sinh các export engineered Layer2 / Layer3

### `direct_benchmark/`

Đây là family train active duy nhất cho `real-only`.

Nó chứa 3 lane nhãn song song:

- `binary`
- `tri_class`
- `four_class`

và luôn dùng cùng 3 model:

- `xgboost`
- `tabnet_classifier`
- `ft_transformer_classifier`

### `reporting/`

- namespace tổng hợp report/chart từ các artifact active

## Legacy

Các tree sau không còn là active family:

- `context_classifier/`
- `pretrain_supervised/`
- `tabpfn_benchmark/`
- `ft_transformer_benchmark/` với vai trò benchmark family riêng

Code và output cũ vẫn được giữ để historical comparison.

## Label Ladder

Registry nhãn active dùng chung:

- `binary`
  - `normal`
  - `abnormal`
- `tri_class`
  - `normal`
  - `system_context`
  - `field_context`
- `four_class`
  - `normal_context`
  - `packet_loss_outage`
  - `water_deficit`
  - `rain_or_fertigation_context`

## Output Layout

Artifact active của `direct_benchmark` được chuẩn hóa theo:

- `direct_benchmark/artifacts/binary/datasets/...`
- `direct_benchmark/artifacts/binary/training/...`
- `direct_benchmark/artifacts/binary/reports/...`
- `direct_benchmark/artifacts/tri_class/...`
- `direct_benchmark/artifacts/four_class/...`

## Data Flow

1. `fuzzy_logic_basic`
   - build dữ liệu benchmark và `big_label`
2. `direct_benchmark/prepare.py`
   - build dataset `real-only` cho một lane nhãn
   - mặc định dùng `coverage_aware_temporal` để giữ coverage cho lớp hiếm ở validation/test nếu dữ liệu cho phép
3. `direct_benchmark/train.py`
   - train 3 model trên build run đó
4. `direct_benchmark/report.py`
   - sinh metric summary và chart

## Rủi ro / giới hạn

- `tri_class` và `four_class` real-only hiện rất lệch lớp
- output historical theo layout cũ vẫn còn trên đĩa và một số tooling cũ vẫn cần fallback để đọc chúng
