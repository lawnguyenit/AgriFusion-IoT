# Direct Benchmark

## Mục đích

`tabular_benchmark/` là family train active duy nhất cho flow `real-only`.

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

- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\benchmark_input_aligned.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\benchmark_input_labeled.csv`
- các export engineered hiện có trong `benchmark_dataset\dataset\`

Nếu các artifact tên chuẩn trên chưa tồn tại, flow active tự fallback sang các artifact `flb_*` tương ứng trong cùng folder dataset:

- `benchmark_input_aligned.csv` -> `flb_input_aligned.csv`
- `benchmark_input_labeled.csv` -> `flb_input_with_events.csv`
- `single_window_exp*.csv` -> `flb_l2_exp*.csv`
- `multi_window_combo*.csv` -> `flb_l3_combo*.csv`

## Output

Output được chuẩn hóa theo trục label lane:

- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\artifacts\binary\datasets\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\artifacts\binary\training\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\artifacts\binary\reports\<run_id>\`

- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\artifacts\tri_class\datasets\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\artifacts\tri_class\training\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\artifacts\tri_class\reports\<run_id>\`

- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\artifacts\four_class\datasets\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\artifacts\four_class\training\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\artifacts\four_class\reports\<run_id>\`

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
- `focus_model_metrics.csv`
- `focus_selected_models.csv`
- `report_summary.md`
- `report_manifest.json`
- `v0\model_metrics.csv`
- `v0\chart_compare_test_macro_f1.png`
- `v0\chart_compare_test_macro_f1_line.png`
- `v0\chart_compare_test_balanced_accuracy.png`
- `v0\chart_compare_test_balanced_accuracy_line.png`
- `v0\chart_compare_confusion_matrix_normalized.png`
- `v0\chart_compare_test_accuracy.png`
- `v0\chart_compare_confusion_matrix_raw.png`
- `v0\chart_xgboost_confusion_matrix_normalized.png`
- `v0\chart_xgboost_confusion_matrix_raw.png`
- `v0\chart_tabnet_classifier_confusion_matrix_normalized.png`
- `v0\chart_tabnet_classifier_confusion_matrix_raw.png`
- `v0\chart_ft_transformer_classifier_confusion_matrix_normalized.png`
- `v0\chart_ft_transformer_classifier_confusion_matrix_raw.png`
- `v1\...`
- `v2\...`

## Command

Report-facing command sequence theo tung lane nhan:

Lane `binary`:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\prepare.py --label-mode binary
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\train.py --label-mode binary
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\report.py --label-mode binary
```

Lane `tri_class`:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\prepare.py --label-mode tri_class
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\train.py --label-mode tri_class
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\report.py --label-mode tri_class
```

Lane `four_class`:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\prepare.py --label-mode four_class
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\train.py --label-mode four_class
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\report.py --label-mode four_class
```

Build lane `binary`:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\prepare.py --label-mode binary
```

Build lane `tri_class`:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\prepare.py --label-mode tri_class
```

Build lane `four_class`:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\prepare.py --label-mode four_class
```

Train từ build run mới nhất của lane:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\train.py --label-mode tri_class
```

Train 2 model cụ thể:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\train.py --label-mode four_class --model-names xgboost tabnet_classifier
```

Sinh report:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\report.py --label-mode tri_class
```

Sinh report cho 3 lane nhãn để lấy bộ chart phục vụ Chương 5:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\report.py --label-mode binary
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\report.py --label-mode tri_class
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\report.py --label-mode four_class
```

Convenience wrapper cũ:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\main.py --label-mode binary
```

## Giả định

- `tri_class` và `four_class` vẫn được phép build/train dù lệch lớp; sự lệch lớp được ghi vào artifact thay vì chặn cứng
- chỉ `auto` mới còn ý nghĩa fallback ở convenience path cũ
- `big_label` từ `benchmark_input_labeled.csv` là nguồn sự thật cho `binary`, `tri_class`, `four_class`
- split active được tối ưu theo nhãn `four_class`, vì nếu lane chi tiết nhất giữ được coverage thì `binary` và `tri_class` cũng được hưởng lợi
- report active cho mục benchmark render `v0`, `v1`, `v2` nếu các version này có trong training run
- trong cùng một `label_mode`, mỗi version dữ liệu có folder riêng; trong từng folder, các chart đều so sánh trực tiếp 3 model trên đúng version đó
- mỗi version hiện sinh song song `bar chart` và `line chart` cho `test_macro_f1` và `test_balanced_accuracy` để dễ chọn kiểu hình phù hợp khi đưa vào báo cáo
- metric chính khi diễn giải là `test_macro_f1`; metric phụ là `test_balanced_accuracy`
- khi render report cho nhánh `binary`, label hiển thị của confusion matrix được chuẩn hóa theo quy ước báo cáo: `normal_context` / `non_normal_context`
- confusion matrix dùng thang màu xanh đơn sắc và annotation đổi màu theo nền để dễ đọc khi đưa vào báo cáo hoặc trình chiếu

## Rủi ro / giới hạn

- dữ liệu `tri_class` và `four_class` real-only hiện rất lệch lớp nên metric có thể dao động mạnh
- confusion matrix trong report hiện được xuất theo từng version ở cả 2 dạng: figure gộp 3 model và PNG riêng cho từng model; bản normalized phù hợp để trình bày, bản raw count phù hợp để truy vết support
- output historical trong `outputs/` vẫn còn tồn tại để đối chiếu nhưng không còn là contract active
