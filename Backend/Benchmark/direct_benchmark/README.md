# Direct Benchmark

## Mục đích

`direct_benchmark/` là family train active duy nhất cho flow `real-only`.

Family này chạy cùng 3 model:

- `xgboost`
- `tabnet_classifier`
- `ft_transformer_classifier`

trên 3 lane nhãn song song:

- `binary`
- `tri_class`
- `four_class`

## Flow

Flow chuẩn hiện tại:

1. `prepare.py`
   - build dataset `real-only` cho một lane nhãn cố định
2. `train.py`
   - train 3-model suite từ build run đã chuẩn bị
3. `report.py`
   - sinh bảng metric và chart tổng hợp từ training run

`main.py` vẫn tồn tại như convenience wrapper `build + train` trong một lệnh, nhưng flow active khuyến nghị là tách riêng 3 bước trên.

Mặc định flow active dùng `coverage_aware_temporal`:

- vẫn tôn trọng trục thời gian
- vẫn giữ purge gap nếu feature schema có lookback
- nhưng tự điều chỉnh ranh giới train/validation/test để các lớp hiếm của `four_class` có cơ hội xuất hiện ở validation và test

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`
- các export engineered hiện có trong `fuzzy_logic_basic\dataset\`

## Output

Output được chuẩn hóa theo trục label lane:

- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\artifacts\binary\datasets\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\artifacts\binary\training\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\artifacts\binary\reports\<run_id>\`

- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\artifacts\tri_class\datasets\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\artifacts\tri_class\training\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\artifacts\tri_class\reports\<run_id>\`

- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\artifacts\four_class\datasets\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\artifacts\four_class\training\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\artifacts\four_class\reports\<run_id>\`

Build artifacts chính:

- `dataset_manifest.json`
- `prepared_dataset.csv`
- `feature_schema.json`
- `label_policy.json`
- `split_label_summary.json`

Training artifacts chính:

- `aggregate_model_metrics.csv`
- `training_report.json`
- `run_config.json`
- `run_status.json`
- `best_result.txt`
- `experiments/<experiment>/models/*.joblib|*.pt`

Report artifacts chính:

- `combined_model_metrics.csv`
- `summary_model_metrics.csv`
- `report_summary.md`
- `chart_test_macro_f1.png`
- `chart_test_accuracy.png`

## Command

Build lane `binary`:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\prepare.py --label-mode binary
```

Build lane `tri_class`:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\prepare.py --label-mode tri_class
```

Build lane `four_class`:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\prepare.py --label-mode four_class
```

Train từ build run mới nhất của lane:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\train.py --label-mode tri_class
```

Train 2 model cụ thể:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\train.py --label-mode four_class --model-names xgboost tabnet_classifier
```

Sinh report:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\report.py --label-mode tri_class
```

Convenience wrapper cũ:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\main.py --label-mode binary
```

## Giả định

- `tri_class` và `four_class` vẫn được phép build/train dù lệch lớp; sự lệch lớp được ghi vào artifact thay vì chặn cứng
- chỉ `auto` mới còn ý nghĩa fallback ở convenience path cũ
- `big_label` từ `flb_input_with_events.csv` là nguồn sự thật cho `binary`, `tri_class`, `four_class`
- split active được tối ưu theo nhãn `four_class`, vì nếu lane chi tiết nhất giữ được coverage thì `binary` và `tri_class` cũng được hưởng lợi

## Rủi ro / giới hạn

- dữ liệu `tri_class` và `four_class` real-only hiện rất lệch lớp nên metric có thể dao động mạnh
- output historical trong `outputs/` vẫn còn tồn tại để đối chiếu nhưng không còn là contract active
