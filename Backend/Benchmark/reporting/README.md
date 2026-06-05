# Reporting

## Mục đích

`Backend/Benchmark/reporting` là namespace active cho phần tổng hợp artifact, biểu đồ và báo cáo benchmark.

Kiến trúc active hiện tại lấy `direct_benchmark` làm family train real-only duy nhất, nên report active cũng bám theo 3 lane nhãn:

- `binary`
- `tri_class`
- `four_class`

## Input

- training artifact đã hoàn tất từ `direct_benchmark`
- `training_report.json`
- `aggregate_model_metrics.csv`
- build manifest liên quan nếu cần truy vết dataset nguồn

## Output

Report active được chuẩn hóa theo:

- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\artifacts\binary\reports\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\artifacts\tri_class\reports\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\artifacts\four_class\reports\<run_id>\`

Artifact chính:

- `combined_model_metrics.csv`
- `summary_model_metrics.csv`
- `report_summary.md`
- `chart_test_macro_f1.png`
- `chart_test_accuracy.png`
- `report_manifest.json`

## Command

Sinh report cho một training run theo lane:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\report.py --label-mode tri_class
```

Hoặc chỉ định thẳng training run:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\report.py --label-mode four_class --run-dir <training_run_dir>
```

## Giả định

- chỉ artifact active từ `direct_benchmark` mới tiếp tục được ghi report mới
- `context_classifier` và các tree cũ chỉ còn vai trò historical
- mỗi lane nhãn có report root riêng để dễ so sánh `binary`, `tri_class`, `four_class`

## Rủi ro / giới hạn hiện tại

- `generate_direct_profile_report.py` vẫn còn nằm trong `direct_benchmark/` vì nó là profile report chuyên biệt cho evidence pack, chưa được gom hẳn về namespace này
- historical runs theo layout cũ vẫn cần fallback nếu có consumer đọc đối chiếu
- dữ liệu `tri_class` và `four_class` real-only đang lệch lớp mạnh, nên report cần được đọc cùng với phân bố lớp trong build/training artifact
